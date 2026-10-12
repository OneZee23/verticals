"""An agent's answer has its own Undo (docs/design/agent-answer-undo.md). Fixture F2 behind the desktop gateway, a real MCP server
on the same database and the fake agent, whose `[tool:NAME {json}]` marks are real calls to that server (`answer_support.py`): an
answer here is marked by the gateway, written by the agent through MCP, kept by the server, and read by the page when it ends.

An answer that changed the board has an Undo on its message in the conversation, and in the field while it stands there. It
takes back what the answer wrote, and only where the goal is still as the answer left it; it becomes Redo. ⌘Z never takes it:
the keys are the person's own (`test_cmd_z_whose_change.py`)."""

from __future__ import annotations

import psycopg
from playwright.sync_api import Page, expect

from verticals.core import docs as core_docs, goals as core_goals
from tests.ui.answer_support import (
    BALLOON, CIRCLE_ANSWER, ONE, THREE, UNDO, answer_without_a_page, ask, ask_for_the_field, look, send, to_the_board,
    ui_answers, ui_reduced_motion, mcp_server,  # noqa: F401  (the fixtures)
)
from tests.ui.conftest import F2_OWNER, UiSession, activate_column
from tests.ui.test_board_undo import board
from tests.ui.undo_helpers import ACTION, expect_no_notice, expect_notice, family, goal, wait_for

MADE = "Made by the answer"
#: The conversation an answer is given in while the window is closed (the gateway's conversations are UUIDs).
CLOSED = "5f0c8b6e-8c1f-4f0e-9a34-6f6f3b0f1a11"
WEEK = ("week", "2026-08-05", "2026-W32")


def made_id(conn: psycopg.Connection) -> str | None:
    row = conn.execute("SELECT id FROM goals WHERE title = %s", (MADE,)).fetchone()
    return row[0] if row else None


def last_pill(page: Page):
    """The Undo on the agent's last message."""
    return page.locator(BALLOON).last.locator(UNDO)


