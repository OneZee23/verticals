"""Columns bounce at their ends again, and the desktop app's Reduce Motion switch stops the board's motion the way the
system setting does (`docs/design/column-bounce.md`).

The app tells the page its answer on <html>: `data-reduce-motion="on"` or `"off"`, set by `desktop/macos/Verticals.swift`
from the View menu at the start of every page and on the page that is open. With no answer (a plain browser, or a Mac whose
person never touched the item) the page asks the system, as before. Every `prefers-reduced-motion` rule of the page also
answers to the switch (`web/vite.config.ts`), and scripts ask `reducedMotion()` (`web/src/lib/motion.ts`).

Chrome checks the real bundle. The Swift half and the bounce under a trackpad need the running app and are not covered here."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession, activate_column
from tests.ui.test_carried_motion import SAMPLER, _board, _change, _trace
from tests.ui.test_nested_sort import GRIP, _create_goal, _move_to_row_once, _press, _row

ATTRIBUTE = "data-reduce-motion"
SLIDE = '.pattern-vertical-board__column[data-vertical="week"] .period-slide:not([data-state="outgoing"])'
CIRCLE = ".circle-field__shape"

OVERSCROLL = f"() => getComputedStyle(document.querySelector('{SLIDE}')).overscrollBehaviorY"
# The longest transition a goal has: the card's own colour and lift (goalCard.css), from the motion tokens in `:root`.
LONGEST_TRANSITION = """(sel) => Math.max(...getComputedStyle(document.querySelector(sel)).transitionDuration
  .split(',').map(parseFloat))"""  # computed durations are in seconds
# Every transition the field starts, as it starts, while the pointer comes and goes. The tags' and the words' fades stay
# under reduced motion; what resizes or moves does not.
WATCH_FIELD = """() => {
  window.__fieldRuns = [];
  document.addEventListener('transitionrun', (e) => {
    if (e.target.closest?.('.circle-field')) window.__fieldRuns.push(e.propertyName);
  }, true);
}"""
FIELD_MOVES = """() => window.__fieldRuns.filter((name) => !['opacity', 'color', 'background-color'].includes(name))"""
# Every frame while a goal is dragged, whether a neighbour slides to make room (a script's translateY animation on a card).
WATCH_GAP = """() => {
  window.__gap = [];
  const frame = () => {
    for (const a of document.getAnimations()) {
      const card = a.effect?.target;
      if (a.constructor !== Animation || !card?.matches?.('.goal-card') || card.closest('.pattern-vertical-board__drag-overlay')) continue;
      for (const key of a.effect.getKeyframes()) {
        if (typeof key.transform === 'string' && key.transform.startsWith('translateY')) window.__gap.push(key.transform);
      }
    }
    window.__watching = requestAnimationFrame(frame);
  };
  frame();
}"""
# Every frame, whether a column's periods or their track travel (a transform or translate animation on them).
WATCH_TRAVEL = """() => {
  window.__travel = [];
  const frame = () => {
    for (const a of document.getAnimations()) {
      if (!a.effect?.target?.matches?.('[data-role="period-track"], [data-role="period-slide"]')) continue;
      for (const key of a.effect.getKeyframes()) {
        for (const property of ['transform', 'translate']) {
          if (key[property] && key[property] !== 'none') window.__travel.push(`${property} ${key[property]}`);
        }
      }
    }
    window.__watching = requestAnimationFrame(frame);
  };
  frame();
}"""


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


MATRIX = pytest.mark.parametrize("ui_reduced_motion,switch,still", [
    ("no-preference", None, False),  # a browser, motion on
    ("reduce", None, True),  # a browser, the system setting on: the only switch there
    ("no-preference", "on", True),  # the app's switch on, the system setting off
    ("reduce", "off", False),  # the person turned the app's switch off over a system setting that is on
], indirect=["ui_reduced_motion"])


@MATRIX
def test_motion_is_still_exactly_when_the_switch_or_the_system_setting_says_so(
    ui_f2: UiSession, switch: str | None, still: bool,
) -> None:
    """Four things that move or may move, each by another route: the column's edge (a rule inside a media block, copied
    for the switch), the field answering the pointer (transitions that block switches off), a goal's lift (the motion
    tokens, set on `:root`) and the carried box's slide (a script asking `reducedMotion()`). All four are still when the
    app says on, or says nothing and the system setting is on; all four move when the app says off, whatever the system
    setting says."""
    session = ui_f2
    _answer(session, switch)
    value, plan = _board(session)
    page = session.page
    assert _answered(page) == switch

    assert page.evaluate(OVERSCROLL) == ("none" if still else "contain"), "the column's edge"

    page.evaluate(WATCH_FIELD)
    page.locator(CIRCLE).hover()
    page.wait_for_timeout(400)
    page.mouse.move(20, 20)
    page.wait_for_timeout(500)
    moves = page.evaluate(FIELD_MOVES)
    assert bool(moves) is not still, f"the field answers the pointer {'at once' if still else 'with a movement'}: {moves}"

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


@MATRIX
def test_a_column_pages_without_travel_when_motion_is_still(ui_f2: UiSession, switch: str | None, still: bool) -> None:
    """Stepping a column to the next period slides its two periods past each other (Column.vue); with motion reduced,
    by the system setting or the app's switch, nothing travels."""
    page = ui_f2.page
    _answer(ui_f2, switch)
    column = '.pattern-vertical-board__column[data-vertical="week"]'
    before = page.locator(column).get_attribute("data-period-key")
    page.locator(column).hover()
    page.evaluate(WATCH_TRAVEL)
    page.locator(f'{column} [data-cap="period-next"]').click()
    expect(page.locator(column)).not_to_have_attribute("data-period-key", before)
    page.wait_for_timeout(600)
    travelled = page.evaluate("() => window.__travel")
    assert bool(travelled) is not still, f"the column {'slid' if travelled else 'paged without travel'}: {travelled[:3]}"


