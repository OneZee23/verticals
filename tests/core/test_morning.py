"""The morning report's day and its task (docs/design/agent-fixes.md, fixes 3 and 2): the server decides whether this
morning's report is still to be asked for, one ask a day per owner, so no window, restart or cleared browser asks twice;
and the one open "Morning report" task is reused and moved to the day instead of another being made."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg
import pytest

from verticals.core import goals, morning
from verticals.core.errors import ValidationError

OWNER = "SYN-morning-owner"
DAY = date(2026, 10, 11)


def test_taking_a_day_makes_no_task(db: psycopg.Connection) -> None:
    """`take` is the claim alone: the test suite marks a day asked with it, and no card appears on its board."""
    assert morning.take(db, owner=OWNER, day=DAY) is True
    assert morning.take(db, owner=OWNER, day=DAY) is False
    assert _open(db) == []
    assert morning.begin(db, owner=OWNER, day=DAY) == morning.Begun(asked=False, task_id=None)  # the day is gone


def test_the_first_ask_of_a_day_takes_it_and_every_later_one_is_told_it_is_taken(db: psycopg.Connection) -> None:
    assert morning.begin(db, owner=OWNER, day=DAY).asked is True
    assert morning.begin(db, owner=OWNER, day=DAY).asked is False
    assert morning.begin(db, owner=OWNER, day=DAY).asked is False


def test_each_day_and_each_owner_has_a_morning_of_its_own(db: psycopg.Connection) -> None:
    assert morning.begin(db, owner=OWNER, day=DAY).asked
    assert morning.begin(db, owner=OWNER, day=DAY + timedelta(days=1)).asked  # tomorrow's morning is a new one
    assert morning.begin(db, owner="SYN-other-owner", day=DAY).asked  # another board's morning is not this board's
    assert not morning.begin(db, owner=OWNER, day=DAY).asked


def test_a_day_taken_stays_taken_after_the_connection_that_took_it_is_gone(db_dsn: str) -> None:
    """The browser's own flag was lost with its cache; this one lives in the database."""
    with psycopg.connect(db_dsn, autocommit=True) as first:
        assert morning.begin(first, owner=OWNER, day=DAY).asked
    with psycopg.connect(db_dsn, autocommit=True) as second:
        assert not morning.begin(second, owner=OWNER, day=DAY).asked


def test_refuses_what_is_not_a_day_or_an_owner(db: psycopg.Connection) -> None:
    for day in ("2026-10-11", datetime(2026, 10, 11, 7, 0), None, 20261011):
        with pytest.raises(ValidationError):
            morning.begin(db, owner=OWNER, day=day)
    for owner in ("", None, 7):
        with pytest.raises(ValidationError):
            morning.begin(db, owner=owner, day=DAY)
    assert db.execute("SELECT count(*) FROM idempotency").fetchone()[0] == 0


def _open(db: psycopg.Connection, owner: str = OWNER) -> list[tuple]:
    """Every open task titled "Morning report" of the owner: id, scale, day, parent."""
    return db.execute(
        "SELECT id, vertical::text, anchor_date, parent_id FROM goals"
        " WHERE owner = %s AND title = 'Morning report' AND done_at IS NULL ORDER BY created_at, id", (owner,),
    ).fetchall()


def _made(db: psycopg.Connection, day: date, **fields) -> str:
    return goals.create(db, owner=OWNER, title="Morning report", vertical="day", anchor_date=day, **fields).goal.id


def test_the_first_morning_makes_the_task_in_its_day(db: psycopg.Connection) -> None:
    begun = morning.begin(db, owner=OWNER, day=DAY)
    task = goals.goal(db, owner=OWNER, id=begun.task_id).goal
    assert (task.title, task.vertical, task.anchor_date, task.parent_id, task.origin, task.done_at) == (
        "Morning report", "day", DAY, None, "app", None)
    assert _open(db) == [(task.id, "day", DAY, None)]


def test_the_next_morning_moves_the_open_task_to_its_day_instead_of_making_another(db: psycopg.Connection) -> None:
    first = morning.begin(db, owner=OWNER, day=DAY).task_id
    for later in (DAY + timedelta(days=1), DAY + timedelta(days=9)):
        assert morning.begin(db, owner=OWNER, day=later).task_id == first
        assert _open(db) == [(first, "day", later, None)]