def test_an_answer_on_its_message_is_taken_back_by_its_undo_and_played_again_by_its_redo(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order, colour = goal(conn, "SYNORD01"), goal(conn, "SYNCOL01")
        assert order[1:4] == WEEK and colour[4] is False

        ask(session, THREE, stay=True)  # the answer ticks a goal, moves one to the month and makes one
        made = made_id(conn)
        assert made and goal(conn, "SYNCOL01")[4] is True and goal(conn, "SYNORD01")[1] == "month"
        made_family = family(conn, made)
        pill = last_pill(page)
        expect(pill).to_have_text("Undo")

        pill.click()
        wait_for(page, lambda: goal(conn, "SYNCOL01"), colour, "the tick is taken back, the goal as it was")
        wait_for(page, lambda: goal(conn, "SYNORD01"), order, "the goal is back in its week, in its place")
        wait_for(page, lambda: made_id(conn), None, "the goal the answer made is gone")
        expect(pill).to_have_text("Redo")
        expect_notice(page, "Put back “Order one” and 2 more")  # the made goal left the view, and the board is behind the conversation
        expect(page.locator(ACTION)).to_have_count(0)  # the message's own pill is the Redo: the notice has no second one

        pill.click()
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the answer is played again: the tick")
        wait_for(page, lambda: goal(conn, "SYNORD01")[1], "month", "the move")
        wait_for(page, lambda: family(conn, made), made_family, "and the goal it made is back, under its id")
        expect(pill).to_have_text("Undo")


def test_an_answer_in_the_field_has_its_undo_and_the_same_place_offers_redo(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order, colour = goal(conn, "SYNORD01"), goal(conn, "SYNCOL01")
        ask_for_the_field(session, THREE)
        pill = page.locator(CIRCLE_ANSWER).locator(UNDO)
        expect(pill).to_have_text("Undo")

        pill.click()
        wait_for(page, lambda: goal(conn, "SYNCOL01"), colour, "the tick is taken back")
        wait_for(page, lambda: goal(conn, "SYNORD01"), order, "the goal is back in its week")
        wait_for(page, lambda: made_id(conn), None, "the goal the answer made is gone")
        expect_notice(page, "Put back “Order one” and 2 more")  # the made goal left the view: it is said, with Redo
        page.keyboard.press("Escape")
        expect_no_notice(page)
        expect(page.locator(CIRCLE_ANSWER).locator(UNDO)).to_have_text("Redo")

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "Redo plays the answer again")
        wait_for(page, lambda: made_id(conn) is not None, True, "with the goal it made")
        expect(page.locator(CIRCLE_ANSWER).locator(UNDO)).to_have_text("Undo")


def rename(page: Page, goal_id: str, title: str) -> None:
    """A person renames a goal on the board: a click on its card, on its title, the new words, Enter."""
    activate_column(page, "day")
    page.click(f'[data-goal-id="{goal_id}"] > [data-cap=reorder]')
    editor = f'[data-goal-id="{goal_id}"] [data-cap="edit-title"]'
    page.wait_for_selector(editor, timeout=5000)
    page.click(editor)
    page.fill(f"{editor}:is(textarea)", title)
    page.press(f"{editor}:is(textarea)", "Enter")


def test_a_goal_the_person_changed_after_the_answer_stays_as_they_left_it_and_the_field_says_so(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ask_for_the_field(
            session, 'Tick and rename [tool:update {"id": "SYNCOL01", "done": true}] '
                     '[tool:update {"id": "SYNCOL02", "title": "Renamed by the agent"}]',
        )
        assert goal(conn, "SYNCOL01")[4] is True and goal(conn, "SYNCOL02")[5] == "Renamed by the agent"
        rename(page, "SYNCOL02", "Renamed by me")  # the person's own words, after the answer
        wait_for(page, lambda: goal(conn, "SYNCOL02")[5], "Renamed by me", "the person's title is stored")

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the tick, still as the answer left it, is taken back")
        expect_notice(page, "Put back “Color check yellow”; what changed since stays")
        assert goal(conn, "SYNCOL02")[5] == "Renamed by me", "the title the person wrote is theirs and stays"

        page.click(ACTION)  # Redo: the tick again, and the title is still the person's
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "Redo ticks it again")
        expect_notice(page, "Redid “Color check yellow”; what changed since stays")
        assert goal(conn, "SYNCOL02")[5] == "Renamed by me"


def test_goals_the_answer_deleted_come_back_with_what_was_under_them_and_go_again_on_redo(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        tree = family(conn, "SYNDAY01")
        assert len(tree) == 4, "SYNDAY01 stands over three subgoals"
        ask_for_the_field(session, 'Clear it [tool:delete {"id": "SYNDAY01", "cascade": true}]')
        assert family(conn, "SYNDAY01") == []

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: family(conn, "SYNDAY01"), tree, "the goal and its three subgoals are back, under their ids")
        page.wait_for_selector('[data-vertical="day"] [data-goal-id="SYNDAY01"]', timeout=5000)
        expect(page.locator(CIRCLE_ANSWER).locator(UNDO)).to_have_text("Redo")

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: family(conn, "SYNDAY01"), [], "Redo deletes them again")
        expect_notice(page, "Deleted “Draft the outline” and 3 subgoals")


