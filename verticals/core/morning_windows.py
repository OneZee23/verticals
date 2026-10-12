"""Where the last morning report stopped reading each source (docs/design/morning-quality.md, "Every source, from where the last
report stopped").

The cut-offs are in the report itself: its last section lists every source with its window (`core/morning_report.py`). Nothing
else keeps them, so no table and no migration: the next morning reads the last report's section and starts each source at the end
of the window it finds there. A source the last report could not read keeps its old end in its row, so a day of silence never
moves a cut-off forward.

IR-02: reads only, takes an open connection, never commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg

from verticals.core import morning_report as report
from verticals.core import sources as core_sources
from verticals.core.field_rules import validate_owner

# A look at the latest few paths is enough: a report a day, and a path that is not a date is skipped.
_LOOK = 60


@dataclass(frozen=True)
class Last:
    """The report before a day: its document, its day, and what its last section says."""

    doc_id: str
    path: str
    day: date
    sources: report.Sources


def last_report(conn: psycopg.Connection, *, owner: str, before: date) -> Last | None:
    """The newest report of a day earlier than `before`, or None. A report made again for the same day never counts as the one
    before it: a rebuilt morning starts where yesterday's report stopped, as the first one did."""
    owner = validate_owner(owner)
    rows = conn.execute(
        "SELECT id, path, body FROM docs WHERE owner = %(owner)s AND starts_with(path, %(folder)s)"
        " ORDER BY path DESC LIMIT %(look)s",
        {"owner": owner, "folder": report.FOLDER + "/", "look": _LOOK},
    ).fetchall()
    for doc_id, path, body in rows:
        day = report.day_of(path)
        if day is not None and day < before:
            return Last(doc_id=doc_id, path=path, day=day, sources=report.parse_sources(body))
    return None


def row_for(source: core_sources.Source, rows: tuple[report.SourceRow, ...]) -> report.SourceRow | None:
    """The row of a report that is this source: the one linking its document (by id or path), else the one with its name. When
    a report lists a source twice, the row that ends last."""
    own = [r for r in rows if r.ref is not None and r.ref in (source.id, source.path)]
    if not own:
        title = (source.title or "").strip().lower()
        own = [r for r in rows if title and r.name.strip().lower() == title]
    ended = [r for r in own if r.end is not None]
    if ended:
        return max(ended, key=lambda r: r.end.timestamp() if r.end else 0.0)
    return own[0] if own else None


def real_sources(conn: psycopg.Connection, *, owner: str) -> list[core_sources.Source]:
    """The sources a report reads: every document under `sources/`, except the app's own Connections, which says which of the
    agent's servers answer and is nothing to read."""
    return [s for s in core_sources.sources(conn, owner=owner) if s.path != core_sources.CONNECTIONS_PATH]


def cutoffs(conn: psycopg.Connection, *, owner: str, before: date) -> dict[str, str]:
    """For each source with an end in the last report's section: its document's id and that end, as an ISO time with its
    offset. A source the last report has no row for, or no end for, has none: it starts where its own document says
    ("Since when")."""
    last = last_report(conn, owner=owner, before=before)
    if last is None:
        return {}
    out = {}
    for source in real_sources(conn, owner=owner):
        row = row_for(source, last.sources.rows)
        if row is not None and row.end is not None:
            out[source.id] = row.end.isoformat()
    return out
