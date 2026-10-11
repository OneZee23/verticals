"""The period bars, | ||| |, on a line pinned at the column's top (docs/design/column-bars.md).

Every column but Life shows three bars at rest, the middle one dark, in place of ← • →. A bar comes at each side under
the pointer and steps the column to the period before and after; the middle one opens the column's spans mode, the one a
dragged task opens on the column's corner (`lib/spans.ts`). When a column scrolls, the line holding them stays pinned at
its top on white, the goals fading out under it over 14 px; it names the kind while the column is at its top and the
period once the big name has gone under it.

The suite's pinned clock is Saturday 8 Aug 2026 and its window 1458 px, so a column is 208 px wide (182 px of room for
its name). Sizes and colours are the board's own: the ink and the light grey the dots in a column's corner already use
(`ColumnDots.vue`), and the kind line's caption type (15/24), whose cap height, 10.7 px, the bars are drawn to.
"""

from __future__ import annotations

import re

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import _DIALOG_RECORDER_SCRIPT, _MORNING_ASKED_SCRIPT, UiSession, activate_column, expand_column

STRIP = '[data-role="column-strip"]'
SPANS = '[data-role="spans-board"]'
SPAN_HEADS = '[data-role="spans-row"] > .pattern-vertical-board__column:not([data-span-edge]) .column-header__sub-label'
PAGED = ("day", "week", "month", "quarter", "year", "decade")
KINDS = {"day": "Day", "week": "Week", "month": "Month", "quarter": "Quarter", "year": "Year", "decade": "Three years"}
# The period each column pages to from the suite's pinned day, Saturday 8 Aug 2026: (this period, the next, the one before).
PERIODS = {
    "day": ("2026-08-08", "2026-08-09", "2026-08-07"),
    "week": ("2026-W32", "2026-W33", "2026-W31"),
    "month": ("2026-08", "2026-09", "2026-07"),
    "quarter": ("2026-Q3", "2026-Q4", "2026-Q2"),
    "year": ("2026", "2027", "2025"),
    "decade": ("2026–2028", "2029–2031", "2023–2025"),
}
# ColumnDots.vue's own colours: the board's ink and its light grey.
INK = "rgb(45, 48, 54)"
LIGHT = "rgb(211, 212, 215)"
# A bar, its gaps and the margin to the column's right edge, in px: the bars are 2 px wide and 11 tall, the cap height of
# the kind line's type, rounded; 3 px apart in the sign, 6 from the bars that come at its sides.
BAR_W, BAR_H, GAP_IN, GAP_OUT, MARGIN = 2, 11, 3, 6, 14
ANCHOR = "2026-08-08"


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    """Motion off, as the suite runs; the tests that read the fades ask for it on."""
    return getattr(request, "param", "reduce")


def _col(page: Page, vertical: str):
    return page.locator(f"{STRIP} > [data-vertical='{vertical}']")


def _hover(page: Page, vertical: str) -> None:
    box = _col(page, vertical).bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, 400)


def _rest(page: Page) -> None:
    """The pointer over Life, which has no bars: the other six stand at rest."""
    _hover(page, "life")
    page.wait_for_timeout(50)


def _frames(page: Page, n: int = 2) -> None:
    """`n` frames drawn: a scroll's event, and what the page does about it, are answered by then."""
    page.evaluate(
        "n => new Promise((done) => { const tick = () => (--n > 0 ? requestAnimationFrame(tick) : done()); requestAnimationFrame(tick); })", n)


def _seed(session: UiSession, vertical: str, n: int, anchor: str = ANCHOR) -> None:
    """Enough goals for a column to scroll."""
    for i in range(n):
        response = httpx.post(
            f"{session.backend.base_url}/api/goals",
            json={"title": f"SYN bars {vertical} {i:02d}", "vertical": vertical, "anchor_date": anchor},
            headers={"Authorization": f"Bearer {session.backend.token}"},
            timeout=10,
        )
        assert response.status_code == 201, response.text


