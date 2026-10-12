"""Whether a report is a bug or a request (docs/design/bug-reports.md, desktop/chat/report_kind.py): the agent tells from the
person's words, so the person picks nothing. It is asked once, in a quiet conversation with no tools and no MCP servers, and
gets the words and nothing else; anything but a clear answer is a request. A stand-in `claude` made under a scratch folder
answers (no model runs, no network); it records what it was started with and what it was sent. Sample words only."""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import stat
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHAT_DIR = ROOT / "desktop" / "chat"

# A `claude` that speaks the CLI's stream-json and does what a file called `mode` in its folder says: answer with the words
# in `reply`, ask permission for a Verticals tool first, hang, exit, or end its turn with an error. It writes its arguments to
# `argv.json`, every message it is sent to `messages.log`, the reply to a permission it asked to `permission.json`, and
# `closed` when its input ends, which is how a test knows the gateway let it go.
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys

def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def text(name, default=""):
    return open(name).read() if os.path.exists(name) else default

json.dump(sys.argv[1:], open("argv.json", "w"))
mode, reply = text("mode", "answer").strip(), text("reply", "bug")
if mode == "exit":
    sys.stderr.write("claude: refused to start\n")
    sys.exit(3)
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("type") == "control_request" and msg["request"]["subtype"] == "initialize":
        out({"type": "control_response", "response": {"subtype": "success", "request_id": msg["request_id"],
                                                         "response": {"models": []}}})
    elif msg.get("type") == "user":
        sent = "".join(b.get("text", "") for b in msg["message"]["content"])
        open("messages.log", "a").write(json.dumps(sent) + "\n")
        if mode == "hang":
            continue
        out({"type": "system", "subtype": "init", "model": "fake-model"})
        if mode == "tool":
            out({"type": "control_request", "request_id": "ask-1", "request": {
                "subtype": "can_use_tool", "tool_name": "mcp__verticals__update", "input": {"id": "x"}}})
            for answer in sys.stdin:
                answered = json.loads(answer)
                if answered.get("type") == "control_response":
                    open("permission.json", "w").write(json.dumps(answered["response"]["response"]))
                    break
        if mode == "error":
            out({"type": "result", "is_error": True, "result": "The stand-in failed on purpose."})
            continue
        out({"type": "stream_event", "event": {"type": "content_block_start", "content_block": {"type": "text"}}})
        out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": reply}}})
        out({"type": "result", "is_error": False, "result": ""})
