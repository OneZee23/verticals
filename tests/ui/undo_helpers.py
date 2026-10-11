"""Shared by the board-undo scenarios (docs/design/board-undo.md): the keys as the page reads them on this platform, polling
that yields to Playwright, one goal's row in the database and the notice in the field."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import psycopg
from playwright.sync_api import Page, expect

NOTICE = '[data-role="field-notice"]'
LINE = f"{NOTICE} [data-role=field-notice-line]"
ACTION = f"{NOTICE} [data-role=field-notice-action]"
CIRCLE_FIELD = ".circle-field"
# A card row is `checkbox | text | schedule trigger`; only the middle strip is inert, so a drag takes hold there.
GRIP = {"x": 50, "y": 6}


def keys(page: Page) -> tuple[str, str]:
    """Undo and redo as this browser reads them: ⌘Z and ⇧⌘Z on Apple platforms, Ctrl+Z and Ctrl+Shift+Z elsewhere."""
    apple = page.evaluate("/Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent)")
    modifier = "Meta" if apple else "Control"
    return f"{modifier}+z", f"{modifier}+Shift+z"


def wait_for(page: Page, probe: Callable[[], Any], want: Any, what: str, timeout: float = 5.0) -> None:
    """Polls `probe` until it returns `want`. Yields to Playwright between looks: a bare sleep would starve its listeners."""
    deadline = time.monotonic() + timeout
    got = probe()
    while got != want and time.monotonic() < deadline:
        page.wait_for_timeout(25)
        got = probe()
    assert got == want, f"{what}: wanted {want!r}, got {got!r}"


def writes(session: Any, since: int = 0) -> list[tuple[str, str, int | None]]:
    """The writes the page has logged since `since` (an index into its request log): method, route, status. The database
    has a write before the page has logged its answer, so a scenario that counts writes waits for the one it expects."""
    return [
        (r["method"], r["url"].split("/api")[-1], r["status"])
        for r in session.request_log[since:]
        if r["method"] != "GET"
    ]


def goal(conn: psycopg.Connection, goal_id: str) -> tuple | None:
    """The row a person would call the goal: its place, its state, its words."""
    return conn.execute(
        "SELECT parent_id, vertical, anchor_date::text, period_key, (done_at IS NOT NULL), title, position "
        "FROM goals WHERE id = %s",
        (goal_id,),
    ).fetchone()


def family(conn: psycopg.Connection, root_id: str) -> list[tuple]:
    """Everything stored for a goal and the goals under it, for telling that a restore put back what was there."""
    return conn.execute(
        "SELECT id, parent_id, path, depth, vertical, anchor_date::text, period_key, title, position, created_at::text "
        "FROM goals WHERE id = %s OR path LIKE %s ORDER BY id",
        (root_id, f"%/{root_id}/%"),
    ).fetchall()


def notice_text(page: Page) -> str | None:
    """The notice's line as written, quotation marks and all; `None` when there is none."""
    return page.evaluate("document.querySelector('[data-role=field-notice-line]')?.textContent ?? null")


def expect_notice(page: Page, text: str) -> None:
    """The notice says `text`. A notice from an older change may still be leaving, so this waits for the words to be these."""
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    wait_for(page, lambda: notice_text(page), text, "the notice says")


def expect_no_notice(page: Page) -> None:
    expect(page.locator(NOTICE)).to_have_count(0, timeout=5000)


def column_ids(page: Page, vertical: str) -> list[str]:
    """The goals a column draws, in the order it draws them."""
    return page.eval_on_selector_all(
        f'[data-vertical="{vertical}"] .goal-card[data-goal-id]:not([data-ghost])', "els => els.map(e => e.dataset.goalId)"
    )
