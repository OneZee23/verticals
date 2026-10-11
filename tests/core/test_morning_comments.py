"""The owner's comments in a report land on their tasks word for word and are read back (docs/design/morning-quality.md,
`core/morning_comments.py`): the cell is cleared only once the thread holds exactly the words, and the same words are never
saved twice."""

from __future__ import annotations

from datetime import date

import psycopg

from tests.core.morning_sample import goal_row, make_report, make_task, report_body, source_doc, source_row, sources_section
from verticals.core import comments as core_comments
from verticals.core import docs as core_docs
from verticals.core import goals, morning, morning_comments
from verticals.core import morning_report as report

OWNER = "SYN-comments-owner"
SUNDAY = date(2026, 10, 11)
MONDAY = date(2026, 10, 12)

WORDS = 'Start with the smaller package — "defer the percentage" | not the tender; see §2, and 100% of it… ☂'


def _report(db: psycopg.Connection, rows: list[str], day: date = SUNDAY) -> str:
    return make_report(db, OWNER, day, report_body(rows, sources=sources_section([])))


def _threads(db: psycopg.Connection, goal: str):
    return core_comments.list_for_goal(db, owner=OWNER, goal_id=goal)


def test_a_comment_lands_on_its_task_in_the_owners_words_and_is_read_back(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment=WORDS)])
    landing = morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert [(item.goal_id, item.text) for item in landing.landed] == [(plan, WORDS)]  # the words as read back from the thread
    (thread,) = _threads(db, plan)
    assert thread.messages[0].body == WORDS and thread.messages[0].author == "agent"
    assert thread.messages[1].body == "From your comment in Morning report — 11 October 2026."  # where it came from, beside it
    assert (landing.failed, landing.cleared) == ((), True)


def test_the_cell_is_cleared_and_says_so_while_every_other_cell_stays(db: psycopg.Connection) -> None:
    plan, notes = make_task(db, OWNER, "Plan the launch"), make_task(db, OWNER, "Write the notes")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment="Go.", next_action="Review it."),
                       goal_row(notes, "Write the notes", comment="")])
    before = core_docs.get(db, owner=OWNER, id=doc)
    morning_comments.land(db, owner=OWNER, doc_id=doc)
    after = core_docs.get(db, owner=OWNER, id=doc)
    first, second = report.task_rows(after.body)
    assert first.comment == "" and report.plain(first.cells[3]) == "Review it. Your comment is on the task."
    old = report.task_rows(before.body)
    assert first.cells[:3] == old[0].cells[:3] and second.cells == old[1].cells  # nothing else in the table moved
    assert after.revision == before.revision + 1
    assert [i for i, (a, b) in enumerate(zip(before.body.split("\n"), after.body.split("\n"))) if a != b] == [first.line]


def test_landing_twice_saves_the_words_once(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment=WORDS)])
    morning_comments.land(db, owner=OWNER, doc_id=doc)
    # The cell comes back (the owner pasted the same words again, or an older copy of the report was restored).
    row = report.task_rows(core_docs.get(db, owner=OWNER, id=doc).body)[0]
    core_docs.save(db, owner=OWNER, id=doc, expected_revision=core_docs.get(db, owner=OWNER, id=doc).revision,
                   body=report.rewrite_rows(core_docs.get(db, owner=OWNER, id=doc).body, {row.line: {row.comment_col: report.escape(WORDS)}}))
    again = morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert len(_threads(db, plan)) == 1 and again.landed[0].reused and again.cleared


def test_a_comment_that_cannot_land_stays_in_its_cell_with_the_reason(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    gone = make_task(db, OWNER, "Book the room")
    goals.delete(db, owner=OWNER, id=gone)
    doc = _report(db, [goal_row(plan, "Plan the launch", comment="Yes."), goal_row(gone, "Book the room", comment="Cancel it."),
                       "| Remember the thanks | No task. | – | – | Send them. |"])
    landing = morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert [item.goal_id for item in landing.landed] == [plan]
    assert len(landing.failed) == 2 and "gone" in landing.failed[0] and "links no task" in landing.failed[1]
    left = {row.title: row.comment for row in report.task_rows(core_docs.get(db, owner=OWNER, id=doc).body)}
    assert left == {"Plan the launch": "", "Book the room": "Cancel it.", "Remember the thanks": "Send them."}


def test_a_report_the_owner_edited_meanwhile_is_read_again_and_the_cell_cleared_in_that_copy(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment="Go.")])
    seen = core_docs.get(db, owner=OWNER, id=doc)  # what the landing read
    rows = {row.line: row for row in report.task_rows(seen.body)}
    # The owner saves a line of their own before the cell is cleared.
    core_docs.save(db, owner=OWNER, id=doc, expected_revision=seen.revision, body=seen.body + "\nA line of their own.\n")
    assert morning_comments._clear(db, owner=OWNER, doc=seen, rows=rows) is True
    after = core_docs.get(db, owner=OWNER, id=doc)
    assert "A line of their own." in after.body and report.task_rows(after.body)[0].comment == ""
    assert after.revision == seen.revision + 2


