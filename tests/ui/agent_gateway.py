"""The desktop gateway for the UI suite's conversation scenarios: the built app, `/api` onto the test backend and the
real `/__chat/*` server, whose agent is `tests/ui/fake_agent/claude` (docs/design-handoff S2.P1).

    python tests/ui/agent_gateway.py <ui_port> <api_port> <state_dir> <token> [<mcp_url>]

With an MCP server's url the fake agent's `[tool:NAME {json}]` marks are real calls to it, and the gateway marks each answer
there (docs/design/agent-answer-undo.md). Without one the url is a closed port: no tool is called and no answer is kept."""

from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main() -> None:
    ui_port, api_port, state, token = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
    mcp_url = sys.argv[5] if len(sys.argv) > 5 else "http://127.0.0.1:9/mcp"
    os.environ["VERTICALS_DESKTOP_UI_PORT"] = ui_port
    os.environ["VERTICALS_DESKTOP_API_PORT"] = api_port
    os.environ["VERTICALS_DESKTOP_STATE"] = str(state)
    os.environ["PATH"] = f"{HERE / 'fake_agent'}:{os.environ.get('PATH', '')}"
    state.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO / "desktop"))
    import launcher  # noqa: E402  (reads the ports above at import)

    launcher.DIST = REPO / "web" / "dist"
    chat = launcher.Chat(state, mcp_url, token)
    server = ThreadingHTTPServer(("127.0.0.1", int(ui_port)), launcher.make_gateway(token, chat))
    print("ready", flush=True)
    try:
        server.serve_forever()
    finally:
        chat.shutdown()


if __name__ == "__main__":
    main()
