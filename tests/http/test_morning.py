"""POST /api/morning over a real server and database (docs/design/agent-fixes.md, fixes 3 and 2): the app asks once its
morning hour has come, and the server tells it whether this morning's report is still to be asked for, with the one open
"Morning report" task, made or moved to that day."""

from __future__ import annotations

import threading
from datetime import date

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


# --- the owner's comments in the last report, and the second agent's verdict (docs/design/morning-quality.md) -----------

OWNER = "t1"  # F2's primary owner, the one the server runs as
WORDS = 'Start with the smaller package — "defer the percentage" | not the tender.'


def _seed_last_report(dsn: str, *, comment: str = WORDS) -> tuple[str, str]:
    """A task and yesterday's report, with the owner's comment in the task's row."""
    from tests.core.morning_sample import goal_row, make_report, make_task, report_body, sources_section
    with psycopg.connect(dsn, autocommit=True) as conn:
        task = make_task(conn, OWNER, "Launch is planned")
        doc = make_report(conn, OWNER, date(2026, 10, 11), report_body([goal_row(task, "Launch is planned", comment=comment)],
                                                                      sources=sources_section([])))
    return task, doc


def test_the_first_ask_of_a_day_brings_the_comments_left_in_the_last_report_already_on_their_tasks(client: httpx.Client, server: Server) -> None:
    task, doc = _seed_last_report(server.dsn)
    first = client.post("/api/morning", params={"date": "2026-10-12"}).json()
    assert first["asked"] is True
    assert [(item["goal_id"], item["title"], item["text"]) for item in first["landed"]] == [(task, "Launch is planned", WORDS)]
    (thread,) = client.get(f"/api/goals/{task}/comments").json()["threads"]
    assert thread["messages"][0]["body"] == WORDS
    assert WORDS not in client.get(f"/api/docs/{doc}").json()["body"]  # the cell was cleared
    assert client.post("/api/morning", params={"date": "2026-10-12"}).json() == {"asked": False, "task_id": None}


def test_a_morning_with_no_report_before_it_lands_nothing(client: httpx.Client) -> None:
    assert client.post("/api/morning", params={"date": "2026-10-12"}).json()["landed"] == []


def _seed_today(dsn: str, task: str, *, read: int = 42) -> None:
    from tests.core.morning_sample import goal_row, make_report, make_task, report_body, source_doc, source_row, sources_section
    with psycopg.connect(dsn, autocommit=True) as conn:
        source_doc(conn, OWNER, "Team chat")
        launch = make_task(conn, OWNER, "Launch is planned")
        make_report(conn, OWNER, date(2026, 10, 12), report_body([goal_row(launch, "Launch is planned")], sources=sources_section([
            source_row("Team chat", "2026-10-11 06:58", "2026-10-12 06:57", read, 11, 4, 6, 3, 15, 3, ref="sources/team-chat.md"),
        ])), task=task)


PASSES = {key: {"result": "pass"} for key in ("sources", "inputs", "continuity", "inbox", "changes", "state", "names", "hierarchy", "where", "copy")}
PATH = "reports/morning/2026-10-12.md"


def test_the_check_route_writes_the_verdict_into_the_report_and_names_what_failed(client: httpx.Client, server: Server) -> None:
    task = client.post("/api/morning", params={"date": "2026-10-12"}).json()["task_id"]
    _seed_today(server.dsn, task, read=44)  # 44 read, 42 placed
    pending = client.post("/api/morning/check", json={"path": PATH, "state": "pending"})
    assert pending.status_code == 200 and pending.json()["state"] == "pending" and pending.json()["failed"] == []
    answered = client.post("/api/morning/check", json={"path": PATH, "checks": PASSES})
    assert answered.status_code == 200, answered.text
    assert answered.json()["failed"] == ["inputs"] and answered.json()["state"] == "checked"
    assert answered.json()["checks"]["inputs"] == {"result": "fail", "note": "Team chat: 44 read, 42 placed.", "label": "Every message placed"}
    body = client.get(f"/api/docs/{answered.json()['doc_id']}").json()["body"]
    assert body.startswith("Checked against the sources by a second agent: 9 of 10 passed, 1 failed.")
    assert "| Every message placed | Failed | Team chat: 44 read, 42 placed. |" in body


def test_the_check_after_a_fix_shows_what_was_fixed(client: httpx.Client, server: Server) -> None:
    task = client.post("/api/morning", params={"date": "2026-10-12"}).json()["task_id"]
    _seed_today(server.dsn, task)
    first = {"names": {"result": "fail", "note": "Two rows are named by what is done."}}
    again = client.post("/api/morning/check", json={"path": PATH, "checks": PASSES, "first": first})
    assert again.status_code == 200 and again.json()["failed"] == []
    body = client.get(f"/api/docs/{again.json()['doc_id']}").json()["body"]
    assert "| Names | Fixed | Failed at first: Two rows are named by what is done. |" in body


def test_a_report_the_second_agent_did_not_finish_says_so(client: httpx.Client, server: Server) -> None:
    task = client.post("/api/morning", params={"date": "2026-10-12"}).json()["task_id"]
    _seed_today(server.dsn, task)
    unchecked = client.post("/api/morning/check", json={"path": PATH, "state": "unchecked", "reason": "It stopped."})
    assert unchecked.json()["state"] == "unchecked"
    body = client.get(f"/api/docs/{unchecked.json()['doc_id']}").json()["body"]
    assert body.startswith("Not checked: It stopped.")


def test_the_check_route_refuses_what_it_cannot_write_and_asks_for_the_token(client: httpx.Client, server: Server) -> None:
    assert client.post("/api/morning/check", json={"path": PATH, "checks": PASSES}).status_code == 404  # no such report
    assert client.post("/api/morning/check", json={"path": "notes/today.md", "checks": PASSES}).status_code == 422
    assert client.post("/api/morning/check", json={"path": PATH, "state": "done"}).status_code == 422
    assert client.post("/api/morning/check", json={"path": PATH, "checks": PASSES, "owner": "someone"}).status_code == 422
    bare = httpx.post(f"{server.base_url}/api/morning/check", json={"path": PATH, "state": "pending"}, timeout=30)
    assert bare.status_code == 401
