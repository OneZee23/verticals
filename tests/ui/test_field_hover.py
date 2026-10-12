"""Under the pointer the field's circle only widens; a click, a key or ⌘K opens it (docs/design/field-hover.md). Pointing
at the circle used to open it, from 84 to 201 px, saying "Find or ask"; now it grows to 116 px, its line from 3 × 24 to
5 × 46 px and the Documents and Inbox buttons above it to 38 px, and nothing opens. The change comes at once and settles
back in 200 ms on the app's ease-out token, and with reduced motion nothing moves. F2, the browser clock pinned to
2026-08-08."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession
from tests.ui.test_agent_conversation import ui_agent  # noqa: F401  (the fixture)
from tests.ui.views import CIRCLE, FIELD, switch_view

ROOT = ".circle-field"
LINE = ".circle-field__line:not(.circle-field__line--second)"
GOAL_ROW = '[data-goal-id="SYNDAY01"] > .goal-card__row'
IDENTITY = ("none", "matrix(1, 0, 0, 1, 0, 0)")


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    return getattr(request, "param", "reduce")


def _centre(page: Page) -> tuple[float, float]:
    box = page.locator(CIRCLE).bounding_box()
    assert box is not None
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _point_at_the_circle(page: Page) -> None:
    page.mouse.move(*_centre(page), steps=4)


def _away(page: Page) -> None:
    page.mouse.move(100, 300, steps=4)  # over the board, nowhere near the field


def _size(page: Page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, selector
    return box["width"], box["height"]


def _css(page: Page, selector: str, prop: str) -> str:
    return page.locator(selector).first.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)


def _buttons(page: Page) -> list[dict]:
    """The buttons above the circle: name, size, and how far the row's middle is from the circle's middle."""
    return page.evaluate(
        """() => {
          const mid = (b) => b.left + b.width / 2;
          const circle = document.querySelector('.circle-field__shape').getBoundingClientRect();
          const buttons = [...document.querySelectorAll('.circle-tag')].map((el) => {
            const b = el.getBoundingClientRect();
            return { tag: el.dataset.tag, w: b.width, h: b.height, left: b.left, right: b.right, bottom: b.bottom,
                     height: getComputedStyle(el).height, radius: getComputedStyle(el).borderRadius };
          });
          const left = Math.min(...buttons.map((b) => b.left)), right = Math.max(...buttons.map((b) => b.right));
          return buttons.map((b) => ({ ...b, rowOff: (left + right) / 2 - mid(circle), circleTop: circle.top }));
        }"""
    )


def test_pointing_at_the_circle_widens_it_and_opens_nothing(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    _away(page)
    assert _size(page, CIRCLE) == (84, 84)
    expect(page.locator(".circle-tags.is-shown")).to_have_count(0)

    _point_at_the_circle(page)
    width, height = _size(page, CIRCLE)
    assert abs(width - 116) < 0.5 and abs(height - 84) < 0.5, (width, height)
    # Still the circle: no caret, no caption, and the field holds no focus.
    expect(page.locator(ROOT)).to_have_attribute("data-state", "rest")
    expect(page.locator(f"{ROOT}[data-focused]")).to_have_count(0)
    expect(page.locator(FIELD)).not_to_be_focused()
    expect(page.locator(".circle-field__words")).to_have_css("opacity", "0")
    # Round ends: half its height.
    expect(page.locator(".circle-field__surface")).to_have_css("border-radius", "42px")
    # The buttons come in with it.
    expect(page.locator(".circle-tags.is-shown")).to_have_count(1)

    _away(page)
    assert _size(page, CIRCLE) == (84, 84)
    expect(page.locator(".circle-tags.is-shown")).to_have_count(0)


def test_the_circle_the_line_and_the_buttons_have_their_sizes_under_the_pointer(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    _away(page)
    assert _css(page, LINE, "height") == "24px" and _css(page, LINE, "width") == "3px"
    assert [b["height"] for b in _buttons(page)] == ["28px", "28px"]

    _point_at_the_circle(page)
    # The line: 5 px wide and 46 px tall, upright in the circle's middle, 19 px from its top and from its bottom, and
    # still round-ended.
    line = page.locator(LINE).bounding_box()
    shape = page.locator(CIRCLE).bounding_box()
    assert line is not None and shape is not None
    assert abs(line["height"] - 46) < 0.5 and abs(line["width"] - 5) < 0.1, line
    assert (_css(page, LINE, "width"), _css(page, LINE, "height"), _css(page, LINE, "borderRadius")) == ("5px", "46px", "2.5px")
    assert abs(line["x"] + line["width"] / 2 - (shape["x"] + shape["width"] / 2)) < 0.5
    assert abs(line["y"] + line["height"] / 2 - (shape["y"] + shape["height"] / 2)) < 0.5
    assert abs((line["y"] - shape["y"]) - 19) < 0.5 and abs((shape["y"] + shape["height"]) - (line["y"] + line["height"]) - 19) < 0.5
    # The Documents and Inbox buttons: 38 px, round, centred over the circle and above it.
    buttons = _buttons(page)
    assert [b["tag"] for b in buttons] == ["docs", "inbox"]
    for b in buttons:
        assert abs(b["w"] - 38) < 0.5 and abs(b["h"] - 38) < 0.5, b
        assert b["height"] == "38px" and b["radius"] == "19px", b
        assert b["bottom"] <= b["circleTop"], b
        assert abs(b["rowOff"]) < 1, b


def test_with_the_agent_the_buttons_are_one_centred_row_and_its_menu_opens_above_them(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    page.wait_for_selector(".goal-card__row")
    _point_at_the_circle(page)
    buttons = _buttons(page)
    assert [b["tag"] for b in buttons] == ["agent", "docs", "inbox"]
    assert all(b["height"] == "38px" for b in buttons), buttons
    assert abs(buttons[0]["rowOff"]) < 1, buttons
    page.locator('.circle-tag[data-tag="agent"]').click()
    picker = page.locator('[role="dialog"][aria-label="Agent settings"]')
    expect(picker).to_be_visible()
    chip, menu = page.locator('.circle-tag[data-tag="agent"]').bounding_box(), picker.bounding_box()
    assert chip is not None and menu is not None
    # 8 px of air between the menu and the button, as with the 28 px button.
    assert abs((chip["y"] - 8) - (menu["y"] + menu["height"])) < 1, (chip, menu)


def test_in_the_inbox_the_field_rests_open_and_pointing_at_it_changes_nothing_more(ui_f2: UiSession) -> None:
    """The hover is the resting circle's: the Inbox's field already rests open, with its invitation to write."""
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    switch_view(page, "inbox")
    _away(page)
    expect(page.locator(ROOT)).to_have_attribute("data-state", "open")
    before = _size(page, CIRCLE)
    _point_at_the_circle(page)
    assert _size(page, CIRCLE) == before
    expect(page.locator(f"{ROOT}[data-pointed]")).to_have_count(0)
    assert [b["height"] for b in _buttons(page)] == ["28px", "28px"]  # the open field's buttons, at its left end


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_line_stands_upright_and_does_not_follow_the_pointer(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(GOAL_ROW)
    # Pointed at a goal, the mascot's line watches it: it leans.
    page.locator(GOAL_ROW).hover()
    page.wait_for_function(
        "() => !['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(getComputedStyle(document.querySelector('.circle-field__line')).transform)",
        timeout=5000,
    )
    # On the circle it stands upright at once, and the hand moving over the circle moves nothing.
    _point_at_the_circle(page)
    assert _css(page, LINE, "transform") in IDENTITY
    x, y = _centre(page)
    centre = page.locator(LINE).bounding_box()
    assert centre is not None
    for dx, dy in ((30, -12), (-30, 12), (0, 0)):
        page.mouse.move(x + dx, y + dy, steps=3)
        now = page.locator(LINE).bounding_box()
        assert now is not None and abs(now["x"] - centre["x"]) < 0.5 and abs(now["y"] - centre["y"]) < 0.5, (dx, dy)
        assert _css(page, LINE, "transform") in IDENTITY
    # And it stays so past the mascot's own look-back and play timers.
    page.wait_for_timeout(1500)
    assert _css(page, LINE, "transform") in IDENTITY


def test_a_click_opens_the_field(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    _point_at_the_circle(page)
    expect(page.locator(ROOT)).to_have_attribute("data-state", "rest")
    page.locator(CIRCLE).click()
    expect(page.locator(ROOT)).to_have_attribute("data-state", "open")
    expect(page.locator(FIELD)).to_be_focused()
    expect(page.locator(FIELD)).to_have_attribute("aria-label", "Find or ask")
    expect(page.locator(".circle-field__caption")).to_have_text("Find or ask")
    expect(page.locator(".circle-field__words")).to_have_css("opacity", "1")
    assert _size(page, CIRCLE)[0] > 150


@pytest.mark.parametrize("pointed", [True, False], ids=["under the pointer", "pointer away"])
@pytest.mark.parametrize("key,state", [("q", "typing"), ("Control+k", "open")])
def test_a_key_opens_the_field(ui_f2: UiSession, key: str, state: str, pointed: bool) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    if pointed:
        _point_at_the_circle(page)
    else:
        _away(page)
    expect(page.locator(ROOT)).to_have_attribute("data-state", "rest")
    page.keyboard.press(key)
    expect(page.locator(ROOT)).to_have_attribute("data-state", state)
    expect(page.locator(FIELD)).to_be_focused()
    if key == "q":
        expect(page.locator(FIELD)).to_have_value("q")


def test_a_pointer_that_cannot_hover_changes_nothing_and_a_tap_still_opens(ui_f2: UiSession) -> None:
    """Hover effects only under `(hover: hover) and (pointer: fine)`: on a phone a mouse event is not a hand over it."""
    browser = ui_f2.context.browser
    assert browser is not None
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, reduced_motion="reduce")
    try:
        page = context.new_page()
        page.goto(ui_f2.base_url)
        page.wait_for_selector(".goal-card__row")
        assert page.evaluate("matchMedia('(hover: hover) and (pointer: fine)').matches") is False
        x, y = _centre(page)
        page.mouse.move(x, y, steps=3)
        assert _size(page, CIRCLE) == (84, 84)
        expect(page.locator(".circle-tags.is-shown")).to_have_count(0)
        page.touchscreen.tap(x, y)
        expect(page.locator(ROOT)).to_have_attribute("data-state", "open")
        expect(page.locator(FIELD)).to_be_focused()
    finally:
        context.close()


FRAMES = """() => {
  const s = window.__field = { frames: [], on: true, t0: performance.now() };
  const shape = document.querySelector('.circle-field__shape'), line = document.querySelector('.circle-field__line');
  const tag = document.querySelector('.circle-tag');
  (function frame() {
    if (!s.on) return;
    s.frames.push({ t: performance.now() - s.t0, w: shape.getBoundingClientRect().width,
                    line: line.getBoundingClientRect().height, lineW: line.getBoundingClientRect().width,
                    tag: tag.getBoundingClientRect().height });
    requestAnimationFrame(frame);
  })();
}"""
RUNNING = """() => {
  const of = (el) => el.getAnimations().filter((a) => a instanceof CSSTransition).map((a) => ({
    prop: a.transitionProperty, ms: a.effect.getTiming().duration, easing: a.effect.getTiming().easing }));
  return { token: getComputedStyle(document.documentElement).getPropertyValue('--ease-out').trim(),
    shape: of(document.querySelector('.circle-field__shape')), line: of(document.querySelector('.circle-field__line')),
    tags: of(document.querySelector('.circle-tags')), tag: of(document.querySelector('.circle-tag')) };
}"""
SIZES = ("min-width", "width", "height", "border-radius")


def _trace(page: Page, act, wait: int) -> tuple[dict, list[dict]]:
    """What runs the moment `act` is done, and every frame of the `wait` ms after it."""
    page.evaluate(FRAMES)
    page.wait_for_timeout(60)
    act()
    running = page.evaluate(RUNNING)
    page.wait_for_timeout(wait)
    return running, page.evaluate("(() => { window.__field.on = false; return window.__field.frames })()")


def _curve(text: str) -> tuple[float, ...]:
    """A `cubic-bezier(...)` as its four numbers, however the stylesheet or the browser spells them (`.2` or `0.2`)."""
    assert text.startswith("cubic-bezier("), text
    return tuple(float(part) for part in text[len("cubic-bezier("):-1].split(","))


def _jumps(frames: list[dict], key: str, low: float, high: float) -> None:
    """The value goes from one end to the other with nothing eased through, and ends at the other end."""
    values = [f[key] for f in frames]
    assert not [v for v in values if low + 0.5 < v < high - 0.5], (key, values)


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_change_comes_at_once_and_settles_back_in_200_ms_on_the_ease_out_token(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    _away(page)
    page.wait_for_timeout(300)

    # Entering: no size transition runs, and no frame is between the rest size and the pointer's.
    running, frames = _trace(page, lambda: _point_at_the_circle(page), 300)
    assert [t for part in ("shape", "line", "tag") for t in running[part] if t["prop"] in SIZES] == [], running
    _jumps(frames, "w", 84, 116)
    _jumps(frames, "line", 24, 46)
    _jumps(frames, "lineW", 3, 5)
    _jumps(frames, "tag", 28, 38)
    assert [round(frames[-1][key]) for key in ("w", "line", "lineW", "tag")] == [116, 46, 5, 38]

    # Leaving: each one settles back in 200 ms on the token's curve, and the size is all that moves.
    running, frames = _trace(page, lambda: page.mouse.move(100, 300), 600)
    token = _curve(running["token"])
    assert token == (0.2, 0, 0, 1), token  # the design system's --ease-out
    for part, prop in (("shape", "min-width"), ("line", "height"), ("line", "width"), ("tag", "height")):
        found = [t for t in running[part] if t["prop"] == prop]
        assert found and all(t["ms"] == 200 and _curve(t["easing"]) == token for t in found), (part, running)
    # Frame by frame: it only gets smaller, never goes under what it settles at, and is there well inside half a second.
    widths = [f["w"] for f in frames]
    assert widths[0] == 116 and widths[-1] == 84, widths
    assert all(b <= a + 0.01 for a, b in zip(widths, widths[1:])), widths
    assert min(widths) >= 84, widths
    began = next(f["t"] for f in frames if f["w"] < 116)
    done = next(f["t"] for f in frames if f["w"] <= 84.5)
    assert 100 <= done - began <= 450, (done - began, widths)


def test_with_reduced_motion_nothing_animates(ui_f2: UiSession) -> None:
    page = ui_f2.page
    page.wait_for_selector(".goal-card__row")
    _away(page)
    page.wait_for_timeout(300)
    for act, final in ((lambda: _point_at_the_circle(page), (116, 5, 38)), (lambda: page.mouse.move(100, 300), (84, 3, 28))):
        running, frames = _trace(page, act, 300)
        assert running["shape"] == [] and running["line"] == [] and running["tags"] == [] and running["tag"] == [], running
        # Not eased towards: no frame is between the two sizes.
        _jumps(frames, "w", 84, 116)
        _jumps(frames, "lineW", 3, 5)
        _jumps(frames, "tag", 28, 38)
        assert [round(frames[-1][key]) for key in ("w", "lineW", "tag")] == list(final)
