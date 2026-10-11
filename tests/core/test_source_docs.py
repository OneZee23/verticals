"""Writing a source document (docs/design/sources.md, `core/source_docs.py`) against a real database: what the agent's
tool does before and after it runs the check. A new source needs every part and a free name; a change replaces only the
parts it names and leaves the rest as the owner left it; the draft says whether the check may run now."""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
import pytest

from verticals.core import docs as core_docs
from verticals.core import source_checks as sc
from verticals.core import source_docs
from verticals.core import sources as core
from verticals.core.errors import NotFound, RevisionMismatch, ValidationError

OWNER = "SYN-source-docs-owner"
NOW = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)

HTTP = {"kind": "http", "url": "https://example.test/health"}
CMD = {"kind": "cmd", "argv": ["/bin/echo", "disk 71% used"], "parse": r"(\d+)%", "max": 90}
WHOLE = {"title": "Health page", "gives": "Whether the service answers.", "how": "Ask the address.", "since": "the last report"}


def _make(db: psycopg.Connection, check: dict, **parts: object) -> core.Source:
    draft = source_docs.prepare(db, owner=OWNER, check=check, **{**WHOLE, **parts})
    return source_docs.save(db, owner=OWNER, draft=draft, now=NOW)


def test_a_new_source_needs_every_part_and_is_made_under_sources(db: psycopg.Connection) -> None:
    draft = source_docs.prepare(db, owner=OWNER, check=HTTP, fixes=["Restart it."], **WHOLE)
    assert (draft.created, draft.id, draft.revision, draft.path) == (True, None, None, "sources/health-page.md")
    assert draft.check is not None and draft.check.hash == sc.Check.from_dict(HTTP).hash
    assert draft.runnable is False, "an address waits for the owner too: it can carry something out"
    saved = source_docs.save(db, owner=OWNER, draft=draft, now=NOW)
    assert (saved.path, saved.title, saved.revision) == ("sources/health-page.md", "Health page", 1)
    assert saved.check is not None and saved.check.as_dict() == sc.Check.from_dict(HTTP).as_dict()
    assert sc.section_text(saved.body, "fixes") == "- Restart it."
    # Writing it wakes it: a row exists (its change rings the bell the open app listens to). A check waits for approval, so
    # it is not due until the owner has approved it, a name lookup like the rest.
    assert saved.row is not None and saved.row.next_check_at == NOW and saved.row.checked_at is None
    assert core.due(saved, NOW) is False and saved.waiting is True
    lookup = _make(db, {"kind": "dns", "host": "example.test"}, title="Name lookup")
    assert core.due(lookup, NOW) is False and lookup.waiting is True and lookup.row is not None, "a name lookup waits too"

    for missing in ("title", "gives", "how", "since", "check"):
        parts = {**WHOLE, "check": HTTP}
        del parts[missing]
        with pytest.raises(ValidationError, match=missing):
            source_docs.prepare(db, owner=OWNER, **parts)
    with pytest.raises(ValidationError, match="gives"):
        source_docs.prepare(db, owner=OWNER, check=HTTP, **{**WHOLE, "gives": "   "})


def test_a_taken_name_is_refused_and_names_the_source_that_has_it(db: psycopg.Connection) -> None:
    first = _make(db, HTTP)
    with pytest.raises(ValidationError, match="already a source") as caught:
        source_docs.prepare(db, owner=OWNER, check=HTTP, **WHOLE)
    assert first.id in caught.value.message and first.path in caught.value.message
    other = source_docs.prepare(db, owner="SYN-source-docs-other", check=HTTP, **WHOLE)
    assert other.path == first.path, "another owner's sources are another owner's"