def _open(session: UiSession, anchor: str | None = None, width: int | None = None) -> Page:
    page = session.page
    if width is not None:
        page.set_viewport_size({"width": width, "height": 779})
    page.goto(f"{session.base_url}/h/{anchor}" if anchor else f"{session.base_url}/")
    page.wait_for_selector(f"{STRIP} > [data-vertical='day'] .column-header")
    page.evaluate("() => document.fonts.ready")
    return page


# What the eye sees of a column's bars: where each stands, in px from the column's own edges, and its colour, counting
# only those that are not faded out (a side bar at rest is there for the keyboard and invisible).
_BARS = """(vertical) => {
  const col = document.querySelector(`[data-role="column-strip"] > [data-vertical="${vertical}"]`);
  const box = col.getBoundingClientRect();
  const shown = (el) => { let o = 1; for (let e = el; e && e !== col; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  return [...col.querySelectorAll('.column-bars__bar')].map((el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left - box.left, right: box.right - r.right, top: r.top - box.top, bottom: r.bottom - box.top,
             w: r.width, h: r.height, color: getComputedStyle(el).backgroundColor, shown: shown(el), cap: el.closest('[data-cap]').dataset.cap };
  }).filter((bar) => bar.shown > 0.01).sort((a, b) => a.left - b.left);
}"""


def _bars(page: Page, vertical: str) -> list[dict]:
    return page.evaluate(_BARS, vertical)


def _wait_bars(page: Page, vertical: str, count: int) -> list[dict]:
    """The bars once `count` of them show (a fade in or out takes a moment under motion)."""
    bars = _bars(page, vertical)
    for _ in range(40):
        if len(bars) == count:
            break
        page.wait_for_timeout(25)
        bars = _bars(page, vertical)
    return bars


def _gaps(bars: list[dict]) -> list[float]:
    return [round(b["left"] - a["left"] - BAR_W, 2) for a, b in zip(bars, bars[1:])]


def test_every_column_but_life_shows_three_bars_at_rest(ui_f2: UiSession) -> None:
    """|||, the middle one dark, in each of the six columns that page; Life has none, and the dot that was "Today" is gone."""
    page = _open(ui_f2)
    _rest(page)
    for vertical in PAGED:
        bars = _wait_bars(page, vertical, 3)
        assert [bar["color"] for bar in bars] == [LIGHT, INK, LIGHT], f"{vertical}: {bars}"
        assert all((bar["w"], bar["h"]) == (BAR_W, BAR_H) for bar in bars), f"{vertical}: the bars' size"
        assert len({round(bar["bottom"], 2) for bar in bars}) == 1, f"{vertical}: the bars stand on one line"
        assert _gaps(bars) == [GAP_IN, GAP_IN], f"{vertical}: 3 px between the bars of the sign"
        # the sign is set in from the right margin by the bar that comes at its side and the gap before it
        assert bars[-1]["right"] == pytest.approx(MARGIN + BAR_W + GAP_OUT, abs=0.01), f"{vertical}: {bars[-1]}"
    expect(_col(page, "life").locator('[data-cap="period-nav"]')).to_have_count(0)
    expect(page.locator('[data-cap="period-today"]')).to_have_count(0)
    expect(page.locator(".column-period-controls")).to_have_count(0)
    # they stand on the kind line, on the baseline of its type, 22 px under the column's top, and reach its cap height
    week = _bars(page, "week")[0]
    assert week["bottom"] == pytest.approx(22, abs=0.01) and week["top"] == pytest.approx(11, abs=0.01)


