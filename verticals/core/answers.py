"""What one write changed on the board, before and after (docs/design/agent-answer-undo.md).

An agent's answer is a run of writes, and the page takes the whole run back as one step. It can do that only if the server says
exactly what each write did: a diff of the board between two moments is wrong whenever the person's own changes land in the
same moments. So the write itself is bracketed: the goals it can touch are read and locked just before it, the write runs,
and the same goals are read again just after, together with the goals the write made (`core/changes.py` hears of those at
`tree.attach`, the one place a goal is inserted). What differs is the change.

The goals a write can touch are known from what it was asked to do: the goals it names, and under a move or a delete their
subtree (a move carries the subgoals that stand in the card, a delete takes all of them). Nothing else a write does is
visible on the board: a reparent rewrites the paths of the subtree, which the board never shows, and a tick makes at most the
next occurrence, which `tree.attach` reports. Locked with `FOR UPDATE`, in id order, in the call's own transaction: a person's
write to one of these goals waits for this one, so what is read before is exactly what the write found, and what is read after
is exactly what it left.

`core/` never imports a transport: the caller (`mcp/`) decides which writes are watched, and keeps what comes back.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg

from verticals.core import changes, tree
from verticals.models import Goal


@dataclass(frozen=True)
class Change:
    """One goal as a write found it and left it. `before` is `None` for a goal the write made, `after` for one it removed."""

    id: str
    before: Goal | None
    after: Goal | None


@dataclass
class Watch:
    """What `watch` found out, filled in when the block ends without an error."""

    changes: list[Change] = field(default_factory=list)


def with_subtrees(conn: psycopg.Connection, *, owner: str, ids: Sequence[str]) -> list[str]:
    """`ids` and every goal under them, parents first. `starts_with`, not `LIKE`: a path is only ever a run of ids, and this
    needs no escaping."""
    rows = conn.execute(
        "SELECT d.id FROM goals g JOIN goals d ON d.owner = g.owner AND starts_with(d.path, g.path)"
        " WHERE g.owner = %(owner)s AND g.id = ANY(%(ids)s) ORDER BY d.depth, d.path",
        {"owner": owner, "ids": list(ids)},
    ).fetchall()
    return [row[0] for row in rows]


def snapshot(conn: psycopg.Connection, *, owner: str, ids: Sequence[str], lock: bool = False) -> dict[str, Goal]:
    """The goals of `ids` that exist, by id. `lock` holds them `FOR UPDATE` until the transaction ends, in id order."""
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT {tree.COLUMNS} FROM goals WHERE owner = %(owner)s AND id = ANY(%(ids)s) ORDER BY id"
        + (" FOR UPDATE" if lock else ""),
        {"owner": owner, "ids": list(ids)},
    ).fetchall()
    goals = [tree._to_goal(row) for row in rows]
    return {goal.id: goal for goal in goals}


@contextmanager
def watch(
    conn: psycopg.Connection, *, owner: str, ids: Sequence[str], subtree: bool = False
) -> Iterator[Watch]:
    """Brackets one write. `ids` are the goals it names; `subtree` adds everything under them. Inside the block, run the
    write. After it, `Watch.changes` lists, goals the write named first and goals it made after them, every one that is not
    as it was. A write that raises changes nothing here: the error goes on up, and nothing is listed."""
    named = list(dict.fromkeys(i for i in ids if isinstance(i, str)))
    seen = with_subtrees(conn, owner=owner, ids=named) if subtree and named else named
    out = Watch()
    with changes.collect() as made:
        before = snapshot(conn, owner=owner, ids=seen, lock=True)
        yield out
        order = list(dict.fromkeys([*seen, *made]))
        after = snapshot(conn, owner=owner, ids=order)
    out.changes = [Change(goal_id, before.get(goal_id), after.get(goal_id)) for goal_id in order if before.get(goal_id) != after.get(goal_id)]
