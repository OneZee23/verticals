"""A deleted goal can be brought back (`core/trash.py`, migration 019; docs/design/board-undo.md). Real Postgres 16, real
F2, no mocks. What is proved here: a delete followed by a restore leaves every table as it was, row for row; the same ids
come back with their comments, evidence, document links and due acknowledgements; a world that moved on in between is
handled (the parent gone or moved, a position taken); and the trash cannot go stale in silence (a new table with a key to
`goals` fails `test_every_table_that_follows_a_goal_is_in_the_trash`).

Run directly:
    PGHOST=127.0.0.1 PGPORT=55432 PGUSER=verticals PGPASSWORD=verticals \\
        .venv/bin/python -m pytest tests/core/test_trash.py -v
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import psycopg
import pytest

from verticals.core import goals, moves, trash
from verticals.core.errors import HasChildren, NotFound, ValidationError

OWNER = "t1"
F2_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "f2_synth.sql"


@pytest.fixture
def f2(db: psycopg.Connection) -> Iterator[psycopg.Connection]:
    db.execute(F2_SQL.read_text())
    db.execute("ANALYZE goals")
    yield db


def _digest(conn: psycopg.Connection, table: str) -> str | None:
    """One value for every row of `table`: equal digests are equal tables, row for row."""
    (value,) = conn.execute(f"SELECT md5(string_agg(t::text, '|' ORDER BY t::text)) FROM {table} t").fetchone()
    return value


def _digests(conn: psycopg.Connection) -> dict[str, str | None]:
    return {table: _digest(conn, table) for table in ("goals", *trash.CASCADED)}


def _dress(conn: psycopg.Connection) -> None:
    """Give SYNDAY01 and its steps everything that cascades away with a goal: evidence, a due acknowledgement, a
    document link on each side, a comment thread with two messages, on the parent and on a step."""
    conn.execute(
        "INSERT INTO goal_evidence (goal_id, owner, status, verified_against_revision, payload)"
        " VALUES ('SYNDAY01', 't1', 'unverified', 0, '{\"sources\": []}')"
    )
    conn.execute(
        "INSERT INTO due_acknowledgements (goal_id, owner, vertical, period_key, verdict, note)"
        " VALUES ('SYNDAY01', 't1', 'day', '2026-08-07', 'overdue', 'slipped')"
    )
    conn.execute(
        "INSERT INTO docs (id, owner, path, title, body) VALUES ('SYNDOC01', 't1', 'notes/outline.md', 'Outline', 'x')"
    )
    conn.execute(
        "INSERT INTO goal_doc_links (owner, goal_id, doc_id, source) VALUES"
        " ('t1', 'SYNDAY01', 'SYNDOC01', 'goal'), ('t1', 'SYNSUB02', 'SYNDOC01', 'doc')"
    )
    conn.execute("INSERT INTO comment_threads (id, owner, goal_id) VALUES ('SYNTHR01', 't1', 'SYNSUB01')")
    conn.execute(
        "INSERT INTO comment_messages (thread_id, id, owner, author, body) VALUES"
        " ('SYNTHR01', 'SYNMSG01', 't1', 'human', 'first'), ('SYNTHR01', 'SYNMSG02', 't1', 'agent', 'second')"
    )


def _trash_rows(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM goal_trash").fetchone()[0]


# --- the round trip ------------------------------------------------------------------------------------------------


def test_delete_then_restore_leaves_every_table_as_it_was(f2: psycopg.Connection) -> None:
    _dress(f2)
    before = _digests(f2)
    assert goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=True) == 4
    gone = _digests(f2)
    assert gone["goals"] != before["goals"], "the delete must have removed rows"
    assert f2.execute("SELECT count(*) FROM comment_messages").fetchone()[0] == 0, "the cascade took them"

    restored = trash.restore(f2, owner=OWNER, id="SYNDAY01")

    assert restored.restored == 4
    assert restored.goal.id == "SYNDAY01" and restored.goal.title == "Draft the outline"
    assert _digests(f2) == before, "every goal and every dependent row must be exactly as it was"
    assert _trash_rows(f2) == 0, "a restored entry is spent"


def test_the_same_ids_come_back_with_their_subgoals_and_dependants(f2: psycopg.Connection) -> None:
    _dress(f2)
    goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=True)
    trash.restore(f2, owner=OWNER, id="SYNDAY01")

    steps = f2.execute("SELECT id, parent_id, depth FROM goals WHERE parent_id = 'SYNDAY01' ORDER BY id").fetchall()
    assert steps == [("SYNSUB01", "SYNDAY01", 6), ("SYNSUB02", "SYNDAY01", 6), ("SYNSUB03", "SYNDAY01", 6)]
    assert f2.execute("SELECT count(*) FROM comment_messages WHERE thread_id = 'SYNTHR01'").fetchone()[0] == 2
    assert f2.execute("SELECT count(*) FROM goal_doc_links").fetchone()[0] == 2
    assert f2.execute("SELECT count(*) FROM goal_evidence WHERE goal_id = 'SYNDAY01'").fetchone()[0] == 1
    assert f2.execute("SELECT count(*) FROM due_acknowledgements WHERE goal_id = 'SYNDAY01'").fetchone()[0] == 1


def test_a_leaf_comes_back_too(f2: psycopg.Connection) -> None:
    before = _digests(f2)
    assert goals.delete(f2, owner=OWNER, id="SYNORD03") == 1
    assert trash.restore(f2, owner=OWNER, id="SYNORD03").restored == 1
    assert _digests(f2) == before


def test_a_refused_delete_leaves_nothing_in_the_trash(f2: psycopg.Connection) -> None:
    with pytest.raises(HasChildren):
        goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=False)
    assert _trash_rows(f2) == 0


# --- nothing to restore --------------------------------------------------------------------------------------------


def test_restoring_what_was_never_deleted_is_not_found(f2: psycopg.Connection) -> None:
    with pytest.raises(NotFound):
        trash.restore(f2, owner=OWNER, id="SYNORD01")
    with pytest.raises(NotFound):
        trash.restore(f2, owner=OWNER, id="NOSUCHID")


def test_restoring_twice_is_not_found_the_second_time(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNORD02")
    trash.restore(f2, owner=OWNER, id="SYNORD02")
    with pytest.raises(NotFound):
        trash.restore(f2, owner=OWNER, id="SYNORD02")


def test_another_owner_cannot_restore_it(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNORD02")
    with pytest.raises(NotFound):
        trash.restore(f2, owner="t2", id="SYNORD02")
    assert f2.execute("SELECT count(*) FROM goals WHERE id = 'SYNORD02'").fetchone()[0] == 0


def test_a_goal_that_is_back_already_is_refused(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNORD02")
    f2.execute(
        "INSERT INTO goals (id, owner, path, title, vertical, anchor_date, period_key, position)"
        " VALUES ('SYNORD02', 't1', '/SYNORD02/', 'Again', 'week', '2026-08-05', '2026-W32', 9216)"
    )
    with pytest.raises(ValidationError) as refused:
        trash.restore(f2, owner=OWNER, id="SYNORD02")
    assert refused.value.detail["field"] == "id"
    assert _trash_rows(f2) == 1, "a refusal must not spend the entry"


# --- a world that moved on -----------------------------------------------------------------------------------------


def test_a_parent_that_is_gone_leaves_the_goal_at_the_top_level(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=True)
    goals.delete(f2, owner=OWNER, id="SYNQ2R01")  # SYNDAY01's parent: a leaf now

    trash.restore(f2, owner=OWNER, id="SYNDAY01")

    root = f2.execute("SELECT parent_id, path, depth FROM goals WHERE id = 'SYNDAY01'").fetchone()
    assert root == (None, "/SYNDAY01/", 0)
    step = f2.execute("SELECT path, depth FROM goals WHERE id = 'SYNSUB01'").fetchone()
    assert step == ("/SYNDAY01/SYNSUB01/", 1), "the steps' paths are rebuilt under the new top"


def test_a_parent_that_moved_gives_the_goal_its_path_as_it_is_now(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNSUB01")
    moves.reparent(f2, owner=OWNER, id="SYNDAY01", parent_id="SYNQ1R01")  # up one level in the ladder

    trash.restore(f2, owner=OWNER, id="SYNSUB01")

    parent_path, parent_depth = f2.execute("SELECT path, depth FROM goals WHERE id = 'SYNDAY01'").fetchone()
    path, depth = f2.execute("SELECT path, depth FROM goals WHERE id = 'SYNSUB01'").fetchone()
    assert path == f"{parent_path}SYNSUB01/" and depth == parent_depth + 1
    assert f2.execute("SELECT parent_id FROM goals WHERE id = 'SYNSUB01'").fetchone()[0] == "SYNDAY01"


def test_a_parent_that_no_longer_takes_a_goal_of_that_scale_leaves_it_at_the_top_level(
    f2: psycopg.Connection,
) -> None:
    """A goal may not be placed above its parent (`core/placement.py`). The parent went down to a day while the week task
    was in the trash: the task comes back without it, rather than as a child that breaks the rule."""
    parent = goals.create(f2, owner=OWNER, title="A month", vertical="month", anchor_date=date(2026, 8, 8)).goal
    child = goals.create(
        f2, owner=OWNER, title="A week task", parent_id=parent.id, vertical="week", anchor_date=date(2026, 8, 5)
    ).goal
    goals.delete(f2, owner=OWNER, id=child.id)
    moves.schedule(f2, owner=OWNER, id=parent.id, vertical="day", anchor_date=date(2026, 8, 8))

    trash.restore(f2, owner=OWNER, id=child.id)

    assert f2.execute("SELECT parent_id, path, depth FROM goals WHERE id = %s", (child.id,)).fetchone() == (
        None, f"/{child.id}/", 0,
    )


def test_a_position_taken_since_is_not_shared(f2: psycopg.Connection) -> None:
    """The last card of a column is deleted and a new card is added: the new one takes the same position
    (`max + 1024`). The restored card goes before it, so no two cards in a column share a position."""
    last = f2.execute(
        "SELECT id, position FROM goals WHERE vertical = 'week' AND period_key = '2026-W32' ORDER BY position DESC LIMIT 1"
    ).fetchone()
    goals.delete(f2, owner=OWNER, id=last[0])
    newer = goals.create(f2, owner=OWNER, title="Added later", vertical="week", anchor_date=date(2026, 8, 5)).goal
    assert newer.position == last[1], "the case under test: the new card took the freed position"

    trash.restore(f2, owner=OWNER, id=last[0])

    order = [
        r[0]
        for r in f2.execute(
            "SELECT id FROM goals WHERE vertical = 'week' AND period_key = '2026-W32' ORDER BY position, id"
        ).fetchall()
    ]
    assert order[-2:] == [last[0], newer.id]
    positions = [r[0] for r in f2.execute(
        "SELECT position FROM goals WHERE vertical = 'week' AND period_key = '2026-W32'").fetchall()]
    assert len(positions) == len(set(positions))


def test_a_document_deleted_since_is_not_brought_back_by_its_link(f2: psycopg.Connection) -> None:
    _dress(f2)
    goals.delete(f2, owner=OWNER, id="SYNDAY01", cascade=True)
    f2.execute("DELETE FROM docs WHERE id = 'SYNDOC01'")  # free now: no link holds it

    trash.restore(f2, owner=OWNER, id="SYNDAY01")

    assert f2.execute("SELECT count(*) FROM goal_doc_links").fetchone()[0] == 0
    assert f2.execute("SELECT count(*) FROM goals WHERE id LIKE 'SYNSUB0%'").fetchone()[0] == 3


# --- what is kept, and for how long -------------------------------------------------------------------------------


def test_the_next_delete_sweeps_old_entries_of_the_same_owner_only(f2: psycopg.Connection) -> None:
    for owner, root, age in (("t1", "OLDMINE1", trash.RETENTION_DAYS + 1), ("t1", "NEWMINE1", 1),
                             ("t2", "OLDTHEIR", trash.RETENTION_DAYS + 1)):
        f2.execute(
            "INSERT INTO goal_trash (owner, root_id, deleted_at, rows) VALUES"
            " (%s, %s, clock_timestamp() - make_interval(days => %s), '{}'::jsonb)",
            (owner, root, age),
        )
    goals.delete(f2, owner=OWNER, id="SYNORD01")
    kept = {r[0] for r in f2.execute("SELECT root_id FROM goal_trash").fetchall()}
    assert kept == {"NEWMINE1", "OLDTHEIR", "SYNORD01"}


def test_the_newest_deletion_of_an_id_is_the_one_restored(f2: psycopg.Connection) -> None:
    goals.delete(f2, owner=OWNER, id="SYNORD02")
    f2.execute(
        "INSERT INTO goal_trash (owner, root_id, deleted_at, rows)"
        " SELECT owner, root_id, deleted_at - interval '1 day', jsonb_set(rows, '{goals,0,title}', '\"Older copy\"')"
        " FROM goal_trash"
    )

    assert trash.restore(f2, owner=OWNER, id="SYNORD02").goal.title == "Order two"
    assert _trash_rows(f2) == 1, "the older entry is left alone"


# --- the guard against a table nobody told the trash about --------------------------------------------------------


def test_every_table_that_follows_a_goal_is_in_the_trash(f2: psycopg.Connection) -> None:
    """A table with a foreign key to `goals` (or to a table that has one) loses rows when a goal is deleted. If it is
    not named in `trash.CASCADED`, those rows are lost for good, with no error. This reads the catalogue, so the next
    migration that adds such a table fails here until the trash knows it."""
    reached = {"goals"}
    while True:
        found = {
            r[0]
            for r in f2.execute(
                "SELECT DISTINCT conrelid::regclass::text FROM pg_constraint"
                " WHERE contype = 'f' AND confrelid::regclass::text = ANY(%s)",
                (sorted(reached),),
            ).fetchall()
        }
        if found <= reached:
            break
        reached |= found
    assert reached - {"goals"} == set(trash.CASCADED)
