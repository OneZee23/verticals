"""The morning report's shape, read and written by code (docs/design/morning-quality.md, `core/morning_report.py`): the sources
section and its windows, the red block, the check line, the rows and the owner's cells. Pure: no database."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tests.core.morning_sample import goal_row, report_body, source_row, sources_section
from verticals.core import morning_report as report
from verticals.core.morning_report import FAIL, GAP, PASS, Outcome

BERLIN = ZoneInfo("Europe/Berlin")


# --- the sources section: windows and counts -------------------------------------------------------------------------


def test_a_row_of_the_sources_section_says_where_its_window_began_and_ended() -> None:
    body = report_body(sources=sources_section([
        source_row("Team chat", "2026-10-11 18:40", "2026-10-12 06:57", 42, 11, 4, 6, 3, 15, 3, ref="sources/team-chat.md"),
    ]))
    section = report.parse_sources(body)
    assert (section.found, section.zone, section.problems) == (True, "Europe/Berlin", ())
    (row,) = section.rows
    assert (row.name, row.ref) == ("Team chat", "sources/team-chat.md")
    assert row.start == datetime(2026, 10, 11, 18, 40, tzinfo=BERLIN)
    assert row.end == datetime(2026, 10, 12, 6, 57, tzinfo=BERLIN)
    assert row.end.isoformat() == "2026-10-12T06:57:00+02:00"
    assert (row.read, row.placed, row.counts) == (42, 42, (11, 4, 6, 3, 15, 3))


def test_a_time_is_read_in_the_zone_the_section_names_so_a_clock_change_cannot_move_a_cut_off() -> None:
    # The night the clocks go back in Berlin: 02:30 happens twice, and the zone, not the report, says which offset the day had.
    rows = [source_row("Mail", "2026-10-24 22:00", "2026-10-25 07:00", 3)]
    end = report.parse_sources(report_body(sources=sources_section(rows))).rows[0].end
    assert end.utcoffset().total_seconds() == 3600  # winter time by the morning
    start = report.parse_sources(report_body(sources=sources_section(rows))).rows[0].start
    assert start.utcoffset().total_seconds() == 7200


def test_a_row_whose_counts_do_not_add_up_shows_as_a_number() -> None:
    row = report.parse_sources(report_body(sources=sources_section([
        source_row("Team chat", "2026-10-11 18:40", "2026-10-12 06:57", 44, 11, 4, 6, 3, 15, 3),  # 42 placed of 44
    ]))).rows[0]
    assert (row.read, row.placed) == (44, 42)


def test_a_source_with_no_window_is_a_row_without_times_not_an_error_in_the_section() -> None:
    body = report_body(sources=sources_section([
        "| Calendar | – | 0 | 0 | 0 | 0 | 0 | 0 | 0 |",
        source_row("Mail", "2026-10-11 07:00", "2026-10-11 07:00", 0, 0, 0, 0, 0, 0, 0),
    ]))
    calendar, mail = report.parse_sources(body).rows
    assert (calendar.start, calendar.end, calendar.problems) == (None, None, ())
    assert mail.start == mail.end  # a source not read keeps its old end


def test_a_window_that_is_not_two_times_is_named_in_the_row() -> None:
    body = report_body(sources=sources_section(["| Mail | since yesterday | 3 | 3 | 0 | 0 | 0 | 0 | 0 |"]))
    (row,) = report.parse_sources(body).rows
    assert row.end is None and row.problems and "two times" in row.problems[0]


def test_a_report_with_no_sources_section_or_no_zone_says_so_and_returns_what_it_could() -> None:
    assert report.parse_sources("Nothing here.\n").problems == ("The report has no Sources section.",)
    no_zone = report.parse_sources(report_body(sources=sources_section(
        [source_row("Mail", "2026-10-11 07:00", "2026-10-12 06:57", 1)], zone=None)))
    assert no_zone.zone is None and no_zone.rows[0].end is None and "time zone" in no_zone.problems[0]
    odd = report.parse_sources(report_body(sources=sources_section(
        [source_row("Mail", "2026-10-11 07:00", "2026-10-12 06:57", 1)], zone="Mars/Olympus")))
    assert "Mars/Olympus" in odd.problems[0] and odd.rows[0].end is None


def test_the_places_are_every_column_after_read_whatever_they_are_called() -> None:
    body = ("## Sources\n\nTimes in UTC.\n\n| Window | Source | Read | Tasks | Waiting | Seen | Left |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| 2026-10-11 07:00 – 2026-10-12 07:00 | Mail | 21 | 6 | 5 | 4 | 6 |\n"
            "| 2026-10-11 07:00 – 2026-10-12 07:00 | Notes | 21 | 6 | 5 | 4 | - |\n")
    mail, notes = report.parse_sources(body).rows
    assert (mail.name, mail.read, mail.counts, mail.placed) == ("Mail", 21, (6, 5, 4, 6), 21)
    assert (notes.counts, notes.placed) == ((6, 5, 4, None), None)  # a cell that is not a number is not a count
    no_places = report.parse_sources("## Sources\n\nTimes in UTC.\n\n| Source | Window | Read |\n| --- | --- | --- |\n| Mail | 2026-10-11 07:00 – 2026-10-12 07:00 | 3 |\n")
    assert "no columns for where the messages went" in no_places.problems[0] and no_places.rows[0].placed is None


def test_the_last_sources_section_is_the_one_and_a_table_in_a_code_block_is_not_a_table() -> None:
    body = ("## Sources\n\nTimes in UTC.\n\n| Source | Window | Read | Tasks | Inbox | Done | Put off | Context | Gap |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| Old | 2026-10-01 07:00 – 2026-10-02 07:00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |\n\n"
            "```\n| Fake | not a row |\n| --- | --- |\n```\n\n" + sources_section(
                [source_row("New", "2026-10-11 07:00", "2026-10-12 07:00", 2)], zone="UTC"))
    assert [row.name for row in report.parse_sources(body).rows] == ["New"]


# --- the red block ---------------------------------------------------------------------------------------------------


def test_what_could_not_be_read_is_the_lines_of_the_unread_block() -> None:
    body = report_body(unread=["Mail: not approved yet, so it was not read.", "Team chat: get_messages was declined."])
    assert report.unread(body) == ["Mail: not approved yet, so it was not read.", "Team chat: get_messages was declined."]
    assert report.unread(report_body()) is None
    assert report.render_unread(["A", "B"]) == "```unread\nA\nB\n```"


# --- the check ---------------------------------------------------------------------------------------------------------


def _all(result: str = PASS) -> dict[str, Outcome]:
    return {key: Outcome(result) for key in report.KEYS}


def test_ten_passes_are_one_line() -> None:
    assert len(report.KEYS) == 10
    assert report.render_verdict(_all()) == "Checked against the sources by a second agent: all 10 passed."


def test_a_verdict_lists_only_the_checks_that_are_not_a_pass_and_counts_the_rest() -> None:
    outcomes = _all() | {"names": Outcome(FAIL, "Two rows are named by what is done, not by the result."),
                         "where": Outcome(GAP, "The calendar answered 40 of 52 events | the rest were cut off.")}
    text = report.render_verdict(outcomes)
    assert text.splitlines()[0] == "Checked against the sources by a second agent: 8 of 10 passed, 1 gap, 1 failed."
    table = text.split("\n\n", 1)[1].splitlines()
    assert table[0] == "| Check | Result | What it found |"
    assert table[2:] == ["| Names | Failed | Two rows are named by what is done, not by the result. |",
                         "| Where each item went | Gap | The calendar answered 40 of 52 events \\| the rest were cut off. |"]
    assert "Every source read" not in text  # a pass is counted, not listed


def test_a_check_that_failed_first_and_passes_now_is_shown_as_fixed_with_what_it_found() -> None:
    text = report.render_verdict(_all(), fixed={"inputs": "Team chat: 44 read, 42 placed."})
    assert text.splitlines()[0].endswith("all 10 passed.")
    assert "| Every message placed | Fixed | Failed at first: Team chat: 44 read, 42 placed. |" in text


def test_a_report_without_a_verdict_says_why_in_the_same_place() -> None:
    assert report.PENDING.startswith("Not checked yet")
    assert report.render_unchecked("The second agent stopped.") == "Not checked: the second agent did not finish. The second agent stopped."
    assert report.check_state(report.PENDING) == "pending"
    assert report.check_state(report.render_unchecked()) == "unchecked"
    assert report.check_state(report.render_verdict(_all())) == "checked"
    assert report.check_state("# Nothing\n") is None


def test_the_check_goes_under_the_red_block_and_replaces_itself_without_touching_the_rest() -> None:
    rows = [goal_row("AAAA1111", "Plan the launch", comment="Move it to next week.")]
    body = report_body(rows, unread=["Mail: not approved yet."], closed=["[Send the invoice](goal:CCCC3333): paid."])
    first = report.set_check(body, "Checked against the sources by a second agent: all 10 passed.")
    lines = first.split("\n")
    assert lines[0] == "```unread" and lines[2] == "```" and lines[3] == ""
    assert lines[4].startswith("Checked against the sources") and lines[5] == ""
    assert first.replace("Checked against the sources by a second agent: all 10 passed.", report.PENDING) == body
    # Again with a table: the old one-line check is replaced, the rest of the document is the same lines.
    verdict = report.render_verdict(_all() | {"state": Outcome(FAIL, "A closed task is in the table.")})
    second = report.set_check(first, verdict)
    assert second.count("Checked against the sources") == 1 and "| Current state | Failed |" in second
    third = report.set_check(second, report.render_verdict(_all()))  # and back to one line: the table goes with the old check
    assert "| Current state |" not in third and third == first
    assert report.set_check(third, report.render_verdict(_all())) == third  # the same verdict twice changes nothing


def test_a_report_with_no_check_line_gets_one_at_the_very_top_or_under_the_red_block() -> None:
    plain = "## Today\n\nSomething.\n"
    assert report.set_check(plain, report.PENDING).split("\n")[:3] == [report.PENDING, "", "## Today"]
    red = "```unread\nMail: no.\n```\n\n## Today\n\nSomething.\n"
    assert report.set_check(red, report.PENDING).split("\n")[:6] == ["```unread", "Mail: no.", "```", "", report.PENDING, ""]


def test_a_check_line_inside_a_code_block_is_not_the_check() -> None:
    body = "```\nChecked against the sources by a second agent: all 10 passed.\n```\n\n## Today\n"
    assert report.check_state(body) is None
    assert report.set_check(body, report.PENDING).startswith(report.PENDING)


def test_a_worse_outcome_wins_and_a_tie_keeps_the_first() -> None:
    asked, floor = Outcome(PASS), Outcome(FAIL, "no")
    assert report.worse(asked, floor) is floor
    assert report.worse(Outcome(FAIL, "a"), Outcome(FAIL, "b")).note == "a"
    assert report.worse(Outcome(GAP, "g"), Outcome(PASS)).result == GAP  # a gap is never a pass


# --- the rows and the owner's cells ----------------------------------------------------------------------------------


def test_a_row_knows_its_task_whether_it_is_a_parent_a_child_and_what_the_owner_wrote() -> None:
    body = report_body([
        goal_row("AAAA1111", "Plan the launch", bold=True, comment='Move it | next week, "please" — and tell Sam.'),
        goal_row("BBBB2222", "Write the notes", child=True),
        goal_row("CCCC3333", "Book the room", comment="[]"),
    ])
    parent, child, other = report.task_rows(body)
    assert (parent.goal, parent.title, parent.bold, parent.child) == ("AAAA1111", "Plan the launch", True, False)
    assert (child.goal, child.title, child.bold, child.child) == ("BBBB2222", "Write the notes", False, True)
    assert parent.comment == 'Move it | next week, "please" — and tell Sam.'  # the words, the bar and the dash as typed
    assert child.comment == "" and other.comment == ""  # an empty cell and the placeholder are both nothing
    assert parent.next_col == 3 and parent.comment_col == 4


def test_a_report_of_the_old_shape_still_gives_its_rows_and_comments() -> None:
    body = ("## Today\n\n| Task / owning session | Summary / purpose | Latest updates / next action | Reader comments and decisions |\n"
            "| --- | --- | --- | --- |\n| [Prepare the strategy](goal:AAAA1111) | Make it usable. | Sent. | Start with the smaller package. |\n")
    (row,) = report.task_rows(body)
    # Its third column is "Latest updates / next action", so the receipt of a landed comment goes there.
    assert (row.goal, row.comment, row.next_col, row.comment_col) == ("AAAA1111", "Start with the smaller package.", 2, 3)


def test_tables_that_are_not_rows_are_not_rows() -> None:
    body = report_body(sources=sources_section([source_row("Mail", "2026-10-11 07:00", "2026-10-12 06:57", 1)]),
                       check=report.render_verdict(_all() | {"names": Outcome(FAIL, "x")}))
    assert report.task_rows(body) == []


def test_only_the_cells_named_are_written_again() -> None:
    rows = [goal_row("AAAA1111", "Plan the launch", comment="Do it."), goal_row("BBBB2222", "Write the notes", comment="")]
    body = report_body(rows)
    (first, _second) = report.task_rows(body)
    new = report.rewrite_rows(body, {first.line: {first.comment_col: "", first.next_col: "Finish it. Your comment is on the task."}})
    after = report.task_rows(new)
    assert after[0].comment == "" and report.unescape(after[0].cells[3]) == "Finish it. Your comment is on the task."
    old_lines, new_lines = body.split("\n"), new.split("\n")
    assert len(old_lines) == len(new_lines)
    assert [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b] == [first.line]  # one line changed, no other


def test_what_was_closed_is_the_goals_the_section_links() -> None:
    body = report_body(closed=["[Send the invoice](goal:CCCC3333): paid on Sunday.", "[Book the room](goal:DDDD4444): done."])
    assert report.closed_goals(body) == ["CCCC3333", "DDDD4444"]
    assert report.closed_goals(report_body()) == []


def test_a_report_path_names_its_day() -> None:
    assert report.day_of("reports/morning/2026-10-12.md") == date(2026, 10, 12)
    assert report.path_for(date(2026, 10, 12)) == "reports/morning/2026-10-12.md"
    for other in ("reports/morning/notes.md", "reports/morning/2026-13-40.md", "reports/evening/2026-10-12.md", ""):
        assert report.day_of(other) is None