def test_a_bar_comes_at_each_side_under_the_pointer(ui_f2: UiSession) -> None:
    """| ||| |: the two outer bars come at once under the pointer and the sign in the middle stays where it was; the other
    columns keep their three; leaving, the sides go."""
    page = _open(ui_f2)
    _rest(page)
    at_rest = _wait_bars(page, "week", 3)
    _hover(page, "week")
    bars = _wait_bars(page, "week", 5)
    assert [bar["color"] for bar in bars] == [LIGHT, LIGHT, INK, LIGHT, LIGHT], bars
    assert [bar["cap"] for bar in bars] == ["period-prev", "period-mode", "period-mode", "period-mode", "period-next"]
    assert _gaps(bars) == [GAP_OUT, GAP_IN, GAP_IN, GAP_OUT]
    assert bars[-1]["right"] == pytest.approx(MARGIN, abs=0.01)
    assert [(b["left"], b["top"]) for b in bars[1:4]] == [(b["left"], b["top"]) for b in at_rest], "the sign stays put"
    assert len(_bars(page, "day")) == 3 and len(_bars(page, "month")) == 3, "the pointer is on Week only"
    _hover(page, "life")
    assert len(_wait_bars(page, "week", 3)) == 3


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_side_bars_appear_at_once_and_fade_back_in_200_ms(ui_f2: UiSession) -> None:
    """The side bars come with the pointer, in the first frame, and go in 200 ms."""
    page = _open(ui_f2)
    _rest(page)
    side = f"{STRIP} > [data-vertical='week'] [data-cap='period-next']"
    assert page.locator(side).evaluate("el => getComputedStyle(el).transitionDuration") == "0.2s", "the fade back takes 200 ms"
    page.evaluate(
        """(side) => {
          const el = document.querySelector(side); const t0 = performance.now(); const log = [];
          window.__fade = log;
          const tick = () => { log.push([performance.now() - t0, parseFloat(getComputedStyle(el).opacity)]); if (performance.now() - t0 < 1500) requestAnimationFrame(tick); };
          requestAnimationFrame(tick);
        }""",
        side,
    )
    page.wait_for_timeout(150)
    _hover(page, "week")
    page.wait_for_timeout(300)
    _hover(page, "life")
    page.wait_for_timeout(700)
    log = page.evaluate("window.__fade")
    came = next(i for i, (_, o) in enumerate(log) if o > 0.01)
    full = next(i for i, (_, o) in enumerate(log) if o > 0.99)
    assert log[full][0] - log[came][0] <= 90, f"the side bar took {log[full][0] - log[came][0]:.0f} ms to come: it appears at once"
    left = next(i for i in range(full, len(log)) if log[i][1] < 0.999)
    gone = next(i for i in range(left, len(log)) if log[i][1] <= 0.001)
    assert any(0.02 < o < 0.98 for _, o in log[left:gone]), "it fades, it does not cut"
    took = log[gone][0] - log[left - 1][0]
    assert 120 <= took <= 260, f"the fade back takes {took:.0f} ms, 200 by design"


def test_under_reduced_motion_the_side_bars_simply_appear_and_go(ui_f2: UiSession) -> None:
    page = _open(ui_f2)
    _rest(page)
    side = f"{STRIP} > [data-vertical='week'] [data-cap='period-prev']"
    assert float(page.locator(side).evaluate("el => parseFloat(getComputedStyle(el).transitionDuration)")) < 0.001
    _hover(page, "week")
    assert len(_wait_bars(page, "week", 5)) == 5
    _hover(page, "life")
    _frames(page)
    assert len(_bars(page, "week")) == 3


def test_a_bar_under_the_pointer_darkens(ui_f2: UiSession) -> None:
    """The one that would be pressed says so: every bar of the button turns ink, the others stay."""
    page = _open(ui_f2)
    _hover(page, "week")
    _wait_bars(page, "week", 5)
    for cap, want in (("period-prev", [INK, LIGHT, INK, LIGHT, LIGHT]), ("period-mode", [LIGHT, INK, INK, INK, LIGHT]),
                      ("period-next", [LIGHT, LIGHT, INK, LIGHT, INK])):
        box = _col(page, "week").locator(f'[data-cap="{cap}"]').bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        _frames(page)
        assert [bar["color"] for bar in _bars(page, "week")] == want, cap


