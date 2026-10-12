"""The morning report's turns (docs/design/morning-quality.md): the agent writes the report, a second agent checks it against the
raw sources, a check that fails sends it back for one fixing turn, and the owner is told it is ready only after that.

It sits inside the gateway's own turn machinery (`chat.py`): the writing turn is the turn the app asked for, and every turn after
it is started the way a message starts one, so each is a turn of its own on the stream (`turn_start`, then `done` with `next`
saying that the report is not ready yet). Everything the agent writes on the board, in the writing turn and in the fixing turn,
is one answer, which the answer's own Undo takes back at once (docs/design/morning-quality.md, docs/design/agent-answer-undo.md):
every turn of the flow names it, and it ends with the final `done`. The check writes nothing, and its calls carry no
conversation. The owner sees one reply: the words of the last turn that spoke, held back until the check is done, and one final
`done`.

The second agent is a fresh agent of the same kind at a lower effort. It only reads: the morning turn's tools, nothing it asks is
put to the owner, and the verdict goes to the server in its own words (`POST /api/morning/check`), which writes it into the report
and says which checks failed. A second agent that cannot be reached or gives no verdict never holds the report for good: the
report is released with "Not checked" and the reason in the place of a verdict. No word of the report, the sources or the verdict
goes into the gateway's log.
"""
from __future__ import annotations

import json
import re
import threading
import time

# The longest the second agent is waited for, in one turn. A tuning knob of the tests, not of the owner.
CHECK_LIMIT = 45 * 60
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PATH = re.compile(r"reports/morning/(\d{4}-\d{2}-\d{2})\.md")
# One step lower for the second agent: it reads and compares, the writing agent thinks.
LOWER = {"ultracode": "high", "ultra": "high", "max": "high", "xhigh": "high", "high": "medium", "medium": "low", "low": "low"}


def lower_effort(effort):
    return LOWER.get(effort or "", "medium")


def report_day(context, text):
    """The day the report is for: the app says it in the ask's context, else the ask's own words name the document."""
    morning = context.get("morning") if isinstance(context, dict) else None
    day = morning.get("day") if isinstance(morning, dict) else None
    if isinstance(day, str) and _DAY.match(day):
        return day
    found = _PATH.search(text or "")
    return found.group(1) if found else None


def parse_verdict(text):
    """The checks the second agent answered: the `checks` object of the last fenced json block in its words (or of the last
    object in them), else None. Only the shape is read here; the server reads the answers."""
    text = text or ""
    blobs = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not blobs and "{" in text and "}" in text:
        blobs = [text[text.index("{"):text.rindex("}") + 1]]
    for blob in reversed(blobs):
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("checks"), dict):
            return data["checks"]
    return None


def check_ask(path):
    return (f"Check the morning report {path}. Read it with doc_get, read the raw sources through the tools their documents name, "
            "and answer the ten checks as your instructions say. Answer with the verdict in one fenced json block and nothing else.")


def recheck_ask(path):
    return (f"The report {path} was fixed. Read it again and check all ten again, against the raw sources, as before. "
            "Answer with the verdict in one fenced json block and nothing else.")


def fix_ask(path, failed):
    """What the writing agent is told when a check fails: which checks, in the report's own words, and what was found."""
    lines = "\n".join(f"- {label}: {note}" if note else f"- {label}" for label, note in failed)
    return (f"A second agent checked this morning report against the raw sources, and these checks failed:\n{lines}\n\n"
            f"Fix the report ({path}): read it with doc_get, change only what these need, and save it with doc_save. Leave every "
            "part that passed as it is, and leave the owner's comments exactly as they are. Then answer as before: two short "
            "lines, with the report linked.")


