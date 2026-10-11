"""Repeatable goals through real core calls and real Postgres; no mocks or in-memory doubles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg
import pytest

from verticals.core import goals
from verticals.core.errors import ValidationError

OWNER = "repeat-core"


def _scheduled(conn: psycopg.Connection, title: str = "Recurring task"):
    return goals.create(
        conn, owner=OWNER, title=title, body="Shared notes", tags=["repeat"],
        vertical="day", anchor_date=date(2026, 8, 10),
    ).goal


def test_repeat_completion_materializes_one_normal_history_row(db: psycopg.Connection) -> None:
    first = _scheduled(db)
    configured = goals.update(
        db, owner=OWNER, id=first.id, repeat={"frequency": "daily", "interval": 1}
    ).goal
    assert configured.repeat_series_id == first.id
    assert configured.repeat_index == 0

    goals.update(db, owner=OWNER, id=first.id, done=True)
    rows = db.execute(
        "SELECT id, done_at, anchor_date, repeat_index, title, body, tags"
        " FROM goals WHERE owner = %s AND repeat_series_id = %s ORDER BY repeat_index",
        (OWNER, first.id),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] is not None and rows[1][1] is None
    assert rows[1][2:4] == (date(2026, 8, 11), 1)
    assert rows[1][4:] == ("Recurring task", "Shared notes", ["repeat"])


def test_repeat_completion_replay_is_idempotent(db: psycopg.Connection) -> None:
    first = _scheduled(db)
    goals.update(db, owner=OWNER, id=first.id, repeat={"frequency": "weekly", "weekdays": [1, 3]})
    goals.update(db, owner=OWNER, id=first.id, done=True)
    goals.update(db, owner=OWNER, id=first.id, done=True)
    (count,) = db.execute(
        "SELECT count(*) FROM goals WHERE owner = %s AND repeat_series_id = %s",
        (OWNER, first.id),
    ).fetchone()
    assert count == 2


def test_a_completion_hands_back_the_occurrence_it_made_and_a_replay_does_not(db: psycopg.Connection) -> None:
    """The page takes the occurrence back with the tick that made it (docs/design/board-undo.md), so the call says which one
    it made; one that was already there is not the call's own."""
    first = _scheduled(db)
    goals.update(db, owner=OWNER, id=first.id, repeat={"frequency": "daily"})

    ticked = goals.update(db, owner=OWNER, id=first.id, done=True)
    assert ticked.spawned is not None
    assert (ticked.spawned.repeat_index, ticked.spawned.anchor_date) == (1, date(2026, 8, 11))
    assert ticked.spawned.done_at is None and ticked.spawned.title == "Recurring task"

    assert goals.update(db, owner=OWNER, id=first.id, done=True).spawned is None, "a replay finds it there"
    assert goals.update(db, owner=OWNER, id=first.id, done=False).spawned is None, "reopening makes nothing"
    assert goals.update(db, owner=OWNER, id=first.id, title="Retitled").spawned is None

    # Taken back: the occurrence goes, and the tick played again makes it again, under another id.
    goals.delete(db, owner=OWNER, id=ticked.spawned.id)
    goals.update(db, owner=OWNER, id=first.id, done=False)
    again = goals.update(db, owner=OWNER, id=first.id, done=True)
    assert again.spawned is not None and again.spawned.id != ticked.spawned.id
    assert again.spawned.repeat_index == 1


def test_a_goal_that_does_not_repeat_hands_back_nothing(db: psycopg.Connection) -> None:
    plain = _scheduled(db, "Plain")
    assert goals.update(db, owner=OWNER, id=plain.id, done=True).spawned is None


def test_repeat_concurrent_completion_has_one_next_occurrence(db_dsn: str) -> None:
    with psycopg.connect(db_dsn, autocommit=True) as conn:
        first = _scheduled(conn)
        goals.update(conn, owner=OWNER, id=first.id, repeat={"frequency": "daily"})

    def complete() -> None:
        with psycopg.connect(db_dsn, autocommit=True) as conn:
            goals.update(conn, owner=OWNER, id=first.id, done=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: complete(), range(2)))
    with psycopg.connect(db_dsn, autocommit=True) as conn:
        indexes = conn.execute(
            "SELECT repeat_index FROM goals WHERE owner = %s AND repeat_series_id = %s"
            " ORDER BY repeat_index",
            (OWNER, first.id),
        ).fetchall()
    assert indexes == [(0,), (1,)]


def test_repeat_end_date_stops_materialization(db: psycopg.Connection) -> None:
    first = _scheduled(db)
    goals.update(
        db, owner=OWNER, id=first.id,
        repeat={"frequency": "daily", "end_date": date(2026, 8, 10)},
    )
    goals.update(db, owner=OWNER, id=first.id, done=True)
    (count,) = db.execute(
        "SELECT count(*) FROM goals WHERE owner = %s AND repeat_series_id = %s",
        (OWNER, first.id),
    ).fetchone()
    assert count == 1


@pytest.mark.parametrize(
    ("rule", "field"),
    [
        ({"frequency": "daily", "interval": 2}, "repeat.interval"),
        ({"frequency": "weekly", "interval": 2, "weekdays": [1]}, "repeat.weekdays"),
        ({"frequency": "monthly", "month_days": []}, "repeat.month_days"),
        ({"frequency": "yearly", "months": [1], "quarters": [1]}, "repeat.weekdays,repeat.month_days,repeat.months,repeat.quarters"),
        ({"frequency": "daily", "count": 4}, "repeat.count"),
    ],
)
def test_repeat_invalid_rule_is_refused_without_storage(
    db: psycopg.Connection, rule: dict, field: str
) -> None:
    first = _scheduled(db, title=str(rule))
    with pytest.raises(ValidationError) as exc:
        goals.update(db, owner=OWNER, id=first.id, repeat=rule)
    assert exc.value.detail["field"] == field
    assert goals.goal(db, owner=OWNER, id=first.id).goal.repeat_rule is None


def test_repeat_refuses_unscheduled_and_parent_goals(db: psycopg.Connection) -> None:
    unscheduled = goals.create(db, owner=OWNER, title="Unscheduled").goal
    with pytest.raises(ValidationError) as exc:
        goals.update(db, owner=OWNER, id=unscheduled.id, repeat={"frequency": "daily"})
    assert exc.value.detail["field"] == "repeat"

    parent = _scheduled(db, "Parent")
    goals.create(db, owner=OWNER, parent_id=parent.id, title="Child")
    with pytest.raises(ValidationError, match="subgoals"):
        goals.update(db, owner=OWNER, id=parent.id, repeat={"frequency": "daily"})
