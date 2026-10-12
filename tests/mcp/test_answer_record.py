"""What each agent answer wrote, kept by the MCP server in memory (docs/design/agent-answer-undo.md). A real
`--transport http` subprocess over the real F2 fixture, a real `mcp` client, no mocks. The gateway's three routes are called the
way the app's chat gateway calls them; the agent's calls carry their conversation in a header, as the gateway makes them.

What is asserted is what the page will be handed: the writes of one answer in order, each goal a write changed as it was and as
it was left, the goals it made and the goals it removed, and nothing for a call that belongs to no answer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import httpx2
import psycopg
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.mcp.conftest import McpHttpServer, mcp_http_subprocess

AUTH = lambda server: {"Authorization": f"Bearer {server.token}"}  # noqa: E731
BASE = lambda server: server.url.removesuffix("/mcp")  # noqa: E731


@asynccontextmanager
async def agent(server: McpHttpServer, conversation: str | None) -> AsyncIterator[ClientSession]:
    """An MCP client the way an agent of the app's chat is connected: bearer token and, when there is one, its conversation."""
    headers = AUTH(server) | ({"X-Verticals-Session": conversation} if conversation else {})
    async with httpx2.AsyncClient(headers=headers, timeout=10.0) as client:
        async with streamable_http_client(server.url, http_client=client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def gateway(server: McpHttpServer, route: str, **body: object) -> dict:
    response = httpx2.post(f"{BASE(server)}/answers/{route}", json=body, headers=AUTH(server), timeout=10.0)
    assert response.status_code == 200, response.text
    return response.json()


async def calls(server: McpHttpServer, conversation: str | None, *steps: tuple[str, dict]) -> list:
    async with agent(server, conversation) as session:
        return [await session.call_tool(name, arguments) for name, arguments in steps]


def an_answer_of(server: McpHttpServer, conversation: str, answer: str, *steps: tuple[str, dict]) -> dict:
    """The gateway opens an answer, the agent makes `steps`, the gateway closes it; what the page is handed."""
    gateway(server, "open", session=conversation, answer=answer)
    anyio.run(calls, server, conversation, *steps)
    gateway(server, "close", answer=answer)
    handed = gateway(server, "claim")["answers"]
    return handed[0] if handed else {}


def test_the_writes_of_one_answer_are_one_record_with_every_goal_as_it_was_and_as_it_was_left(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        answer = an_answer_of(
            server, "chat-one", "answer-1",
            ("update", {"id": "SYNCOL01", "done": True}),
            ("schedule", {"id": "SYNCOL02", "vertical": "day", "anchor_date": "2026-08-09"}),
            ("create", {"title": "Made by the answer", "vertical": "day", "anchor_date": "2026-08-08"}),
        )

    assert answer["id"] == "answer-1" and answer["session"] == "chat-one"
    assert answer["ended_at"] >= answer["started_at"] and answer["truncated"] is False
    writes = answer["writes"]
    assert [(w["seq"], w["tool"]) for w in writes] == [(1, "update"), (2, "schedule"), (3, "create")]
    assert [w["at"] for w in writes] == sorted(w["at"] for w in writes)

    (tick,) = writes[0]["changes"]
    assert tick["id"] == "SYNCOL01" and tick["before"]["done_at"] is None and tick["after"]["done_at"] is not None
    (move,) = writes[1]["changes"]
    assert move["before"]["anchor_date"] == "2026-08-08" and move["after"]["anchor_date"] == "2026-08-09"
    assert move["before"]["period_key"] == "2026-08-08" and move["after"]["period_key"] == "2026-08-09"
    (made,) = writes[2]["changes"]
    assert made["before"] is None and made["after"]["title"] == "Made by the answer" and made["after"]["origin"] == "agent"
    assert all("position" in c["after"] and "updated_at" in c["after"] for w in writes for c in w["changes"])


def test_a_call_with_no_conversation_or_no_open_answer_belongs_to_nobody(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        anyio.run(calls, server, None, ("update", {"id": "SYNCOL01", "done": True}))  # an agent outside the app
        anyio.run(calls, server, "chat-two", ("update", {"id": "SYNCOL02", "done": True}))  # a conversation with no answer open
        gateway(server, "open", session="chat-two", answer="answer-2")
        anyio.run(calls, server, "chat-other", ("update", {"id": "SYNCOL03", "done": True}))  # another conversation
        gateway(server, "close", answer="answer-2")

        assert gateway(server, "claim") == {"answers": []}, "an answer that wrote nothing is nothing"

    with psycopg.connect(f2_dsn, autocommit=True) as conn:
        ticked = conn.execute("SELECT id FROM goals WHERE id IN ('SYNCOL01','SYNCOL02','SYNCOL03') AND done_at IS NOT NULL ORDER BY id").fetchall()
    assert ticked == [("SYNCOL01",), ("SYNCOL02",), ("SYNCOL03",)], "the writes themselves happened, unrecorded"


def test_two_conversations_at_once_each_keep_their_own_answer(f2_dsn: str, tmp_path: Path) -> None:
    async def both(server: McpHttpServer) -> None:
        async with agent(server, "chat-a") as a, agent(server, "chat-b") as b:
            await a.call_tool("update", {"id": "SYNCOL01", "done": True})
            await b.call_tool("update", {"id": "SYNCOL02", "done": True})
            await a.call_tool("update", {"id": "SYNCOL03", "done": True})

    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        gateway(server, "open", session="chat-a", answer="answer-a")
        gateway(server, "open", session="chat-b", answer="answer-b")
        anyio.run(both, server)
        gateway(server, "close", answer="answer-a")
        gateway(server, "close", answer="answer-b")
        handed = {a["id"]: [c["id"] for w in a["writes"] for c in w["changes"]] for a in gateway(server, "claim")["answers"]}

    assert handed == {"answer-a": ["SYNCOL01", "SYNCOL03"], "answer-b": ["SYNCOL02"]}


def test_reads_and_failed_writes_are_not_recorded_and_a_write_of_the_same_words_is(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        answer = an_answer_of(
            server, "chat-three", "answer-3",
            ("board", {"date": "2026-08-08"}),
            ("update", {"id": "NOSUCHID", "done": True}),
            ("update", {"id": "SYNCOL01", "title": "Retitled"}),
            ("update", {"id": "SYNCOL01", "title": "Retitled"}),
        )

    first, again = answer["writes"]
    assert [w["tool"] for w in answer["writes"]] == ["update", "update"], "the read and the refused write are not there"
    assert first["changes"][0]["after"]["title"] == "Retitled"
    # The same words again is still a write: the server stamped the goal. The record says so, so that a goal the answer made is
    # known by the stamp its last write left, and "touched since" means a write after that one.
    (stamped,) = again["changes"]
    assert stamped["before"]["title"] == stamped["after"]["title"] and stamped["after"]["updated_at"] > stamped["before"]["updated_at"]


def test_an_answer_is_handed_over_once_and_only_when_it_has_ended(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        gateway(server, "open", session="chat-four", answer="answer-4")
        anyio.run(calls, server, "chat-four", ("update", {"id": "SYNCOL01", "done": True}))
        assert gateway(server, "claim") == {"answers": []}, "still open: the page waits for its end"

        gateway(server, "close", answer="answer-4")
        first = gateway(server, "claim")["answers"]
        assert [a["id"] for a in first] == ["answer-4"]
        assert gateway(server, "claim") == {"answers": []}, "handed over once"

        # A write that comes in after the answer ended (an agent stopped mid-call) is nobody's.
        anyio.run(calls, server, "chat-four", ("update", {"id": "SYNCOL02", "done": True}))
        assert gateway(server, "claim") == {"answers": []}


def test_the_next_answer_of_a_conversation_ends_one_that_was_left_open(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        gateway(server, "open", session="chat-five", answer="answer-5a")
        anyio.run(calls, server, "chat-five", ("update", {"id": "SYNCOL01", "done": True}))
        gateway(server, "open", session="chat-five", answer="answer-5b")  # the close of 5a never came
        anyio.run(calls, server, "chat-five", ("update", {"id": "SYNCOL02", "done": True}))
        gateway(server, "close", answer="answer-5b")
        handed = [(a["id"], [c["id"] for w in a["writes"] for c in w["changes"]]) for a in gateway(server, "claim")["answers"]]

    assert handed == [("answer-5a", ["SYNCOL01"]), ("answer-5b", ["SYNCOL02"])]


def test_a_tick_of_a_repeating_goal_records_the_occurrence_it_made_as_made(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        answer = an_answer_of(
            server, "chat-six", "answer-6",
            ("update", {"id": "SYNCOL04", "repeat": {"frequency": "daily", "interval": 1}}),
            ("update", {"id": "SYNCOL04", "done": True}),
        )

    tick = answer["writes"][1]["changes"]
    assert [c["id"] for c in tick][0] == "SYNCOL04" and len(tick) == 2
    made = tick[1]
    assert made["before"] is None and made["after"]["title"] == tick[0]["after"]["title"] and made["after"]["done_at"] is None


def test_a_delete_names_the_goal_it_took_and_lists_the_subtree_as_removed(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        answer = an_answer_of(server, "chat-seven", "answer-7", ("delete", {"id": "SYNDAY01", "cascade": True}))

    (write,) = answer["writes"]
    assert write["tool"] == "delete" and write["root"] == "SYNDAY01"
    assert {c["id"] for c in write["changes"]} == {"SYNDAY01", "SYNSUB01", "SYNSUB02", "SYNSUB03"}
    assert all(c["before"] is not None and c["after"] is None for c in write["changes"])


def test_the_routes_need_the_token_and_refuse_what_is_not_theirs(f2_dsn: str, tmp_path: Path) -> None:
    with mcp_http_subprocess(f2_dsn, tmp_path) as server:
        assert httpx2.post(f"{BASE(server)}/answers/claim", json={}, timeout=10.0).status_code == 401
        assert httpx2.post(f"{BASE(server)}/answers/open", json={"session": "x"}, headers=AUTH(server), timeout=10.0).status_code == 404
        assert httpx2.post(f"{BASE(server)}/answers/open", json={"session": "bad id!", "answer": "a"}, headers=AUTH(server), timeout=10.0).status_code == 404
        assert httpx2.get(f"{BASE(server)}/answers/claim", headers=AUTH(server), timeout=10.0).status_code == 405
        assert httpx2.post(f"{BASE(server)}/answers/claim", content=b"{", headers=AUTH(server), timeout=10.0).status_code == 400
        # The MCP endpoint itself is where it was.
        assert httpx2.post(server.url, json={}, headers=AUTH(server), timeout=10.0).status_code != 404
