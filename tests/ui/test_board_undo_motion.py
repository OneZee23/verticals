"""How undo moves (docs/design/board-undo.md; `web/src/lib/undoGlide.ts`, `web/src/components/FieldNotice.vue`): a change you
can see is undone in place with its own movement played back: the goal glides from where it stands to where it goes, the rows
around it slide to make room, all as one movement and never a jump. A tick has its own motion and adds none. With reduced
motion nothing glides. The notice comes up from nearly full size and the field fades as it does, and both go the same way.
Traced frame by frame in the page, so a one-frame jump shows."""

from __future__ import annotations

import math

import psycopg
import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession, activate_column
from tests.ui.undo_helpers import ACTION, CIRCLE_FIELD, GRIP, NOTICE, expect_no_notice, goal, keys, wait_for

ORD01_ROW = '[data-goal-id="SYNORD01"] > .goal-card__row'
MONTH_BODY = '[data-vertical="month"] .pattern-vertical-board__body'

ROWS = r"""(ids) => {
  const s = window.__undo = { frames: [], on: false, t0: 0 };
  // Read after the frame is painted (a task after the animation frame), so what is read is what was shown.
  function sample(now) {
    const f = { t: now - s.t0, rows: {}, glides: document.getAnimations().filter((a) => a.id === 'undo-glide').length };
    for (const id of ids) {
      const real = document.querySelector(`.goal-card[data-goal-id="${id}"]:not([data-ghost])`);
      const shown = document.querySelector(`[data-flight-for="${id}"]`) ?? real;
      if (!shown) { f.rows[id] = null; continue; }
      const r = shown.getBoundingClientRect();
      f.rows[id] = { x: r.left, y: r.top, w: r.width, h: r.height, col: real?.closest('[data-vertical]')?.dataset.vertical ?? null, flying: shown !== real };
    }
    s.frames.push(f);
  }
  function frame(now) {
    if (!s.on) return;
    requestAnimationFrame(frame);
    setTimeout(() => { if (s.on) sample(now); }, 0);
  }
  s.start = () => { s.frames = []; s.on = true; s.t0 = performance.now(); requestAnimationFrame(frame); };
  s.stop = () => { s.on = false; return s.frames; };
}"""

PILL = r"""() => {
  const s = window.__pill = { frames: [], on: false, t0: 0 };
  function frame(now) {
    if (!s.on) return;
    const pill = document.querySelector('[data-role="field-notice"]');
    const field = document.querySelector('.circle-field');
    s.frames.push({
      t: now - s.t0,
      pill: pill ? { opacity: parseFloat(getComputedStyle(pill).opacity), scale: parseFloat(getComputedStyle(pill).scale) || 1 } : null,
      field: parseFloat(getComputedStyle(field).opacity),
    });
    requestAnimationFrame(frame);
  }
  s.start = () => { s.frames = []; s.on = true; s.t0 = performance.now(); requestAnimationFrame(frame); };
  s.stop = () => { s.on = false; return s.frames; };
}"""


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    return getattr(request, "param", "no-preference")


def board(session: UiSession) -> Page:
    session.page.wait_for_selector('[data-goal-id="SYNDAY01"]', timeout=10000)
    return session.page


def rect(page: Page, goal_id: str) -> dict:
    return page.evaluate(
        """(id) => { const r = document.querySelector(`.goal-card[data-goal-id="${id}"]:not([data-ghost])`).getBoundingClientRect();
                      return { x: r.left, y: r.top, w: r.width, h: r.height } }""",
        goal_id,
    )


