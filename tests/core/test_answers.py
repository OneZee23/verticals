"""`verticals/core/answers.py` (docs/design/agent-answer-undo.md): one write, bracketed, says exactly what it changed. Real
Postgres, the real F2 fixture, no mocks. The write is the core's own call, so what is asserted is what the page will be told:
the goals the write named, the subgoals a move or a delete carries, and the goals the write made, each as it was and as it was left."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest

from verticals.core import answers, changes, goals, moves
from verticals.core.errors import NotFound

OWNER = "t1"
F2_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "f2_synth.sql"


@pytest.fixture
def f2(db: psycopg.Connection) -> Iterator[psycopg.Connection]:
    db.execute(F2_SQL.read_text())
    db.execute("ANALYZE goals")
    yield db


def _by_id(found: answers.Watch) -> dict[str, answers.Change]:
    return {change.id: change for change in found.changes}


def test_a_tick_is_one_change_with_the_goal_as_it_was_and_as_it_was_left(f2: psycopg.Connection) -> None:
    with answers.watch(f2, owner=OWNER, ids=["SYNCOL01"]) as found:
        goals.update(f2, owner=OWNER, id="SYNCOL01", done=True)

    (change,) = found.changes
    assert change.id == "SYNCOL01"
    assert change.before is not None and change.before.done_at is None
    assert change.after is not None and change.after.done_at is not None
    assert change.after.updated_at > change.before.updated_at


def test_a_write_that_changes_nothing_lists_nothing(f2: psycopg.Connection) -> None:
    with answers.watch(f2, owner=OWNER, ids=["SYNCOL01", "SYNCOL02"]) as found:
        pass

    assert found.changes == []


def test_only_the_goals_named_are_read_so_a_stranger_changing_another_is_not_blamed(f2: psycopg.Connection) -> None:
    with answers.watch(f2, owner=OWNER, ids=["SYNCOL01"]) as found:
        goals.update(f2, owner=OWNER, id="SYNCOL01", title="Retitled by the write")
        goals.update(f2, owner=OWNER, id="SYNCOL02", title="Somebody else's")  # not named, so not this write's

    assert [change.id for change in found.changes] == ["SYNCOL01"]


def test_a_tick_of_a_repeating_goal_lists_the_occurrence_it_made_as_made(f2: psycopg.Connection) -> None:
    goals.update(f2, owner=OWNER, id="SYNCOL04", repeat={"frequency": "daily", "interval": 1})

    with answers.watch(f2, owner=OWNER, ids=["SYNCOL04"]) as found:
        ticked = goals.update(f2, owner=OWNER, id="SYNCOL04", done=True)

    assert ticked.spawned is not None
    changed = _by_id(found)
    assert set(changed) == {"SYNCOL04", ticked.spawned.id}
    assert changed[ticked.spawned.id].before is None and changed[ticked.spawned.id].after is not None
    assert changed["SYNCOL04"].before is not None and changed["SYNCOL04"].after is not None


def test_a_created_plan_lists_every_node_as_made_in_the_order_it_was_made(f2: psycopg.Connection) -> None:
    with answers.watch(f2, owner=OWNER, ids=[]) as found:
        created = goals.create(
            f2, owner=OWNER, title="A plan", vertical="week", anchor_date=date(2026, 8, 12),
            children=[{"title": "First", "children": [{"title": "Deeper"}]}, {"title": "Second"}],
        )

    ids = [change.id for change in found.changes]
    assert ids[0] == created.goal.id and set(ids) == {created.goal.id, *(child.id for child in created.children)}
    assert len(ids) == 4
    assert all(change.before is None and change.after is not None for change in found.changes)


def test_a_move_with_its_subtree_lists_the_subgoals_that_travel_and_leaves_the_others(f2: psycopg.Connection) -> None:
    anchor = date(2026, 8, 12)
    parent = goals.create(f2, owner=OWNER, title="parent", vertical="week", anchor_date=anchor).goal
    nested = goals.create(f2, owner=OWNER, title="nested", parent_id=parent.id, vertical="week", anchor_date=anchor).goal
    elsewhere = goals.create(f2, owner=OWNER, title="elsewhere", parent_id=parent.id, vertical="week", anchor_date=date(2026, 8, 19)).goal

    with answers.watch(f2, owner=OWNER, ids=[parent.id], subtree=True) as found:
        moves.schedule(f2, owner=OWNER, id=parent.id, vertical="month", anchor_date=anchor)

    changed = _by_id(found)
    assert set(changed) == {parent.id, nested.id}, "the nested subgoal travelled; the one in another week did not"
    assert changed[parent.id].before.vertical == "week" and changed[parent.id].after.vertical == "month"
    assert changed[nested.id].after.period_key == "2026-08"
    assert elsewhere.id not in changed


def test_a_delete_lists_the_goal_and_everything_under_it_as_removed(f2: psycopg.Connection) -> None:
    with answers.watch(f2, owner=OWNER, ids=["SYNDAY01"], subtree=True) as found:
        goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=True)

    assert {change.id for change in found.changes} == {"SYNDAY01", "SYNSUB01", "SYNSUB02", "SYNSUB03"}
    assert all(change.before is not None and change.after is None for change in found.changes)


def test_a_write_that_raises_lists_nothing_and_stops_listening(f2: psycopg.Connection) -> None:
    with pytest.raises(NotFound):
        with answers.watch(f2, owner=OWNER, ids=["SYNCOL01"], subtree=True) as found:
            goals.update(f2, owner=OWNER, id="NOSUCHID", done=True)
    assert found.changes == []

    # The window closed with the error: a goal made afterwards is nobody's to hear of.
    with changes.collect() as heard:
        pass
    goals.create(f2, owner=OWNER, title="after the error")
    assert heard == []


def test_goals_made_are_heard_only_inside_a_window_and_only_by_that_window(f2: psycopg.Connection) -> None:
    changes.note_made("OUTSIDE1")  # nobody is listening: nothing happens, nothing breaks
    with changes.collect() as outer:
        outer_made = goals.create(f2, owner=OWNER, title="made inside").goal
        with changes.collect() as inner:
            inner_made = goals.create(f2, owner=OWNER, title="made in the inner window").goal
        after_inner = goals.create(f2, owner=OWNER, title="made after the inner window").goal

    assert inner == [inner_made.id]
    assert outer == [outer_made.id, after_inner.id], "the inner window took its own goal and handed the sink back"


def test_a_goal_that_belongs_to_another_owner_is_not_read(f2: psycopg.Connection) -> None:
    other = goals.create(f2, owner="t2", title="not yours").goal
    assert answers.snapshot(f2, owner=OWNER, ids=[other.id]) == {}
    assert answers.with_subtrees(f2, owner=OWNER, ids=[other.id]) == []