@pytest.mark.parametrize("vertical", PAGED)
def test_the_side_bars_page_the_column(ui_f2: UiSession, vertical: str) -> None:
    """The bar at the right steps its column to the next period and the left one to the one before, by the column's own
    unit; one click, one period; and back."""
    page = _open(ui_f2)
    here, after, before = PERIODS[vertical]
    column = _col(page, vertical)
    expect(column).to_have_attribute("data-period-key", here)
    activate_column(page, vertical)  # the pointer is on the column, as it is for a person
    column.locator('[data-cap="period-next"]').click()
    expect(column).to_have_attribute("data-period-key", after)
    expect(column.locator('[data-role="period-slide"]')).to_have_count(1)
    column.locator('[data-cap="period-prev"]').click()
    expect(column).to_have_attribute("data-period-key", here)
    expect(column.locator('[data-role="period-slide"]')).to_have_count(1)
    column.locator('[data-cap="period-prev"]').click()
    expect(column).to_have_attribute("data-period-key", before)


def test_t_still_goes_back_to_today(ui_f2: UiSession) -> None:
    """The dot between the arrows is gone with them; the board's own key to today is not."""
    page = _open(ui_f2)
    activate_column(page, "week")
    _col(page, "week").locator('[data-cap="period-next"]').click()
    expect(_col(page, "week")).to_have_attribute("data-period-key", "2026-W33")
    page.keyboard.press("t")
    expect(_col(page, "week")).to_have_attribute("data-period-key", "2026-W32")


def test_a_click_on_the_lines_words_does_what_a_click_on_the_header_does(ui_f2: UiSession) -> None:
    """The line covers the header's kind: a click on its words widens the column, and pages nothing."""
    page = _open(ui_f2)
    box = _col(page, "week").bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + 30, box["y"] + 14)
    expect(_col(page, "week")).to_have_class(re.compile("pattern-vertical-board__column--active"))
    expect(_col(page, "week")).to_have_attribute("data-period-key", "2026-W32")
    page.mouse.click(box["x"] + 30, box["y"] + 14)
    expect(_col(page, "week")).not_to_have_class(re.compile("pattern-vertical-board__column--active"))


@pytest.mark.parametrize("vertical,view,how,floats", [
    ("week", "Weeks", ["This week", "Next week", "In 2 weeks"], "month"),
    ("month", "Months", ["This month", "Next month", "In 2 months"], "quarter"),
])
def test_the_middle_bar_opens_the_spans_mode(ui_f2: UiSession, vertical: str, view: str, how: list[str], floats: str) -> None:
    """The mode a dragged task opens on the column's corner: a week in each column for Week, a month in each for Month,
    this period first, the next one up floating wide over them, and the field naming the view. Esc, with nothing in the
    hand, leaves it and the board is as it was."""
    page = _open(ui_f2)
    here = _col(page, vertical).get_attribute("data-period-key")
    _col(page, vertical).locator('[data-cap="period-mode"]').click()
    expect(page.locator(SPANS)).to_have_count(1, timeout=5000)
    expect(page.locator(SPANS)).to_have_attribute("data-vertical", vertical)
    heads = page.locator(SPAN_HEADS)
    for i, words in enumerate(how):
        expect(heads.nth(i)).to_have_text(words)
    expect(page.locator(f'[data-role="spans-floating"] [data-vertical="{floats}"]')).to_have_count(1)
    expect(page.locator('[data-role="moving-view"]')).to_have_text(view)
    # neither the floating column nor a span pages, so neither has bars that would do nothing, nor the line
    expect(page.locator(f'{SPANS} [data-cap="period-nav"]')).to_have_count(0)
    expect(page.locator(f'{SPANS} [data-role="column-line"]')).to_have_count(0)
    page.keyboard.press("Escape")
    expect(page.locator(SPANS)).to_have_count(0, timeout=5000)
    expect(page.locator(STRIP)).to_have_count(1)
    expect(_col(page, vertical)).to_have_attribute("data-period-key", here or "")
    expect(page.locator('[data-role="moving-stack"]')).to_have_count(0)


