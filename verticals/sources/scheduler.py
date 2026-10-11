"""The timer (docs/design/sources.md): every source is checked every hour while the API runs, with no model.

A pass (`run_due`) reads the source documents, runs the checks that are due and hands each answer to
`core.sources.record`, which keeps it and applies the two-failures rule. The `Timer` repeats the pass on a thread of its
own, started and stopped by the API's lifespan. It never touches a request: it takes a pool connection only for its short
reads and writes, and holds none while a check runs.

Why a thread and not a task of the event loop: the work is blocking by nature (a command, a lookup, a socket), the loop is
the requests' and must stay theirs, and a thread with a stop flag ends exactly when it is told to. Every check inside the
pass has its own deadline (`runner.run_check`), so a stuck one cannot hold the timer, and a stop ends a running command at
once.

A source is looked at when its time has come, when its check was edited since its last answer, or at once after the owner
approves it (`poke`). A check that runs on this Mac and a check that could run anywhere are both run here for now; each
check already says which it is (`where`), for the day a cloud server takes the anywhere ones.

The automatic first look (not built; the hook is `Ran.recorded.turned_red`): the pass returns which sources just turned
red, and one place in the app that already starts a conversation on its own could send the same message the Fix button
sends, once per incident. Nothing here starts an agent turn.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from psycopg_pool import ConnectionPool

from verticals.core import sources as core
from verticals.sources import runner

logger = logging.getLogger("verticals.sources")

FIRST_LOOK = 20.0  # seconds after the API starts before the first pass: the start is busy enough


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Ran:
    """One check the pass ran: which document, what it found and what that did to the colour."""

    id: str
    path: str
    result: core.Result
    recorded: core.Recorded


def run_due(
    pool: ConnectionPool,
    *,
    owner: str,
    stop: threading.Event | None = None,
    connections: Sequence[str] = (),
    clock: Callable[[], datetime] = utcnow,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    path: str | None = None,
) -> list[Ran]:
    """One pass: run every check that is due and keep its answer. Returns what it ran, in order."""
    stop = stop or threading.Event()
    environ = os.environ if environ is None else environ
    with pool.connection() as conn:
        if "claude" in connections and runner.find_exe("claude", home=home, path=path or environ.get("PATH")):
            core.ensure_connections(conn, owner=owner)
        found = core.sources(conn, owner=owner)
    ran: list[Ran] = []
    for source in found:
        if stop.is_set():
            break
        check = source.check
        if check is None or (check.kind == "connections" and "claude" not in connections):
            continue
        if not core.due(source, clock()):
            continue
        with pool.connection() as conn:
            if not core.claim(conn, owner=owner, source=source, now=clock()):
                continue  # another pass has it
        result = runner.run_check(check, stop=stop, home=home, environ=environ, connections=connections, path=path)
        if result is None:
            break  # the app is closing: an unfinished check is no answer
        with pool.connection() as conn:
            recorded = core.record(conn, owner=owner, doc_id=source.id, check_hash=check.hash, result=result, now=clock())
        if recorded.turned_red:
            logger.warning("source %s is red: %s", source.path, result.detail)
        elif recorded.recovered:
            logger.warning("source %s answers again", source.path)
        ran.append(Ran(id=source.id, path=source.path, result=result, recorded=recorded))
    return ran


class Timer:
    """Runs `run_due` on a thread of its own: first after `first_look` seconds, then every `tick`; at once on `poke`."""

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        owner: str,
        tick: float = 60.0,
        first_look: float = FIRST_LOOK,
        connections: Sequence[str] = (),
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._pool, self._owner, self._tick, self._first = pool, owner, tick, min(first_look, tick) if tick else 0.0
        self._connections, self._clock = tuple(connections), clock
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the thread, unless the timer is off (a tick of 0) or already running."""
        if self._tick <= 0 or self.running:
            return
        self._thread = threading.Thread(target=self._loop, name="sources-timer", daemon=True)
        self._thread.start()

    def poke(self) -> None:
        """Look now: the owner just approved a check."""
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the thread to end and wait for it. A running command is killed, a running lookup is given up on."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        delay = self._first
        while not self._stop.is_set():
            self._wake.wait(delay)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                run_due(self._pool, owner=self._owner, stop=self._stop, connections=self._connections, clock=self._clock)
            except Exception as exc:  # noqa: BLE001 - a database that is down, a pool that is busy: look again next time
                logger.warning("sources: a pass failed (%s: %s)", type(exc).__name__, exc)
            delay = self._tick