@MATRIX
def test_a_dragged_goal_opens_its_gap_at_once_when_motion_is_still(
    ui_f2: UiSession, switch: str | None, still: bool,
) -> None:
    """Carrying a goal over a column opens a gap where it would land, and the goals around it make room: they slide into
    their new places (Column.vue for a column's own goals, GoalCard.vue for a goal's steps). With motion reduced, by the
    system setting or the app's switch, the gap simply opens."""
    session = ui_f2
    page = session.page
    _answer(session, switch)
    parent = _create_goal(session, "SYN parent with steps", "week")
    steps = [_create_goal(session, f"SYN step {n}", "week", parent_id=parent) for n in (1, 2, 3)]
    page.reload()
    activate_column(page, "week")

    def carry(source: str, target: str) -> list[str]:
        """Pick `source` up, take it over `target`, hold it there a moment, put it back; the slides seen on the way."""
        page.evaluate(WATCH_GAP)
        _press(page, page.locator(_row(source)), GRIP)
        _move_to_row_once(page, lambda: page.locator(_row(target)), lambda box: (box["x"] + 50, box["y"] + box["height"] - 4))
        slid = page.evaluate("() => window.__gap")
        page.keyboard.press("Escape")
        page.mouse.up()
        page.wait_for_timeout(400)
        return slid

    top = page.evaluate("""() => [...document.querySelectorAll('.pattern-vertical-board__column[data-vertical="week"] [data-role="period-slide"]:not([data-state="outgoing"]) .pattern-vertical-board__body > .card-stack > .goal-card')]
      .map((card) => card.dataset.goalId).filter((id) => id !== '%s')""" % parent)
    assert len(top) >= 3, top
    column_slid = carry(top[0], top[2])
    nested_slid = carry(steps[0], steps[2])
    assert bool(column_slid) is not still, f"a column's goals {'made room' if column_slid else 'opened the gap at once'}: {column_slid[:2]}"
    assert bool(nested_slid) is not still, f"a goal's steps {'made room' if nested_slid else 'opened the gap at once'}: {nested_slid[:2]}"