def test_a_goal_the_answer_made_that_somebody_took_up_since_is_left_and_the_answer_is_let_go(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ask_for_the_field(session, 'Make it [tool:create {"title": "Made by the answer", "vertical": "day", "anchor_date": "2026-08-08"}]')
        made = made_id(conn)
        assert made
        session.gestures.click(f'[data-goal-id="{made}"] > .goal-card__row label.checkbox')  # the person takes it up: ticks it
        wait_for(page, lambda: goal(conn, made)[4], True, "the person's tick is stored")

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        expect_notice(page, "“Made by the answer” changed since, so it stays")
        assert goal(conn, made)[4] is True, "the goal is still there, as the person left it"
        expect(page.locator(ACTION)).to_have_count(0)  # nothing was taken back, so there is nothing to play again
        page.keyboard.press("Escape")
        expect(page.locator(CIRCLE_ANSWER).locator(UNDO)).to_have_count(0)  # and the answer, which cannot be taken back now, has none


def test_the_tick_of_a_repeating_goal_goes_back_with_the_occurrence_it_made_and_comes_back_without_a_second(ui_answers: UiSession) -> None:
    session = ui_answers
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        core_goals.update(conn, owner=F2_OWNER, id="SYNCOL04", repeat={"frequency": "daily", "interval": 1})
        session.page.reload()
        page = board(session)
        series = lambda: conn.execute(  # noqa: E731
            "SELECT count(*), min(id) FILTER (WHERE id <> 'SYNCOL04') FROM goals "
            "WHERE repeat_series_id = (SELECT repeat_series_id FROM goals WHERE id = 'SYNCOL04')"
        ).fetchone()

        ask_for_the_field(session, 'Tick it [tool:update {"id": "SYNCOL04", "done": true}]')
        count, occurrence = series()
        assert count == 2 and occurrence, "the tick made the next occurrence"

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: goal(conn, "SYNCOL04")[4], False, "the tick is taken back")
        wait_for(page, lambda: series(), (1, None), "and the occurrence it made goes with it")
        expect_notice(page, "Removed “Color check blue” and 1 more")  # the occurrence left the view; Esc ends the notice once it is up
        page.keyboard.press("Escape")

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: goal(conn, "SYNCOL04")[4], True, "Redo ticks it again")
        wait_for(page, lambda: series(), (2, occurrence), "and it is the same occurrence that is back, not a second one")