class Quiet:
    """What the second agent is handed in place of the conversation: its words and its tool calls are the flow's business, not the
    owner's, so nothing it emits reaches the stream, and it only reads, so nothing it asks is ever put to the owner."""

    def __init__(self, flow, settings):
        self.flow, self.settings, self.text = flow, settings, ""

    def emit(self, event):
        kind = event.get("t")
        if kind == "text_start" and self.text:
            self.text += "\n\n"
        elif kind == "text":
            self.text += str(event.get("text", ""))
        elif kind == "tool":
            self.flow.chat.log.info("check tool name=%s session=%s", event.get("name"), str(self.flow.s.id)[:8])

    def ask(self, agent, key, title, body, options, tool=None, tool_input=None):
        agent.decide(key, next((value for _, value in options if value == "decline"), options[-1][1]))

    def resolve(self, key, label):
        pass

    def turn_done(self, error, detail):
        self.flow.checked(error, detail)

    def agent_exited(self, agent, code, detail):
        # What the CLI said on its way out is for the gateway's log, not for the report.
        self.flow.chat.log.warning("check exit code=%s detail=%s session=%s", code, " ".join(str(detail or "").split())[:300],
                                   str(self.flow.s.id)[:8])
        self.flow.checked(True, f"it exited with code {code}")


