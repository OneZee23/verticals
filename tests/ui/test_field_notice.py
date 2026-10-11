"""The notice in the field (docs/design/board-undo.md): a change that leaves your view is said where the field stands, in one
line, with Undo at its right end; six seconds, or Esc, or a click elsewhere. Fixture F2, the pinned clock (Saturday 8 Aug
2026, so tomorrow is the 9th and next week begins on Monday the 10th)."""

from __future__ import annotations

import time

import psycopg
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession, activate_column
from tests.ui.undo_helpers import (
    ACTION, CIRCLE_FIELD, LINE, NOTICE, expect_no_notice, expect_notice, goal, keys, notice_text, wait_for,
)

FIELD_TEXT = ".circle-field__words textarea"


def open_menu(page: Page, vertical: str, goal_id: str) -> None:
    activate_column(page, vertical)
    page.click(f'[data-goal-id="{goal_id}"] [data-role=goal-actions-trigger]')
    page.wait_for_selector('[data-role="goal-context-menu"]', timeout=5000)


def move(page: Page, goal_id: str, how: str) -> None:
    """Tomorrow, next-week or inbox from the card's menu."""
    open_menu(page, "day", goal_id)
    page.click(f'#dropdownPortal [data-move="{how}"]')


def board(session: UiSession) -> Page:
    session.page.wait_for_selector('[data-goal-id="SYNDAY01"]', timeout=10000)
    return session.page


