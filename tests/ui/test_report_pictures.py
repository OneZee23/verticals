"""Pictures above the field (docs/design/bug-reports.md). A picture dropped on the window or pasted into the field stands above
the field, in the stack a goal let go over it waits in, and the field widens to hold them; past a few they overlap, so any
number still fits; the one under the pointer lifts out, bigger. The words typed beside them describe the report and narrow
nothing. F2, the browser clock pinned to 2026-08-08, motion off (the tests look at where things stand, not how they got there)."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession
from tests.ui.report_support import FIELD, ITEM, PIC, SHAPE, STACK_GAP, box, drag, drop, file, files, paste, text_file

CIRCLE = ".circle-field"
LIFT = 2.6  # FieldPictures.vue's --lift
PICKED = re.compile(r"\bis-picked\b")
HIT = ".field-pictures__hit"
CROSS = '[data-role="field-picture-remove"]'


def _board(page: Page) -> None:
    page.wait_for_selector(".goal-card__row")


def _pictures(page: Page, count: int, **size: int) -> None:
    drop(page, files(count, **size))
    expect(page.locator(ITEM)).to_have_count(count)


def _centre(page: Page, nth: int) -> tuple[float, float]:
    found = box(page, PIC, nth)
    return found["x"] + found["width"] / 2, found["y"] + found["height"] / 2


def _heights(page: Page) -> list[float]:
    return [round(found["height"], 1) for found in (box(page, PIC, n) for n in range(page.locator(ITEM).count()))]


def test_pictures_dropped_on_the_window_stand_above_the_field_and_widen_it(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    assert box(page, SHAPE)["width"] == 84
    # The page takes the drop: a file let go on a web view would otherwise open in it.
    assert drop(page, files(3)) is True
    expect(page.locator(ITEM)).to_have_count(3)

    field = box(page, SHAPE)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "open")
    expect(page.locator(FIELD)).to_have_attribute("aria-label", "Say what you see and what you want")
    assert field["width"] > 200
    # Each is 56 px tall and as wide as its picture is (160 x 100 makes 90), in a row 8 px apart, over the field, inside it.
    for n in range(3):
        found = box(page, PIC, n)
        assert found["height"] == pytest.approx(56, abs=0.6) and found["width"] == pytest.approx(90, abs=0.6), found
        assert found["y"] + found["height"] <= field["y"], "the stack stands above the field"
        assert found["x"] >= field["x"] and found["x"] + found["width"] <= field["x"] + field["width"] + 0.5, (found, field)
    for n in range(2):
        a, b = box(page, PIC, n), box(page, PIC, n + 1)
        assert b["x"] - (a["x"] + a["width"]) == pytest.approx(STACK_GAP, abs=0.6)
    # The pictures are the ones dropped, in the order they came.
    srcs = page.locator(f"{PIC} img").evaluate_all("images => images.map((img) => img.naturalWidth + 'x' + img.naturalHeight)")
    assert srcs == ["160x100"] * 3
    # The field is free for the words: the keys are in it at once.
    expect(page.locator(FIELD)).to_be_focused()


def _z(page: Page, nth: int) -> str:
    return page.locator(PIC).nth(nth).evaluate("pic => getComputedStyle(pic).zIndex")


def test_the_one_under_the_pointer_lifts_out_bigger_and_settles_back(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 3)
    assert _heights(page) == [56.0, 56.0, 56.0]

    x, y = _centre(page, 1)
    page.mouse.move(x, y)
    lifted = box(page, PIC, 1)
    assert lifted["height"] == pytest.approx(56 * LIFT, abs=1.5) and lifted["width"] == pytest.approx(90 * LIFT, abs=1.5), lifted
    # It rises out of the row from its bottom edge and lies over its neighbours; they stay as they were.
    assert lifted["y"] + lifted["height"] == pytest.approx(box(page, PIC, 0)["y"] + 56 - 6, abs=1.5)
    assert _heights(page)[0] == 56.0 and _heights(page)[2] == 56.0
    assert _z(page, 1) == "2" and _z(page, 0) == "auto" and _z(page, 2) == "auto"
    assert lifted["y"] > 0 and lifted["x"] > 0, "it is whole on the screen"
    # What the pointer is on is the picture's place in the row, so the lifted one lets it through to its neighbours: moving
    # along the row lifts them one after the other, though the lifted picture lies over them.
    x2, y2 = _centre(page, 2)
    page.mouse.move(x2, y2, steps=6)
    page.wait_for_function("() => [...document.querySelectorAll('.field-pictures__pic')].map((p) => Math.round(p.getBoundingClientRect().height))[2] > 100")
    assert _heights(page)[1] == 56.0

    page.mouse.move(40, 40)
    page.wait_for_function("() => [...document.querySelectorAll('.field-pictures__pic')].every((p) => Math.round(p.getBoundingClientRect().height) === 56)")


def test_a_press_picks_a_picture_and_its_cross_takes_it_off(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 3)
    # Looking is the pointer's; the cross is for one picked.
    x, y = _centre(page, 1)
    page.mouse.move(x, y)
    expect(page.locator(ITEM).nth(1).locator(CROSS)).to_have_css("opacity", "0")
    page.locator(HIT).nth(1).click()
    expect(page.locator(ITEM).nth(1)).to_have_class(PICKED)
    expect(page.locator(ITEM).nth(1).locator(CROSS)).to_have_css("opacity", "1")
    cross = box(page, CROSS, 1)
    lifted = box(page, PIC, 1)
    assert cross["x"] + cross["width"] / 2 == pytest.approx(lifted["x"] + lifted["width"], abs=1.5), "on the lifted picture's corner"
    assert cross["y"] + cross["height"] / 2 == pytest.approx(lifted["y"], abs=1.5)
    page.locator(ITEM).nth(1).locator(CROSS).click()
    expect(page.locator(ITEM)).to_have_count(2)


def test_past_a_few_they_overlap_and_any_number_still_fits_inside_the_field(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 4)
    # Four of 90 and their gaps are 384 px, which the field holds: none overlaps.
    for n in range(3):
        a, b = box(page, PIC, n), box(page, PIC, n + 1)
        assert b["x"] - (a["x"] + a["width"]) == pytest.approx(STACK_GAP, abs=0.6)

    drop(page, files(1))
    expect(page.locator(ITEM)).to_have_count(5)
    # The fifth takes the stack past what the field gives it (440): they overlap now, and none is outside the field.
    a, b = box(page, PIC, 0), box(page, PIC, 1)
    assert b["x"] < a["x"] + a["width"]
    field = box(page, SHAPE)
    last = box(page, PIC, 4)
    assert last["x"] + last["width"] <= field["x"] + field["width"] + 0.5

    # Many: nothing is cut off, every one is still there, each further right than the one before, all inside the field.
    drop(page, files(9, 80, 50))
    expect(page.locator(ITEM)).to_have_count(14)
    field = box(page, SHAPE)
    assert field["width"] <= 720
    lefts = [box(page, PIC, n)["x"] for n in range(14)]
    assert lefts == sorted(lefts) and len(set(lefts)) == 14, lefts
    assert box(page, PIC, 13)["x"] + box(page, PIC, 13)["width"] <= field["x"] + field["width"] + 0.5
    assert box(page, PIC, 0)["x"] >= field["x"] - 0.5

    # Every one is reachable: the seventh lifts out over the others.
    seventh = box(page, PIC, 6)
    page.mouse.move(seventh["x"] + 3, seventh["y"] + seventh["height"] / 2)
    assert box(page, PIC, 6)["height"] == pytest.approx(56 * LIFT, abs=1.5)
    assert _z(page, 6) == "2"
    assert _heights(page).count(56.0) == 13


def test_there_is_no_cap_on_how_many(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 60, width=80, height=50)
    field = box(page, SHAPE)
    lefts = [box(page, PIC, n)["x"] for n in range(60)]
    assert lefts == sorted(lefts)
    assert all(box(page, PIC, n)["x"] + box(page, PIC, n)["width"] <= field["x"] + field["width"] + 0.5 for n in (0, 30, 59))


def test_a_picture_pasted_into_the_field_stands_above_it_and_words_paste_as_words(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    # Words with a picture, as a page copies them, are words: the page leaves the paste to the field.
    assert paste(page, files(1), text="copied words") is False
    expect(page.locator(ITEM)).to_have_count(0)
    # A picture alone, as a screenshot copied from the screen is, is taken.
    assert paste(page, [file("screenshot.png")]) is True
    expect(page.locator(ITEM)).to_have_count(1)
    expect(page.locator(FIELD)).to_be_focused()
    assert paste(page, [file("another.png", seed=3)]) is True
    expect(page.locator(ITEM)).to_have_count(2)


def test_a_paste_into_another_editor_is_left_to_it(ui_f2: UiSession) -> None:
    """A document's body has its own rule for a picture pasted into it (it drops it): the field does not take that paste."""
    page = ui_f2.page
    _board(page)
    taken = page.evaluate(
        """() => {
          const editor = document.createElement('div')
          editor.contentEditable = 'true'
          document.body.append(editor)
          editor.focus()
          const data = new DataTransfer()
          data.items.add(new File([new Uint8Array([1])], 'x.png', { type: 'image/png' }))
          return !editor.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
        }""")
    assert taken is False
    expect(page.locator(ITEM)).to_have_count(0)


