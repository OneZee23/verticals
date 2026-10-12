"""Which goals a call made, told to whoever is watching (docs/design/agent-answer-undo.md).

The page takes an agent's answer back as one step, so the server has to know exactly what each write of the answer did, and
a goal the write made is the one thing it cannot read off a snapshot taken before: the goal was not there. `tree.attach` is
the only place a goal is inserted by a write (a created plan, every node of it, and the occurrence a tick of a repeating goal
makes), and it says so here. Nothing is listening unless a caller asked (`collect`), so every other write pays one lookup of an
empty variable.

A context variable, not a global: a call runs in its own worker thread, and a second call that runs at the same moment must
not be told about the first one's goals. `core/` never imports a transport, so the one that wants to know (`mcp/`) opens the
window and the core only reports into it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_made: ContextVar[list[str] | None] = ContextVar("verticals_goals_made", default=None)


def note_made(goal_id: str) -> None:
    """A write has just inserted this goal. Heard only inside `collect`."""
    sink = _made.get()
    if sink is not None:
        sink.append(goal_id)


@contextmanager
def collect() -> Iterator[list[str]]:
    """The ids of the goals inserted while the block runs, in the order they were made."""
    sink: list[str] = []
    token = _made.set(sink)
    try:
        yield sink
    finally:
        _made.reset(token)
