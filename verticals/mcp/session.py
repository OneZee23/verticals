"""`session_link`: an agent in a Claude Code or Codex session ties that session to a task (docs/design/task-sessions.md).

A session lives in its agent's own app; the task's links list it, the goal's menu opens it and the card shows when it goes on,
and the desktop app keeps that list. This tool is how an agent that began outside the app tells the app which task it is
working on, over the loopback address the app gave this server (`VERTICALS_GATEWAY_URL`). It writes nothing to the board: the
only thing it changes is the app's own list of sessions, and the same call twice is the same link, so it has no `client_token`.
Outside the desktop app there is no such address and no such list, and the tool says so. Nothing reads what is said in a session:
the app links a session only through this call.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import psycopg
from mcp import types

from verticals.core import goals as core_goals
from verticals.mcp.shapes import error_result, ok

_AGENTS = {"claude": "Claude Code", "codex": "Codex"}

SESSION_LINK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string", "description": "The task's id: what follows verticals://goal/ in its link."},
        "agent": {"type": "string", "enum": sorted(_AGENTS), "description": "The agent you are."},
        "session": {
            "type": "string",
            "description": "Your session's id. Codex: your thread id, the CODEX_THREAD_ID variable of your shell. "
                           "Claude Code: leave it out and give cwd, as it is never told its own.",
        },
        "cwd": {
            "type": "string",
            "description": "The folder you work in, an absolute path. Claude Code: the app takes the session written to in the "
                           "last minute in that folder for yours. Either agent: the session is resumed from there.",
        },
    },
    "required": ["goal", "agent"],
}

TOOLS: tuple[types.Tool, ...] = (
    types.Tool(
        name="session_link",
        description=(
            "Tie this session to a task, so the app lists it among the task's sessions, opens it from there and notices when it "
            "goes on. Call it once, as soon as you see a link like verticals://goal/<id> in the conversation: <id> is `goal`. "
            "Say which agent you are. Codex gives `session`, its thread id (the CODEX_THREAD_ID variable of its shell). Claude "
            "Code is never told its own id, so it gives `cwd`, the folder it works in, and the app takes the session written to "
            "there in the last minute. Needs the Verticals desktop app. Changes nothing on the board; the same call again is "
            "the same link, and a session that already belongs to a task keeps it."
        ),
        input_schema=SESSION_LINK_SCHEMA,
    ),
)

_TIMEOUT_SECONDS = 5


def _ask_the_app(gateway_url: str, body: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """The app's answer to the link and no reason, or no answer and why not, in the app's own words where it gave them."""
    request = urllib.request.Request(
        f"{gateway_url.rstrip('/')}/__chat/link", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}"), ""
    except urllib.error.HTTPError as exc:
        try:
            return None, str(json.loads(exc.read()).get("error") or f"the app refused it ({exc.code})")
        except (ValueError, AttributeError):
            return None, f"the app refused it ({exc.code})"
    except (OSError, ValueError):
        return None, "the Verticals app did not answer"


def handle_session_link(
    conn: psycopg.Connection, owner: str, args: dict[str, Any], gateway_url: str
) -> types.CallToolResult:
    goal = core_goals.goal(conn, owner=owner, id=args["goal"]).goal  # a task that is not the owner's is not found
    if not gateway_url:
        return error_result("No Verticals app is keeping sessions here: this server was not started by it")
    body = {
        "goal": {"id": goal.id, "title": goal.title},
        "provider": args["agent"],
        "session": args.get("session") or None,
        "cwd": args.get("cwd") or None,
    }
    reply, why = _ask_the_app(gateway_url, body)
    if reply is None:
        return error_result(f"Not linked: {why}")
    kept = reply.get("goal") or {}
    structured = {"goal": kept, "agent": args["agent"], "session": reply.get("session"), "linked": bool(reply.get("same"))}
    title = (kept.get("title") or goal.title)[:60]
    if reply.get("same"):
        return ok(f"Linked this {_AGENTS[args['agent']]} session to {title!r} [{goal.id}]", structured)
    return ok(f"This session belongs to {title!r} [{kept.get('id')}] already, and keeps it", structured)
