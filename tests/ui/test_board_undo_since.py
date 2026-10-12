"""⌘Z is the person's own (docs/design/board-undo.md). An agent working in the background (a real MCP server and client,
`agent_writes.py`) never enters the history, and a step is put back only where the goal still holds what the step left: what
the agent changed after it stays as the agent left it, the step's other changes still go back, and the field says so in its
one line. Fixture F2, the pinned clock (Saturday 8 Aug 2026)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import psycopg
from playwright.sync_api import expect

from verticals.core import goals as core_goals
from tests.ui.agent_writes import agent_at_work
from tests.ui.conftest import UiSession
from tests.ui.test_board_undo import MONTH_BODY, TICK, board, open_menu
from tests.ui.undo_helpers import (
    ACTION, GRIP, expect_no_notice, expect_notice, goal, keys, wait_for, write_log, writes,
)


def tick_by_hand(session: UiSession, conn: psycopg.Connection, goal_id: str) -> None:
    """The person ticks a goal in the day column, and the tick is stored and logged: a step."""
    before = len(writes(session))
    session.gestures.click(f'[data-goal-id="{goal_id}"] > .goal-card__row label.checkbox')
    wait_for(session.page, lambda: goal(conn, goal_id)[4], True, f"{goal_id} is ticked")
    wait_for(session.page, lambda: len(writes(session)), before + 1, "the tick is logged")


def test_an_agents_writes_never_enter_the_history_so_cmd_z_takes_back_the_persons_own_last_change(
    ui_f2: UiSession, tmp_path: Path,
) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn, agent_at_work(session, tmp_path) as agent:
        done = lambda goal_id: goal(conn, goal_id)[4]  # noqa: E731
        agent("update", id="SYNCOL02", done=True)  # before the person's change
        wait_for(page, lambda: done("SYNCOL02"), True, "the agent's tick is stored")
        expect(page.locator('[data-goal-id="SYNCOL02"] input.checkbox__input')).to_be_checked(timeout=5000)
        tick_by_hand(session, conn, "SYNCOL01")
        agent("schedule", id="SYNORD01", vertical="month", anchor_date="2026-08-08")  # and after it
        wait_for(page, lambda: goal(conn, "SYNORD01")[1], "month", "the agent's move is stored")
        page.wait_for_selector('[data-vertical="month"] [data-goal-id="SYNORD01"]', timeout=5000)

        page.keyboard.press(undo)
        wait_for(page, lambda: done("SYNCOL01"), False, "⌘Z takes back the person's tick")
        assert done("SYNCOL02") is True, "and leaves the agent's"
        assert goal(conn, "SYNORD01")[1] == "month", "and the agent's move"

        # The agent's work is not in the history, whenever it came: there is nothing left to take back.
        start = len(session.request_log)
        page.keyboard.press(undo)
        page.wait_for_timeout(500)
        assert writes(session, start) == [], write_log(session, start)
        assert done("SYNCOL02") is True and goal(conn, "SYNORD01")[1] == "month"

        page.keyboard.press(redo)  # and the only step there is plays again
        wait_for(page, lambda: done("SYNCOL01"), True, "⇧⌘Z ticks it again")
        assert done("SYNCOL02") is True and goal(conn, "SYNORD01")[1] == "month"


def test_a_move_an_agent_moved_again_stays_where_the_agent_put_it_and_the_field_says_so(
    ui_f2: UiSession, tmp_path: Path,
) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn, agent_at_work(session, tmp_path) as agent:
        where = lambda: goal(conn, "SYNCOL03")[1:4]  # noqa: E731
        tick_by_hand(session, conn, "SYNCOL01")  # the step before
        open_menu(page, "day", "SYNCOL03")
        page.click('#dropdownPortal [data-move="tomorrow"]')
        wait_for(page, where, ("day", "2026-08-09", "2026-08-09"), "the person moved it to tomorrow")
        expect_notice(page, "Moved “Color check green” to tomorrow")
        agent("schedule", id="SYNCOL03", vertical="week", anchor_date="2026-08-12")
        wait_for(page, where, ("week", "2026-08-12", "2026-W33"), "the agent moved it again")

        start = len(session.request_log)
        page.keyboard.press(undo)
        expect_notice(page, "“Color check green” changed since, so it stays")
        expect(page.locator(ACTION)).to_have_count(0)  # nothing was taken back, so there is nothing to play again
        page.wait_for_timeout(500)
        assert writes(session, start) == [], f"nothing is written: {write_log(session, start)}"
        assert where() == ("week", "2026-08-12", "2026-W33"), "the goal stays where the agent put it"

        # The step is spent: there is nothing of it to play again, and the next ⌘Z goes on to the step before it.
        page.keyboard.press(redo)
        page.wait_for_timeout(400)
        assert writes(session, start) == [], "⇧⌘Z has nothing to play"
        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the next ⌘Z takes back the earlier tick")
        assert where() == ("week", "2026-08-12", "2026-W33")
        page.keyboard.press(redo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "and ⇧⌘Z ticks it again")
        assert where() == ("week", "2026-08-12", "2026-W33")


def test_what_an_agent_already_put_back_is_nothing_to_put_back_and_nothing_is_said(
    ui_f2: UiSession, tmp_path: Path,
) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn, agent_at_work(session, tmp_path) as agent:
        tick_by_hand(session, conn, "SYNCOL01")
        agent("update", id="SYNCOL01", done=False)  # the agent opened it again: it is what ⌘Z would do
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the agent opened the goal")

        start = len(session.request_log)
        page.keyboard.press(undo)
        page.wait_for_timeout(600)
        assert writes(session, start) == [], write_log(session, start)
        assert goal(conn, "SYNCOL01")[4] is False
        expect_no_notice(page)


def test_a_subgoal_an_agent_moved_since_stays_while_the_rest_of_the_family_goes_back(
    ui_f2: UiSession, tmp_path: Path,
) -> None:
    """A step holds each goal it changed on its own: a goal dragged to another column with its subgoals, one of which the agent
    then moved elsewhere, goes back to its week without that subgoal, and the line says that part stays."""
    session = ui_f2
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        week = date(2026, 8, 5)
        parent = core_goals.create(conn, owner="t1", title="SYN held parent", vertical="week", anchor_date=week).goal
        kids = [
            core_goals.create(conn, owner="t1", title=f"SYN held kid {n}", parent_id=parent.id, vertical="week", anchor_date=week).goal
            for n in range(2)
        ]
        session.page.reload()
        page = board(session)
        undo, redo = keys(page)
        places = lambda: [  # noqa: E731
            conn.execute("SELECT vertical, period_key FROM goals WHERE id = %s", (one.id,)).fetchone() for one in (parent, *kids)
        ]
        with agent_at_work(session, tmp_path) as agent:
            row = f'[data-goal-id="{parent.id}"] > .goal-card__row'
            expect(page.locator(row)).to_be_visible(timeout=10000)
            session.gestures.drag(row, MONTH_BODY, source_position=GRIP, target_position=GRIP)
            wait_for(page, places, [("month", "2026-08")] * 3, "the goal and its subgoals were dragged to the month")
            page.wait_for_selector(f'[data-vertical="month"] [data-goal-id="{kids[1].id}"]', timeout=5000)
            agent("schedule", id=kids[1].id, vertical="week", anchor_date="2026-08-12")
            wait_for(page, places, [("month", "2026-08")] * 2 + [("week", "2026-W33")], "the agent moved one subgoal to next week")

            page.keyboard.press(undo)
            wait_for(page, places, [("week", "2026-W32")] * 2 + [("week", "2026-W33")], "the family is back, the subgoal the agent moved is not")
            expect_notice(page, "Put back “SYN held parent”; what changed since stays")
            expect(page.locator(ACTION)).to_have_text("Redo")  # something did go back, so it can be played again

            page.click(ACTION)
            wait_for(page, places, [("month", "2026-08")] * 2 + [("week", "2026-W33")], "Redo moves the family again, and still leaves that subgoal")
            expect_notice(page, "Redid “SYN held parent”; what changed since stays")
