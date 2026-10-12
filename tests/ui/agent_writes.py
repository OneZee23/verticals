"""An agent working in the background, for the undo scenarios (docs/design/board-undo.md): its writes go to the test's own database
through a real MCP server (`python -m verticals.mcp.server --transport http`) and a real MCP client, the way Claude's or Codex's
do, while the page is open. The page learns of them from the change feed, as it does in the app; nothing here touches the page.

The client runs in a thread of its own: Playwright's synchronous API keeps an event loop in this one."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio

from tests.mcp.conftest import mcp_http_subprocess, open_mcp_http_session
from tests.ui.conftest import F2_OWNER, TEST_TOKEN, UiSession

Agent = Callable[..., Any]


@contextmanager
def agent_at_work(session: UiSession, tmp_path: Path) -> Iterator[Agent]:
    """`agent(tool, **arguments)` calls one of Verticals' MCP tools as an agent would and returns what it answered. A refused call
    fails the test: a scenario that wants one says so."""
    with mcp_http_subprocess(session.backend.dsn, tmp_path, owner=F2_OWNER, token=TEST_TOKEN) as server:

        async def call(tool: str, arguments: dict[str, Any]) -> Any:
            async with open_mcp_http_session(server) as agent:
                result = await agent.call_tool(tool, arguments)
            assert not result.is_error, f"the agent's {tool} was refused: {result.content}"
            return result.structured_content

        with ThreadPoolExecutor(max_workers=1) as thread:
            yield lambda tool, **arguments: thread.submit(anyio.run, call, tool, arguments).result(timeout=30)
