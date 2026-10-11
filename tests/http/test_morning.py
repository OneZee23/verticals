"""POST /api/morning over a real server and database (docs/design/agent-fixes.md, fixes 3 and 2): the app asks once its
morning hour has come, and the server tells it whether this morning's report is still to be asked for, with the one open
"Morning report" task, made or moved to that day."""

from __future__ import annotations

import threading

import httpx
import psycopg

from tests.http.conftest import Server


def test_the_first_ask_of_a_day_is_asked_and_later_ones_are_not(client: httpx.Client) -> None:
    first = client.post("/api/morning", params={"date": "2026-10-11"})
    assert first.status_code == 200, first.text
    assert first.json()["asked"] is True
    assert client.post("/api/morning", params={"date": "2026-10-11"}).json() == {"asked": False, "task_id": None}
    assert client.post("/api/morning", params={"date": "2026-10-12"}).json()["asked"] is True


def test_every_morning_has_the_one_open_task_in_its_day(client: httpx.Client) -> None:
    """The first morning makes the task; the next moves that same task to its day, so the board holds one."""
    first = client.post("/api/morning", params={"date": "2026-10-11"}).json()["task_id"]
    task = client.get(f"/api/goals/{first}").json()
    assert (task["title"], task["vertical"], task["anchor_date"], task["origin"], task["done_at"]) == (
        "Morning report", "day", "2026-10-11", "app", None)
    assert client.post("/api/morning", params={"date": "2026-10-12"}).json()["task_id"] == first
    assert client.get(f"/api/goals/{first}").json()["anchor_date"] == "2026-10-12"
    board = client.get("/api/board", params={"date": "2026-10-12"}).json()
    day = next(column for column in board["columns"] if column["vertical"] == "day")
    assert [goal["id"] for goal in day["goals"] if goal["title"] == "Morning report"] == [first]
    client.patch(f"/api/goals/{first}", json={"done": True})
    second = client.post("/api/morning", params={"date": "2026-10-13"}).json()["task_id"]
    assert second != first  # a finished task is never reopened


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