def test_the_mode_opens_from_this_period_whichever_the_column_shows(ui_f2: UiSession) -> None:
    """Paged two weeks on, the Week column's mode still starts at this week, as the mode does from the corner."""
    page = _open(ui_f2)
    activate_column(page, "week")
    for key in ("2026-W33", "2026-W34"):
        _col(page, "week").locator('[data-cap="period-next"]').click()
        expect(_col(page, "week")).to_have_attribute("data-period-key", key)
    _col(page, "week").locator('[data-cap="period-mode"]').click()
    expect(page.locator(SPANS)).to_have_count(1, timeout=5000)
    expect(page.locator(SPAN_HEADS).first).to_have_text("This week")
    page.keyboard.press("Escape")
    expect(page.locator(SPANS)).to_have_count(0, timeout=5000)


# What the pinned line shows, read off the page: its state, both of its words with how much each is seen, where it stands
# under the column's top, and the fade under it.
_LINE = """(vertical) => {
  const col = document.querySelector(`[data-role="column-strip"] > [data-vertical="${vertical}"]`);
  const line = col.querySelector('[data-role="column-line"]');
  const kind = line.querySelector('[data-role="column-line-kind"]');
  const name = line.querySelector('[data-role="column-line-name"]');
  const box = col.getBoundingClientRect(), lineBox = line.getBoundingClientRect();
  const fade = getComputedStyle(line, '::after');
  const slide = col.querySelector('.period-slide:not([data-state="outgoing"])');
  const title = col.querySelector('.t-title');
  return {
    state: line.dataset.state, kind: kind.textContent.trim(), name: name.textContent.trim(),
    kindShown: parseFloat(getComputedStyle(kind).opacity), nameShown: parseFloat(getComputedStyle(name).opacity),
    top: lineBox.top - box.top, left: lineBox.left - box.left, right: box.right - lineBox.right, height: lineBox.height,
    background: getComputedStyle(line).backgroundColor,
    fade: { top: parseFloat(fade.top), height: fade.height, image: fade.backgroundImage, opacity: parseFloat(fade.opacity) },
    scrollTop: slide.scrollTop, titleTop: title.getBoundingClientRect().top - box.top,
  };
}"""


def _line(page: Page, vertical: str) -> dict:
    return page.evaluate(_LINE, vertical)


def _scroll(page: Page, vertical: str, top: int) -> None:
    _col(page, vertical).locator(".period-slide:not([data-state='outgoing'])").evaluate("(el, top) => { el.scrollTop = top }", top)
    _frames(page)


def _wait_line(page: Page, vertical: str, state: str) -> dict:
    """The line once it says `state` and the word of that state is the one seen."""
    expect(_col(page, vertical).locator('[data-role="column-line"]')).to_have_attribute("data-state", state)
    role = "column-line-kind" if state == "kind" else "column-line-name"
    page.wait_for_function(
        """([vertical, role]) => {
          const line = document.querySelector(`[data-role="column-strip"] > [data-vertical="${vertical}"] [data-role="column-line"]`);
          return parseFloat(getComputedStyle(line.querySelector(`[data-role="${role}"]`)).opacity) > 0.99;
        }""",
        arg=[vertical, role],
    )
    return _line(page, vertical)