def test_a_row_the_owner_changed_meanwhile_is_not_cleared_over_their_words(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment="Go.")])
    seen = core_docs.get(db, owner=OWNER, id=doc)
    rows = {row.line: row for row in report.task_rows(seen.body)}
    core_docs.save(db, owner=OWNER, id=doc, expected_revision=seen.revision,
                   body=report.rewrite_rows(seen.body, {row.line: {row.comment_col: "Go, but later."} for row in rows.values()}))
    assert morning_comments._clear(db, owner=OWNER, doc=seen, rows=rows) is False  # these words were never landed
    assert report.task_rows(core_docs.get(db, owner=OWNER, id=doc).body)[0].comment == "Go, but later."


def test_a_report_the_app_will_not_take_back_leaves_the_cell_and_the_words_are_saved_once(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    body = report_body([goal_row(plan, "Plan the launch", comment="Go.")], sources=sources_section([]))
    room = core_docs.MAX_DOC_BODY_BYTES - len(body.encode()) - 10  # ten bytes under the limit: the receipt does not fit
    doc = make_report(db, OWNER, SUNDAY, body + "x" * room)
    landing = morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert [item.text for item in landing.landed] == ["Go."] and landing.cleared is False
    assert report.task_rows(core_docs.get(db, owner=OWNER, id=doc).body)[0].comment == "Go."
    assert morning_comments.land(db, owner=OWNER, doc_id=doc).landed[0].reused  # the next morning: found there, not saved again
    assert len(_threads(db, plan)) == 1


def test_a_report_with_no_comments_is_left_alone(db: psycopg.Connection) -> None:
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch")])
    before = core_docs.get(db, owner=OWNER, id=doc)
    landing = morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert landing == morning_comments.Landing(landed=(), failed=(), cleared=False)
    assert core_docs.get(db, owner=OWNER, id=doc).revision == before.revision
    assert _threads(db, plan) == ()


def test_beginning_the_next_morning_lands_the_last_reports_comments_and_hands_them_to_the_ask(db: psycopg.Connection) -> None:
    source_doc(db, OWNER, "Team chat")
    plan = make_task(db, OWNER, "Plan the launch")
    doc = _report(db, [goal_row(plan, "Plan the launch", comment=WORDS)])
    begun = morning.begin(db, owner=OWNER, day=MONDAY)
    assert begun.asked and begun.task_id
    assert [(item.goal_id, item.title, item.text) for item in begun.landed] == [(plan, "Plan the launch", WORDS)]
    assert report.task_rows(core_docs.get(db, owner=OWNER, id=doc).body)[0].comment == ""
    assert _threads(db, plan)[0].messages[0].body == WORDS
    assert morning.begin(db, owner=OWNER, day=MONDAY).asked is False  # the day is taken once, and so is its landing


def test_a_morning_begins_even_when_the_last_report_cannot_be_read(db: psycopg.Connection) -> None:
    core_docs.create(db, owner=OWNER, path="reports/morning/2026-10-11.md", title="Morning report — 11 October 2026",
                     body="| Task | Your comment |\n| --- | --- |\n| [A](goal:NOSUCHID) | Do it. |\n\n```\nunclosed")
    begun = morning.begin(db, owner=OWNER, day=MONDAY)
    assert begun.asked and begun.task_id and begun.landed == ()


def test_the_source_document_is_not_touched_by_landing(db: psycopg.Connection) -> None:
    chat = source_doc(db, OWNER, "Team chat")
    plan = make_task(db, OWNER, "Plan the launch")
    before = core_docs.get(db, owner=OWNER, id=chat)
    doc = make_report(db, OWNER, SUNDAY, report_body([goal_row(plan, "Plan the launch", comment="Go.")], sources=sources_section(
        [source_row("Team chat", "2026-10-10 07:00", "2026-10-11 07:00", 1, ref="sources/team-chat.md")])))
    morning_comments.land(db, owner=OWNER, doc_id=doc)
    assert core_docs.get(db, owner=OWNER, id=chat).revision == before.revision
