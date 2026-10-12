"""What the agent-answer scenarios share (docs/design/agent-answer-undo.md): F2 behind the desktop gateway, a real MCP server on the
same database, and the fake agent, whose `[tool:NAME {json}]` marks are real calls to that server over MCP, carrying the
conversation the gateway wrote into its connection. So an answer here is made the way a real one is: the gateway marks it, the
agent's calls reach the server with the mark, the server keeps what each write changed, and the page reads the record when the
answer ends.

The tests press the pill or ⌘Z; nothing here reads the record or reaches into the page."""

from __future__ import annotations

import json
import os
import signal
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from tests.mcp.conftest import McpHttpServer, mcp_http_subprocess, open_mcp_http_session
from tests.ui.conftest import F2_OWNER, TEST_TOKEN, UiSession, _backend, _make_ui_session
from tests.ui.test_agent_conversation import _agent_gateway
from tests.ui.undo_helpers import write_log, writes
from tests.ui.views import FIELD

BALLOON = '[data-balloon][data-who="agent"]'
READ = "/__chat/answers"
#: The pill of an answer's own Undo (it reads Redo once the answer is taken back), on its message and in the field.
UNDO = '[data-role="answer-undo"]'
CIRCLE_ANSWER = '[data-role="circle-answer"]'
CHOICE = '[data-role="field-notice-choice"]'

#: Answers, by the marks the fake agent reads. One that ticks a goal, moves another and makes a third.
THREE = (
    'Tick, move, make [tool:update {"id": "SYNCOL01", "done": true}] '
    '[tool:schedule {"id": "SYNORD01", "vertical": "month", "anchor_date": "2026-08-08"}] '
    '[tool:create {"title": "Made by the answer", "vertical": "day", "anchor_date": "2026-08-08"}]'
)
#: One that moves a goal and ticks another, and one that only moves a goal.
TWO = (
    'Move and tick [tool:schedule {"id": "SYNORD02", "vertical": "month", "anchor_date": "2026-08-08"}] '
    '[tool:update {"id": "SYNCOL03", "done": true}]'
)
ONE = 'Move [tool:schedule {"id": "SYNORD02", "vertical": "month", "anchor_date": "2026-08-08"}]'


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    """These scenarios run with the motion the app has (no preference), as the person sees it, unless a test asks for another."""
    return getattr(request, "param", "no-preference")


@pytest.fixture
def mcp_server(f2_dsn: str, tmp_path: Path) -> Iterator[McpHttpServer]:
    """A real MCP server (`python -m verticals.mcp.server --transport http`) on the test's database, for the owner F2 belongs to."""
    with mcp_http_subprocess(f2_dsn, tmp_path, owner=F2_OWNER, token=TEST_TOKEN) as server:
        yield server


@pytest.fixture
def ui_answers(
    browser: Browser, f2_dsn: str, mcp_server: McpHttpServer, tmp_path: Path, request: pytest.FixtureRequest, web_dist: None,
    ui_reduced_motion: str,
) -> Iterator[UiSession]:
    """F2 served by the desktop gateway, whose fake agent calls the MCP server and whose answers the server keeps."""
    with _backend(f2_dsn, F2_OWNER, tmp_path) as backend:
        with _agent_gateway(backend, tmp_path, mcp_url=mcp_server.url) as base_url:
            yield from _make_ui_session(
                browser=browser, backend=backend, static_base_url=base_url, request=request, reduced_motion=ui_reduced_motion,
            )


def reads(session: UiSession) -> int:
    """How many times the page has asked the gateway for the answers that ended."""
    return sum(1 for r in session.request_log if r["method"] == "POST" and r["url"].endswith(READ))


def board_writes(session: UiSession, since: int = 0) -> list[tuple[str, str, int | None]]:
    """The writes the page made to the board's API since `since`: not its reading of the answers, which is a POST too."""
    return [w for w in writes(session, since) if "/__chat/" not in w[1]]


def board_write_log(session: UiSession, since: int = 0) -> list[str]:
    """The same writes, each with what it carried, for the message of an assertion that counts them."""
    return [line for line in write_log(session, since) if "/__chat/" not in line]


def sent_to_the_agent(session: UiSession, since: int = 0) -> int:
    """How many messages the page sent to the agent since `since`: a key that asks is the app's own and sends none."""
    return sum(1 for r in session.request_log[since:] if r["method"] == "POST" and r["url"].endswith("/__chat/send"))


def wait_for_reads(session: UiSession, more_than: int) -> None:
    for _ in range(400):
        if reads(session) > more_than:
            return
        session.page.wait_for_timeout(25)
    raise AssertionError("the page did not read the answer when it ended")


def reads_since_the_window_opened(session: UiSession) -> int:
    """The reads made since the page was last loaded: its own, when it opens, and the ones its conversation's past turns ask for."""
    log = session.request_log
    opened = max((i for i, r in enumerate(log) if r["method"] == "GET" and r["url"].rstrip("/") == session.base_url.rstrip("/")), default=-1)
    return sum(1 for r in log[opened + 1:] if r["method"] == "POST" and r["url"].endswith(READ))


def settle(session: UiSession) -> None:
    """Waits until the window has made the reads it makes on its own when it opens, and has stopped: a read still on its way would
    be taken for the one an answer's end asks for."""
    before = -1
    for _ in range(200):
        now = reads_since_the_window_opened(session)
        if now and now == before:
            return
        before = now
        session.page.wait_for_timeout(250)
    raise AssertionError("the window did not finish its first reads")


