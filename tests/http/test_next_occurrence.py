"""`PATCH /api/goals/{id}` with `done: true` on a repeating goal says which occurrence it made (docs/design/board-undo.md),
so the page can take that one back with the tick. The rule itself is proved in `tests/core/test_repeat.py`; this file proves
the wire. Each test gets its own fresh F2 clone."""

from __future__ import annotations

import httpx


def _repeat_daily(client: httpx.Client, goal_id: str) -> None:
    resp = client.patch(f"/api/goals/{goal_id}", json={"repeat": {"frequency": "daily", "interval": 1}})
    assert resp.status_code == 200


def test_ticking_a_repeating_goal_answers_with_the_occurrence_it_made(client: httpx.Client) -> None:
    _repeat_daily(client, "SYNCOL04")

    resp = client.patch("/api/goals/SYNCOL04", json={"done": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "SYNCOL04" and body["done_at"] is not None
    made = body["next_occurrence"]
    assert made["id"] != "SYNCOL04" and made["title"] == body["title"]
    assert made["done_at"] is None and made["vertical"] == "day"
    assert made["anchor_date"] == "2026-08-09", "the day after the goal it follows"
    assert client.get(f"/api/goals/{made['id']}").status_code == 200


def test_a_replay_a_reopen_and_a_goal_that_does_not_repeat_make_no_occurrence(client: httpx.Client) -> None:
    _repeat_daily(client, "SYNCOL04")
    first = client.patch("/api/goals/SYNCOL04", json={"done": True}).json()
    assert "next_occurrence" in first

    assert "next_occurrence" not in client.patch("/api/goals/SYNCOL04", json={"done": True}).json(), "already there"
    assert "next_occurrence" not in client.patch("/api/goals/SYNCOL04", json={"done": False}).json()
    assert "next_occurrence" not in client.patch("/api/goals/SYNCOL05", json={"done": True}).json()
