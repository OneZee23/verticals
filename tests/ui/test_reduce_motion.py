"""Columns bounce at their ends again, and the desktop app's Reduce Motion switch stops the board's motion the way the
system setting does (`docs/design/column-bounce.md`).

The app tells the page its answer on <html>: `data-reduce-motion="on"` or `"off"`, set by `desktop/macos/Verticals.swift`
from the View menu at the start of every page and on the page that is open. With no answer (a plain browser, or a Mac whose
person never touched the item) the page asks the system, as before. Every `prefers-reduced-motion` rule of the page also
answers to the switch (`web/vite.config.ts`), and scripts ask `reducedMotion()` (`web/src/lib/motion.ts`).

Chrome checks the real bundle. The Swift half and the bounce under a trackpad need the running app and are not covered here."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.ui.conftest import UiSession
from tests.ui.test_carried_motion import SAMPLER, _board, _change, _trace

ATTRIBUTE = "data-reduce-motion"
SLIDE = '.pattern-vertical-board__column[data-vertical="week"] .period-slide:not([data-state="outgoing"])'
CIRCLE = ".circle-field__shape"

OVERSCROLL = f"() => getComputedStyle(document.querySelector('{SLIDE}')).overscrollBehaviorY"
# The longest transition a goal has: the card's own colour and lift (goalCard.css), from the motion tokens in `:root`.
LONGEST_TRANSITION = """(sel) => Math.max(...getComputedStyle(document.querySelector(sel)).transitionDuration
  .split(',').map(parseFloat))"""  # computed durations are in seconds
# Every transition the field starts, as it starts. The tags' and the words' fades stay under reduced motion; what resizes
# or moves does not.
WATCH_FIELD = """() => {
  window.__fieldRuns = [];
  document.addEventListener('transitionrun', (e) => {
    if (e.target.closest?.('.circle-field')) window.__fieldRuns.push(e.propertyName);
  }, true);
}"""
FIELD_MOVES = """() => window.__fieldRuns.filter((name) => !['opacity', 'color', 'background-color'].includes(name))"""


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    return getattr(request, "param", "no-preference")


def _answer(session: UiSession, value: str | None) -> None:
    """What the app does: its answer on <html> from the start of every page (a user script at document start), and on
    the page that is open now. None is a browser, or a Mac whose person never touched the item: no answer."""
    if value is None:
        return
    set_it = f"document.documentElement.setAttribute('{ATTRIBUTE}', '{value}')"
    session.context.add_init_script(
        script=f"""(() => {{
          if (document.documentElement) {{ {set_it}; return; }}
          new MutationObserver((_, watch) => {{ if (document.documentElement) {{ watch.disconnect(); {set_it}; }} }})
            .observe(document, {{ childList: true }});
        }})()"""
    )
    session.page.evaluate(f"() => {set_it}")


def _answered(page: Page) -> str | None:
    return page.evaluate(f"document.documentElement.getAttribute('{ATTRIBUTE}')")


def test_a_column_bounces_at_its_ends_on_a_fine_pointer(ui_f2: UiSession) -> None:
    """The rule that stopped the trackpad's rubber band on fine pointers is gone: a column keeps `contain`, which
    holds the scroll in the column and leaves the bounce to the system."""
    page = ui_f2.page
    assert page.evaluate("matchMedia('(pointer: fine)').matches"), "the old rule only applied to fine pointers"
    assert page.evaluate(OVERSCROLL) == "contain"


@pytest.mark.parametrize("ui_reduced_motion,switch,still", [
    ("no-preference", None, False),  # a browser, motion on
    ("reduce", None, True),  # a browser, the system setting on: the only switch there
    ("no-preference", "on", True),  # the app's switch on, the system setting off
    ("reduce", "off", False),  # the person turned the app's switch off over a system setting that is on
], indirect=["ui_reduced_motion"])
def test_motion_is_still_exactly_when_the_switch_or_the_system_setting_says_so(
    ui_f2: UiSession, switch: str | None, still: bool,
) -> None:
    """Four things that move or may move, each by another route: the column's edge (a rule inside a media block, copied
    for the switch), the field opening (transitions that block switches off), a goal's lift (the motion tokens, set on
    `:root`) and the carried box's slide (a script asking `reducedMotion()`). All four are still when the app says on, or
    says nothing and the system setting is on; all four move when the app says off, whatever the system setting says."""
    session = ui_f2
    _answer(session, switch)
    value, plan = _board(session)
    page = session.page
    assert _answered(page) == switch

    assert page.evaluate(OVERSCROLL) == ("none" if still else "contain"), "the column's edge"

    page.evaluate(WATCH_FIELD)
    page.locator(CIRCLE).hover()
    page.wait_for_timeout(400)
    moves = page.evaluate(FIELD_MOVES)
    assert bool(moves) is not still, f"the field opens {'at once' if still else 'with a movement'}: {moves}"

    page.evaluate(SAMPLER, plan)
    frames = _trace(page, lambda: page.locator(f'[data-goal-id="{value}"] > .goal-card__row').hover(), 700)
    longest = page.evaluate(LONGEST_TRANSITION, f'.goal-card[data-goal-id="{value}"]')
    assert (longest < 0.001) is still, f"the pointed goal's lift takes {longest} s"
    moved = frames[_change(frames, 1):]
    assert all(f["planTf"] == "none" for f in moved) is still, "the carried box slides what stays"


def test_the_switch_acts_on_the_page_that_is_open(ui_f2: UiSession) -> None:
    """The View menu item changes the answer on the page in front of the person, with no reload: the goal's lift and
    the column's edge follow at once, back and forth, and taking the answer away hands the page back to the system."""
    page = ui_f2.page
    value, _ = _board(ui_f2)
    page.locator(f'[data-goal-id="{value}"] > .goal-card__row').hover()
    card = f'.goal-card[data-goal-id="{value}"]'
    assert page.evaluate(LONGEST_TRANSITION, card) > 0.1 and page.evaluate(OVERSCROLL) == "contain"

    for answer, still in (("on", True), ("off", False), ("on", True)):
        page.evaluate(f"document.documentElement.setAttribute('{ATTRIBUTE}', '{answer}')")
        assert (page.evaluate(LONGEST_TRANSITION, card) < 0.001) is still
        assert page.evaluate(OVERSCROLL) == ("none" if still else "contain")
    page.evaluate(f"document.documentElement.removeAttribute('{ATTRIBUTE}')")
    assert page.evaluate(LONGEST_TRANSITION, card) > 0.1, "no answer: the system setting, which is off here"
