"""The morning report's day and its task (docs/design/agent-fixes.md, fixes 3 and 2).

The report itself is the agent's: the app asks for it once its morning hour has come (web `lib/morning.ts`) and the agent
writes it as a document (desktop/chat/prompt-morning.md). The server decides two things around it.

Whether this morning's ask is still to be made, once a day for each owner. The app used to keep that in a flag of its own
in each browser, so a second window, a restart on another browser or a cleared cache asked a second time and a second
report followed. The day is an idempotent action like any write with a `client_token` (`core/idem.py`): the token names
the day, the first call reserves it and every later one finds it taken. A reservation lives 24 hours, longer than the
day it names.

Which task the report hangs on. There is one open task titled "Morning report"; each morning it is moved to that day,
and a new one is made only when none is open. Each morning's report is still a new document, linked to that task by the
agent; earlier reports stay as they are. Before this the agent made a task a morning and the open ones piled up.

IR-02: takes an open connection, never commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime as _datetime

import psycopg

from verticals.core import goals, idem, moves, vertical
from verticals.core.errors import ValidationError

# The task's title, as the web names it (`MORNING_TITLE` in lib/morning.ts); "its" task is found by it.
TITLE = "Morning report"


@dataclass(frozen=True)
class Begun:
    asked: bool  # True for the one call that took the day; False for every later one
    task_id: str | None  # the open task, in `day`, when asked; None otherwise


def _task_for(conn: psycopg.Connection, *, owner: str, day: _date) -> str:
    """The one open task of the report, in `day`: the open one already there, else the newest open one moved there, else
    a new one. Several open ones (the agent made a new one each morning) are the owner's to close: one is used, none is
    added and the rest are left as they are. A finished task is never reopened."""
    found = conn.execute(
        "SELECT id, coalesce(vertical = %(scale)s::vertical_scale AND anchor_date = %(day)s, false) AS placed FROM goals"
        " WHERE owner = %(owner)s AND title = %(title)s AND done_at IS NULL"
        " ORDER BY placed DESC, created_at DESC, id DESC LIMIT 1",
        {"owner": owner, "title": TITLE, "scale": vertical.DAY, "day": day},
    ).fetchone()
    if found is None:
        return goals.create(
            conn, owner=owner, title=TITLE, vertical=vertical.DAY, anchor_date=day, origin="app"
        ).goal.id
    task_id, placed = found
    if not placed:
        moves.schedule(conn, owner=owner, id=task_id, vertical=vertical.DAY, anchor_date=day)
    return task_id


def take(conn: psycopg.Connection, *, owner: str, day: _date) -> bool:
    """Take `day` for `owner`: True for the one call that gets it, False for every other, from any window or after any
    restart. `idem.reserve` is one INSERT that two calls at the same moment cannot both win: the second waits for the
    first's commit and finds the reservation there."""
    if not isinstance(owner, str) or not owner:
        raise ValidationError("owner must be a non-empty string", field="owner")
    if not isinstance(day, _date) or isinstance(day, _datetime):
        raise ValidationError("day must be a date", field="day")
    token = f"morning:{day.isoformat()}"
    with conn.transaction():
        reserved = idem.reserve(conn, owner=owner, client_token=token, request_digest=idem.digest({"morning": day.isoformat()}))
        if isinstance(reserved, idem.Replayed):
            return False
        idem.complete(conn, owner=owner, client_token=token, response={"asked": True})
    return True


def begin(conn: psycopg.Connection, *, owner: str, day: _date) -> Begun:
    """The first call of a day returns `asked=True` with the report's task, made or moved to `day`, and the app asks the
    agent; every other call returns `asked=False` and touches nothing. One transaction: a day is never taken without its
    task being there."""
    with conn.transaction():
        if not take(conn, owner=owner, day=day):
            return Begun(asked=False, task_id=None)
        return Begun(asked=True, task_id=_task_for(conn, owner=owner, day=day))