open("closed", "w").write("yes")
'''


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


class _Host:
    """What report_kind needs of the chat: where the agent runs, where the state is, and a log."""

    def __init__(self, root: Path) -> None:
        self.workdir = root / "workspace"
        self.state_dir = root / "state"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger(f"report-kind-{id(self)}")
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        self.lines = _Lines()
        self.log.addHandler(self.lines)

    def said(self, mode: str, reply: str = "bug") -> None:
        (self.workdir / "mode").write_text(mode)
        (self.workdir / "reply").write_text(reply)

    def recorded(self, name: str) -> str:
        path = self.workdir / name
        return path.read_text() if path.exists() else ""


@pytest.fixture
def kind(scratch_dir: Path) -> Iterator[tuple[object, _Host]]:
    """report_kind, imported as the launcher imports it (desktop/chat on the path), with a stand-in `claude` first on PATH."""
    bin_dir = scratch_dir / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    path_before = os.environ.get("PATH", "")
    sys.path.insert(0, str(CHAT_DIR))
    os.environ["PATH"] = f"{bin_dir}:{path_before}"
    try:
        yield importlib.import_module("report_kind"), _Host(scratch_dir)
    finally:
        os.environ["PATH"] = path_before
        sys.path.remove(str(CHAT_DIR))
        for name in ("report_kind", "chat"):
            sys.modules.pop(name, None)


def test_the_agent_tells_a_bug_from_a_request_by_its_first_word(kind) -> None:
    module, host = kind
    for reply, wanted in (("bug", "bug"), ("Bug.", "bug"), (" REQUEST\n", "request"), ("request", "request"), ("**bug**", "bug")):
        host.said("answer", reply)
        assert module.ask(host, "The card jumped back", {}) == wanted, reply


def test_when_it_cannot_tell_the_answer_is_a_request(kind) -> None:
    module, host = kind
    for reply in ("It is hard to say from this.", "", "bugs", "It is a bug", "42"):
        host.said("answer", reply)
        assert module.ask(host, "Something about Fridays", {}) == "request", reply
    assert all(line.startswith("report_kind result=request why=unclear ms=") for line in host.lines.lines), host.lines.lines


def test_it_is_started_with_no_tools_no_servers_and_a_prompt_of_its_own(kind) -> None:
    module, host = kind
    host.said("answer", "bug")
    module.ask(host, "The card jumped back", {"provider": "claude", "model": "some-model", "effort": "xhigh", "permission": "bypassPermissions"})
    argv = json.loads(host.recorded("argv.json"))
    pairs = dict(zip(argv, argv[1:]))
    # No built-in tool, and only the empty server list: it has nothing to reach the board or the Mac with.
    assert pairs["--tools"] == "" and "--strict-mcp-config" in argv
    assert json.loads(Path(pairs["--mcp-config"]).read_text()) == {"mcpServers": {}}
    assert Path(pairs["--mcp-config"]) == host.state_dir / "chat-mcp-none.json"
    assert pairs["--permission-mode"] == "manual"
    # The person's model, the lowest effort whatever they chose for the chat, its own prompt and not the chat's.
    assert pairs["--model"] == "some-model" and pairs["--effort"] == "low"
    prompt = pairs["--append-system-prompt"]
    assert prompt == module.PROMPT and "bug or request" in prompt and "You have no tools" in prompt
    assert "--add-dir" not in argv and "Verticals" not in prompt and "board" not in prompt


def test_it_gets_the_words_and_nothing_else(kind) -> None:
    module, host = kind
    host.said("answer", "bug")
    words = "  I dragged the card to Friday and it jumped back  "
    module.ask(host, words, {})
    sent = [json.loads(line) for line in host.recorded("messages.log").splitlines()]
    assert sent == [f"{module.ASK}{words.strip()}\n\nIs it a bug or a request?"]
    # Words that run on are cut: a report's words are a few lines, and a pasted page is not what is being sorted.
    (host.workdir / "messages.log").unlink()
    module.ask(host, "x" * 5000, {})
    sent = json.loads(host.recorded("messages.log").splitlines()[0])
    assert len(sent) < len(module.ASK) + module.WORDS_CHARS + 60 and "x" * module.WORDS_CHARS in sent and "x" * (module.WORDS_CHARS + 1) not in sent


def test_it_has_no_tool_to_use(kind) -> None:
    module, host = kind
    host.said("tool", "request")
    assert module.ask(host, "Make the card snap to the day", {}) == "request"
    assert json.loads(host.recorded("permission.json"))["behavior"] == "deny"


def test_it_is_not_asked_when_there_is_nobody_to_ask(kind) -> None:
    module, host = kind
    host.said("answer", "bug")
    # Another agent: Codex has no such quiet turn here.
    assert module.ask(host, "The card jumped back", {"provider": "codex"}) == "request"
    # No words, or words that are not text.
    assert module.ask(host, "   ", {}) == "request" and module.ask(host, None, {}) == "request" and module.ask(host, 42, {}) == "request"
    assert host.recorded("argv.json") == "", "no agent was started for any of these"
    # No Claude Code on this Mac (the lookup is the chat's own; the real one would find the person's real CLI).
    found = module.which
    module.which = lambda provider: None
    try:
        assert module.ask(host, "The card jumped back", {}) == "request"
    finally:
        module.which = found
    assert host.recorded("argv.json") == ""
    assert [line.split(" ms=")[0] for line in host.lines.lines] == ["report_kind result=request why=no_agent", "report_kind result=request why=no_words",
                                                                   "report_kind result=request why=no_words", "report_kind result=request why=no_words",
                                                                   "report_kind result=request why=no_agent"]


def test_a_slow_or_failing_agent_is_a_request_and_is_let_go(kind) -> None:
    module, host = kind
    host.said("hang")
    started = time.time()
    assert module.ask(host, "The card jumped back", {}, timeout=1.0) == "request"
    assert 1.0 <= time.time() - started < 6, "the person waits for the timeout and not much longer"
    deadline = time.time() + 5
    while not (host.workdir / "closed").exists() and time.time() < deadline:
        time.sleep(0.05)
    assert (host.workdir / "closed").exists(), "the agent's input was closed, so it could end"
    for mode in ("exit", "error"):
        host.said(mode)
        assert module.ask(host, "The card jumped back", {}) == "request", mode
    assert [re.search(r"why=(\w+)", line).group(1) for line in host.lines.lines] == ["timeout", "failed", "failed"]


def test_the_log_says_what_was_told_and_never_the_words(kind) -> None:
    module, host = kind
    host.said("answer", "bug")
    assert module.ask(host, "Quarterly plan for Acme jumped back", {}) == "bug"
    (line,) = host.lines.lines
    assert re.fullmatch(r"report_kind result=bug ms=\d+", line), line
    # The gateway's log cleaner keeps this line as it is: it names the verdict and the time, nothing of the person's.
    sys.path.insert(0, str(CHAT_DIR))
    try:
        facts = importlib.import_module("report_facts")
        assert facts.clean_agent_line(f"2026-10-12T03:21:07+0400 {line}") == f"2026-10-12T03:21:07+0400 {line}"
        assert facts.clean_agent_line("2026-10-12T03:21:07+0400 report_kind result=request why=timeout ms=25001") == \
            "2026-10-12T03:21:07+0400 report_kind result=request why=timeout ms=25001"
    finally:
        sys.path.remove(str(CHAT_DIR))
        sys.modules.pop("report_facts", None)
