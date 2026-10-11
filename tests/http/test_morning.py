"""POST /api/morning over a real server and database (docs/design/agent-fixes.md, fix 3): the app asks once its morning
hour has come, and the server tells it whether this morning's report is still to be asked for."""

from __future__ import annotations

import threading

import httpx
import psycopg

from tests.http.conftest import Server


def test_the_first_ask_of_a_day_is_asked_and_later_ones_are_not(client: httpx.Client) -> None:
    first = client.post("/api/morning", params={"date": "2026-10-11"})
    assert first.status_code == 200, first.text
    assert first.json() == {"asked": True}
    assert client.post("/api/morning", params={"date": "2026-10-11"}).json() == {"asked": False}
    assert client.post("/api/morning", params={"date": "2026-10-12"}).json() == {"asked": True}


def test_a_second_window_asking_at_the_same_moment_never_makes_a_second_ask(server: Server) -> None:
    """Eight windows, one barrier: exactly one is told to ask."""
    answers: list[bool] = []
    barrier = threading.Barrier(8)

    def window() -> None:
        with httpx.Client(base_url=server.base_url, headers={"Authorization": f"Bearer {server.token}"}, timeout=30) as c:
            barrier.wait()
            answers.append(c.post("/api/morning", params={"date": "2026-10-11"}).json()["asked"])

    threads = [threading.Thread(target=window) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(answers) == [False] * 7 + [True]
    with psycopg.connect(server.dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM idempotency WHERE client_token = 'morning:2026-10-11'").fetchone()[0] == 1


def test_a_day_is_required_and_so_is_the_token(client: httpx.Client, server: Server) -> None:
    assert client.post("/api/morning").status_code == 422
    assert client.post("/api/morning", params={"date": "yesterday"}).status_code == 422
    bare = httpx.post(f"{server.base_url}/api/morning", params={"date": "2026-10-11"}, timeout=30)
    assert bare.status_code == 401
