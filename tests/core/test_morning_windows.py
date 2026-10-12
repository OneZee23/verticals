"""Every source, from where the last report stopped (docs/design/morning-quality.md, `core/morning_windows.py`): the cut-offs are
in the last report's own last section, and the next morning starts each source there."""

from __future__ import annotations

from datetime import date

import psycopg

from tests.core.morning_sample import make_report, report_body, source_doc, source_row, sources_section
from verticals.core import docs as core_docs
from verticals.core import morning, morning_windows

OWNER = "SYN-windows-owner"
MONDAY = date(2026, 10, 12)


def _report(db: psycopg.Connection, day: date, rows: list[str], owner: str = OWNER) -> str:
    return make_report(db, owner, day, report_body(sources=sources_section(rows)))


def test_each_source_starts_where_the_last_report_stopped_reading_it(db: psycopg.Connection) -> None:
    chat = source_doc(db, OWNER, "Team chat")
    mail = source_doc(db, OWNER, "Mail")
    calendar = source_doc(db, OWNER, "Calendar")
    _report(db, date(2026, 10, 11), [
        source_row("Team chat", "2026-10-10 07:00", "2026-10-11 06:58", 12, ref="sources/team-chat.md"),
        source_row("Mail", "2026-10-10 07:00", "2026-10-11 06:41", 5, ref=mail),  # linked by the document's id
        source_row("Calendar", "2026-10-10 07:00", "2026-10-11 07:02", 3),  # not linked: found by its name
    ])
    cutoffs = morning_windows.cutoffs(db, owner=OWNER, before=MONDAY)
    assert cutoffs == {chat: "2026-10-11T06:58:00+02:00", mail: "2026-10-11T06:41:00+02:00",
                       calendar: "2026-10-11T07:02:00+02:00"}


def test_the_report_before_the_day_is_the_newest_earlier_one_and_never_the_day_itself_or_a_later_one(db: psycopg.Connection) -> None:
    chat = source_doc(db, OWNER, "Team chat")
    row = lambda end: [source_row("Team chat", "2026-10-01 07:00", end, 1, ref="sources/team-chat.md")]  # noqa: E731
    _report(db, date(2026, 10, 9), row("2026-10-09 07:00"))
    _report(db, date(2026, 10, 11), row("2026-10-11 07:00"))
    _report(db, MONDAY, row("2026-10-12 07:00"))  # the day's own report, made already: rebuilding it starts from yesterday's
    _report(db, date(2026, 10, 13), row("2026-10-13 07:00"))
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {chat: "2026-10-11T07:00:00+02:00"}
    assert morning_windows.cutoffs(db, owner=OWNER, before=date(2026, 10, 10)) == {chat: "2026-10-09T07:00:00+02:00"}
    assert morning_windows.last_report(db, owner=OWNER, before=date(2026, 10, 9)) is None


def test_a_source_the_last_report_could_not_read_keeps_its_old_end(db: psycopg.Connection) -> None:
    """A day of silence never moves a cut-off: the row of an unread source ends where its old window ended."""
    mail = source_doc(db, OWNER, "Mail")
    _report(db, date(2026, 10, 10), [source_row("Mail", "2026-10-09 07:00", "2026-10-10 07:00", 4, ref="sources/mail.md")])
    _report(db, date(2026, 10, 11), [source_row("Mail", "2026-10-10 07:00", "2026-10-10 07:00", 0, 0, 0, 0, 0, 0, 0, ref="sources/mail.md")])
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {mail: "2026-10-10T07:00:00+02:00"}


def test_no_report_yet_a_source_not_in_it_and_a_row_with_no_end_have_no_cut_off(db: psycopg.Connection) -> None:
    source_doc(db, OWNER, "Team chat")
    new = source_doc(db, OWNER, "Mail")
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {}  # the first morning
    _report(db, date(2026, 10, 11), ["| Team chat | – | 0 | 0 | 0 | 0 | 0 | 0 | 0 |"])
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {}  # a row with no end, and a source with no row (Mail)
    assert new not in morning_windows.cutoffs(db, owner=OWNER, before=MONDAY)


def test_a_report_that_does_not_follow_the_shape_gives_no_cut_offs_and_breaks_nothing(db: psycopg.Connection) -> None:
    source_doc(db, OWNER, "Team chat")
    core_docs.create(db, owner=OWNER, path="reports/morning/2026-10-11.md", title="Morning report — 11 October 2026",
                     body="A few lines the agent wrote its own way.\n\n| Source | Window |\n| --- | --- |\n| Team chat | yesterday |\n")
    core_docs.create(db, owner=OWNER, path="reports/morning/notes.md", title="Notes", body="Not a day.")
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {}


def test_the_apps_own_connections_document_is_not_a_source_to_read(db: psycopg.Connection) -> None:
    from verticals.core import sources as core_sources
    core_sources.ensure_connections(db, owner=OWNER)
    chat = source_doc(db, OWNER, "Team chat")
    assert [s.id for s in morning_windows.real_sources(db, owner=OWNER)] == [chat]


def test_another_owners_reports_and_sources_are_not_seen(db: psycopg.Connection) -> None:
    source_doc(db, OWNER, "Team chat")
    other = source_doc(db, "SYN-windows-other", "Team chat")
    make_report(db, "SYN-windows-other", date(2026, 10, 11), report_body(sources=sources_section(
        [source_row("Team chat", "2026-10-10 07:00", "2026-10-11 07:00", 1, ref="sources/team-chat.md")])))
    assert morning_windows.cutoffs(db, owner=OWNER, before=MONDAY) == {}
    assert list(morning_windows.cutoffs(db, owner="SYN-windows-other", before=MONDAY)) == [other]


def test_beginning_a_morning_does_not_need_a_report_to_read(db: psycopg.Connection) -> None:
    """The first morning, with no report before it: the day begins, nothing lands, nothing fails."""
    begun = morning.begin(db, owner=OWNER, day=MONDAY)
    assert begun.asked and begun.landed == ()
