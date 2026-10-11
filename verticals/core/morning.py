"""The morning report's day (docs/design/agent-fixes.md, fix 3).

The report itself is the agent's: the app asks for it once its morning hour has come (web `lib/morning.ts`) and the agent
writes it as a document (desktop/chat/prompt-morning.md). What the server decides is whether this morning's ask is still
to be made, once a day for each owner. The app used to keep that in a flag of its own in each browser, so a second window,
a restart on another browser or a cleared cache asked a second time and a second report followed.

The day is an idempotent action like any write with a `client_token` (`core/idem.py`): the token names the day, the first
call reserves it and every later one finds it taken. A reservation lives 24 hours, longer than the day it names.

IR-02: takes an open connection, never commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime as _datetime

import psycopg

from verticals.core import idem
from verticals.core.errors import ValidationError


@dataclass(frozen=True)
class Begun:
    asked: bool  # True for the one call that took the day; False for every later one


def begin(conn: psycopg.Connection, *, owner: str, day: _date) -> Begun:
    """Take `day` for `owner`. The first call of a day returns `asked=True` and the app asks the agent; every other call,
    from any window or after any restart, returns `asked=False`. `idem.reserve` is one INSERT that two calls at the same
    moment cannot both win: the second waits for the first's commit and finds the reservation there."""
    if not isinstance(owner, str) or not owner:
        raise ValidationError("owner must be a non-empty string", field="owner")
    if not isinstance(day, _date) or isinstance(day, _datetime):
        raise ValidationError("day must be a date", field="day")
    token = f"morning:{day.isoformat()}"
    with conn.transaction():
        reserved = idem.reserve(conn, owner=owner, client_token=token, request_digest=idem.digest({"morning": day.isoformat()}))
        if isinstance(reserved, idem.Replayed):
            return Begun(asked=False)
        idem.complete(conn, owner=owner, client_token=token, response={"asked": True})
    return Begun(asked=True)
