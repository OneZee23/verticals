"""Sample morning reports for the tests of the report's shape (docs/design/morning-quality.md). Sample data only: sources are
"Team chat", "Mail" and "Calendar", tasks are the generic work of a small launch."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone

import psycopg

from verticals.core import docs as core_docs
from verticals.core import goals
from verticals.core import morning_checks, morning_report
from verticals.core import source_checks as sc
from verticals.core import sources as core_sources

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc)

ZONE = "Europe/Berlin"
COLUMNS = ("Source", "Window", "Read", "Tasks", "Inbox", "Done", "Put off", "Context", "Gap")
ROW_HEAD = "| Task | Purpose | Latest | Next action | Your comment |\n| --- | --- | --- | --- | --- |"


def source_doc(db: psycopg.Connection, owner: str, name: str, *, reads: Sequence[str] = (), approved: bool = True) -> str:
    """A source document, its check a name lookup (what a check reaches is not what is looked at here), approved by the owner
    unless `approved` is False: a source waiting for the owner's Approve cannot be read."""
    raw = {"kind": "dns", "host": "example.test", **({"reads": list(reads)} if reads else {})}
    body = sc.build_body(gives=f"What {name} says.", how="Read it.", since="The last report's cut-off.",
                         check=sc.Check.from_dict(raw), fixes=[])
    doc = core_docs.create(db, owner=owner, path=f"sources/{name.lower().replace(' ', '-')}.md", title=name, body=body).doc
    if approved:
        source = core_sources.find(db, owner=owner, ref=doc.id)
        core_sources.approve(db, owner=owner, doc_id=doc.id, check_hash=source.check.hash, now=NOW)
    return doc.id


def source_row(name: str, start: str, end: str, read: int, *counts: int, ref: str | None = None) -> str:
    """One row of the Sources table. `counts` are tasks, Inbox, done, put off, context and gap, in that order; by default
    all of what was read is a task."""
    placed = counts or (read, 0, 0, 0, 0, 0)
    label = f"[{name}](doc:{ref})" if ref else name
    return f"| {label} | {start} – {end} | {read} | " + " | ".join(str(c) for c in placed) + " |"


def sources_section(rows: Sequence[str], zone: str | None = ZONE) -> str:
    head = f"| {' | '.join(COLUMNS)} |\n| " + " | ".join("---" for _ in COLUMNS) + " |"
    return "## Sources\n\n" + (f"Times in {zone}.\n\n" if zone else "") + head + "\n" + "\n".join(rows) + "\n"


def report_body(
    rows: Sequence[str] = (), sources: str | None = None, *, unread: Sequence[str] = (), check: str | None = None,
    closed: Sequence[str] = (),
) -> str:
    """A report in the shape the skill asks for: the red block when something was not read, the check line, the rows, what
    was closed, the sources."""
    parts = []
    if unread:
        parts.append("```unread\n" + "\n".join(unread) + "\n```")
    parts.append(check or "Not checked yet: a second agent is reading it against the sources.")
    if rows:
        parts.append("## Today\n\n" + ROW_HEAD + "\n" + "\n".join(rows))
    if closed:
        parts.append("## Closed since the last report\n\n" + "\n".join(f"- {line}" for line in closed))
    parts.append(sources if sources is not None else sources_section([]))
    return "\n\n".join(parts) + "\n"


def goal_row(goal_id: str, title: str, *, bold: bool = False, child: bool = False, comment: str = "",
             latest: str = "Started.", next_action: str = "Finish it.") -> str:
    """A row of tasks. The owner's words go in as the document keeps them: a bar is escaped, as the app's editor saves it."""
    name = f"[{title}](goal:{goal_id})"
    name = f"**{name}**" if bold else f"– {name}" if child else name
    return f"| {name} | The purpose. | {latest} | {next_action} | {morning_report.escape(comment)} |"


def make_report(db: psycopg.Connection, owner: str, day: date, body: str, *, task: str | None = None) -> str:
    """The report of `day` as a document with its title, linked to the Morning report task when one is given."""
    doc = core_docs.create(db, owner=owner, path=f"reports/morning/{day.isoformat()}.md",
                           title=morning_checks.report_title(day), body=body).doc
    if task is not None:
        current = goals.goal(db, owner=owner, id=task).goal
        goals.update(db, owner=owner, id=task, body=(current.body or "") + f"[{doc.title}](doc:{doc.path})")
    return doc.id


def make_task(db: psycopg.Connection, owner: str, title: str, *, parent: str | None = None, day: date | None = None) -> str:
    kwargs = {"parent_id": parent} if parent else {}
    if day is not None:
        kwargs.update(vertical="day", anchor_date=day)
    return goals.create(db, owner=owner, title=title, **kwargs).goal.id
