"""R4/R5/R6 card interactions through Chromium, live HTTP, and real Postgres."""

from __future__ import annotations

import psycopg

from playwright.sync_api import expect

from tests.ui.conftest import UiSession, activate_column

MENU = '[data-role="goal-context-menu"]'


def _card(goal_id: str) -> str:
    return f'[data-goal-id="{goal_id}"]'


def _affordance(goal_id: str) -> str:
    return f'{_card(goal_id)} [data-role="goal-affordance"]'


def test_a_leaf_and_a_goal_with_steps_both_complete_by_their_box(ui_f2: UiSession) -> None:
    """docs/design/goal-menu.md: a goal completes by its box, as a goal without steps already does. A goal with steps used
    to open its menu instead (and complete from "Complete" there); its box is a box like any other now."""
    session = ui_f2
    session.page.wait_for_selector(_affordance("SYNCOL01"))
    assert session.page.locator(_affordance("SYNCOL01")).get_attribute("data-affordance") == "leaf"
    with session.page.expect_response(
        lambda response: response.request.method == "PATCH"
        and response.url.endswith("/api/goals/SYNCOL01")
    ):
        session.page.click(_affordance("SYNCOL01"))
    session.page.wait_for_selector(f'{_card("SYNCOL01")}.goal-card--done')

    assert session.page.locator(_affordance("SYNDAY01")).get_attribute("data-affordance") == "parent"
    for done in (True, False):
        with session.page.expect_response(
            lambda response: response.request.method == "PATCH"
            and response.url.endswith("/api/goals/SYNDAY01")
        ) as sent:
            session.page.click(_affordance("SYNDAY01"))
        assert sent.value.request.post_data_json == {"done": done}
        with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
            assert conn.execute(
                "SELECT done_at IS NOT NULL FROM goals WHERE id = 'SYNDAY01'"
            ).fetchone() == (done,)
        assert session.page.locator(MENU).count() == 0, "the box completes; it opens no menu"


def test_right_click_uses_same_menu_with_the_reschedule_and_move_groups(ui_f2: UiSession) -> None:
    """S5.P5.035; docs/design/goal-menu.md: one grey "Reschedule" over Tomorrow, Next week and Date, one grey "Move" over
    Into a goal and To Inbox."""
    session = ui_f2
    card = session.page.locator(_card("SYNCOL03"))
    card.wait_for(state="visible")
    card.click(button="right")
    session.page.wait_for_selector(MENU)
    for gone in ("comment", "complete", "ignore", "details"):
        assert session.page.locator(f'{MENU} [data-menu-item="{gone}"]').count() == 0
    reschedule = session.page.locator(f'{MENU} [data-menu-section="reschedule"]')
    expect(reschedule.locator(".goal-actions__heading")).to_have_text("Reschedule")
    assert [t.strip() for t in reschedule.locator("[data-move]").all_inner_texts()] == ["Tomorrow", "Next week", "Date"]
    move = session.page.locator(f'{MENU} [data-menu-section="move"]')
    expect(move.locator(".goal-actions__heading")).to_have_text("Move")
    assert [t.strip() for t in move.locator("[data-move]").all_inner_texts()] == ["Into a goal", "To Inbox"]
    assert session.page.locator(f'{MENU} [data-cap="park"]').count() == 0


def test_inbox_takes_the_goal_off_its_dates(ui_f2: UiSession) -> None:
    """S5.P5.004: "To Inbox" under Move clears the goal's schedule; it leaves the board for the Inbox."""
    session = ui_f2
    card = session.page.locator(_card("SYNORD01"))
    card.wait_for(state="visible")
    activate_column(session.page, "week")
    card.click(button="right")
    with session.page.expect_response(
        lambda response: response.request.method == "PUT"
        and response.url.endswith("/api/goals/SYNORD01/schedule")
    ):
        session.page.click(f'{MENU} [data-move="inbox"]')
    session.page.wait_for_selector(_card("SYNORD01"), state="detached")

    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        assert conn.execute(
            "SELECT vertical, period_key FROM goals WHERE id = 'SYNORD01'"
        ).fetchone() == (None, None)