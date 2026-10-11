"""Repeat rules through a real HTTP server and real Postgres; no ASGI test transport."""

from __future__ import annotations

from datetime import date

import httpx
import psycopg


def _create(client: httpx.Client) -> dict:
    response = client.post(
        "/api/goals",
        json={"title": "HTTP recurrence", "vertical": "day", "anchor_date": "2026-08-10"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_http_repeat_configures_and_completion_materializes(client: httpx.Client, server) -> None:
    created = _create(client)
    rule = {"frequency": "weekly", "interval": 1, "weekdays": [1, 4]}
    configured = client.patch(f"/api/goals/{created['id']}", json={"repeat": rule})
    assert configured.status_code == 200, configured.text
    assert configured.json()["repeat"] == rule

    completed = client.patch(f"/api/goals/{created['id']}", json={"done": True})
    assert completed.status_code == 200, completed.text
    with psycopg.connect(server.dsn, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT repeat_index, anchor_date FROM goals"
            " WHERE owner = 't1' AND repeat_series_id = %s ORDER BY repeat_index",
            (created["id"],),
        ).fetchall()
    assert rows == [(0, date(2026, 8, 10)), (1, date(2026, 8, 13))]


def test_http_repeat_boundary_names_invalid_fields(client: httpx.Client) -> None:
    created = _create(client)
    invalid = client.patch(
        f"/api/goals/{created['id']}",
        json={"repeat": {"frequency": "weekly", "interval": 3, "weekdays": [1]}},
    )
    assert invalid.status_code == 422
    assert "repeat.weekdays" in invalid.text
    detail = client.get(f"/api/goals/{created['id']}").json()
    assert detail["repeat"] is None

    extra = client.patch(
        f"/api/goals/{created['id']}",
        json={"repeat": {"frequency": "daily", "occurrences": 4}},
    )
    assert extra.status_code == 422


def test_http_repeat_is_refused_for_bulk_patch(client: httpx.Client) -> None:
    first = _create(client)
    second = _create(client)
    response = client.patch(
        "/api/goals",
        json={
            "ids": [first["id"], second["id"]],
            "patch": {"repeat": {"frequency": "daily"}},
        },
    )
    assert response.status_code == 422
    assert "repeat" in response.text


def test_http_a_goal_with_steps_repeats_and_each_new_time_brings_them_back_unticked(client: httpx.Client, server) -> None:
    """docs/design/goal-menu.md: the server used to answer 422 "goals with subgoals cannot repeat"."""
    created = client.post(
        "/api/goals",
        json={
            "title": "HTTP review", "vertical": "day", "anchor_date": "2026-08-10",
            "children": [
                {"title": "Check the inbox", "body": "Every account", "tags": ["admin"],
                 "children": [{"title": "Archive the old ones"}]},
                {"title": "Plan the day"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    parent = created.json()
    first_step, nested, second_step = parent["children"]  # flattened in creation order: a step, its step, the next step
    assert nested["parent_id"] == first_step["id"]

    configured = client.patch(f"/api/goals/{parent['id']}", json={"repeat": {"frequency": "daily"}})
    assert configured.status_code == 200, configured.text
    for private in (parent, first_step):  # the goal and its first step are private, its second step is not
        assert client.patch(f"/api/goals/{private['id']}", json={"private": True}).status_code == 200
    for done in (first_step, nested):
        assert client.patch(f"/api/goals/{done['id']}", json={"done": True}).status_code == 200
    completed = client.patch(f"/api/goals/{parent['id']}", json={"done": True})
    assert completed.status_code == 200, completed.text
    assert completed.json()["open_descendants"] == 1  # only the finished time's own second step is still open

    with psycopg.connect(server.dsn, autocommit=True) as conn:
        (again_id,) = conn.execute(
            "SELECT id FROM goals WHERE owner = 't1' AND repeat_series_id = %s AND repeat_index = 1",
            (parent["id"],),
        ).fetchone()
    again = client.get(f"/api/goals/{again_id}").json()
    assert again["anchor_date"] == "2026-08-11"
    assert again["private"] is True
    assert [c["private"] for c in again["children"]] == [True, False], "each step copy keeps its own flag"
    assert [(c["title"], c["done_at"]) for c in again["children"]] == [
        ("Check the inbox", None), ("Plan the day", None),
    ], "the same steps, in the same order, none ticked"
    assert [c["id"] for c in again["children"]] != [first_step["id"], second_step["id"]]
    assert again["children"][0]["tags"] == ["admin"]
    grandchildren = client.get(f"/api/goals/{again['children'][0]['id']}").json()["children"]
    assert [(c["title"], c["done_at"]) for c in grandchildren] == [("Archive the old ones", None)]

    # The finished time keeps its steps as they were.
    old = client.get(f"/api/goals/{parent['id']}").json()
    assert [(c["id"], c["done_at"] is not None) for c in old["children"]] == [
        (first_step["id"], True), (second_step["id"], False),
    ]