def test_a_change_replaces_only_the_parts_it_names(db: psycopg.Connection) -> None:
    source = _make(db, HTTP, fixes=["Restart it."])
    # The owner adds a line of their own to a section by hand.
    mine = sc.set_section(source.body, "how", "Ask the address.\nIf it is slow, wait a minute before believing it.")
    core_docs.save(db, owner=OWNER, id=source.id, expected_revision=source.revision, body=mine)

    draft = source_docs.prepare(db, owner=OWNER, ref=source.id, fixes=[])
    assert (draft.created, draft.changed, draft.id, draft.revision) == (False, True, source.id, 2)
    assert sc.section_text(draft.body, "fixes") == sc.NO_FIXES
    assert "If it is slow, wait a minute before believing it." in draft.body, "the owner's own line stays"
    assert draft.check is not None and draft.check.hash == source.check.hash
    saved = source_docs.save(db, owner=OWNER, draft=draft, now=NOW)
    assert saved.revision == 3 and saved.title == "Health page"

    # The same change again changes nothing, and writes no revision.
    again = source_docs.prepare(db, owner=OWNER, ref="sources/health-page.md", fixes=[])
    assert again.changed is False
    assert source_docs.save(db, owner=OWNER, draft=again, now=NOW).revision == 3

    # A new title is the document's own; its file name stays.
    renamed = source_docs.save(db, owner=OWNER, draft=source_docs.prepare(db, owner=OWNER, ref=source.id, title="Service health"), now=NOW)
    assert (renamed.title, renamed.path) == ("Service health", "sources/health-page.md")


def test_a_check_may_run_only_with_the_owners_approval_of_exactly_that_check(db: psycopg.Connection) -> None:
    mcp = {"kind": "mcp", "url": "http://127.0.0.1:9100/mcp", "tool": "get_status"}
    lookup = {"kind": "dns", "host": "example.test"}
    for title, raw, other in (
        ("Disk", CMD, {**CMD, "argv": ["/bin/echo", "disk 72% used"]}),
        ("Health page", HTTP, {**HTTP, "url": "https://example.test/health?x=1"}),
        ("Status tool", mcp, {**mcp, "args": {"scope": "all"}}),
        ("Name", lookup, {**lookup, "host": "other.example.test"}),
    ):
        source = _make(db, raw, title=title)
        waiting = source_docs.prepare(db, owner=OWNER, ref=source.id)
        assert (waiting.check.gated, waiting.runnable) == (True, False), title

        core.approve(db, owner=OWNER, doc_id=source.id, check_hash=source.check.hash, now=NOW)
        approved = source_docs.prepare(db, owner=OWNER, ref=source.id)
        assert (approved.approved_hash, approved.runnable) == (source.check.hash, True), title

        changed = source_docs.prepare(db, owner=OWNER, ref=source.id, check=other)
        assert changed.check.hash != source.check.hash
        assert changed.runnable is False, f"the approval of the {raw['kind']} check was of the other one"

    # A check written fresh is not runnable, whatever kind it is.
    assert not source_docs.prepare(db, owner=OWNER, check=lookup, **{**WHOLE, "title": "Another name"}).runnable


def test_the_apps_own_connections_check_cannot_be_written_or_run_by_the_agent(db: psycopg.Connection) -> None:
    with pytest.raises(ValidationError, match="kind"):
        source_docs.prepare(db, owner=OWNER, check={"kind": "connections"}, **WHOLE)
    connections = core.find(db, owner=OWNER, ref=core.ensure_connections(db, owner=OWNER))
    draft = source_docs.prepare(db, owner=OWNER, ref=connections.id, fixes=["Sign in again."])
    assert draft.check is not None and draft.check.kind == "connections"
    assert draft.runnable is False, "the app runs it itself, hourly, through the CLI"


def test_a_hand_edited_check_nobody_can_read_has_no_check_and_runs_nothing(db: psycopg.Connection) -> None:
    source = _make(db, HTTP)
    broken = source.body.replace('"url"', '"adress"')
    core_docs.save(db, owner=OWNER, id=source.id, expected_revision=source.revision, body=broken)
    draft = source_docs.prepare(db, owner=OWNER, ref=source.id, fixes=[])
    assert (draft.check, draft.runnable) == (None, False)
    # Writing a good check puts it right.
    fixed = source_docs.prepare(db, owner=OWNER, ref=source.id, check=HTTP)
    assert fixed.check is not None and not fixed.runnable, "a good check is back, and waits for the owner like any address"


def test_a_stale_draft_is_refused_and_an_unknown_source_is_not_found(db: psycopg.Connection) -> None:
    source = _make(db, HTTP)
    draft = source_docs.prepare(db, owner=OWNER, ref=source.id, fixes=["Restart it."])
    core_docs.save(db, owner=OWNER, id=source.id, expected_revision=source.revision, body=source.body + "\nMore.")
    with pytest.raises(RevisionMismatch):
        source_docs.save(db, owner=OWNER, draft=draft, now=NOW)
    with pytest.raises(NotFound):
        source_docs.prepare(db, owner=OWNER, ref="sources/none.md", fixes=[])