def send(session: UiSession, words: str) -> int:
    """Writes to the agent the way a person does. Returns how many times the page had asked for answers by then."""
    settle(session)
    seen = reads(session)
    session.page.keyboard.press("Control+k")
    session.page.locator(FIELD).fill(words)
    session.page.keyboard.press("Enter")
    return seen


def to_the_board(page: Page) -> None:
    """A click on the board sends the conversation away; the keys are the board's again."""
    page.locator('[data-role="out-of-focus"]').click(position={"x": 60, "y": 60})
    expect(page.locator(".app-content--out-of-focus")).to_have_count(0)
    page.evaluate("document.activeElement instanceof HTMLElement && document.activeElement.blur()")


def answered(session: UiSession, seen: int) -> None:
    """The agent has answered, its end has reached the page and the page has read the answer that ended (`seen` is what `send`
    returned)."""
    page = session.page
    wait_for_reads(session, seen)
    expect(page.locator(BALLOON).last).to_contain_text("Done", timeout=20000)
    expect(page.locator('[data-role="agent-step"]')).to_have_count(0, timeout=10000)
    page.wait_for_timeout(250)  # and has made its Undo of it


def ask(session: UiSession, words: str, *, stay: bool = False) -> None:
    """A whole request: the words and the answer. The conversation is sent away, so the board is in front and the keys are the
    board's, unless `stay` keeps it open for its messages' Undo."""
    answered(session, send(session, words))
    if not stay and session.page.locator(".app-content--out-of-focus").count():
        to_the_board(session.page)


def ask_for_the_field(session: UiSession, words: str) -> None:
    """A request whose answer lands in the field: the conversation is sent away while the agent works (`[slow]`), so the answer
    stands in the circle, with its Undo if it changed the board."""
    seen = send(session, words + " [slow]")
    session.page.wait_for_timeout(150)
    to_the_board(session.page)
    expect(session.page.locator(CIRCLE_ANSWER)).to_contain_text("Done", timeout=20000)
    wait_for_reads(session, seen)
    session.page.wait_for_timeout(250)


def later(page: Page, seconds: float) -> None:
    """Moves the page's clock on, by the tests' own clock control: nothing waits. (`Date.now()` is fixed at the pinned moment and
    stands still until it is moved; the timers run as they do.)"""
    page.clock.set_fixed_time(page.evaluate("Date.now()") / 1000 + seconds)


def look(pill: Locator) -> dict[str, str]:
    """What a pill looks like, as the browser computed it."""
    return pill.evaluate(
        """el => {
          const css = getComputedStyle(el)
          return Object.fromEntries(['height', 'paddingLeft', 'paddingRight', 'borderRadius', 'backgroundColor', 'color',
            'fontFamily', 'fontSize', 'fontWeight', 'lineHeight'].map((k) => [k, css[k]]))
        }"""
    )


def choices(page: Page) -> list[str]:
    """What the question ⌘Z asks offers, pill by pill, as it reads."""
    return [text.strip() for text in page.locator(CHOICE).all_text_contents()]


@contextmanager
def outside_agent(server: McpHttpServer) -> Iterator[Callable[..., Any]]:
    """`agent(tool, **arguments)` calls one of Verticals' MCP tools as an agent the app did not start would: no conversation in its
    connection, so none of its writes is part of an answer. The client runs in a thread of its own: Playwright's synchronous API
    keeps an event loop in this one."""

    async def call(tool: str, arguments: dict[str, Any]) -> Any:
        async with open_mcp_http_session(server) as agent:
            result = await agent.call_tool(tool, arguments)
        assert not result.is_error, f"the agent's {tool} was refused: {result.content}"
        return result.structured_content

    with ThreadPoolExecutor(max_workers=1) as thread:
        yield lambda tool, **arguments: thread.submit(anyio.run, call, tool, arguments).result(timeout=30)


@contextmanager
def held(server: McpHttpServer) -> Iterator[None]:
    """The MCP server stops answering, without being restarted (SIGSTOP), so the gateway cannot read the record of the answers."""
    os.kill(server.pid, signal.SIGSTOP)
    try:
        yield
    finally:
        os.kill(server.pid, signal.SIGCONT)


def answer_without_a_page(base_url: str, session_id: str, words: str) -> None:
    """The agent answers a request with no window open to hear it (the morning report is given so): the words go to the gateway
    directly, and this returns when the turn has ended."""
    claude = next(a for a in httpx.get(f"{base_url}/__chat/agents", timeout=10).json()["agents"] if a["id"] == "claude")
    sent = httpx.post(f"{base_url}/__chat/send", timeout=10, json={
        "session": session_id, "text": words, "mode": "send",
        "context": {"today": "2026-08-08", "tz": "UTC", "url": "/", "title": "Verticals"},
        "settings": {"provider": "claude", "model": "", "effort": claude["defaultEffort"], "fast": False,
                     "permission": claude["defaultPermission"]},
    })
    sent.raise_for_status()
    with httpx.stream("GET", f"{base_url}/__chat/events", params={"session": session_id, "since": 0, "boot": ""}, timeout=30) as events:
        for line in events.iter_lines():
            if not line.startswith("data:"):
                continue
            try:
                said = json.loads(line[5:])
            except ValueError:
                continue
            if isinstance(said, dict) and isinstance(said.get("event"), dict) and said["event"].get("t") == "done":
                return
    raise AssertionError("the turn never ended")
