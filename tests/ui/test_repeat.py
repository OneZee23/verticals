"""Repeat configuration through the real browser, HTTP server, and Postgres."""

from __future__ import annotations

import psycopg
from playwright.sync_api import expect

from tests.ui.conftest import UiSession


def test_repeat_menu_uses_nested_kit_surface_and_marks_the_card(ui_f2: UiSession) -> None:
    session = ui_f2
    card = '[data-goal-id="SYNCOL04"]'
    session.gestures.click(f'{card} [data-role="goal-actions-trigger"]')
    session.gestures.click('[data-role="goal-actions-menu"] [data-action="repeat"] button')

    menu = session.page.locator('[data-role="repeat-menu"]')
    menu.wait_for(state="visible")
    assert menu.get_attribute("role") == "menu"
    assert menu.locator('[role="dialog"]').count() == 0
    labels = menu.locator(':scope > button[role="menuitem"]').all_text_contents()
    assert labels[:6] == ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly", "Every decade"]

    session.gestures.click('[data-role="repeat-menu"] button[role="menuitem"]:has-text("Daily")')
    session.page.wait_for_timeout(300)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        (rule,) = conn.execute(
            "SELECT repeat_rule FROM goals WHERE owner = 't1' AND id = 'SYNCOL04'"
        ).fetchone()
    assert rule == {"frequency": "daily", "interval": 1}
    session.page.reload()
    session.page.wait_for_selector(f'{card} [data-role="repeat-indicator"]')

    # D89: the rule in force must show as the selected one when the menu is reopened. Postgres
    # hands jsonb back in its own key order, so the client's old stringify comparison marked
    # nothing — a defect no dict-equality assertion above can see. Read it off the DOM.
    session.gestures.click(f'{card} [data-role="goal-actions-trigger"]')
    session.gestures.click('[data-role="goal-actions-menu"] [data-action="repeat"] button')
    reopened = session.page.locator('[data-role="repeat-menu"]')
    reopened.wait_for(state="visible")
    active = reopened.locator(':scope > button[role="menuitem"]._active').all_text_contents()
    assert active == ["Daily"], active


def test_a_goal_with_steps_repeats_and_ticking_its_box_brings_the_steps_back(ui_f2: UiSession) -> None:
    """docs/design/goal-menu.md. The app used to refuse Repeat on a goal with subgoals (D91: its menu item greyed, with
    "Only for goals without subgoals"). SYNDAY01 has three steps: Repeat is live in its menu, and the next time comes
    back with the same steps in the same order, none ticked."""
    session = ui_f2
    page = session.page
    card = '[data-goal-id="SYNDAY01"]'
    session.gestures.click(f'{card} > .goal-card__row [data-role="goal-actions-trigger"]')
    repeat = page.locator('[data-role="goal-actions-menu"] [data-action="repeat"] button')
    expect(repeat).to_be_enabled()
    assert page.locator('[data-role="goal-actions-menu"] .goal-actions__why').count() == 0
    session.gestures.click('[data-role="goal-actions-menu"] [data-action="repeat"] button')
    with page.expect_response(lambda r: r.request.method == "PATCH" and r.url.endswith("/api/goals/SYNDAY01")):
        session.gestures.click('[data-role="repeat-menu"] button[role="menuitem"]:has-text("Daily")')
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        (rule,) = conn.execute("SELECT repeat_rule FROM goals WHERE owner = 't1' AND id = 'SYNDAY01'").fetchone()
    assert rule == {"frequency": "daily", "interval": 1}

    with page.expect_response(lambda r: r.request.method == "PATCH" and r.url.endswith("/api/goals/SYNDAY01")):
        session.gestures.click(f'{card} [data-role="goal-affordance"]')
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        again = conn.execute(
            "SELECT id, anchor_date FROM goals WHERE owner = 't1' AND repeat_series_id = 'SYNDAY01' AND repeat_index = 1"
        ).fetchone()
        assert again is not None and str(again[1]) == "2026-08-09"
        steps = conn.execute(
            "SELECT title, done_at FROM goals WHERE owner = 't1' AND parent_id = %s ORDER BY position", (again[0],)
        ).fetchall()
    assert steps == [("Collect the sources", None), ("Name the argument", None), ("Cut the first pass", None)]