def test_a_scrolled_column_pins_its_line_and_names_the_period(ui_f2: UiSession) -> None:
    """At its top the line says the kind, "Week", where the header's own kind stands; scrolled until the big name has gone
    under it, the period, "3–9 Aug". It stays at the column's top on white all along, over the goals, and fades them over
    14 px: the line's own 28 px take every click, the 14 under it none."""
    _seed(ui_f2, "week", 40)
    page = _open(ui_f2)
    top = _wait_line(page, "week", "kind")
    assert (top["kind"], top["name"]) == ("Week", "3–9 Aug")
    assert top["top"] == 0 and top["height"] == 28 and top["background"] == "rgb(255, 255, 255)"
    assert top["left"] == 0 and top["right"] == 0, "the line is the column's width"
    assert top["fade"]["top"] == 28 and top["fade"]["height"] == "14px", "the fade is 14 px, right under the line"
    assert "linear-gradient" in top["fade"]["image"] and "255, 255, 255" in top["fade"]["image"]
    assert top["fade"]["opacity"] == 0, "at rest nothing fades: the big name stands right under the line"
    assert top["titleTop"] > 0, "the big name stands below the line"

    _scroll(page, "week", 7)
    near = _wait_line(page, "week", "kind")
    assert near["kind"] == "Week" and near["top"] == 0 and 0.4 < near["fade"]["opacity"] < 0.6, near["fade"]

    _scroll(page, "week", 300)
    named = _wait_line(page, "week", "period")
    assert named["name"] == "3–9 Aug" and named["top"] == 0, "pinned at the top of the column"
    assert named["scrollTop"] == 300 and named["titleTop"] < -200, "the big name has scrolled up and away"
    assert named["fade"]["opacity"] == 1

    # the line's own height takes the click, so a goal that is out of sight under it is not opened; the fade under it lets
    # the pointer through to what shows there
    box = _col(page, "week").bounding_box()
    assert box is not None
    covers = "([x, y]) => document.elementFromPoint(x, y)?.closest('[data-role=\"column-line\"]') !== null"
    assert page.evaluate(covers, [box["x"] + 80, box["y"] + 10]) is True
    assert page.evaluate(covers, [box["x"] + 80, box["y"] + 34]) is False

    _scroll(page, "week", 0)
    _wait_line(page, "week", "kind")


def test_a_wheel_over_the_line_scrolls_the_column(ui_f2: UiSession) -> None:
    """The line is part of the slide that scrolls, as the header is: the pointer on it, scrolled or not, wheels the goals,
    and the line stays."""
    _seed(ui_f2, "week", 40)
    page = _open(ui_f2)
    box = _col(page, "week").bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + 80, box["y"] + 10)
    for want in (100, 220):
        page.mouse.wheel(0, 150)
        page.wait_for_function(
            "(want) => document.querySelector('[data-role=\"column-strip\"] > [data-vertical=\"week\"] .period-slide').scrollTop >= want",
            arg=want,
        )
        assert _line(page, "week")["top"] == 0


def test_an_opened_goal_is_scrolled_into_view_below_the_line(ui_f2: UiSession) -> None:
    """A goal that has to scroll to be seen whole stops 16 px under the edge the goals scroll under (lib/columnFit.ts):
    below the line and its 14 px of fade, not under them."""
    _seed(ui_f2, "week", 40)
    page = _open(ui_f2)
    _scroll(page, "week", 300)
    column = _col(page, "week")
    low = column.locator(".goal-card[data-row-key]").evaluate_all(
        """(cards) => { const col = cards[0].closest('[data-vertical]').getBoundingClientRect();
          const seen = cards.filter((c) => { const r = c.getBoundingClientRect(); return r.top > col.top + 60 && r.bottom < innerHeight - 40; });
          return seen[seen.length - 1].dataset.goalId; }""")
    column.locator(f'.goal-card[data-goal-id="{low}"] > .goal-card__row .goal-card__title').first.click()
    expect(page.locator(".goal-card--detail-open")).to_have_count(1)
    page.wait_for_function("() => !document.body.dataset.familyMoving")
    _frames(page, 6)
    top = column.locator(".goal-card--detail-open").evaluate(
        "(card) => card.getBoundingClientRect().top - card.closest('[data-vertical]').getBoundingClientRect().top")
    assert top >= 42, f"the opened goal stands {top:.0f} px under the column's top: under the line and its fade"