def test_each_answer_takes_back_only_what_it_wrote(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order = goal(conn, "SYNORD02")
        ask(session, 'Tick [tool:update {"id": "SYNCOL01", "done": true}]', stay=True)
        ask(session, ONE, stay=True)
        assert goal(conn, "SYNCOL01")[4] is True and goal(conn, "SYNORD02")[1] == "month"
        first, second = page.locator(BALLOON).locator(UNDO).all()  # the two answers, each with its own

        first.click()
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the first answer's tick is taken back")
        assert goal(conn, "SYNORD02")[1] == "month", "and the second answer's move is not"
        expect(first).to_have_text("Redo")
        expect(second).to_have_text("Undo")

        second.click()
        wait_for(page, lambda: goal(conn, "SYNORD02"), order, "the second answer's move is taken back by its own")
        assert goal(conn, "SYNCOL01")[4] is False


def test_an_answer_given_with_no_window_open_has_its_undo_when_the_window_opens(ui_answers: UiSession) -> None:
    """The morning report is given so: the app's agent answers while its window is closed. Nothing is restarted: the server has kept
    what the answer wrote, and the window reads it when it opens."""
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order, colour = goal(conn, "SYNORD01"), goal(conn, "SYNCOL01")
        page.evaluate("id => localStorage.setItem('vt-chat:current', JSON.stringify(id))", CLOSED)
        page.goto("about:blank")  # the window is closed
        answer_without_a_page(session.base_url, CLOSED, THREE)
        assert goal(conn, "SYNCOL01")[4] is True and goal(conn, "SYNORD01")[1] == "month" and made_id(conn)

        page.goto(session.base_url)  # the window opens, its conversation the one the agent answered in
        board(session)
        send(session, "Anything else?")
        pill = page.locator(BALLOON).first.locator(UNDO)
        expect(pill).to_have_text("Undo", timeout=10000)
        expect(page.locator(BALLOON).first).to_contain_text("Done: Tick, move, make")

        pill.click()
        wait_for(page, lambda: goal(conn, "SYNCOL01"), colour, "the answer given while the window was closed is taken back")
        wait_for(page, lambda: goal(conn, "SYNORD01"), order, "with its move")
        wait_for(page, lambda: made_id(conn), None, "and the goal it made")
        expect(pill).to_have_text("Redo")


def test_an_answer_that_changed_nothing_on_the_board_has_no_undo(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    ask(session, "Just a word", stay=True)
    ask(session, 'Look for it [tool:update {"id": "NOSUCHID", "done": true}]', stay=True)  # a call the server refused wrote nothing
    expect(page.locator(BALLOON).last).to_contain_text("Done: Look for it")
    assert page.locator(UNDO).count() == 0
    to_the_board(page)
    ask_for_the_field(session, "Just a word")
    assert page.locator(CIRCLE_ANSWER).locator(UNDO).count() == 0


def look_of_the_notices_undo(page: Page, conn: psycopg.Connection):
    """The pill of the notice a delete says, as the browser drew it (its own Undo)."""
    activate_column(page, "day")
    page.click('[data-goal-id="SYNCOL03"] [data-role=goal-actions-trigger]')
    page.wait_for_selector('[data-role="goal-context-menu"]', timeout=5000)
    page.click('#dropdownPortal [data-action="delete"]')
    expect_notice(page, "Deleted “Color check green”")
    page.mouse.move(5, 5)
    page.wait_for_timeout(600)
    seen = look(page.locator(ACTION))
    page.click(ACTION)  # Undo: the goal is back
    wait_for(page, lambda: goal(conn, "SYNCOL03") is not None, True, "the goal is back")
    return seen


def test_the_pill_has_the_notices_own_look_and_stands_inside_the_field_in_both_its_shapes(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = core_docs.create(conn, owner=F2_OWNER, path="reports/syn-note.md", title="SYN report — 8 August 2026").doc.id
        notice_pill = look_of_the_notices_undo(page, conn)
        expect_no_notice(page)

        def inside(shape_name: str) -> None:
            pill = page.locator(CIRCLE_ANSWER).locator(UNDO)
            expect(pill).to_have_text("Undo")
            page.mouse.move(5, 5)
            page.wait_for_timeout(800)  # the field has grown around its words
            assert look(pill) == notice_pill, f"{shape_name}: the pill looks as the notice's own Undo does"
            shape, box = page.locator(".circle-field__shape").bounding_box(), pill.bounding_box()
            assert shape and box
            for side, gap in {
                "left": box["x"] - shape["x"], "right": shape["x"] + shape["width"] - box["x"] - box["width"],
                "top": box["y"] - shape["y"], "bottom": shape["y"] + shape["height"] - box["y"] - box["height"],
            }.items():
                assert gap >= 8, f"{shape_name}: the pill stands {gap:.1f} px from the {side} of the field"

        ask_for_the_field(session, THREE)
        inside("an answer's words")
        page.keyboard.press("Escape")  # the answer goes
        page.locator(CIRCLE_ANSWER).wait_for(state="detached")

        send(session, f'[tool:update {{"id": "SYNCOL05", "done": true}}] [slow] [say] Your report is ready. [SYN report](#doc/{doc})')
        page.wait_for_timeout(150)
        to_the_board(page)
        # What an answer links stands under its words as chips (docs/design/agent-chips.md): that is the shape it takes.
        expect(page.locator(".circle-field__answer--chips")).to_contain_text("SYN report", timeout=20000)
        inside("an answer that links a document")


def test_what_became_of_an_answer_is_kept_for_the_window_that_opens_later(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ask(session, THREE, stay=True)
        last_pill(page).click()
        wait_for(page, lambda: made_id(conn), None, "the answer is taken back")
        expect(last_pill(page)).to_have_text("Redo")

        page.reload()  # the window opens again, the server as it was
        board(session)
        send(session, "Anything else?")
        expect(page.locator(BALLOON).first.locator(UNDO)).to_have_text("Redo", timeout=10000)
        page.locator(BALLOON).first.locator(UNDO).click()
        wait_for(page, lambda: made_id(conn) is not None, True, "and it is played again from there")
