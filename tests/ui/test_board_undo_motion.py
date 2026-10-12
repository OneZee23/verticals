"""How undo moves (docs/design/board-undo.md; `web/src/lib/undoGlide.ts`, `web/src/components/FieldNotice.vue`): a change you
can see is undone in place with its own movement played back: the goal glides from where it stands to where it goes, the rows
around it slide to make room, all as one movement and never a jump. A tick has its own motion and adds none. With reduced
motion nothing glides. The notice comes up from nearly full size and the field fades as it does, and both go the same way.
Traced frame by frame in the page, so a one-frame jump shows."""

from __future__ import annotations

import math
import threading

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


# Which of the two, the copy that flies and the card it becomes, is drawn in each frame; read after the frame is painted.
SHOWN = r"""(id) => {
  const s = window.__shown = { frames: [], on: false, t0: 0 };
  const drawn = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden' && parseFloat(getComputedStyle(el).opacity) > 0.01;
  function sample(now) {
    const real = document.querySelector(`.goal-card[data-goal-id="${id}"]:not([data-ghost])`);
    const copy = document.querySelector(`[data-flight-for="${id}"]`);
    s.frames.push({ t: now - s.t0, copy: drawn(copy), real: drawn(real) });
  }
  function frame(now) {
    if (!s.on) return;
    requestAnimationFrame(frame);
    setTimeout(() => { if (s.on) sample(now); }, 0);
  }
  s.start = () => { s.frames = []; s.on = true; s.t0 = performance.now(); requestAnimationFrame(frame); };
  s.stop = () => { s.on = false; return s.frames; };
}"""