def test_a_second_ask_of_the_same_day_moves_and_makes_nothing(db: psycopg.Connection) -> None:
    task = morning.begin(db, owner=OWNER, day=DAY).task_id
    stamp = db.execute("SELECT updated_at FROM goals WHERE id = %s", (task,)).fetchone()[0]
    assert morning.begin(db, owner=OWNER, day=DAY) == morning.Begun(asked=False, task_id=None)
    assert db.execute("SELECT updated_at FROM goals WHERE id = %s", (task,)).fetchone()[0] == stamp
    assert len(_open(db)) == 1


def test_a_task_already_in_the_day_is_left_exactly_as_it_is(db: psycopg.Connection) -> None:
    """A morning report task made before this rule, or by hand, in today already."""
    made = _made(db, DAY)
    stamp = db.execute("SELECT updated_at FROM goals WHERE id = %s", (made,)).fetchone()[0]
    assert morning.begin(db, owner=OWNER, day=DAY).task_id == made
    assert db.execute("SELECT updated_at FROM goals WHERE id = %s", (made,)).fetchone()[0] == stamp


def test_a_parked_task_or_one_under_a_goal_comes_to_the_day_and_keeps_its_place_in_the_tree(db: psycopg.Connection) -> None:
    parent = goals.create(db, owner=OWNER, title="SYN a value", vertical="life", anchor_date=DAY).goal.id
    child = _made(db, DAY - timedelta(days=3), parent_id=parent)
    assert morning.begin(db, owner=OWNER, day=DAY).task_id == child
    assert _open(db) == [(child, "day", DAY, parent)]
    parked = goals.create(db, owner="SYN-parked-owner", title="Morning report").goal.id  # no date at all
    assert morning.begin(db, owner="SYN-parked-owner", day=DAY).task_id == parked
    assert _open(db, "SYN-parked-owner") == [(parked, "day", DAY, None)]


def test_a_finished_task_is_never_reopened_the_next_morning_makes_a_new_one(db: psycopg.Connection) -> None:
    first = morning.begin(db, owner=OWNER, day=DAY).task_id
    goals.update(db, owner=OWNER, id=first, done=True)
    second = morning.begin(db, owner=OWNER, day=DAY + timedelta(days=1)).task_id
    assert second != first
    assert _open(db) == [(second, "day", DAY + timedelta(days=1), None)]
    assert goals.goal(db, owner=OWNER, id=first).goal.done_at is not None


def test_several_open_tasks_from_before_use_the_one_in_the_day_else_the_newest_and_leave_the_rest(db: psycopg.Connection) -> None:
    """The agent used to make one a morning. They are the owner's to close; the rule adds none and moves one."""
    older, newer = _made(db, DAY - timedelta(days=2)), _made(db, DAY - timedelta(days=1))
    assert morning.begin(db, owner=OWNER, day=DAY).task_id == newer
    assert sorted(_open(db)) == sorted([(older, "day", DAY - timedelta(days=2), None), (newer, "day", DAY, None)])
    # With one of them in the day already, that one is used and nothing moves.
    tomorrow = DAY + timedelta(days=1)
    settled = _made(db, tomorrow)
    assert morning.begin(db, owner=OWNER, day=tomorrow).task_id == settled
    assert (older, "day", DAY - timedelta(days=2), None) in _open(db)


def test_another_owners_task_and_a_task_by_another_name_are_not_touched(db: psycopg.Connection) -> None:
    foreign = goals.create(db, owner="SYN-other-owner", title="Morning report", vertical="day", anchor_date=DAY - timedelta(days=4)).goal.id
    notes = goals.create(db, owner=OWNER, title="Morning report notes", vertical="day", anchor_date=DAY - timedelta(days=4)).goal.id
    mine = morning.begin(db, owner=OWNER, day=DAY).task_id
    assert mine not in (foreign, notes)
    for untouched in (foreign, notes):
        assert db.execute("SELECT anchor_date FROM goals WHERE id = %s", (untouched,)).fetchone()[0] == DAY - timedelta(days=4)
