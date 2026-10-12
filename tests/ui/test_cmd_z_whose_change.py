"""⌘Z, and whose change it means (docs/design/agent-answer-undo.md). The owner: "If action was human and it was less than 5 seconds
ago, it's definietly human." and "maybe agent should ask what exactly to cancel if that's unclear". The rules, in order:

  (a) inside any text the key is the text's own: it never asks and never takes back a change on the board;
  (b) the person's own last change is less than 5 seconds old: it is taken back at once, whatever an agent did;
  (c) no agent's answer changed the board since the person's own last change: taken back at once, however old;
  (d) an agent's answer changed the board after the person's last change, and that is 5 seconds old or more, or there is none:
      the field asks, in the notice's shape: "Take back" and the candidates as pills. A pick takes that back; Esc, a click
      elsewhere or six seconds take nothing back. It is the app's own question: no model is asked.

Fixture F2 behind the desktop gateway with a real MCP server (`answer_support.py`). The 5 seconds are the page's clock, moved by the
tests' own clock control (`page.clock`): nothing here waits for them, except the six seconds the question itself stands."""

from __future__ import annotations

import time

import psycopg
import pytest
from playwright.sync_api import expect

from tests.ui.answer_support import (
    CHOICE, CIRCLE_ANSWER, ONE, TWO, UNDO, ask, ask_for_the_field, board_write_log, board_writes, choices, held, later, mcp_server,  # noqa: F401
    outside_agent, reads, sent_to_the_agent, ui_answers, ui_reduced_motion, wait_for_reads,  # noqa: F401
)
from tests.ui.conftest import UiSession
from tests.ui.test_board_undo import TICK, board
from tests.ui.test_cmd_z_in_text import PLACES, TYPED, text_of
from tests.ui.undo_helpers import NOTICE, expect_no_notice, goal, keys, notice_text, wait_for

OWN = "Completed “Color check yellow”"
THE_AGENTS = "2 changes by the agent"


