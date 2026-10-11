"""The Sources timer (docs/design/sources.md, `verticals/sources/scheduler.py`): a pass over real documents in a real
database, with the checks run for real against local fixtures and a clock the test moves by hand; and the thread that
repeats it, started, poked, kept alive when the database is gone, and stopped."""

from __future__ import annotations

import json
import secrets
import stat
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg
import pytest

from verticals.core import docs as core_docs
from verticals.core import source_checks as sc
from verticals.core import sources as core
from verticals.db.pool import open_pool
from verticals.sources import scheduler

OWNER = "SYN-timer-owner"
T0 = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)


class Clock:
    """A clock the test moves."""

    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def move(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class _Health(BaseHTTPRequestHandler):
    up = True

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200 if type(self).up else 503)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def health() -> Iterator[tuple[str, type[_Health]]]:
    handler = type("Handler", (_Health,), {"up": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/health", handler
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def pool(db_dsn: str) -> Iterator[object]:
    opened = open_pool(db_dsn, min_size=1, max_size=3)
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


def _add(db: psycopg.Connection, name: str, raw: dict) -> str:
    body = sc.build_body(gives="Something.", how="Read it.", since="Every hour.", check=sc.Check.from_dict(raw), fixes=[])
    return core_docs.create(db, owner=OWNER, path=f"sources/{name}.md", title=name.title(), body=body).doc.id


def _view(db: psycopg.Connection, doc_id: str, clock: Clock) -> core.View:
    return core.view(core.find(db, owner=OWNER, ref=doc_id), clock.now)


def _pass(pool, clock: Clock, home: Path, **kwargs) -> list[scheduler.Ran]:
    return scheduler.run_due(pool, owner=OWNER, clock=clock, home=home, environ={"PATH": "/usr/bin:/bin"}, **kwargs)


def test_a_pass_runs_what_is_due_and_keeps_the_answers(db: psycopg.Connection, pool, home: Path, health) -> None:
    url, _ = health
    clock = Clock()
    web = _add(db, "web", {"kind": "http", "url": url, "expect": {"status": "ok"}})
    host = _add(db, "host", {"kind": "dns", "host": "localhost"})
    ran = _pass(pool, clock, home)
    assert sorted(r.path for r in ran) == ["sources/host.md", "sources/web.md"]
    assert all(r.result.ok for r in ran)
    seen = _view(db, web, clock)
    assert (seen.status, seen.detail, seen.checked_at) == (core.OK, 'HTTP 200, status="ok"', T0)
    assert _view(db, host, clock).detail.startswith("resolves to ")

    # Nothing is due again until the hour is up.
    assert _pass(pool, clock, home) == []
    clock.move(minutes=59)
    assert _pass(pool, clock, home) == []
    clock.move(minutes=2)
    assert len(_pass(pool, clock, home)) == 2


def test_a_source_that_stops_answering_turns_red_on_the_second_look_five_minutes_later(db: psycopg.Connection, pool, home: Path, health) -> None:
    url, server = health
    clock = Clock()
    web = _add(db, "web", {"kind": "http", "url": url})
    assert _pass(pool, clock, home)[0].result.ok
    server.up = False
    clock.move(hours=1)
    first = _pass(pool, clock, home)[0]
    assert (first.result.detail, first.recorded.failures, first.recorded.turned_red) == ("HTTP 503", 1, False)
    assert _view(db, web, clock).status == core.OK, "one failure is looked at again quietly"
    clock.move(minutes=4)
    assert _pass(pool, clock, home) == [], "not before five minutes"
    clock.move(minutes=1)
    second = _pass(pool, clock, home)[0]
    assert (second.recorded.failures, second.recorded.turned_red) == (2, True)
    red = _view(db, web, clock)
    assert (red.status, red.since, red.detail) == (core.RED, T0 + timedelta(hours=1), "HTTP 503")
    # It answers again at the next hourly look.
    server.up = True
    clock.move(hours=1)
    back = _pass(pool, clock, home)[0]
    assert (back.recorded.recovered, _view(db, web, clock).status) == (True, core.OK)


def test_a_command_is_not_run_until_the_owner_approves_it_and_not_again_after_a_change(db: psycopg.Connection, pool, home: Path) -> None:
    clock = Clock()
    raw = {"kind": "cmd", "argv": ["/bin/echo", "disk 71% used"], "parse": r"(\d+)%", "max": 90}
    disk = _add(db, "disk", raw)
    assert _pass(pool, clock, home) == [], "a command nobody approved is never run"
    assert _view(db, disk, clock).why == core.WAITING

    source = core.find(db, owner=OWNER, ref=disk)
    core.approve(db, owner=OWNER, doc_id=disk, check_hash=source.check.hash, now=clock.now)
    ran = _pass(pool, clock, home)
    assert [(r.path, r.result.ok, r.result.value) for r in ran] == [("sources/disk.md", True, 71.0)]
    assert _view(db, disk, clock).status == core.OK

    # The agent changes the command: it waits for the new approval and the old answer no longer stands.
    changed = sc.set_section(source.body, "check", sc.render_block(sc.Check.from_dict({**raw, "argv": ["/bin/echo", "disk 95% used"]})))
    core_docs.save(db, owner=OWNER, id=disk, expected_revision=source.revision, body=changed)
    clock.move(hours=2)
    assert _pass(pool, clock, home) == []
    assert _view(db, disk, clock).why == core.WAITING


def test_a_check_edited_since_its_last_answer_is_run_at_once(db: psycopg.Connection, pool, home: Path, health) -> None:
    url, _ = health
    clock = Clock()
    doc = _add(db, "web", {"kind": "http", "url": url})
    _pass(pool, clock, home)
    source = core.find(db, owner=OWNER, ref=doc)
    changed = sc.set_section(source.body, "check", sc.render_block(sc.Check.from_dict({"kind": "http", "url": url, "status": 503})))
    core_docs.save(db, owner=OWNER, id=doc, expected_revision=source.revision, body=changed)
    clock.move(minutes=1)
    ran = _pass(pool, clock, home)
    assert [(r.path, r.result.ok) for r in ran] == [("sources/web.md", False)], "a minute later, not an hour"


def test_a_check_another_pass_has_taken_is_left_to_it(db: psycopg.Connection, pool, home: Path, health) -> None:
    url, _ = health
    clock = Clock()
    doc = _add(db, "web", {"kind": "http", "url": url})
    assert core.claim(db, owner=OWNER, source=core.find(db, owner=OWNER, ref=doc), now=clock.now)
    assert _pass(pool, clock, home) == []
    clock.move(minutes=11)
    assert len(_pass(pool, clock, home)) == 1, "a pass that died leaves a lease that runs out"


def test_a_pass_that_is_told_to_stop_runs_nothing_and_records_nothing(db: psycopg.Connection, pool, home: Path, health) -> None:
    url, _ = health
    clock = Clock()
    doc = _add(db, "web", {"kind": "http", "url": url})
    stop = threading.Event()
    stop.set()
    assert _pass(pool, clock, home, stop=stop) == []
    assert core.find(db, owner=OWNER, ref=doc).row is None


def _fake_claude(directory: Path, output: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "claude"
    script.write_text(f"#!/bin/sh\ncat <<'END'\n{output}\nEND\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return f"{directory}:/usr/bin:/bin"


def test_the_connections_source_exists_only_where_the_app_is_told_to_ask(db: psycopg.Connection, pool, home: Path, tmp_path: Path) -> None:
    clock = Clock()
    path = _fake_claude(tmp_path / "bin", "Checking MCP server health…\n\na: https://a.test (HTTP) - ✓ Connected\nb: ./b - ✗ Failed to connect")
    assert _pass(pool, clock, home, path=path) == []
    assert core.sources(db, owner=OWNER) == [], "asked nothing, made nothing"

    ran = _pass(pool, clock, home, connections=["claude"], path=path)
    assert [(r.path, r.result.ok) for r in ran] == [("sources/connections.md", False)]
    view = _view(db, core.find(db, owner=OWNER, ref=core.CONNECTIONS_PATH).id, clock)
    assert (view.title, view.kind, view.detail) == ("Connections", "connections", "1 of 2 answer; not answering: b (failed to connect)")
    # Taken off the list of agents, the document stays and is left alone.
    clock.move(hours=2)
    assert _pass(pool, clock, home, connections=[], path=path) == []


# --- the thread ------------------------------------------------------------------------------------------------------


def _wait(condition: Callable[[], bool], seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_the_timer_looks_on_its_own_when_poked_and_stops_when_told(db: psycopg.Connection, pool, health) -> None:
    url, _ = health
    doc = _add(db, "web", {"kind": "http", "url": url})
    timer = scheduler.Timer(pool, owner=OWNER, tick=3600.0, first_look=0.05)
    timer.start()
    assert timer.running
    assert _wait(lambda: core.find(db, owner=OWNER, ref=doc).row is not None), "the first look comes on its own"
    first = core.find(db, owner=OWNER, ref=doc).row.checked_at

    # Nothing is due for an hour, but a poke looks now: the owner just approved a check.
    cmd = _add(db, "disk", {"kind": "cmd", "argv": ["/bin/echo", "hi"]})
    source = core.find(db, owner=OWNER, ref=cmd)
    core.approve(db, owner=OWNER, doc_id=cmd, check_hash=source.check.hash, now=datetime.now(timezone.utc))
    timer.poke()
    assert _wait(lambda: core.find(db, owner=OWNER, ref=cmd).row.checked_at is not None), "a poke looks at once"
    assert core.find(db, owner=OWNER, ref=doc).row.checked_at == first, "and only at what is due"

    started = time.monotonic()
    timer.stop()
    assert not timer.running and time.monotonic() - started < 2


def test_a_timer_that_is_off_starts_nothing(pool) -> None:
    timer = scheduler.Timer(pool, owner=OWNER, tick=0)
    timer.start()
    assert not timer.running
    timer.poke()
    timer.stop()


def test_a_pass_that_fails_does_not_end_the_timer(db_dsn: str) -> None:
    pool = open_pool(db_dsn, min_size=1, max_size=2)
    timer = scheduler.Timer(pool, owner=OWNER, tick=0.1, first_look=0.05)
    pool.close()  # every pass from here on fails, as when the database is gone
    timer.start()
    time.sleep(0.6)
    assert timer.running, "a database that is down is looked at again next time"
    timer.stop()
    assert not timer.running


def test_stopping_ends_a_command_that_is_running(db: psycopg.Connection, pool, home: Path) -> None:
    length = f"{20 + secrets.randbelow(9)}.{secrets.randbelow(10**6):06d}"
    doc = _add(db, "slow", {"kind": "cmd", "argv": ["/bin/sleep", length], "timeout": 30})
    source = core.find(db, owner=OWNER, ref=doc)
    core.approve(db, owner=OWNER, doc_id=doc, check_hash=source.check.hash, now=datetime.now(timezone.utc))
    timer = scheduler.Timer(pool, owner=OWNER, tick=3600.0, first_look=0.05)
    timer.start()
    assert _wait(lambda: (row := core.find(db, owner=OWNER, ref=doc).row) is not None and row.leased_until is not None), "the pass has taken it"
    time.sleep(0.3)
    started = time.monotonic()
    timer.stop()
    assert time.monotonic() - started < 2, "the timer does not wait for the command"
    row = core.find(db, owner=OWNER, ref=doc).row
    assert row.checked_at is None and row.failures == 0, "a command cut short by the closing app is no failure"
    time.sleep(0.3)
    assert subprocess.run(["pgrep", "-f", f"sleep {length}"], capture_output=True).returncode == 1, "and the command is gone"