class MorningFlow:
    """The turns of one morning report, from the writing turn to the one answer the owner sees."""

    def __init__(self, chat, session, settings, context, day):
        self.chat, self.s, self.settings, self.context, self.day = chat, session, settings, context, day
        self.path = f"reports/morning/{day}.md"
        self.stage = "write"
        self.checker, self.seat = None, None
        self.first = None          # the outcomes of the first check, as the server answered them
        self.finished = False
        self.stopped = False
        self.failure = ""          # why the second agent's last turn failed, when it did
        self.turn_over = threading.Event()
        self.lock = threading.Lock()

    @classmethod
    def begin(cls, chat, session, settings, context, text):
        """The flow for a morning ask, or None when there is no way to run it: no server to hand the verdict to, or no day."""
        day = report_day(context, text)
        if day is None or not getattr(chat, "api_url", None):
            return None
        return cls(chat, session, settings, context, day)

    # -- what the session asks of the flow ---------------------------------------------------------------------

    def took(self, error, detail):
        """A turn of the session's own agent (the writing turn, the fixing turn) has ended. True when the flow goes on from here, in
        a thread of its own: this is called on the agent's reader thread, which must go back to reading."""
        if self.finished:
            return False
        threading.Thread(target=self._after, args=(error, detail), daemon=True).start()
        return True

    def stop(self):
        self.stopped = True
        self._interrupt_checker()

    def _interrupt_checker(self):
        checker = self.checker
        if checker is not None:
            try:
                checker.interrupt()
            except Exception:  # noqa: BLE001 — a stop must never raise
                pass

    def abandon(self):
        """The session's agent is gone (or the app is closing): nothing is waited for any more."""
        with self.lock:
            self.finished = True
        self.turn_over.set()
        self._close_checker()
        self.s.flow, self.s.holding = None, None

    def _close_checker(self):
        checker, self.checker = self.checker, None
        if checker is not None:
            try:
                checker.close()
            except Exception:  # noqa: BLE001
                pass

    # -- the turns -------------------------------------------------------------------------------------------

    def _log(self, what):
        self.chat.log.info("morning %s session=%s", what, str(self.s.id)[:8])

    def _step(self, label):
        self.s.emit({"t": "step", "label": label})

    def _end_turn(self, then):
        """The turn that just ended is an answer of its own on the stream, and the report is not ready: `next` says what comes."""
        self.s.emit({"t": "done", "error": False, "detail": "", "next": then,
                     "ms": int((time.time() - (self.s.started_at or time.time())) * 1000), "at": time.time()})

    def _after(self, error, detail):
        """The session's own agent ended a turn: the writing turn, or the fixing turn."""
        if error or self.stopped:
            self._mark("unchecked", "It stopped before it was finished." if self.stopped else "It was not finished.")
            return self.finish(True, detail or ("Stopped" if self.stopped else ""))
        self._log("written" if self.stage == "write" else "fixed")
        first = self.first is None
        # No report, nothing to check: an agent that answered without writing one (or a server that is not there) has its
        # answer told at once, as before.
        if first and not self._mark("pending"):
            return self.finish(False, "")
        self._check(first)

    def _mark(self, state, reason=""):
        """Put the report's check line at `state`. False when the server would not: there is no such report, or no server."""
        try:
            self.chat.api("POST", "/api/morning/check", {"path": self.path, "state": state, "reason": reason})
            return True
        except Exception as e:  # noqa: BLE001 — the log says what the server answered
            self.chat.log.warning("morning mark %s failed %s session=%s", state, str(e)[:200], str(self.s.id)[:8])
            return False

    def _check(self, first):
        """Run the second agent over the report and act on its verdict."""
        self._end_turn("check")
        self.stage = "check"
        self._step("Checking the report" if first else "Checking it again")
        try:
            text = self._ask_checker(check_ask(self.path) if first else recheck_ask(self.path))
            checks = parse_verdict(text) if text is not None and not self.stopped else None
            if checks is None and text is not None and not self.stopped and not self.failure:
                # Once more, in the same conversation: it read the report already, so asking again costs little.
                self._log("no verdict, asking again")
                text = self._ask_checker("Your last answer had no verdict I could read. Answer with the verdict in one fenced json "
                                         "block and nothing else.")
                checks = parse_verdict(text) if text is not None and not self.stopped else None
        except Exception as e:  # noqa: BLE001 — a second agent that will not start is a report that is not checked
            self.chat.log.warning("morning checker failed %s session=%s", str(e)[:200], str(self.s.id)[:8])
            return self._unchecked("The second agent could not start.")
        if self.finished:
            return
        if self.stopped:
            return self._unchecked("It stopped before the check was finished.", error=True)
        if checks is None:
            why = (f"The second agent stopped: {self.failure}." if self.failure
                   else "The second agent did not answer in time." if text is None else "The second agent gave no verdict.")
            return self._unchecked(why)
        try:
            body = {"path": self.path, "checks": checks, **({} if first else {"first": self.first})}
            result = self.chat.api("POST", "/api/morning/check", body, timeout=60)
        except Exception as e:  # noqa: BLE001
            self.chat.log.warning("morning verdict not written %s session=%s", str(e)[:200], str(self.s.id)[:8])
            return self._unchecked("The verdict could not be written into the report.")
        if first:
            self.first = result.get("checks") or {}
        failed = result.get("failed") or []
        self._log(f"checked first={first} failed={','.join(failed) or '-'} gaps={len(result.get('gaps') or [])}")
        if failed and first:
            return self._fix(result)
        self.finish(False, "")

    def _ask_checker(self, text):
        """One turn of the second agent: its last words, or None when it did not answer in time."""
        if self.checker is None:
            settings = {**self.settings, "role": "checker", "effort": lower_effort(self.settings.get("effort"))}
            self.seat = Quiet(self, settings)
            self.checker = self.chat.make_agent(self.seat, settings)
        self.seat.text, self.failure = "", ""
        self.turn_over.clear()
        self.s.emit({"t": "turn_start", "provider": self.settings["provider"], "model": self.settings.get("model"),
                     "effort": self.seat.settings.get("effort"), "stage": "check", "answer": self.s.answer})
        self.checker.send(f"<app_context>\n{self.chat.describe(self.context)}\n</app_context>\n\n{text}")
        answered = self.turn_over.wait(CHECK_LIMIT)
        if self.finished:
            return None
        self._end_turn("verdict")
        if not answered:
            self._interrupt_checker()
            return None
        return self.seat.text

    def checked(self, error, detail):
        """The second agent's turn has ended (it answered, failed, or its process stopped)."""
        if self.finished:
            return
        self.failure = " ".join(str(detail or "").split())[:200] if error else ""
        self.turn_over.set()

    def _fix(self, result):
        failed = [(item.get("label") or key, item.get("note") or "")
                  for key, item in (result.get("checks") or {}).items() if item.get("result") == "fail"]
        self.stage = "fix"
        self._mark("pending")  # while it is fixed and checked again, the report says it is not checked
        self._step("Fixing the report")
        self.s.holding = []  # the first words are about a report that is being changed: only the fixed one is told
        self.chat.start_turn(self.s, fix_ask(self.path, failed), self.context, self.settings, stage="fix")
        if not self.s.running and not self.finished:
            self.abandon()  # the fixing turn could not start: the session has already told the owner

    def _unchecked(self, reason, error=False):
        self._mark("unchecked", reason)
        self.finish(error, "Stopped" if error else "")

    def finish(self, error, detail):
        """The report is ready (or the turn failed): the held words are told, the second agent goes, and the answer ends."""
        with self.lock:
            if self.finished:
                return
            self.finished = True
        held, self.s.holding = self.s.holding or [], None
        self._close_checker()
        for event in held:
            self.s.emit(event)
        self.s.flow = None
        self._log(f"ready error={bool(error)}")
        self.s.finish(error, detail)