def own_change(session: UiSession, conn: psycopg.Connection) -> None:
    """The person ticks a goal, and the page has heard that the write went through."""
    before = len(board_writes(session))
    session.gestures.click(TICK)
    wait_for(session.page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")
    wait_for(session.page, lambda: len(board_writes(session)), before + 1, "the tick is logged")


def the_answer_stands(conn: psycopg.Connection) -> None:
    """What TWO did, still there."""
    assert goal(conn, "SYNORD02")[1] == "month" and goal(conn, "SYNCOL03")[4] is True


def nothing_taken_back(session: UiSession, conn: psycopg.Connection, since: int) -> None:
    """The tick and the answer stand, and the page wrote nothing to the board; no model was asked."""
    assert goal(conn, "SYNCOL01")[4] is True, "the person's tick stands"
    the_answer_stands(conn)
    assert board_writes(session, since) == [], "no write went out"
    assert sent_to_the_agent(session, since) == 0, "the question is the app's own: no message went to the agent"


def asked(session: UiSession, undo: str) -> None:
    """⌘Z, and the question it puts in the field."""
    session.page.keyboard.press(undo)
    expect(session.page.locator(NOTICE)).to_be_visible(timeout=5000)
    wait_for(session.page, lambda: notice_text(session.page), "Take back", "the question says what it asks")


# --- (a) inside text -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("place", list(PLACES))
def test_inside_any_text_cmd_z_is_the_texts_own_and_never_asks(ui_answers: UiSession, place: str) -> None:
    session = ui_answers
    page = board(session)
    undo, redo = keys(page)
    reach, own_save = PLACES[place]
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        ask(session, TWO)
        later(page, 6)  # outside text, this is a question: an answer came after a change of the person's that is 6 seconds old

        target = reach(session, conn)
        before_typing = text_of(target)
        start = len(session.request_log)
        page.keyboard.type(TYPED)
        assert TYPED in text_of(target), f"{place}: the words were typed"

        page.keyboard.press(undo)
        page.wait_for_timeout(300)
        assert text_of(target) == before_typing, f"{place}: the typing is undone, by the text's own ⌘Z (got {text_of(target)!r})"
        expect_no_notice(page)
        page.keyboard.press(redo)
        page.wait_for_timeout(300)
        assert TYPED in text_of(target), f"{place}: ⇧⌘Z types it again, in the text"
        expect_no_notice(page)
        page.wait_for_timeout(1500)  # what a place saves of its own is on its way by now
        stray = [line for line in board_write_log(session, start) if not (own_save and own_save.search(line))]
        assert stray == [], f"{place}: no write goes out for the key: {stray}"
        assert goal(conn, "SYNCOL01")[4] is True, f"{place}: the person's tick stands"
        the_answer_stands(conn)


# --- (b) and (c): at once ------------------------------------------------------------------------------------------------


def test_the_persons_own_change_less_than_five_seconds_old_is_taken_back_at_once_whatever_an_agent_did(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        ask(session, TWO)  # an agent's answer after it
        later(page, 4)
        start = len(session.request_log)

        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the tick, the person's own, is taken back at once")
        expect_no_notice(page)  # no question: the tick is in view, so nothing is said either
        the_answer_stands(conn)
        assert sent_to_the_agent(session, start) == 0


def test_an_answer_that_came_before_the_persons_change_does_not_make_cmd_z_ask(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        ask(session, TWO)  # the answer came first
        own_change(session, conn)  # the person's change after it
        later(page, 600)  # ten minutes on
        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "taken back at once: no answer changed the board since")
        expect_no_notice(page)
        the_answer_stands(conn)


def test_an_answer_that_changed_nothing_on_the_board_does_not_make_cmd_z_ask(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        ask(session, "Just a word")  # an answer, after the person's change, that wrote nothing
        later(page, 600)
        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "taken back at once, however old")
        expect_no_notice(page)


# --- (d): the question ---------------------------------------------------------------------------------------------------


def test_when_an_answer_came_after_a_change_five_seconds_old_the_field_asks_and_nothing_is_taken_back_yet(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        ask(session, TWO)
        later(page, 5.5)
        start = len(session.request_log)

        asked(session, undo)
        assert choices(page) == [OWN, THE_AGENTS], "the person's own last change, as the notice words it, and the agent's last answer"
        assert page.locator(f"{NOTICE} [data-role=field-notice-action]").count() == 0, "a question has pills, no Undo"
        page.wait_for_timeout(400)
        nothing_taken_back(session, conn, start)


@pytest.mark.parametrize("pick", ["own", "agent"])
def test_a_pick_takes_back_that_and_only_that(ui_answers: UiSession, pick: str) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order = goal(conn, "SYNORD02")
        own_change(session, conn)
        ask(session, TWO)
        later(page, 6)
        asked(session, undo)

        page.locator(CHOICE).nth(0 if pick == "own" else 1).click()
        if pick == "own":
            wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the person's tick is taken back")
            the_answer_stands(conn)
        else:
            wait_for(page, lambda: goal(conn, "SYNORD02"), order, "the answer's move is taken back")
            wait_for(page, lambda: goal(conn, "SYNCOL03")[4], False, "and its tick")
            assert goal(conn, "SYNCOL01")[4] is True, "the person's own tick stands"
        expect(page.locator(NOTICE).filter(has=page.locator(CHOICE))).to_have_count(0)  # the question is gone

        if pick == "agent":
            # The answer is taken back, so it is nobody's to ask about: the next ⌘Z is the person's own, at once.
            page.keyboard.press(undo)
            wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the next ⌘Z takes the person's own change")


def test_with_no_change_of_their_own_the_question_offers_the_answer_alone_in_the_words_of_the_one_goal_it_changed(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order = goal(conn, "SYNORD02")
        ask(session, ONE)
        asked(session, undo)
        assert choices(page) == ["Moved “Order two” to this month by the agent"]
        assert goal(conn, "SYNORD02")[1] == "month", "nothing is taken back until a pick"
        page.locator(CHOICE).click()
        wait_for(page, lambda: goal(conn, "SYNORD02"), order, "the pick takes the answer back")


def test_esc_and_a_click_elsewhere_and_the_six_seconds_take_nothing_back(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        ask(session, TWO)
        later(page, 6)
        start = len(session.request_log)

        asked(session, undo)
        page.keyboard.press("Escape")
        expect_no_notice(page)
        nothing_taken_back(session, conn, start)

        asked(session, undo)
        page.mouse.click(5, 5)  # a click elsewhere
        expect_no_notice(page)
        nothing_taken_back(session, conn, start)

        asked(session, undo)
        shown = time.monotonic()
        page.wait_for_timeout(4500)
        expect(page.locator(NOTICE)).to_be_visible()  # still asking at four and a half seconds
        gone = None
        while time.monotonic() - shown < 7.5:
            if page.locator(NOTICE).count() == 0:
                gone = time.monotonic() - shown
                break
            page.wait_for_timeout(25)
        assert gone is not None and 5.6 <= gone <= 7.0, f"the question stands six seconds, it stood {gone}"
        nothing_taken_back(session, conn, start)


def test_a_gateway_that_does_not_answer_does_not_hold_the_key(ui_answers: UiSession, mcp_server) -> None:  # noqa: F811
    """⌘Z is the app's own and instant: it asks the gateway which answers ended, but does not wait long for the reply."""
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        own_change(session, conn)
        seen = reads(session)
        with held(mcp_server):
            pressed = time.monotonic()
            page.keyboard.press(undo)
            wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the tick is taken back without the gateway's word", timeout=3)
            assert time.monotonic() - pressed < 2.0, f"the key waited {time.monotonic() - pressed:.1f} s for the gateway"
        wait_for_reads(session, seen)  # the read that was held is answered now


# --- an answer is not a step of the keys -----------------------------------------------------------------------------------


def test_an_answer_is_never_a_step_of_the_keys(ui_answers: UiSession) -> None:
    session = ui_answers
    page = board(session)
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        order = goal(conn, "SYNORD02")
        ask_for_the_field(session, ONE)
        page.locator(CIRCLE_ANSWER).locator(UNDO).click()
        wait_for(page, lambda: goal(conn, "SYNORD02"), order, "the answer is taken back by its own Undo")
        start = len(session.request_log)

        page.keyboard.press(redo)  # ⇧⌘Z does not play the answer again
        page.keyboard.press(undo)  # and ⌘Z has nothing: the answer is taken back, so it is nobody's to ask about
        page.wait_for_timeout(600)
        expect_no_notice(page)
        assert board_writes(session, start) == []
        assert goal(conn, "SYNORD02") == order

        page.locator(CIRCLE_ANSWER).locator(UNDO).click()  # Redo, from the answer
        wait_for(page, lambda: goal(conn, "SYNORD02")[1], "month", "the answer is played again from its own Redo")
        asked(session, undo)  # standing again, with nothing of the person's own before it: ⌘Z asks
        assert choices(page) == ["Moved “Order two” to this month by the agent"]
        page.keyboard.press("Escape")
        assert goal(conn, "SYNORD02")[1] == "month"


# --- an agent the app did not start --------------------------------------------------------------------------------------


def test_an_agent_the_app_did_not_start_has_no_undo_and_never_makes_cmd_z_ask(ui_answers: UiSession, mcp_server) -> None:  # noqa: F811
    session = ui_answers
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn, outside_agent(mcp_server) as agent:
        own_change(session, conn)
        agent("schedule", id="SYNORD02", vertical="month", anchor_date="2026-08-08")  # no conversation of the app's behind it
        page.wait_for_selector('[data-vertical="month"] [data-goal-id="SYNORD02"]', timeout=10000)
        later(page, 60)

        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "⌘Z is the person's own: at once, however old")
        expect_no_notice(page)
        assert goal(conn, "SYNORD02")[1] == "month", "and the agent's move is left"
        assert page.locator(UNDO).count() == 0, "an agent the app did not start has no Undo anywhere"