def test_the_line_takes_the_period_once_the_name_is_under_it_and_gives_it_back_sooner(ui_f2: UiSession) -> None:
    """Between the two states there is no flicker: it takes the period at 32 px, once the big name is under the line, and
    gives it back at 27, a few px sooner on the way up."""
    _seed(ui_f2, "week", 40)
    page = _open(ui_f2)
    down = {}
    for top in (0, 20, 28, 31, 32, 33, 40, 100):
        _scroll(page, "week", top)
        down[top] = _line(page, "week")["state"]
    assert down == {0: "kind", 20: "kind", 28: "kind", 31: "kind", 32: "period", 33: "period", 40: "period", 100: "period"}
    up = {}
    for top in (40, 30, 29, 28, 27, 10):
        _scroll(page, "week", top)
        up[top] = _line(page, "week")["state"]
    assert up == {40: "period", 30: "period", 29: "period", 28: "period", 27: "kind", 10: "kind"}


def test_the_bars_stay_in_reach_on_a_scrolled_column(ui_f2: UiSession) -> None:
    """They are on the line: scrolled far down, the side bar still pages the column, which comes in at its top."""
    _seed(ui_f2, "week", 40)
    page = _open(ui_f2)
    _hover(page, "week")
    _scroll(page, "week", 300)
    _wait_line(page, "week", "period")
    _col(page, "week").locator('[data-cap="period-next"]').click()
    expect(_col(page, "week")).to_have_attribute("data-period-key", "2026-W33")
    expect(_col(page, "week").locator('[data-role="period-slide"]')).to_have_count(1)
    line = _wait_line(page, "week", "kind")
    assert line["kind"] == "Week" and line["scrollTop"] == 0


def test_the_line_says_the_words_the_header_chose(ui_f2: UiSession) -> None:
    """Beside an open column Day's room is 152 px: its big name, Wednesday, takes its short form, "Wed" (the 164.5 px of
    the whole word do not fit); the pinned line says the same word, and the kind stays "Day"."""
    _seed(ui_f2, "day", 40, "2026-08-05")
    page = _open(ui_f2, "2026-08-05", width=1470)
    expand_column(page, "month")
    expect(_col(page, "day").locator(".t-title")).to_have_text("Wed", timeout=5000)
    _scroll(page, "day", 300)
    line = _wait_line(page, "day", "period")
    assert (line["name"], line["kind"]) == ("Wed", "Day")
    _scroll(page, "day", 0)
    # opened, the column has room for the whole word, in the header and on the line
    expand_column(page, "day")
    expect(_col(page, "day").locator(".t-title")).to_have_text("Wednesday", timeout=5000)
    _scroll(page, "day", 300)
    assert _wait_line(page, "day", "period")["name"] == "Wednesday"


def test_the_line_brings_along_what_the_kind_line_carried(ui_f2: UiSession) -> None:
    """A period outside this year says its year on the kind line, and a week whose month moved up there says the month. The
    line names the period without its kind, so it says them after the name: a column scrolled to January 2027 does not
    read as this January, nor a week as no month's."""
    _seed(ui_f2, "month", 40, "2027-01-10")
    page = _open(ui_f2, "2027-01-10")
    top = _wait_line(page, "month", "kind")
    assert (top["kind"], top["name"]) == ("Month · ’27", "January · ’27")
    _scroll(page, "month", 300)
    assert _wait_line(page, "month", "period")["name"] == "January · ’27"

    # beside an open column "25–31 May" does not fit its 152 px: the month moves up to the kind line, "Week · May"
    _seed(ui_f2, "week", 40, "2026-05-27")
    page = _open(ui_f2, "2026-05-27", width=1470)
    expand_column(page, "day")
    expect(_col(page, "week").locator(".t-title")).to_have_text("25–31", timeout=5000)
    assert _wait_line(page, "week", "kind")["kind"] == "Week · May"
    _scroll(page, "week", 300)
    assert _wait_line(page, "week", "period")["name"] == "25–31 · May"