def test_files_that_are_no_pictures_are_kept_from_opening_and_not_taken(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    url = page.url
    # A file dropped on a web view would open in it, in place of the app: the page takes the drop and does nothing with it.
    assert drop(page, [text_file()]) is True
    page.wait_for_timeout(200)
    assert page.url == url
    expect(page.locator(ITEM)).to_have_count(0)
    page.wait_for_selector(".goal-card__row")
    # Words dragged over (no file in them) are not the page's to take.
    assert page.evaluate(
        """() => { const e = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }); return !document.body.dispatchEvent(e) }""") is False


def test_a_file_dragged_over_the_window_opens_the_field_and_says_what_the_drop_does(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "rest")
    drag(page, files(1), ["dragenter", "dragover"])
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "open")
    expect(page.locator(FIELD)).to_have_attribute("aria-label", "Drop pictures")
    assert box(page, SHAPE)["width"] > 150
    # Out again without a drop: the circle is the circle.
    drag(page, files(1), ["dragleave"])
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "rest")
    expect(page.locator(ITEM)).to_have_count(0)


def test_the_words_beside_the_pictures_narrow_nothing(ui_f2: UiSession) -> None:
    """Typing in the field filters the board, as Find does; with pictures above it the words say what the person sees and wants, and the board
    stays as it is while they are written."""
    page = ui_f2.page
    _board(page)
    before = page.locator(".goal-card__row").count()
    assert before > 3
    _pictures(page, 2)
    page.locator(FIELD).press_sequentially("the card jumped back when I dropped it")
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "typing")
    page.wait_for_timeout(500)  # past the finding's settle time: the server would have been asked by now
    assert page.locator(".goal-card__row").count() == before
    expect(page.locator(".pattern-vertical-board--nothing-found")).to_have_count(0)
    # The send arrow is the report's.
    expect(page.locator(".circle-field__send")).to_have_attribute("aria-label", "Make the report")


