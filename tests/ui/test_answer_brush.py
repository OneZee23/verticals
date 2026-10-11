"""An answer waiting in the field can be brushed away (docs/design/agent-fixes.md, fix 8): a sideways swipe on the trackpad or a
drag down sends it back into the circle, as Esc does, and the conversation keeps it. The shape follows the hand one to one
(within 4 px), a short pull returns it to its place and is no click on the answer, and what the system finishes lands without
overshoot (kk-motion). The agent is the fake one behind the real gateway, as in `test_agent_conversation.py`."""

from __future__ import annotations

import json

from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession
from tests.ui.test_agent_conversation import BALLOON, CIRCLE, CONVERSATION, _send, ui_agent  # noqa: F401  (the fixture)

SHAPE = ".circle-field__shape"
ANSWER = '[data-role="circle-answer"]'


def _answer_waits(page: Page) -> dict:
    """The agent's answer stands in the field, the conversation closed; its shape's box."""
    page.wait_for_selector(".goal-card__row")
    _send(page, "Tell me more [long] [slow]")
    page.locator('[data-role="out-of-focus"]').click(position={"x": 60, "y": 60})
    expect(page.locator(ANSWER)).to_contain_text("Here is the first part", timeout=10000)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
    page.wait_for_timeout(700)  # the shape has grown around it
    box = page.locator(SHAPE).bounding_box()
    assert box is not None
    return box


def _centre(box: dict) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _shift(page: Page, home: dict) -> tuple[float, float]:
    """How far the shape stands from where it rests."""
    box = page.locator(SHAPE).bounding_box()
    assert box is not None
    return box["x"] - home["x"], box["y"] - home["y"]


def _sent_back(page: Page) -> None:
    """The answer is gone from the field and the conversation is not what it went to: it is the circle again (or, with the
    pointer still over it, the circle that opens when pointed at)."""
    expect(page.locator(ANSWER)).to_have_count(0)
    expect(page.locator(CIRCLE)).not_to_have_attribute("data-state", "answer")
    expect(page.locator(CONVERSATION)).to_have_count(0)


