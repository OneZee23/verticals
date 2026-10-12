"""`POST /api/goals/{id}/restore` (docs/design/board-undo.md): what a delete took away comes back under the same ids.
Each test gets its own fresh F2 clone (`server`/`client`'s fixture chain), so absolute row counts are safe to assert.
The rules themselves are proved in `tests/core/test_trash.py`; this file proves the wire: the route, its status codes and
the card it returns.
"""

from __future__ import annotations

import httpx
import psycopg


def _row_count(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        (count,) = conn.execute("SELECT count(*) FROM goals").fetchone()
    return count


def test_a_deleted_subtree_comes_back_with_the_same_ids(client: httpx.Client, server) -> None:
    assert client.delete("/api/goals/SYNDAY01", params={"cascade": "true"}).status_code == 204
    assert _row_count(server.dsn) == 45
    assert client.get("/api/goals/SYNSUB02").status_code == 404

    resp = client.post("/api/goals/SYNDAY01/restore")

    assert resp.status_code == 200
    card = resp.json()
    assert card["id"] == "SYNDAY01" and card["title"] == "Draft the outline"
    assert card["restored"] == 4
    assert _row_count(server.dsn) == 49
    detail = client.get("/api/goals/SYNDAY01").json()
    assert [child["id"] for child in detail["children"]] == ["SYNSUB01", "SYNSUB02", "SYNSUB03"]
    assert client.get("/api/goals/SYNSUB02").json()["title"] == "Name the argument"


def test_the_restored_goal_is_on_the_board_again(client: httpx.Client) -> None:
    def day_ids() -> set[str]:
        board = client.get("/api/board", params={"date": "2026-08-08"}).json()
        return {goal["id"] for column in board["columns"] if column["vertical"] == "day" for goal in column["goals"]}

    assert "SYNCOL03" in day_ids()
    client.delete("/api/goals/SYNCOL03")
    assert "SYNCOL03" not in day_ids()

    client.post("/api/goals/SYNCOL03/restore")

    assert "SYNCOL03" in day_ids()


def test_nothing_to_restore_is_the_plain_404(client: httpx.Client) -> None:
    for goal_id in ("SYNORD01", "NOSUCHID"):
        resp = client.post(f"/api/goals/{goal_id}/restore")
        assert resp.status_code == 404
        assert resp.json() == {"error": "not_found"}


def test_a_restore_is_spent_once(client: httpx.Client) -> None:
    client.delete("/api/goals/SYNORD02")
    assert client.post("/api/goals/SYNORD02/restore").status_code == 200
    assert client.post("/api/goals/SYNORD02/restore").status_code == 404


def test_a_goal_that_exists_already_is_refused_with_its_field(client: httpx.Client, server) -> None:
    client.delete("/api/goals/SYNORD02")
    with psycopg.connect(server.dsn, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO goals (id, owner, path, title, vertical, anchor_date, period_key, position)"
            " VALUES ('SYNORD02', 't1', '/SYNORD02/', 'Again', 'week', '2026-08-05', '2026-W32', 9216)"
        )

    resp = client.post("/api/goals/SYNORD02/restore")

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "id"]


def test_restore_needs_the_bearer_token(server) -> None:
    resp = httpx.post(f"{server.base_url}/api/goals/SYNORD02/restore")
    assert resp.status_code == 401