def test_backspace_picks_the_last_picture_and_a_second_takes_it_off_and_esc_sends_them_away(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 3)
    page.locator(FIELD).focus()
    page.keyboard.press("Backspace")
    # Picked, it is lifted as the pointer lifts one.
    expect(page.locator(ITEM).nth(2)).to_have_class(PICKED)
    assert box(page, PIC, 2)["height"] == pytest.approx(56 * LIFT, abs=1.5)
    page.keyboard.press("Backspace")
    expect(page.locator(ITEM)).to_have_count(2)
    expect(page.locator(ITEM).nth(1)).to_have_class(PICKED)
    page.keyboard.press("Escape")
    expect(page.locator(ITEM).nth(1)).not_to_have_class(PICKED)
    expect(page.locator(ITEM)).to_have_count(2)
    page.keyboard.press("Escape")
    expect(page.locator(ITEM)).to_have_count(0)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "open")  # focused still: the field waits for words


def test_a_tap_picks_a_picture_and_a_second_tap_lets_go(ui_f2: UiSession) -> None:
    page = ui_f2.page
    _board(page)
    _pictures(page, 2)
    page.locator(HIT).nth(0).click()
    expect(page.locator(ITEM).nth(0)).to_have_class(PICKED)
    page.mouse.move(40, 40)
    assert box(page, PIC, 0)["height"] == pytest.approx(56 * LIFT, abs=1.5), "a picked one stays lifted when the pointer leaves"
    page.locator(HIT).nth(0).click()
    expect(page.locator(ITEM).nth(0)).not_to_have_class(PICKED)