# The flight stopped at a chosen moment: every animation on the page set to that time, then the copy and the card read.
AT = r"""(t) => {
  for (const a of document.getAnimations()) a.currentTime = Math.min(t, a.effect.getComputedTiming().endTime);
  const box = (el, selector) => { const r = (selector ? el.querySelector(selector) : el).getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
  const drawn = (el) => getComputedStyle(el).visibility !== 'hidden' && parseFloat(getComputedStyle(el).opacity) > 0.01;
  const look = (el) => ({ card: box(el), title: box(el, '.goal-card__title-text'), check: box(el, '.checkbox__box'), drawn: drawn(el) });
  const real = document.querySelector('.goal-card[data-goal-id="SYNORD01"]:not([data-ghost])');
  const copy = document.querySelector('[data-flight-for="SYNORD01"]');
  return { t, copy: copy ? look(copy) : null, real: look(real) };
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


def trace_from_the_key(page: Page, recorder: str, key: str) -> None:
    """Starts a recorder in the key's own event, ahead of everything the page does with the key, and presses the key. No frame from
    before the key is in the trace. (Started in a call of its own, the recorder's first frame can come before the key does: the
    key reaches the page a few milliseconds after the call returns, a frame is 16, and about one run in five had one frame of the
    board as it was before the key, which is not the undo's.)"""
    page.evaluate(
        """(name) => {
          const on = (e) => { if (e.key.toLowerCase() !== 'z') return; window.removeEventListener('keydown', on, true); window[name].start() }
          window.addEventListener('keydown', on, true)
        }""",
        recorder,
    )
    page.keyboard.press(key)


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


def check_the_glide(frames: list[dict], was: dict, neighbour_was: dict, now: dict, neighbour_now: dict) -> None:
    """What the frames of an undone drag must show: the goal and the row that makes room start where they stood, as big as they were,
    only move toward where they go, arrive together in about the board's 300 ms, and the goal is never nowhere."""
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


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_undoing_a_drag_glides_the_goal_and_the_rows_around_it_as_one_movement(ui_f2: UiSession) -> None:
    page, undo, was, neighbour_was = after_the_drop(ui_f2)
    page.evaluate(ROWS, ["SYNORD01", "SYNORD02"])
    trace_from_the_key(page, "__undo", undo)
    page.wait_for_timeout(900)
    frames = page.evaluate("window.__undo.stop()")
    check_the_glide(frames, was, neighbour_was, rect(page, "SYNORD01"), rect(page, "SYNORD02"))


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_glide_starts_with_the_key_however_long_the_server_takes_to_answer(ui_f2: UiSession) -> None:
    """The page asks the server what the goal holds before it writes (an agent may have changed it a moment ago, and the board hears
    of that after a pause), and what the person sees does not wait for the answer. The server here is held up for 800 ms by
    a lock on the goals table, which stops every read and write; the frames are the same as with a server that answers at once,
    and the write goes when the server does."""
    session = ui_f2
    page, undo, was, neighbour_was = after_the_drop(session)
    page.evaluate(ROWS, ["SYNORD01", "SYNORD02"])
    with psycopg.connect(session.backend.dsn) as holder, psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        holder.execute("LOCK TABLE goals IN ACCESS EXCLUSIVE MODE")
        release = threading.Timer(0.8, holder.commit)
        release.start()
        trace_from_the_key(page, "__undo", undo)
        page.wait_for_timeout(900)
        frames = page.evaluate("window.__undo.stop()")
        release.join()
        wait_for(page, lambda: goal(conn, "SYNORD01")[1], "week", "the goal is put back once the server answers", timeout=8)
    check_the_glide(frames, was, neighbour_was, rect(page, "SYNORD01"), rect(page, "SYNORD02"))


@pytest.mark.parametrize("ui_reduced_motion", ["reduce"], indirect=True)
def test_with_reduced_motion_undo_puts_the_goal_back_without_a_glide(ui_f2: UiSession) -> None:
    page, undo, was, _ = after_the_drop(ui_f2)
    page.evaluate(ROWS, ["SYNORD01", "SYNORD02"])
    trace_from_the_key(page, "__undo", undo)
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
        trace_from_the_key(page, "__undo", undo)
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
    esc = page.evaluate("performance.now() - window.__pill.t0")  # the recorder's clock, as the key is sent
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
    # Timed from the key that dismissed it to the last frame it is drawn in, as the person feels it. (From the first frame past
    # 400 ms, which came before the key by however long the test's own wait overshot, a loaded machine read 224 for 220.)
    assert (leaving[-1]["t"] - esc) <= 220, "and a little quicker than it came"


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


def start_the_flight(session: UiSession) -> tuple[Page, dict, float]:
    """SYNORD01 dropped in Month and undone, the flight stopped before its first frame has moved on. Returns the page, the
    card as it stood in Month, and the flight's length."""
    page, undo, was, _ = after_the_drop(session)
    page.keyboard.press(undo)
    page.wait_for_function("document.querySelector('[data-flight-for]') !== null", timeout=3000)
    page.evaluate("document.getAnimations().forEach((a) => a.pause())")
    total = page.evaluate("document.getAnimations().find((a) => a.id === 'undo-glide').effect.getComputedTiming().endTime")
    return page, was, total


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_no_frame_of_the_flight_draws_the_goal_twice(ui_f2: UiSession) -> None:
    page, undo, _, _ = after_the_drop(ui_f2)
    page.evaluate(SHOWN, "SYNORD01")
    trace_from_the_key(page, "__shown", undo)
    page.wait_for_timeout(900)
    frames = page.evaluate("window.__shown.stop()")
    flight = [i for i, f in enumerate(frames) if f["copy"]]
    assert flight, "the goal flew as a copy"
    assert not [f for f in frames if f["copy"] and f["real"]], "the copy and the card are never drawn together"
    first, last = flight[0], flight[-1]
    assert all(f["copy"] != f["real"] for f in frames[first:]), "from the first frame of the flight on, the goal is drawn once, never none"
    assert frames[last + 1]["real"] and not frames[last + 1]["copy"], "the card is drawn in the frame after the copy's last"
    assert 150 <= frames[last]["t"] - frames[first]["t"] <= 450, "about the board's 300 ms"


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_flying_goal_grows_into_the_card_it_becomes_and_sits_exactly_on_it(ui_f2: UiSession) -> None:
    """Week is the open column here: its cards are bigger than Month's, in their text, their checkbox and their gaps. The
    copy is stopped at chosen moments of the flight, the last of them 40, 16 and 1 ms from the end."""
    page, was, total = start_the_flight(ui_f2)
    assert 250 <= total <= 350
    seen = [page.evaluate(AT, t) for t in (0, total * 0.33, total * 0.66, total - 40, total - 16, total - 1, total)]

    first = seen[0]
    for key in ("card", "title", "check"):
        assert first["real"][key]["w"] > first["copy"][key]["w"] * 1.4, f"the {key} is bigger in Week than in Month, or this proves nothing"
    assert abs(first["copy"]["card"]["x"] - was["x"]) < 1 and abs(first["copy"]["card"]["w"] - was["w"]) < 1, "it starts as the card it was"

    for look in seen[:-1]:
        assert look["copy"]["drawn"] and not look["real"]["drawn"], f"at {look['t']:.0f} ms the copy is drawn and the card is not"
    for left, right in zip(seen, seen[1:-1]):
        for key in ("title", "check"):
            assert right["copy"][key]["w"] >= left["copy"][key]["w"] - 0.3, f"the {key} only grows toward the card it becomes"

    # 1 ms before the end the copy is on the card: its box, its checkbox and its words.
    near, end = seen[-2], seen[-1]
    for key in ("card", "check"):
        got, want = near["copy"][key], near["real"][key]
        assert all(abs(got[axis] - want[axis]) < 1 for axis in "xywh"), f"the {key} sits on the real one: {got} against {want}"
    got, want = near["copy"]["title"], near["real"]["title"]
    assert abs(got["x"] - want["x"]) < 1 and abs(got["w"] - want["w"]) < 1, f"the words stand where the real ones do: {got} against {want}"
    assert abs((got["y"] + got["h"] / 2) - (want["y"] + want["h"] / 2)) < 1.5, "and on the same line"

    # In the instant the flight ends the copy is gone and the card is there: one frame, nothing between.
    assert not end["copy"]["drawn"] and end["real"]["drawn"]


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_a_card_that_is_not_the_same_card_only_travels(ui_f2: UiSession) -> None:
    """When the copy's parts are not the card's parts (one of them has been changed under the page's hands), nothing can be
    matched: the copy keeps its size, still ends where the card is, and still gives way in one frame."""
    page, undo, was, _ = after_the_drop(ui_f2)
    page.evaluate("document.querySelector('[data-vertical=\"month\"] [data-goal-id=\"SYNORD01\"] .goal-card__row').append(document.createElement('i'))")
    page.keyboard.press(undo)
    page.wait_for_function("document.querySelector('[data-flight-for]') !== null", timeout=3000)
    page.evaluate("document.getAnimations().forEach((a) => a.pause())")
    total = page.evaluate("document.getAnimations().find((a) => a.id === 'undo-glide').effect.getComputedTiming().endTime")
    seen = [page.evaluate(AT, t) for t in (0, total / 2, total - 1, total)]
    for look in seen[:-1]:
        assert look["copy"]["drawn"] and not look["real"]["drawn"]
        assert abs(look["copy"]["card"]["w"] - was["w"]) < 1, "the copy keeps the size it had"
    near = seen[-2]
    assert abs(near["copy"]["card"]["x"] - near["real"]["card"]["x"]) < 1 and abs(near["copy"]["card"]["y"] - near["real"]["card"]["y"]) < 1
    assert not seen[-1]["copy"]["drawn"] and seen[-1]["real"]["drawn"]