def test_the_notice_names_what_happened_to_which_goal(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        move(page, "SYNCOL01", "tomorrow")
        expect_notice(page, "Moved “Color check yellow” to tomorrow")
        wait_for(page, lambda: goal(conn, "SYNCOL01")[2], "2026-08-09", "tomorrow is stored")

        move(page, "SYNCOL02", "next-week")  # a new change says its own words, in the place of the older notice
        expect_notice(page, "Moved “Color check pink” to next week")
        wait_for(page, lambda: goal(conn, "SYNCOL02")[2:4], ("2026-08-10", "2026-W33"), "next week is stored")

        move(page, "SYNCOL03", "inbox")
        expect_notice(page, "Moved “Color check green” to the Inbox")
        wait_for(page, lambda: goal(conn, "SYNCOL03")[1], None, "the goal has no column")
        assert page.locator(NOTICE).count() == 1, "one notice at a time"


def test_undo_in_the_notice_puts_the_goal_back_and_the_notice_goes(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    _, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        where = lambda: goal(conn, "SYNCOL01")[1:4]  # noqa: E731
        was = where()
        move(page, "SYNCOL01", "tomorrow")
        expect_notice(page, "Moved “Color check yellow” to tomorrow")
        expect(page.locator(ACTION)).to_have_text("Undo")
        page.click(ACTION)
        wait_for(page, where, was, "the goal is back on its day")
        page.wait_for_selector('[data-vertical="day"] [data-goal-id="SYNCOL01"]', timeout=5000)
        expect_no_notice(page)  # it is in view again: nothing more to say

        page.keyboard.press(redo)  # the keys do what the button does
        wait_for(page, lambda: where()[1], "2026-08-09", "redo moves it to tomorrow again")
        expect_notice(page, "Moved “Color check yellow” to tomorrow")


def test_the_inbox_goal_is_put_back_on_its_day_by_undo(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        where = lambda: goal(conn, "SYNCOL03")[1:4]  # noqa: E731
        was = where()
        move(page, "SYNCOL03", "inbox")
        expect_notice(page, "Moved “Color check green” to the Inbox")
        page.keyboard.press(undo)
        wait_for(page, where, was, "the goal is back where it was")
        page.wait_for_selector('[data-vertical="day"] [data-goal-id="SYNCOL03"]', timeout=5000)
        expect_no_notice(page)


def scroll_day_column(page: Page, to: str) -> None:
    page.eval_on_selector(
        '[data-goal-id="SYNCOL01"]',
        "(el, to) => { const box = el.closest('.period-slide'); box.scrollTop = to === 'bottom' ? box.scrollHeight : 0 }",
        to,
    )


def test_a_goal_put_back_out_of_sight_is_said_in_the_field(ui_f2: UiSession) -> None:
    """In the open it is not: a goal that returns inside the column's visible part is seen coming back; one that returns
    below the fold, where the column has scrolled away from it, is not, and the field says it."""
    session = ui_f2
    page = board(session)
    page.set_viewport_size({"width": 1458, "height": 300})
    undo, redo = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        there = lambda: goal(conn, "SYNCOL07") is not None  # noqa: E731
        scroll_day_column(page, "bottom")
        open_menu(page, "day", "SYNCOL07")
        page.click('#dropdownPortal [data-action="delete"]')
        wait_for(page, there, False, "the goal is deleted")
        expect_notice(page, "Deleted “Color check none”")

        page.keyboard.press(undo)  # the column still shows where it stood: seen, so nothing is said
        wait_for(page, there, True, "undo brings it back")
        page.wait_for_selector('[data-goal-id="SYNCOL07"]', timeout=5000)
        page.wait_for_timeout(500)
        expect_no_notice(page)

        page.keyboard.press(redo)
        wait_for(page, there, False, "redo deletes it again")
        expect_notice(page, "Deleted “Color check none”")

        scroll_day_column(page, "top")  # the hand has gone up the column: where it lands is below the fold
        page.keyboard.press(undo)
        wait_for(page, there, True, "undo brings it back once more")
        expect_notice(page, "Put back “Color check none”")
        expect(page.locator(ACTION)).to_have_text("Redo")


def test_the_notice_is_a_black_pill_where_the_field_stands(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    circle = page.locator(".circle-field__shape").bounding_box()
    assert circle is not None
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.wait_for_timeout(300)  # let it settle in
    look = page.evaluate(
        """() => {
          const box = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
          const css = (el, p) => getComputedStyle(el).getPropertyValue(p);
          const pill = document.querySelector('[data-role="field-notice"]');
          const line = pill.querySelector('[data-role="field-notice-line"]');
          const action = pill.querySelector('[data-role="field-notice-action"]');
          const field = document.querySelector('.circle-field');
          return {
            pill: box(pill), action: box(action), line: box(line),
            pillCss: { bg: css(pill, 'background-color'), color: css(pill, 'color'), font: css(pill, 'font-size') + '/' + css(pill, 'line-height'), radius: css(pill, 'border-radius') },
            lineFont: css(line, 'font-size') + '/' + css(line, 'line-height'),
            actionCss: { bg: css(action, 'background-color'), color: css(action, 'color'), radius: css(action, 'border-radius') },
            field: { visibility: css(field, 'visibility'), opacity: css(field, 'opacity') },
            attribute: document.documentElement.hasAttribute('data-field-notice'),
            viewport: { width: innerWidth, height: innerHeight },
          };
        }"""
    )
    pill, action = look["pill"], look["action"]
    assert pill["height"] == 64, f"64 px tall, got {pill['height']}"
    assert look["pillCss"]["bg"] == "rgb(0, 0, 0)" and look["pillCss"]["color"] == "rgb(255, 255, 255)"
    assert look["lineFont"] == "15px/22px", f"one line at 15/22, got {look['lineFont']}"
    assert action["height"] == 40, f"Undo is a pill 40 px tall, got {action['height']}"
    assert look["actionCss"]["bg"] == "rgb(255, 255, 255)" and look["actionCss"]["color"] == "rgb(0, 0, 0)"
    assert abs((pill["left"] + pill["right"]) / 2 - look["viewport"]["width"] / 2) < 1, "centred, as the field is"
    assert abs((pill["top"] + pill["bottom"]) / 2 - (circle["y"] + circle["height"] / 2)) < 1, "on the circle's own centre line"
    assert pill["right"] - action["right"] == 12 and abs((action["top"] + action["bottom"]) / 2 - (pill["top"] + pill["bottom"]) / 2) < 0.6, (
        "Undo sits 12 px from the pill's end, in its middle"
    )
    assert look["line"]["height"] == 22, "the line is one line"
    assert look["attribute"] and look["field"]["visibility"] == "hidden", "the field is out of the way while the notice stands"


def test_a_long_title_is_cut_with_an_ellipsis_and_the_words_around_it_are_not(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    long = "A goal with a title long enough to fill the whole field and then some more of the same kind of words " * 2
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        conn.execute("UPDATE goals SET title = %s WHERE id = 'SYNCOL01'", (long.strip(),))
    page.reload()
    page.wait_for_selector('[data-goal-id="SYNCOL01"]', timeout=10000)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.wait_for_timeout(300)
    look = page.evaluate(
        """() => {
          const pill = document.querySelector('[data-role="field-notice"]');
          const title = pill.querySelector('.field-notice__title');
          const parts = [...pill.querySelectorAll('.field-notice__line > *')].map((el) => el.getBoundingClientRect());
          const action = pill.querySelector('[data-role="field-notice-action"]').getBoundingClientRect();
          const box = pill.getBoundingClientRect();
          return {
            cut: title.scrollWidth > title.clientWidth, overflow: getComputedStyle(title).textOverflow,
            width: box.width, viewport: innerWidth, lineEnd: Math.max(...parts.map((r) => r.right)), actionLeft: action.left,
            high: pill.querySelector('[data-role="field-notice-line"]').getBoundingClientRect().height,
            text: pill.querySelector('[data-role="field-notice-line"]').textContent,
          };
        }"""
    )
    assert look["cut"] and look["overflow"] == "ellipsis", "the title is cut with an ellipsis"
    assert look["width"] <= 560 and look["width"] <= look["viewport"] - 32, f"the pill stays within its width, got {look['width']}"
    assert look["lineEnd"] <= look["actionLeft"], "the line ends before Undo begins"
    assert look["high"] == 22, "still one line"
    assert look["text"].startswith("Moved “A goal with a title") and look["text"].endswith("” to tomorrow"), (
        "the words around the title are whole"
    )


def test_the_notice_stays_six_seconds_and_the_field_comes_back(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    shown = time.monotonic()
    page.wait_for_timeout(5000 - int((time.monotonic() - shown) * 1000))
    expect(page.locator(NOTICE)).to_be_visible()  # still there at five seconds
    gone = None
    while time.monotonic() - shown < 7.5:
        if page.locator(NOTICE).count() == 0:
            gone = time.monotonic() - shown
            break
        page.wait_for_timeout(25)
    assert gone is not None, "the notice never went"
    assert 5.7 <= gone <= 7.0, f"the notice stays six seconds, it stayed {gone:.2f}"
    assert page.evaluate("document.documentElement.hasAttribute('data-field-notice')") is False
    expect(page.locator(CIRCLE_FIELD)).to_be_visible()
    assert page.locator(CIRCLE_FIELD).evaluate("el => getComputedStyle(el).visibility") == "visible"


def test_the_pointer_on_the_notice_holds_the_time(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    shown = time.monotonic()
    page.wait_for_timeout(4500 - int((time.monotonic() - shown) * 1000))
    page.locator(ACTION).hover()  # the hand is on Undo as the time runs out
    page.wait_for_timeout(3000)  # well past the sixth second
    expect(page.locator(NOTICE)).to_be_visible()
    page.mouse.move(40, 40)  # the hand leaves: the rest of the time, and not less than two seconds
    left = time.monotonic()
    wait_for(page, lambda: page.locator(NOTICE).count(), 0, "the notice goes after the hand has left", timeout=4.5)
    assert 1.4 <= time.monotonic() - left <= 3.8, f"it went {time.monotonic() - left:.2f} s after the hand left"


def test_esc_ends_the_notice_at_once(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect_no_notice(page)
    expect(page.locator(CIRCLE_FIELD)).to_be_visible()


def test_a_letter_typed_while_the_notice_stands_puts_the_field_back_and_goes_into_it(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.keyboard.press("x")  # the field's first letter: it must be back to take it
    expect_no_notice(page)
    expect(page.locator(FIELD_TEXT)).to_have_value("x")
    assert page.evaluate("document.activeElement === document.querySelector('.circle-field__words textarea')")

    page.locator(FIELD_TEXT).fill("")
    page.keyboard.press("Escape")
    page.locator(FIELD_TEXT).blur()
    move(page, "SYNCOL02", "tomorrow")  # and ⌘K, the other way to the field
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.keyboard.press(f"{undo.split('+')[0]}+k")
    expect_no_notice(page)
    assert page.evaluate("document.activeElement === document.querySelector('.circle-field__words textarea')")


def test_a_click_elsewhere_ends_the_notice_and_still_reaches_what_it_aimed_at(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        move(page, "SYNCOL01", "tomorrow")
        expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
        page.click('[data-goal-id="SYNCOL02"] > .goal-card__row label.checkbox')  # a tick, somewhere else
        expect_no_notice(page)
        wait_for(page, lambda: goal(conn, "SYNCOL02")[4], True, "the click went on to tick the goal")
        assert goal(conn, "SYNCOL01")[2] == "2026-08-09", "the notice's own change was left alone"


def test_a_click_on_the_notice_itself_does_not_end_it(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    move(page, "SYNCOL01", "tomorrow")
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.locator(LINE).click()
    page.wait_for_timeout(400)
    expect(page.locator(NOTICE)).to_be_visible()
    assert notice_text(page) == "Moved “Color check yellow” to tomorrow"


def test_the_keys_stay_the_fields_own_in_a_text_field(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click('[data-goal-id="SYNCOL01"] > .goal-card__row label.checkbox')
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")

        # In the field itself the keys are the field's: typing, then ⌘Z, takes back typing and never the tick.
        page.click(".circle-field__shape")
        page.locator(FIELD_TEXT).type("some words")
        page.keyboard.press(undo)
        page.wait_for_timeout(400)
        assert goal(conn, "SYNCOL01")[4] is True, "a key in the field did not touch the board"
        page.keyboard.press("Escape")
        page.locator(FIELD_TEXT).blur()

        # The keydown itself is left alone in a text field, and taken on a focused checkbox, which is no text field.
        press = """(args) => {
          const el = document.querySelector(args.selector); el.focus();
          const event = new KeyboardEvent('keydown', { key: 'z', metaKey: args.apple, ctrlKey: !args.apple, bubbles: true, cancelable: true });
          el.dispatchEvent(event);
          return event.defaultPrevented;
        }"""
        apple = undo.startswith("Meta")
        assert page.evaluate(press, {"selector": FIELD_TEXT, "apple": apple}) is False, "the field keeps ⌘Z"
        assert goal(conn, "SYNCOL01")[4] is True
        checkbox = '[data-goal-id="SYNCOL01"] > .goal-card__row input.checkbox__input'
        assert page.evaluate(press, {"selector": checkbox, "apple": apple}) is True, "a focused checkbox is not a text field"
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "so the keys took the tick back")


def test_a_title_being_edited_keeps_its_keys(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click('[data-goal-id="SYNCOL02"] > .goal-card__row label.checkbox')
        wait_for(page, lambda: goal(conn, "SYNCOL02")[4], True, "the tick is stored")
        activate_column(page, "day")
        page.click('[data-goal-id="SYNCOL06"] > [data-cap=reorder]')
        title = '[data-goal-id="SYNCOL06"] [data-cap="edit-title"]'
        page.wait_for_selector(title, timeout=5000)
        page.click(title)
        editor = f"{title}:is(textarea)"
        page.fill(editor, "A title in the making")
        page.keyboard.press(undo)
        page.wait_for_timeout(400)
        assert goal(conn, "SYNCOL02")[4] is True, "⌘Z in a title is the title's own"
        page.press(editor, "Escape")