def _the_conversation_keeps_it(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(page.locator(CONVERSATION)).to_have_count(1)
    expect(page.locator(f'{BALLOON}[data-who="agent"]').last).to_contain_text("The third part closes it")


def _swipe(page: Page, step: float, times: int, pause: int = 16) -> None:
    for _ in range(times):
        page.mouse.wheel(step, 0)
        page.wait_for_timeout(pause)


def test_a_sideways_swipe_follows_the_hand_then_sends_the_answer_back(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    page.mouse.move(*_centre(home))
    _swipe(page, 18, 2)
    # the answer moves as a page would under the fingers: one to one, 36 px of swipe, 36 px of answer
    dx, dy = _shift(page, home)
    assert abs(dx - -36) <= 4 and abs(dy) <= 1, (dx, dy)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
    _swipe(page, 18, 4)  # past 64 px it goes, the swipe still going
    _sent_back(page)
    page.wait_for_timeout(400)
    assert page.locator(SHAPE).evaluate("el => el.style.transform") == ""
    _the_conversation_keeps_it(page)


def test_a_short_swipe_goes_back_to_its_place_and_the_answer_stays(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    page.mouse.move(*_centre(home))
    _swipe(page, 12, 3)
    assert abs(_shift(page, home)[0] - -36) <= 4
    page.wait_for_timeout(400)  # the wheel is quiet: it returns
    assert _shift(page, home) == (0, 0)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
    expect(page.locator(ANSWER)).to_contain_text("Here is the first part")


def test_scrolling_over_the_answer_is_no_brush(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    page.mouse.move(*_centre(home))
    for _ in range(4):
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(16)
    page.mouse.wheel(10, 60)  # mostly down: still not a swipe
    page.wait_for_timeout(300)
    assert _shift(page, home) == (0, 0)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")


def test_a_drag_down_follows_the_hand_and_sends_the_answer_back_when_let_go_far_enough(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    x, y = _centre(home)
    page.mouse.move(x, y)
    page.mouse.down()
    for step in range(1, 7):  # slowly, so that it is the distance that decides
        page.mouse.move(x, y + step * 8)
        page.wait_for_timeout(60)
    # one to one with the hand, less the few pixels of a press that are no drag yet
    dx, dy = _shift(page, home)
    assert abs(dy - (6 * 8 - 8)) <= 4 and abs(dx) <= 1, (dx, dy)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
    page.mouse.up()
    _sent_back(page)
    page.wait_for_timeout(400)
    assert page.locator(SHAPE).evaluate("el => el.style.transform") == ""
    _the_conversation_keeps_it(page)


def test_a_quick_flick_down_is_enough_whatever_the_distance(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    x, y = _centre(home)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + 12)
    page.mouse.move(x, y + 24, steps=3)  # 24 px in a few milliseconds: far above 0.11 px/ms
    page.mouse.up()
    _sent_back(page)


def test_a_short_drag_returns_to_its_place_and_is_not_a_click_on_the_answer(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    home = _answer_waits(page)
    x, y = _centre(home)
    page.mouse.move(x, y)
    page.mouse.down()
    for step in range(1, 5):
        page.mouse.move(x, y + step * 5)
        page.wait_for_timeout(120)  # 20 px, slowly: neither far nor fast
    page.mouse.up()
    page.wait_for_timeout(400)
    assert _shift(page, home) == (0, 0)
    expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
    expect(page.locator(CONVERSATION)).to_have_count(0)  # the end of a drag is no click, which would open the conversation


def test_a_mouse_drag_up_or_sideways_is_no_brush_and_no_click_and_a_still_click_still_opens_the_conversation(
    ui_agent: UiSession,  # noqa: F811
) -> None:
    page = ui_agent.page
    home = _answer_waits(page)
    x, y = _centre(home)
    for to in ((x, y - 40), (x + 60, y + 2)):  # the drag the design does not name: up, and sideways with the mouse
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(*to, steps=4)
        page.wait_for_timeout(100)
        assert _shift(page, home) == (0, 0)
        page.mouse.up()
        page.wait_for_timeout(200)
        expect(page.locator(CIRCLE)).to_have_attribute("data-state", "answer")
        expect(page.locator(CONVERSATION)).to_have_count(0)  # a drag's end is no click on the answer
    # a click that moves a little (under the slop) is still a click: the answer goes up into the conversation
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 2, y + 3)
    page.mouse.up()
    expect(page.locator(CONVERSATION)).to_have_count(1)
    expect(page.locator(f'{BALLOON}[data-who="agent"]').last).to_contain_text("The third part closes it")


def test_esc_still_sends_the_answer_back(ui_agent: UiSession) -> None:  # noqa: F811
    page = ui_agent.page
    _answer_waits(page)
    page.keyboard.press("Escape")
    _sent_back(page)
    _the_conversation_keeps_it(page)


def test_what_the_system_finishes_lands_in_the_circle_without_overshoot(ui_agent: UiSession) -> None:  # noqa: F811
    """kk-motion, measured with motion on: from the moment of letting go the shape's offset runs to nothing and its size to the
    circle's together, in under 250 ms, and it never passes where it is going."""
    page = ui_agent.page
    page.emulate_media(reduced_motion="no-preference")
    home = _answer_waits(page)
    x, y = _centre(home)
    page.mouse.move(x, y)
    page.mouse.down()
    for step in range(1, 7):
        page.mouse.move(x, y + step * 8)
        page.wait_for_timeout(60)
    page.evaluate(
        """rest => {
          const shape = document.querySelector('.circle-field__shape')
          window.__frames = []
          const t0 = performance.now()
          window.__up = null
          shape.addEventListener('pointerup', () => { window.__up = performance.now() - t0 }, { once: true })
          const tick = () => {
            const box = shape.getBoundingClientRect()
            window.__frames.push([performance.now() - t0, box.bottom - rest, box.width, box.height])
            if (performance.now() - t0 < 700) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        }""",
        home["y"] + home["height"],
    )
    page.wait_for_timeout(150)  # frames of it held, then let go
    page.mouse.up()
    page.wait_for_timeout(900)
    frames = json.loads(page.evaluate("() => JSON.stringify(window.__frames)"))
    let_go = page.evaluate("() => window.__up")
    assert let_go is not None
    offsets = [frame[1] for frame in frames]
    # it is let go about 40 px below its place, and nothing about it jumps: the frames before are where the hand left it
    held = [frame[1] for frame in frames if frame[0] < let_go]
    assert held and min(held) > 30 and max(held) - min(held) <= 1, held
    last = frames[-1]
    assert abs(last[1]) <= 1 and last[3] == 84 and 84 <= last[2] < home["width"], last
    settled = next(frame[0] for frame in frames if frame[0] > let_go and frame[3] == 84 and abs(frame[1]) <= 1) - let_go
    assert settled <= 250, (settled, [(round(f[0] - let_go), round(f[1]), round(f[2]), round(f[3])) for f in frames if f[0] > let_go][:24])
    # no overshoot: the offset only falls toward home, and the size only toward the circle's; neither passes it
    fall = offsets[offsets.index(max(offsets)):]
    assert all(b <= a + 1 for a, b in zip(fall, fall[1:])), fall
    assert min(offsets) >= -1, min(offsets)
    assert min(frame[3] for frame in frames) >= 84 and min(frame[2] for frame in frames) >= 84
