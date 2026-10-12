"""`session_link` (docs/design/task-sessions.md): an agent in a Claude Code or Codex session ties it to a task. A real MCP client
against the real server, which is told where the desktop app is, and a real gateway (tests/ui/agent_gateway.py, the one the UI
suite serves its app from) that keeps the link. The agents' homes are inside the gateway's state folder: samples, never the
owner's own."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import anyio
import httpx2

from tests.mcp.conftest import REPO_ROOT, TEST_TOKEN, _free_port, _terminate, _wait_tcp, open_mcp_stdio

TASK = "SYNDAY01"  # "Draft the outline", the primary owner's day goal in F2
CODEX_THREAD = "0198f2c4-7b1e-7a35-b3d2-2c4e5f6a7b89"
CLAUDE_SESSION = "5f0c6a52-9d57-4c0e-9d9e-3b1f6f2f7a10"
OTHER_CLAUDE = "0b3e8a44-1b52-4f77-8c3f-6c5d2e9a1b21"
FOLDER = "/Users/sample/Sample Project"


@contextmanager
def desktop_gateway(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """The desktop gateway of the UI suite, alone: its chat routes keep the sessions of tasks, under a state folder of its own."""
    port, state, log_path = _free_port(), tmp_path / "desktop-state", tmp_path / "gateway.log"
    with open(log_path, "w") as logfile:
        proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "tests" / "ui" / "agent_gateway.py"), str(port), str(_free_port()), str(state), TEST_TOKEN],
            cwd=REPO_ROOT, stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            _wait_tcp("127.0.0.1", port, proc, log_path, timeout=30.0)
            yield f"http://127.0.0.1:{port}", state
        finally:
            _terminate(proc, port)


def claude_transcript(state: Path, folder: str, session: str, age: float = 3.0) -> Path:
    """A sample Claude transcript where Claude keeps it, written `age` seconds ago."""
    path = state / "claude-config" / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", folder) / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample\n" * 400)
    os.utime(path, (time.time() - age, time.time() - age))
    return path


def sessions_of(gateway: str, goal: str) -> list[dict]:
    with httpx2.Client(timeout=10.0) as client:
        return client.get(f"{gateway}/__chat/goal", params={"id": goal}).json()["conversations"]


def _server_args(gateway: str | None) -> tuple[str, ...]:
    return ("-m", "verticals.mcp.server", *(("--gateway-url", gateway) if gateway else ()))


async def _call(f2_dsn: str, tmp_path: Path, gateway: str | None, arguments: dict, label: str = "session-link"):
    async with open_mcp_stdio(f2_dsn, tmp_path, label=label, server_args=_server_args(gateway)) as (session, streams):
        result = await session.call_tool("session_link", arguments)
        streams.assert_hygiene(token=TEST_TOKEN)
        return result


def test_the_tool_tells_an_agent_to_call_it_when_it_sees_a_tasks_link(f2_dsn: str, tmp_path: Path) -> None:
    async def listed():
        async with open_mcp_stdio(f2_dsn, tmp_path, label="session-link-list") as (session, _streams):
            return {t.name: t for t in (await session.list_tools()).tools}

    tool = anyio.run(listed)["session_link"]
    text = " ".join(tool.description.split())
    assert "as soon as you see a link like verticals://goal/<id> in the conversation" in text
    assert "CODEX_THREAD_ID" in text and "Claude Code is never told its own id" in text
    assert tool.input_schema["required"] == ["goal", "agent"] and tool.input_schema["additionalProperties"] is False
    assert tool.input_schema["properties"]["agent"]["enum"] == ["claude", "codex"]


def test_a_codex_thread_is_linked_to_a_task_and_the_app_lists_it(f2_dsn: str, tmp_path: Path) -> None:
    with desktop_gateway(tmp_path) as (gateway, state):
        result = anyio.run(_call, f2_dsn, tmp_path, gateway, {"goal": TASK, "agent": "codex", "session": CODEX_THREAD, "cwd": FOLDER})
        assert result.is_error is False
        assert result.content[0].text == f"Linked this Codex session to 'Draft the outline' [{TASK}]"
        assert result.structured_content["linked"] is True and result.structured_content["session"] == CODEX_THREAD
        (found,) = sessions_of(gateway, TASK)
        assert (found["provider"], found["agentSession"], found["cwd"]) == ("codex", CODEX_THREAD, FOLDER)
        assert found["title"] == "Draft the outline" and found["outside"] is False
        # Again: the same link, once.
        again = anyio.run(_call, f2_dsn, tmp_path, gateway, {"goal": TASK, "agent": "codex", "session": CODEX_THREAD}, "again")
        assert again.is_error is False and len(sessions_of(gateway, TASK)) == 1


def test_claude_code_gives_its_folder_and_the_app_finds_the_session_written_to_there(f2_dsn: str, tmp_path: Path) -> None:
    with desktop_gateway(tmp_path) as (gateway, state):
        claude_transcript(state, FOLDER, OTHER_CLAUDE, age=3600)       # an old session in the same folder
        claude_transcript(state, FOLDER, CLAUDE_SESSION, age=4)        # the one it is
        claude_transcript(state, "/Users/sample/Elsewhere", "7a1f0c3e-0000-4000-8000-00000000000a", age=1)
        result = anyio.run(_call, f2_dsn, tmp_path, gateway, {"goal": TASK, "agent": "claude", "cwd": FOLDER})
        assert result.is_error is False, result.content
        assert result.structured_content["session"] == CLAUDE_SESSION
        (found,) = sessions_of(gateway, TASK)
        assert (found["provider"], found["agentSession"], found["cwd"]) == ("claude", CLAUDE_SESSION, FOLDER)


def test_a_session_that_already_belongs_to_a_task_keeps_it(f2_dsn: str, tmp_path: Path) -> None:
    with desktop_gateway(tmp_path) as (gateway, _state):
        anyio.run(_call, f2_dsn, tmp_path, gateway, {"goal": TASK, "agent": "codex", "session": CODEX_THREAD}, "first")
        second = anyio.run(_call, f2_dsn, tmp_path, gateway, {"goal": "SYNSUB01", "agent": "codex", "session": CODEX_THREAD}, "second")
        assert second.is_error is False and second.structured_content["linked"] is False
        assert second.content[0].text == f"This session belongs to 'Draft the outline' [{TASK}] already, and keeps it"
        assert sessions_of(gateway, "SYNSUB01") == [] and len(sessions_of(gateway, TASK)) == 1


def test_what_the_tool_cannot_do_it_says_in_a_short_line(f2_dsn: str, tmp_path: Path) -> None:
    with desktop_gateway(tmp_path) as (gateway, state):
        claude_transcript(state, FOLDER, CLAUDE_SESSION, age=3)
        claude_transcript(state, FOLDER, OTHER_CLAUDE, age=2)

        def says(gate: str | None, arguments: dict, label: str) -> str:
            result = anyio.run(_call, f2_dsn, tmp_path, gate, arguments, label)
            assert result.is_error is True, (arguments, result.content)
            text = result.content[0].text
            assert len(text) < 200  # S-54: an error is a line
            return text

        assert says(gateway, {"goal": "SYNNOPE1", "agent": "codex", "session": CODEX_THREAD}, "unknown") == "no goal 'SYNNOPE1' for owner 't1'"
        assert says(gateway, {"goal": "SYNOTH01", "agent": "codex", "session": CODEX_THREAD}, "foreign") == "no goal 'SYNOTH01' for owner 't1'"  # the other owner's
        assert says(gateway, {"goal": TASK, "agent": "codex"}, "no-thread") == "Not linked: Codex: give your thread id, the CODEX_THREAD_ID of your shell"
        assert says(gateway, {"goal": TASK, "agent": "claude", "cwd": FOLDER}, "two") == (
            "Not linked: 2 Claude sessions were written to in that folder in the last minute: give your session id")
        assert says(gateway, {"goal": TASK, "agent": "claude", "session": "nope"}, "bad-id") == "Not linked: The session id is not an id"
        assert says(None, {"goal": TASK, "agent": "codex", "session": CODEX_THREAD}, "no-app") == (
            "No Verticals app is keeping sessions here: this server was not started by it")
        assert says(f"http://127.0.0.1:{_free_port()}", {"goal": TASK, "agent": "codex", "session": CODEX_THREAD}, "app-away") == (
            "Not linked: the Verticals app did not answer")
        assert sessions_of(gateway, TASK) == []  # nothing was linked by any of those


def test_the_server_takes_only_a_loopback_address_for_the_app(f2_dsn: str, tmp_path: Path) -> None:
    for bad in ("https://127.0.0.1:8288", "http://example.com:8288", "http://127.0.0.1", "ftp://127.0.0.1:8288"):
        done = subprocess.run(
            [sys.executable, "-m", "verticals.mcp.server", "--gateway-url", bad], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
            env={**os.environ, "VERTICALS_DATABASE_URL": f2_dsn, "VERTICALS_TOKEN": TEST_TOKEN}, input="",
        )
        assert done.returncode == 1 and "--gateway-url must be 'http://127.0.0.1:<port>'" in done.stderr, (bad, done.stderr)