def test_life_has_the_line_and_no_bars(ui_f2: UiSession) -> None:
    """Life does not page, so it has no bars; its goals still scroll under the same line, "Life" and then "All time"."""
    _seed(ui_f2, "life", 40)
    page = _open(ui_f2)
    expect(_col(page, "life").locator('[data-cap="period-nav"]')).to_have_count(0)
    top = _wait_line(page, "life", "kind")
    assert (top["kind"], top["name"], top["top"]) == ("Life", "All time", 0)
    _scroll(page, "life", 300)
    assert _wait_line(page, "life", "period")["name"] == "All time"


def test_the_bars_are_buttons_named_by_the_columns_kind(ui_f2: UiSession) -> None:
    """"Previous week", "Week mode", "Next week" for Week, and the same by each column's kind, for the keyboard and for
    assistive tech: three buttons, the side bars first and last."""
    page = _open(ui_f2)
    for vertical in PAGED:
        kind = KINDS[vertical]
        want = [f"Previous {kind.lower()}", f"{kind} mode", f"Next {kind.lower()}"]
        column = _col(page, vertical)
        bars = column.locator("[data-cap='period-prev'], [data-cap='period-mode'], [data-cap='period-next']")
        assert bars.evaluate_all("els => els.map((el) => [el.tagName, el.getAttribute('aria-label')])") == [["BUTTON", name] for name in want]
        for name in want:
            expect(column.get_by_role("button", name=name, exact=True)).to_have_count(1)


def test_the_keyboard_reaches_every_bar_and_shows_them(ui_f2: UiSession) -> None:
    """Tab goes through a column's three bars, which come first in it, whether the pointer is there or not, and a bar in
    focus brings its sides into view; Enter pages, Space opens the mode, Esc leaves it."""
    page = _open(ui_f2)
    _rest(page)
    assert len(_bars(page, "week")) == 3
    week = _col(page, "week")
    week.locator('[data-cap="period-prev"]').focus()
    assert len(_wait_bars(page, "week", 5)) == 5, "a bar in focus shows the whole sign"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.cap") == "period-mode"
    mark = week.locator('[data-cap="period-mode"] .column-bars__mark').evaluate("el => getComputedStyle(el).backgroundColor")
    assert mark == "rgba(45, 48, 54, 0.08)", f"focus has a mark: {mark}"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.cap") == "period-next"
    page.keyboard.press("Enter")
    expect(week).to_have_attribute("data-period-key", "2026-W33")
    expect(week.locator('[data-role="period-slide"]')).to_have_count(1)
    week.locator('[data-cap="period-mode"]').focus()
    page.keyboard.press("Space")
    expect(page.locator(SPANS)).to_have_count(1, timeout=5000)
    page.keyboard.press("Escape")
    expect(page.locator(SPANS)).to_have_count(0, timeout=5000)


def test_on_touch_the_side_bars_stay_in_view(ui_f2: UiSession) -> None:
    """Nothing hovers on a touch screen, so the bars are all there at rest, and a tap does what the pointer does."""
    context = ui_f2.context.browser.new_context(
        viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True, reduced_motion="reduce")
    context.add_init_script(script=_DIALOG_RECORDER_SCRIPT)
    context.add_init_script(script=_MORNING_ASKED_SCRIPT)
    page = context.new_page()
    try:
        page.clock.set_fixed_time("2026-08-08T09:00:00+03:00")
        page.goto(ui_f2.base_url)
        page.wait_for_selector(f"{STRIP} > [data-vertical='day'] .column-header")
        assert page.evaluate("matchMedia('(hover: hover) and (pointer: fine)').matches") is False
        bars = _wait_bars(page, "day", 5)
        assert [bar["color"] for bar in bars] == [LIGHT, LIGHT, INK, LIGHT, LIGHT], bars
        assert bars[-1]["right"] == pytest.approx(MARGIN, abs=0.01)
        _col(page, "day").locator('[data-cap="period-next"]').tap()
        expect(_col(page, "day")).to_have_attribute("data-period-key", "2026-08-09")
        _col(page, "day").locator('[data-cap="period-mode"]').tap()
        expect(page.locator(SPANS)).to_have_count(1, timeout=5000)
    finally:
        context.close()