def away(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def after_the_drop(session: UiSession) -> tuple[Page, str, dict, dict]:
    """SYNORD01 dragged from Week to Month, stored and settled; the rows it will glide between, as they stand."""
    page = board(session)
    session.gestures.drag(ORD01_ROW, MONTH_BODY, source_position=GRIP, target_position=GRIP)
    page.wait_for_selector('[data-vertical="month"] [data-goal-id="SYNORD01"]', timeout=5000)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        wait_for(page, lambda: goal(conn, "SYNORD01")[1], "month", "the drop is stored")
    page.wait_for_timeout(900)  # the landing's own flight is over
    return page, keys(page)[0], rect(page, "SYNORD01"), rect(page, "SYNORD02")


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_undoing_a_drag_glides_the_goal_and_the_rows_around_it_as_one_movement(ui_f2: UiSession) -> None:
    page, undo, was, neighbour_was = after_the_drop(ui_f2)
    page.evaluate(ROWS, ["SYNORD01", "SYNORD02"])
    page.evaluate("window.__undo.start()")
    page.keyboard.press(undo)
    page.wait_for_timeout(900)
    frames = page.evaluate("window.__undo.stop()")
    now, neighbour_now = rect(page, "SYNORD01"), rect(page, "SYNORD02")
    assert away(now, was) > 100 and neighbour_now["y"] > neighbour_was["y"] + 10, "the goal moved columns and the next row made room"

    for who, start, end in (("SYNORD01", was, now), ("SYNORD02", neighbour_was, neighbour_now)):
        seen = [(f["t"], f["rows"][who]) for f in frames if f["rows"][who] is not None and (who != "SYNORD01" or f["rows"][who]["col"] == "week")]
        assert seen, f"{who} was never drawn in its new place"
        first_t, first = seen[0]
        assert away(first, start) < 3, f"{who}'s first frame in its new place is where it stood ({away(first, start):.1f} px off), not a jump"
        assert abs(first["w"] - start["w"]) < 6 and abs(first["h"] - start["h"]) < 6, (
            f"{who} starts as big as it was ({first['w']:.0f} x {first['h']:.0f}, was {start['w']:.0f} x {start['h']:.0f}), not as the card it becomes"
        )
        # Then it only moves toward where it goes, and arrives.
        distances = [away(row, end) for _, row in seen]
        assert all(b <= a + 0.5 for a, b in zip(distances, distances[1:])), f"{who} goes back and forth: {distances}"
        arrived = next(t for (t, row) in seen if away(row, end) < 1)
        assert 200 <= arrived - first_t <= 450, f"{who} took {arrived - first_t:.0f} ms, about the board's 300"

    assert any(f["glides"] for f in frames), "the glide is the page's own animation"
    # Never a frame where the goal is nowhere once it has been drawn.
    drawn = [f["rows"]["SYNORD01"] is not None for f in frames]
    assert drawn.index(True) == next(i for i, f in enumerate(frames) if f["rows"]["SYNORD01"] and f["rows"]["SYNORD01"]["col"] == "week")
    assert all(drawn[drawn.index(True):]), "the goal vanished for a frame"
    # Both go as one: they arrive together.
    ends = [next(f["t"] for f in frames if f["rows"][who] and away(f["rows"][who], end) < 1) for who, end in (("SYNORD01", now), ("SYNORD02", neighbour_now))]
    assert abs(ends[0] - ends[1]) < 50, f"the goal and the row that made room arrive {abs(ends[0] - ends[1]):.0f} ms apart"


@pytest.mark.parametrize("ui_reduced_motion", ["reduce"], indirect=True)
def test_with_reduced_motion_undo_puts_the_goal_back_without_a_glide(ui_f2: UiSession) -> None:
    page, undo, was, _ = after_the_drop(ui_f2)
    page.evaluate(ROWS, ["SYNORD01", "SYNORD02"])
    page.evaluate("window.__undo.start()")
    page.keyboard.press(undo)
    page.wait_for_timeout(700)
    frames = page.evaluate("window.__undo.stop()")
    assert not any(f["glides"] for f in frames), "nothing glides when motion is reduced"
    first = next(f["rows"]["SYNORD01"] for f in frames if f["rows"]["SYNORD01"] and f["rows"]["SYNORD01"]["col"] == "week")
    assert away(first, rect(page, "SYNORD01")) < 1, "it is where it goes from its first frame"


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_undoing_a_tick_adds_no_glide_of_its_own(ui_f2: UiSession) -> None:
    session = ui_f2
    page = board(session)
    undo, _ = keys(page)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click('[data-goal-id="SYNCOL01"] > .goal-card__row label.checkbox')
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")
        page.wait_for_timeout(900)
        page.evaluate(ROWS, ["SYNCOL01", "SYNCOL02"])
        page.evaluate("window.__undo.start()")
        page.keyboard.press(undo)
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], False, "the tick is taken back")
        page.wait_for_timeout(600)
        frames = page.evaluate("window.__undo.stop()")
    assert not any(f["glides"] for f in frames), "a tick has its own motion; undo adds none"


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference", "reduce"], indirect=True)
def test_the_notice_comes_up_with_the_field_fading_and_goes_the_same_way(ui_f2: UiSession, ui_reduced_motion: str) -> None:
    session = ui_f2
    page = board(session)
    reduced = ui_reduced_motion == "reduce"
    page.evaluate(PILL)
    page.evaluate("window.__pill.start()")
    activate_column(page, "day")
    page.click('[data-goal-id="SYNCOL01"] [data-role=goal-actions-trigger]')
    page.click('#dropdownPortal [data-move="tomorrow"]')
    expect(page.locator(NOTICE)).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)
    page.keyboard.press("Escape")
    expect_no_notice(page)
    page.wait_for_timeout(300)
    frames = page.evaluate("window.__pill.stop()")

    shown = [f for f in frames if f["pill"] is not None]
    came = next(i for i, f in enumerate(shown) if f["pill"]["opacity"] >= 1)
    coming = shown[: came + 1]
    assert coming[0]["pill"]["opacity"] < 1, "the pill does not appear at full strength in one frame"
    assert all(b["pill"]["opacity"] >= a["pill"]["opacity"] - 0.001 for a, b in zip(coming, coming[1:])), "it only gets stronger as it comes"
    scales = [f["pill"]["scale"] for f in coming]
    if reduced:
        assert all(abs(s - 1) < 0.001 for s in scales), "reduced motion: a crossfade, no scale"
    else:
        assert 0.94 <= scales[0] <= 0.99 and scales[-1] == 1, f"it comes up from nearly full size, not from nothing: {scales[:3]}"
        assert all(b >= a - 0.001 for a, b in zip(scales, scales[1:])), "and only grows"
        assert 100 <= (coming[-1]["t"] - coming[0]["t"]) <= 260, "in about 150 ms"
    # The field leaves as the pill comes, and is back once the pill has gone.
    assert min(f["field"] for f in frames) == 0 and frames[-1]["field"] == 1, "the field fades out while the notice stands and comes back"
    leaving = [f for f in shown if f["t"] > shown[came]["t"] + 400]
    assert leaving and leaving[-1]["pill"]["opacity"] < 1, "the notice goes with a fade, not at once"
    assert (leaving[-1]["t"] - leaving[0]["t"]) <= 220, "and a little quicker than it came"


def test_undo_in_the_notice_is_reached_with_the_keyboard_too(ui_f2: UiSession) -> None:
    """Tab reaches Undo while the notice stands, and Enter takes the change back: the notice is not for the pointer only."""
    session = ui_f2
    page = board(session)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        activate_column(page, "day")
        page.click('[data-goal-id="SYNCOL01"] [data-role=goal-actions-trigger]')
        page.click('#dropdownPortal [data-move="tomorrow"]')
        expect(page.locator(ACTION)).to_be_visible(timeout=5000)
        page.locator(ACTION).focus()
        page.keyboard.press("Enter")
        wait_for(page, lambda: goal(conn, "SYNCOL01")[2], "2026-08-08", "Enter on Undo takes the move back")
        expect_no_notice(page)
        expect(page.locator(CIRCLE_FIELD)).to_be_visible()
