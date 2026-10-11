"""The morning report's day (docs/design/agent-fixes.md, fix 3): the server decides whether this morning's report is
still to be asked for, one ask a day per owner, so no window, restart or cleared browser asks twice."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg
import pytest

from verticals.core import morning
from verticals.core.errors import ValidationError

OWNER = "SYN-morning-owner"
DAY = date(2026, 10, 11)


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
