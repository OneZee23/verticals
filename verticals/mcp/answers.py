"""The record of what each agent answer wrote (docs/design/agent-answer-undo.md), kept in this process's memory.

The desktop app's chat gateway tells this server which answer is open for each chat conversation (`open`, `close`), and every
call the agent makes carries its conversation in a header (`X-Verticals-Session`). A call that comes in while its conversation
has an answer open is that answer's: when it is a write, `tools.call_tool` brackets it with `core/answers.py`, and what the
write changed, each goal as it was and as it was left, is added to the answer here. Nothing is guessed from a diff of the
board: the record is what the writes did.

When an answer ends the page asks for it (`claim`) and turns it into one ⌘Z step. An answer is handed over once; the page's
history lives as long as the page, as the person's own steps do. Memory only, from when this process started: no table, and
the record goes with the process, which is as long as the app's history is meant to reach.

Calls with no session, or from a conversation with no answer open, are nobody's: an agent used from Claude Code or Codex
outside the app is not in this history. No SQL here (`tests/static/test_seam.py`): `core/answers.py` reads the goals, and this
module only keeps what it says and answers the three routes the gateway and the page use.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from verticals.core.answers import Change
from verticals.mcp.shapes import goal_dict

#: The header every call of a conversation carries; the gateway writes it into the agent's MCP connection.
SESSION_HEADER = "x-verticals-session"

#: Writes the record follows, and what each one can touch: the goals it names, and with `True` everything under them (a move
#: carries the subgoals that stand in its card, a delete takes them all).
WATCHED: dict[str, tuple[str, bool]] = {
    "update": ("id", False), "schedule": ("id", True), "reparent": ("id", False), "park": ("id", False),
    "delete": ("id", True), "due_ack": ("id", False), "size_report": ("goal_id", False), "create": ("", False),
}

#: How many answers are kept (the oldest handed-over ones go first), and how many writes one answer may record.
MAX_ANSWERS = 200
MAX_WRITES = 5000
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def watched(name: str, arguments: dict[str, Any]) -> tuple[list[str], bool] | None:
    """The goals a write named and whether its subtree is in play; `None` for a tool the record does not follow."""
    if name not in WATCHED:
        return None
    key, subtree = WATCHED[name]
    if name == "update" and arguments.get("ids") is not None:
        ids = [i for i in arguments["ids"] if isinstance(i, str)]
    else:
        value = arguments.get(key) if key else None
        ids = [value] if isinstance(value, str) else []
    return ids, subtree


def write_of(name: str, arguments: dict[str, Any], changes: Sequence[Change]) -> dict[str, Any]:
    """One write as the record keeps it: the tool, and each goal it changed as a card before and after. `root` names the goal a
    delete took away, whose subtree is in `changes`."""
    return {
        "tool": name,
        "root": arguments.get("id") if name == "delete" and isinstance(arguments.get("id"), str) else None,
        "changes": [
            {"id": c.id, "before": goal_dict(c.before) if c.before else None, "after": goal_dict(c.after) if c.after else None}
            for c in changes
        ],
    }


class AnswerStore:
    """The open answers by conversation, and every answer's writes. One lock: calls come from worker threads and the three routes
    from the event loop."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._answers: dict[str, dict[str, Any]] = {}
        self._open: dict[str, str] = {}

    def open(self, session: str, answer: str) -> None:
        """An answer begins for a conversation. One that was still open for it (a close that never came) ends first."""
        with self._lock:
            previous = self._open.get(session)
            if previous and previous != answer:
                self._end(previous)
            self._open[session] = answer
            self._answers[answer] = {
                "id": answer, "session": session, "started_at": self._clock(), "ended_at": None,
                "claimed": False, "writes": [], "truncated": False,
            }
            self._trim()

    def close(self, answer: str) -> None:
        with self._lock:
            self._end(answer)

    def current(self, session: str | None) -> str | None:
        """The answer open for the conversation, if any."""
        with self._lock:
            return self._open.get(session) if session else None

    def record(self, answer: str, write: dict[str, Any]) -> None:
        """A write of the answer, with the time it landed. A write that arrives after the answer ended (an agent that was stopped
        mid-call) is nobody's: it is not added to an answer the page may already hold."""
        with self._lock:
            found = self._answers.get(answer)
            if found is None or found["ended_at"] is not None:
                return
            if len(found["writes"]) >= MAX_WRITES:
                found["truncated"] = True
                return
            found["writes"].append({**write, "seq": len(found["writes"]) + 1, "at": self._clock()})

    def claim(self) -> list[dict[str, Any]]:
        """The answers that have ended and wrote something, oldest first, each handed over once."""
        with self._lock:
            ready = [a for a in self._answers.values() if a["ended_at"] is not None and a["writes"] and not a["claimed"]]
            ready.sort(key=lambda a: a["ended_at"])
            for answer in ready:
                answer["claimed"] = True
            return [{k: v for k, v in a.items() if k != "claimed"} for a in ready]

    def snapshot(self, answer: str) -> dict[str, Any] | None:
        """One answer as it stands, ended or not and handed over or not: for tests and for whoever debugs a step."""
        with self._lock:
            found = self._answers.get(answer)
            return json.loads(json.dumps(found)) if found else None

    def _end(self, answer: str) -> None:
        found = self._answers.get(answer)
        if found is None or found["ended_at"] is not None:
            return
        found["ended_at"] = self._clock()
        if self._open.get(found["session"]) == answer:
            del self._open[found["session"]]
        if not found["writes"]:
            del self._answers[answer]  # an answer that wrote nothing is not worth keeping

    def _trim(self) -> None:
        extra = len(self._answers) - MAX_ANSWERS
        if extra <= 0:
            return
        for answer in sorted(
            (a for a in self._answers.values() if a["ended_at"] is not None),
            key=lambda a: (not a["claimed"], a["ended_at"]),
        )[:extra]:
            del self._answers[answer["id"]]


# --- the three routes the gateway and the page use ----------------------------------------------------------------------


def _valid(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.match(value))


class AnswerRoutes:
    """Pure ASGI, in front of the MCP app and behind the bearer check: `POST /answers/open` (`{session, answer}`),
    `POST /answers/close` (`{answer}`) and `POST /answers/claim`. Anything else goes on to the MCP app untouched."""

    def __init__(self, app: Callable, store: AnswerStore) -> None:
        self.app = app
        self.store = store

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/answers/"):
            await self.app(scope, receive, send)
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body") or len(body) > 65536:
                break
        status, payload = self._handle(scope["method"], scope["path"], body)
        data = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
        ]})
        await send({"type": "http.response.body", "body": data})

    def _handle(self, method: str, path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
        if method != "POST":
            return 405, {"error": "method not allowed"}
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return 400, {"error": "bad json"}
        body = body if isinstance(body, dict) else {}
        route = path.removeprefix("/answers/")
        if route == "open" and _valid(body.get("session")) and _valid(body.get("answer")):
            self.store.open(body["session"], body["answer"])
            return 200, {"ok": True}
        if route == "close" and _valid(body.get("answer")):
            self.store.close(body["answer"])
            return 200, {"ok": True}
        if route == "claim":
            return 200, {"answers": self.store.claim()}
        return 404, {"error": "not found"}
