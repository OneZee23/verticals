"""Pictures inside a text, as an agent reads them (verticals/core/pictures.py, docs/design/bug-reports.md). A report holds its
screenshots as data URLs in its body: hundreds of kilobytes of base64 that an agent has no use for and a context window no
room for. So every MCP read of a document or a goal returns each picture as a short placeholder, `[picture 1]`, and every
word as it is, and a placeholder the agent keeps when it writes the text back is the picture again: editing the words of a
report never costs it its pictures. Over a real stdio session, real F2, no mocks; the stored text is read straight from the
database, which is the person's own view."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import psycopg

from tests.mcp.conftest import TEST_OWNER, TEST_TOKEN, open_mcp_stdio

PATH = "reports/bugs/2026-10-12-120000.md"
WORDS = "I dragged the card to Friday and it jumped back"
TAIL = "Verticals 0.4, macOS 27 (arm64)\n\n## App log\n`app: up`"
# Sample bytes, not pictures anyone could open: what matters is that they are a lot of base64 inside a data URL.
BIG_JPG = "/9j/4AAQSkZJRgABAQAAAQABAAD/" + "2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD" * 400
BIG_PNG = "iVBORw0KGgo" + "AAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" * 400
TINY = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
ONE = f"![Picture 1](data:image/jpeg;base64,{BIG_JPG})"
TWO = f"![Picture 2](data:image/png;base64,{BIG_PNG})"
REPORT = f"{WORDS}\n\n{ONE}\n{TWO}\n\n{TAIL}"
READ = f"{WORDS}\n\n[picture 1]\n[picture 2]\n\n{TAIL}"


def _stored_body(dsn: str, doc_id: str) -> str:
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("SELECT body FROM docs WHERE owner = %s AND id = %s", (TEST_OWNER, doc_id)).fetchone()
    assert row is not None
    return row[0]


async def _read_a_report(dsn: str, tmp_path: Path):
    async with open_mcp_stdio(dsn, tmp_path, label="pictures-read") as (session, streams):
        created = await session.call_tool("doc_create", {"path": PATH, "title": "Report", "body": REPORT})
        doc_id = created.structured_content["doc"]["id"]
        by_id = await session.call_tool("doc_get", {"id": doc_id})
        by_path = await session.call_tool("doc_get", {"path": PATH})
        revision = await session.call_tool("doc_revision", {"id": doc_id, "revision": 1})
        tools = await session.list_tools()
        streams.assert_hygiene(token=TEST_TOKEN)
    return doc_id, created, by_id, by_path, revision, tools.tools


def test_doc_get_of_a_report_returns_its_words_and_placeholders_and_is_small(f2_dsn: str, tmp_path: Path) -> None:
    doc_id, created, by_id, by_path, revision, tools = anyio.run(_read_a_report, f2_dsn, tmp_path)

    assert len(REPORT) > 50_000, "the report is large because of its pictures"
    for result in (created, by_id, by_path):
        assert result.is_error is False, result.content[0].text if result.content else result
        assert result.structured_content["doc"]["body"] == READ
        # Small on the wire, in both the structured part and the text part, whatever the pictures weigh.
        assert len(json.dumps(result.structured_content)) < 1500, len(json.dumps(result.structured_content))
        assert sum(len(c.text) for c in result.content) < 300
        assert "base64" not in json.dumps(result.structured_content) and "data:image" not in json.dumps(result.structured_content)
    assert by_id.structured_content["doc"]["linked_goals"] == []
    # A past revision is read the same way.
    assert revision.structured_content["revision"]["body"] == READ and len(json.dumps(revision.structured_content)) < 1500

    # The person's own view is untouched: the stored text still holds both pictures, byte for byte.
    assert _stored_body(f2_dsn, doc_id) == REPORT
    # The agent is told what a placeholder is, where it reads.
    by_name = {t.name: t.description for t in tools}
    assert "[picture 1]" in by_name["doc_get"] and "[picture N]" in by_name["doc_save"]


async def _edit_a_report(dsn: str, tmp_path: Path):
    async with open_mcp_stdio(dsn, tmp_path, label="pictures-edit") as (session, streams):
        created = await session.call_tool("doc_create", {"path": PATH, "title": "Report", "body": REPORT})
        doc_id = created.structured_content["doc"]["id"]
        # The agent rewrites the words and leaves the placeholders where they are.
        words_only = await session.call_tool(
            "doc_save", {"id": doc_id, "expected_revision": 1, "body": READ.replace("jumped back", "went back to where it was")})
        stored_after_words = _stored_body(dsn, doc_id)
        # It takes the first picture out and moves the second to the top.
        reordered = await session.call_tool(
            "doc_save", {"id": doc_id, "expected_revision": 2, "body": f"[picture 2]\n\n{WORDS}\n\n{TAIL}"})
        stored_after_reorder = _stored_body(dsn, doc_id)
        # A body with no placeholder is a body with no picture; a save that sends none leaves the text as it is.
        title_only = await session.call_tool("doc_save", {"id": doc_id, "expected_revision": 3, "title": "Renamed"})
        stored_after_title = _stored_body(dsn, doc_id)
        stale = await session.call_tool("doc_save", {"id": doc_id, "expected_revision": 1, "body": READ})
        streams.assert_hygiene(token=TEST_TOKEN)
    return words_only, stored_after_words, reordered, stored_after_reorder, title_only, stored_after_title, stale


def test_a_report_edited_through_doc_save_keeps_the_pictures_its_placeholders_stand_for(f2_dsn: str, tmp_path: Path) -> None:
    words_only, after_words, reordered, after_reorder, title_only, after_title, stale = anyio.run(_edit_a_report, f2_dsn, tmp_path)

    assert words_only.is_error is False, words_only.content[0].text if words_only.content else words_only
    assert words_only.structured_content["doc"]["revision"] == 2
    assert after_words == REPORT.replace("jumped back", "went back to where it was"), "both pictures are in the stored text again"
    assert words_only.structured_content["doc"]["body"] == READ.replace("jumped back", "went back to where it was")

    assert reordered.is_error is False
    assert after_reorder == f"{TWO}\n\n{WORDS}\n\n{TAIL}", "one picture moved, the other taken out"
    assert reordered.structured_content["doc"]["body"] == f"[picture 1]\n\n{WORDS}\n\n{TAIL}", "and the new text reads from 1 again"

    assert title_only.is_error is False and after_title == after_reorder
    assert stale.is_error is True and "revision" in stale.content[0].text.lower(), "the lock is the one it was"


async def _goal_body(dsn: str, tmp_path: Path):
    body = f"What happened.\n\n![shot](data:image/png;base64,{TINY})\n\nAnd after."
    async with open_mcp_stdio(dsn, tmp_path, label="pictures-goal") as (session, streams):
        wrote = await session.call_tool("update", {"id": "SYNDAY01", "body": body})
        read = await session.call_tool("goal", {"id": "SYNDAY01"})
        kept = await session.call_tool("update", {"id": "SYNDAY01", "body": "What really happened.\n\n[picture 1]\n\nAnd after."})
        stored_after_kept = _goal_stored(dsn)
        # Many goals take one body: a placeholder is only text there, as no one goal's picture is meant.
        many = await session.call_tool("update", {"ids": ["SYNDAY01", "SYNCOL01"], "body": "Same.\n\n[picture 1]"})
        stored_after_many = _goal_stored(dsn)
        streams.assert_hygiene(token=TEST_TOKEN)
    return body, wrote, read, kept, stored_after_kept, many, stored_after_many


def _goal_stored(dsn: str, id_: str = "SYNDAY01") -> str:
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("SELECT body FROM goals WHERE owner = %s AND id = %s", (TEST_OWNER, id_)).fetchone()
    assert row is not None
    return row[0]


def test_a_goal_with_a_picture_reads_as_a_placeholder_and_keeps_it_when_its_words_change(f2_dsn: str, tmp_path: Path) -> None:
    body, wrote, read, kept, after_kept, many, after_many = anyio.run(_goal_body, f2_dsn, tmp_path)

    assert wrote.is_error is False, wrote.content[0].text if wrote.content else wrote
    assert read.structured_content["goal"]["body"] == "What happened.\n\n[picture 1]\n\nAnd after."
    assert kept.is_error is False
    assert after_kept == "What really happened.\n\n" + f"![shot](data:image/png;base64,{TINY})" + "\n\nAnd after."
    assert many.is_error is False and after_many == "Same.\n\n[picture 1]"
