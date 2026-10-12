"""Each column is named by its period, its kind small above it, and a name is never cut (docs/design/column-names.md).

The names are a pure function of the board's anchor and of "now", and the web app has no unit-test runner, so these
cases drive the real board the way `test_url_history.py` does: the clock is pinned with `page.clock.set_fixed_time`
(never the real date) and the board is opened at an anchor by its own address, `/h/<date>`. One session walks many
cases, because a session (backend, static server, browser) costs more than a page load.

Read for every column: the big name is `.t-title`, the small kind above it `.t-caption`. Each period has its name in
forms from long to short, and a column shows the longest that fits its room (`lib/fitName.ts`). The rooms the cases
read are the design's own 184 px (a window of 1470 px, no column open), the 152 px of the everyday state (the same
window with a column open) and the desktop app's first window, 1320 px, with 163 px and, beside an open column, 134 px.
"""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession, activate_column, expand_column
from tests.ui.test_moving import SPANS, _centre, _glide, _grab

STRIP = '[data-role="column-strip"]'
VERTICALS = ("day", "week", "month", "quarter", "year", "decade", "life")
KINDS = ("Day", "Week", "Month", "Quarter", "Year", "Three years", "Life")

# The design's "now": a Sunday, the last day of the week 5–11 Oct.
NOW = "2026-10-11T09:00:00+03:00"
# conftest.PINNED_CLOCK_ISO: a Saturday, in the week 3–9 Aug.
SATURDAY = "2026-08-08T09:00:00+03:00"

_READ = f"""() => Object.fromEntries([...document.querySelectorAll('{STRIP} > [data-vertical]')].map((col) => [
  col.dataset.vertical,
  [col.querySelector('.t-title')?.textContent.trim(), col.querySelector('.t-caption')?.textContent.trim()],
]))"""
_CUT = f"""() => [...document.querySelectorAll('{STRIP} > [data-vertical]')].flatMap((col) => {{
  const cut = (el, what) => (el && el.scrollWidth > el.clientWidth ? [`${{col.dataset.vertical}} ${{what}}`] : []);
  return [...cut(col.querySelector('.t-title'), 'name'), ...cut(col.querySelector('.t-caption'), 'kind')];
}})"""


@pytest.fixture
def ui_reduced_motion(request: pytest.FixtureRequest) -> str:
    """Motion off, as the suite runs; the one test that reads a movement frame by frame asks for it on."""
    return getattr(request, "param", "reduce")


def _open(session: UiSession, now: str, anchor: str | None = None, width: int | None = None) -> Page:
    """The board as it stands at `now`, on `anchor` (or on today), in a window `width` px wide (or the suite's)."""
    page = session.page
    if width is not None:
        page.set_viewport_size({"width": width, "height": 820})
    page.clock.set_fixed_time(now)
    page.goto(f"{session.base_url}/h/{anchor}" if anchor else f"{session.base_url}/")
    page.wait_for_selector(f'[data-vertical="day"][data-period-key="{anchor or now[:10]}"] .column-header')
    page.evaluate("() => document.fonts.ready")
    return page


def _names(page: Page) -> dict[str, tuple[str, str]]:
    """`{vertical: (name, kind)}`: what each column's header says, big and small."""
    return {vertical: (name, kind) for vertical, (name, kind) in page.evaluate(_READ).items()}


def _cut(page: Page) -> list[str]:
    """What the ellipsis shows on: "week name" for a column whose name is wider than its room, "week kind" for its kind."""
    return page.evaluate(_CUT)


def _wait_for_names(page: Page, expected: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """The names once the columns say what `expected` says (a layout change is answered in the frame it is drawn in, and
    a read right after the click may come before it), or the last names read."""
    names = _names(page)
    for _ in range(40):
        if all(names.get(vertical) == want for vertical, want in expected.items()):
            break
        page.wait_for_timeout(50)
        names = _names(page)
    return names


def test_the_seven_names_at_now(ui_f2: UiSession) -> None:
    """At now the seven names are Today, 5–11 Oct, October, Q4, ’26, ’26–’28, All time, their kinds above them
    Day, Week, Month, Quarter, Year, Three years, Life; in the type the board already has."""
    page = _open(ui_f2, NOW)
    names = _names(page)
    assert list(names) == list(VERTICALS)
    assert [names[v][0] for v in VERTICALS] == ["Today", "5–11 Oct", "October", "Q4", "’26", "’26–’28", "All time"]
    assert [names[v][1] for v in VERTICALS] == list(KINDS)
    assert _cut(page) == [], "a name is cut off by the column's edge"

    for vertical in VERTICALS:
        column = page.locator(f'{STRIP} > [data-vertical="{vertical}"]')
        name, kind = column.locator(".t-title"), column.locator(".t-caption")
        # The board's own styles, not new ones: the name 700 at 31/40, the kind 15/24 in the board's grey.
        assert name.evaluate("el => { const s = getComputedStyle(el); return [s.fontWeight, s.fontSize, s.lineHeight]; }") == [
            "700", "31px", "40px",
        ]
        assert kind.evaluate("el => { const s = getComputedStyle(el); return [s.fontSize, s.lineHeight, s.color]; }") == [
            "15px", "24px", "rgba(45, 48, 54, 0.52)",
        ]
        name_box, kind_box = name.bounding_box(), kind.bounding_box()
        assert name_box is not None and kind_box is not None
        assert kind_box["y"] + kind_box["height"] <= name_box["y"] + name_box["height"] / 2, f"{vertical}: the kind is not above the name"


# Every month pair a week can cross, one real week each: (an anchor in it, the name in a column of 182 px, the name where
# there is room for it all). The anchors are the week's Sunday, its Monday, a month's last day or something between, so the
# anchor lies on both sides of the boundary. The column of 182 px shows the longest form that fits, measured in the title
# font: the whole name where it is no wider than 182 px (26 Jan–1 Feb is 177.8, 29 Jun–5 Jul 167.1, 27 Jul–2 Aug 175.7;
# 28 Dec–3 Jan is 183.8), else the one without the last day (the widest, 30 Apr–May, is 179.3). The last row is the
# design's own example, "30 Apr–May" and "30 Apr–6 May".
MONTH_PAIRS = (
    ("2026-02-01", "26 Jan–1 Feb", "26 Jan–1 Feb"),
    ("2026-02-28", "23 Feb–Mar", "23 Feb–1 Mar"),
    ("2026-03-30", "30 Mar–Apr", "30 Mar–5 Apr"),
    ("2026-04-30", "27 Apr–May", "27 Apr–3 May"),
    ("2027-05-31", "31 May–Jun", "31 May–6 Jun"),
    ("2026-07-05", "29 Jun–5 Jul", "29 Jun–5 Jul"),
    ("2026-07-31", "27 Jul–2 Aug", "27 Jul–2 Aug"),
    ("2026-08-31", "31 Aug–Sep", "31 Aug–6 Sep"),
    ("2026-10-04", "28 Sep–Oct", "28 Sep–4 Oct"),
    ("2026-10-31", "26 Oct–Nov", "26 Oct–1 Nov"),
    ("2026-12-02", "30 Nov–Dec", "30 Nov–6 Dec"),
    ("2026-12-31", "28 Dec–Jan", "28 Dec–3 Jan"),
    ("2029-04-30", "30 Apr–May", "30 Apr–6 May"),
)


def test_a_week_across_two_months_names_its_end_only_where_there_is_room(ui_f2: UiSession) -> None:
    """"30 Apr–May" in a narrow column, "30 Apr–6 May" in a wide one: all twelve pairs, each in the longest form its room
    holds. A week inside one month stays "5–11 Oct" in both."""
    wrong: list[str] = []
    for anchor, narrow, wide in MONTH_PAIRS:
        page = _open(ui_f2, NOW, anchor)
        found_narrow = _names(page)["week"][0]
        cut = _cut(page)
        expand_column(page, "week")
        found_wide = _wait_for_names(page, {"week": (wide, "Week")})["week"][0]
        if (found_narrow, found_wide) != (narrow, wide):
            wrong.append(f"{anchor}: narrow {found_narrow!r} (want {narrow!r}), wide {found_wide!r} (want {wide!r})")
        if cut:
            wrong.append(f"{anchor}: cut off in the narrow columns {cut}")
    assert not wrong, "\n".join(wrong)

    page = _open(ui_f2, NOW, "2026-10-07")
    assert _names(page)["week"][0] == "5–11 Oct"
    expand_column(page, "week")
    assert _names(page)["week"][0] == "5–11 Oct"


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LAST_DAY = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # February at its longest
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
_MEASURE = """(labels) => {
  const title = document.querySelector('[data-vertical="week"] .t-title');
  const probe = title.cloneNode(false);
  probe.style.cssText = 'position:absolute;visibility:hidden;display:inline-block;width:auto;max-width:none;'
    + 'overflow:visible;text-overflow:clip';
  title.parentElement.appendChild(probe);
  const widest = {};
  for (const [family, texts] of Object.entries(labels)) {
    widest[family] = Math.max(...texts.map((text) => { probe.textContent = text; return probe.getBoundingClientRect().width; }));
  }
  probe.remove();
  return { widest, room: title.parentElement.getBoundingClientRect().width, faces: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family) };
}"""
# The kind lines against the room the kind has: the title's row, less the 36 px the kind row keeps free at the right.
_MEASURE_KIND = """(labels) => {
  const caption = document.querySelector('[data-vertical="week"] .t-caption');
  const probe = caption.cloneNode(false);
  probe.style.cssText = 'position:absolute;visibility:hidden;display:inline-block;width:auto;max-width:none;'
    + 'overflow:visible;text-overflow:clip';
  caption.parentElement.appendChild(probe);
  const widths = Object.fromEntries(labels.map((text) => { probe.textContent = text; return [text, probe.getBoundingClientRect().width]; }));
  probe.remove();
  return { widths, room: caption.parentElement.getBoundingClientRect().width - 36 };
}"""


def _widest(page: Page, labels: dict[str, list[str]]) -> dict:
    page.wait_for_function("() => document.fonts.status === 'loaded'", timeout=5000)
    measured = page.evaluate(_MEASURE, labels)
    assert any("Commissioner" in face for face in measured["faces"]), f"measured without the title font: {measured['faces']}"
    return measured


def _widest_kind(page: Page, labels: list[str]) -> dict:
    page.wait_for_function("() => document.fonts.status === 'loaded'", timeout=5000)
    return page.evaluate(_MEASURE_KIND, labels)


# What a name's shortest form may take beyond its room, `--column-spill` in ColumnHeader.vue.
SPILL = 8


def test_the_forms_fit_the_rooms_the_board_gives_them(ui_f2: UiSession) -> None:
    """The names are set in the board's title type, which does not shrink, so each form is measured, in the font as the app
    loads it, against the room it is meant for: the design's 184 px (a window of 1470 px, no column open) for the forms
    the board shows there, the 152 px of the everyday state (the same window with a column open) and the 134 px of the
    desktop app's first window with a column open for the shortest form of each name, which may take 8 px more. The kind
    lines are measured the same way against the kind's room. A font or a size that makes one too wide cannot cut a name
    unseen."""
    rest = _open(ui_f2, NOW, width=1470)
    pairs = [
        f"{start} {MONTHS[m]}–{MONTHS[(m + 1) % 12]}"
        for m in range(12)
        for start in range(LAST_DAY[m] - (6 if m == 1 else 5), LAST_DAY[m] + 1)
    ]
    whole = _widest(rest, {
        "month pairs": pairs,
        "weekdays": list(WEEKDAYS),
        "months": list(MONTH_NAMES),
        "week in one month": [f"{a}–{a + 6} {MONTHS[m]}" for m in range(12) for a in range(1, LAST_DAY[m] - 5)],
        "dates": [f"{d} {MONTHS[m]}" for m in range(12) for d in range(1, LAST_DAY[m] + 1)],
        "the rest": ["Today", "All time", "Q1", "Q2", "Q3", "Q4", "’25", "’26", "’27", "’28", "’29", "’26–’28", "’23–’25",
                     "’29–’31"],
    })
    assert whole["room"] == pytest.approx(184, abs=0.01), "the design's narrow column is 184 px at a window of 1470 px"
    too_wide = {family: round(width, 1) for family, width in whole["widest"].items() if width > whole["room"]}
    assert not too_wide, f"wider than the narrow column's {whole['room']:.1f} px: {too_wide}"
    assert whole["widest"]["month pairs"] > 170, "the measure is too small to be the title type"

    expand_column(rest, "day")
    everyday = _widest(rest, {
        "shortest pairs": [f"{MONTHS[m]}–{MONTHS[(m + 1) % 12]}" for m in range(12)],
        "weekdays": [day[:3] for day in WEEKDAYS],
        "months": [name[:3] for name in MONTH_NAMES],
        "week in one month": [f"{a}–{a + 6}" for a in range(1, 26)],
        "dates": [f"{d} {MONTHS[m]}" for m in range(12) for d in range(1, LAST_DAY[m] + 1)],
        "the rest": ["Today", "All time", "Q4", "’26", "’26–’28", "’29–’31"],
    })
    assert 152 < everyday["room"] < 153, "the other columns' room is 152 px with one open at 1470 px"
    too_wide = {family: round(width, 1) for family, width in everyday["widest"].items() if width > everyday["room"]}
    assert not too_wide, f"the shortest forms are wider than the {everyday['room']:.1f} px beside an open column: {too_wide}"

    kinds = (
        ["Day", "Week", "Month", "Quarter", "Year", "Three years", "Life"]
        + [f"{kind} · ’27" for kind in ("Day", "Week", "Month", "Quarter")]
        + [f"Week · {month}" for month in MONTHS]
        + [f"Week · {month} ’27" for month in MONTHS]
    )
    seen = _widest_kind(rest, kinds)
    assert seen["room"] == pytest.approx(everyday["room"] - 36, abs=0.01)
    assert not {k: round(w, 1) for k, w in seen["widths"].items() if w > seen["room"]}, "a kind line is wider than its room"

    # The desktop app's first window with a column open: 134 px for the name, 98 for the kind. Every shortest form but
    # one fits as it is, and "Apr–May" (134.8) takes 0.8 px of the 8 it may; the kind line "Week · May ’27" (100.7) takes
    # 2.7 px of its 8.
    narrow = _open(ui_f2, NOW, width=1320)
    expand_column(narrow, "quarter")
    tight = _widest(narrow, {
        "shortest pairs": [f"{MONTHS[m]}–{MONTHS[(m + 1) % 12]}" for m in range(12)],
        "weekdays": [day[:3] for day in WEEKDAYS],
        "months": [name[:3] for name in MONTH_NAMES],
        "week in one month": [f"{a}–{a + 6}" for a in range(1, 26)],
        "dates": [f"{d} {MONTHS[m]}" for m in range(12) for d in range(1, LAST_DAY[m] + 1)],
        "the rest": ["Today", "All time", "Q4", "’26", "’26–’28", "’29–’31", "’98–’00"],
    })
    assert tight["room"] == pytest.approx(134, abs=0.01), "the other columns' room is 134 px with one open at 1320 px"
    beyond = {family: round(width, 1) for family, width in tight["widest"].items() if width > tight["room"] + SPILL}
    assert not beyond, f"the shortest forms are wider than {tight['room']:.0f} px and {SPILL} px more: {beyond}"
    assert not {f: w for f, w in tight["widest"].items() if w > tight["room"] and f != "shortest pairs"}, "only a pair may spill"
    seen = _widest_kind(narrow, kinds)
    assert seen["room"] == pytest.approx(98, abs=0.01)
    beyond = {k: round(w, 1) for k, w in seen["widths"].items() if w > seen["room"] + SPILL}
    assert not beyond, f"a kind line is wider than its {seen['room']:.0f} px and {SPILL} px more: {beyond}"


# (the clock, an anchor, the name Day shows). Saturday 8 Aug is in the week Mon 3 – Sun 9 Aug.
DAYS = (
    (SATURDAY, "2026-08-08", "Today"),
    (SATURDAY, "2026-08-03", "Monday"),
    (SATURDAY, "2026-08-05", "Wednesday"),
    (SATURDAY, "2026-08-09", "Sunday"),
    (SATURDAY, "2026-08-02", "2 Aug"),
    (SATURDAY, "2026-08-10", "10 Aug"),
    (SATURDAY, "2026-10-15", "15 Oct"),
    # The current week moves with now: on Sunday 11 Oct it is Mon 5 – Sun 11 Oct ...
    (NOW, "2026-10-05", "Monday"),
    (NOW, "2026-10-11", "Today"),
    (NOW, "2026-10-12", "12 Oct"),
    (NOW, "2026-10-04", "4 Oct"),
    # ... and on Monday 12 Oct, Mon 12 – Sun 18 Oct: the day before it is already a date.
    ("2026-10-12T09:00:00+03:00", "2026-10-11", "11 Oct"),
    ("2026-10-12T09:00:00+03:00", "2026-10-18", "Sunday"),
)


def test_day_says_its_weekday_in_the_current_week_and_its_date_further_away(ui_f2: UiSession) -> None:
    """Today is "Today"; another day of the current week, Monday to Sunday around now, says its weekday; any other day,
    before or after, says its date."""
    wrong = []
    for now, anchor, name in DAYS:
        found = _names(_open(ui_f2, now, anchor))["day"]
        if found != (name, "Day"):
            wrong.append(f"now {now[:10]}, day {anchor}: {found!r} (want {(name, 'Day')!r})")
    assert not wrong, "\n".join(wrong)


# What the board says at the edges of the year, now being Saturday 8 Aug 2026. (anchor, {vertical: (name, kind)}) for the
# columns the year touches; a period outside 2026 carries its year in the kind line, "Month · ’27", and a week that
# touches 2026 is still this year's.
YEAR_EDGES = (
    ("2025-12-31", {
        "day": ("31 Dec", "Day · ’25"),
        "week": ("29 Dec–Jan", "Week"),  # Mon 29 Dec 2025 – Sun 4 Jan 2026 reaches into 2026
        "month": ("December", "Month · ’25"),
        "quarter": ("Q4", "Quarter · ’25"),
        "year": ("’25", "Year"),
        "decade": ("’23–’25", "Three years"),
    }),
    ("2026-12-31", {
        "day": ("31 Dec", "Day"),
        "week": ("28 Dec–Jan", "Week"),
        "month": ("December", "Month"),
        "quarter": ("Q4", "Quarter"),
        "year": ("’26", "Year"),
        "decade": ("’26–’28", "Three years"),
    }),
    ("2027-01-01", {
        "day": ("1 Jan", "Day · ’27"),
        "week": ("28 Dec–Jan", "Week"),  # the same week as 31 Dec: Mon 28 Dec 2026 – Sun 3 Jan 2027
        "month": ("January", "Month · ’27"),
        "quarter": ("Q1", "Quarter · ’27"),
        "year": ("’27", "Year"),
        "decade": ("’26–’28", "Three years"),
    }),
    ("2027-01-04", {
        "day": ("4 Jan", "Day · ’27"),
        "week": ("4–10 Jan", "Week · ’27"),
        "month": ("January", "Month · ’27"),
        "quarter": ("Q1", "Quarter · ’27"),
        "year": ("’27", "Year"),
        "decade": ("’26–’28", "Three years"),
    }),
    ("2028-12-31", {
        "day": ("31 Dec", "Day · ’28"),
        "week": ("25–31 Dec", "Week · ’28"),
        "month": ("December", "Month · ’28"),
        "quarter": ("Q4", "Quarter · ’28"),
        "year": ("’28", "Year"),
        "decade": ("’26–’28", "Three years"),
    }),
    ("2029-01-01", {
        "day": ("1 Jan", "Day · ’29"),
        "week": ("1–7 Jan", "Week · ’29"),
        "month": ("January", "Month · ’29"),
        "quarter": ("Q1", "Quarter · ’29"),
        "year": ("’29", "Year"),
        "decade": ("’29–’31", "Three years"),
    }),
    # A week across New Year outside the current year takes the year it starts in: Mon 30 Dec 2030 – Sun 5 Jan 2031, whose
    # whole name, 30 Dec–5 Jan, is 185.9 px.
    ("2030-12-31", {
        "week": ("30 Dec–Jan", "Week · ’30"),
    }),
)


def test_a_period_outside_the_current_year_carries_the_year_in_the_kind_line(ui_f2: UiSession) -> None:
    """Day, Week, Month and Quarter carry it, short; Year and Three years are their years, written short, and Life has
    none."""
    wrong = []
    for anchor, expected in YEAR_EDGES:
        names = _names(_open(ui_f2, SATURDAY, anchor))
        for vertical, want in expected.items():
            if names[vertical] != want:
                wrong.append(f"{anchor} {vertical}: {names[vertical]!r} (want {want!r})")
        if "life" in names and names["life"] != ("All time", "Life"):
            wrong.append(f"{anchor} life: {names['life']!r}")
    assert not wrong, "\n".join(wrong)


def test_the_year_edge_belongs_to_now_not_to_the_anchor(ui_f2: UiSession) -> None:
    """On Saturday 2 Jan 2027 the current week is Mon 28 Dec 2026 – Sun 3 Jan 2027, so Thursday 31 Dec is a weekday and
    last year at once, and this week is not given a year."""
    now = "2027-01-02T09:00:00+03:00"
    names = _names(_open(ui_f2, now))
    assert names["day"] == ("Today", "Day")
    assert names["week"] == ("28 Dec–Jan", "Week")
    assert names["month"] == ("January", "Month")
    assert names["year"] == ("’27", "Year")
    assert _names(_open(ui_f2, now, "2026-12-31"))["day"] == ("Thursday", "Day · ’26")
    assert _names(_open(ui_f2, now, "2026-12-27"))["day"] == ("27 Dec", "Day · ’26")


# A name is never cut with "…": where the room is short the column falls back to a shorter form of the same name. Each row
# is (a window's width, the column opened or None, an anchor, {vertical: (name, kind)}); the clock is `NOW`, and the rooms
# are 184 px at 1470 px with nothing open, 152 px beside an open column there, 163 px at 1320 px with nothing open and
# 134 px beside an open column there. The forms' widths, in px: Wednesday 164.5, Wed 64.8; September 157.0, Sep 53.3;
# 25–31 May 155.3, 25–31 86.8; 21–27 Dec 145.2, 21–27 85.2; 14–20 Sep 149.4, 14–20 90.1; 27 Apr–3 May 199.3,
# 27 Apr–May 175.2, Apr–May 134.8. A kind line has the title's room less the 36 px its row keeps free at the right (148, 116,
# 127 and 98 px in the four layouts): "Week · Dec ’27" takes 97.1 of the 98, "Week · Nov ’27" 98.6, "Week · Mar ’27" 99.0,
# "Week · May ’27" 100.7. The shortest form of a name, and a kind line, may take 8 px beyond their room before the
# ellipsis shows (`--column-spill`, ColumnHeader.vue), which is all that "Apr–May" (0.8 px) and those three need.
LAYOUTS = (
    # 1470 px, nothing open: 184 px, every name whole (a pair across two months in its second form)
    (1470, None, "2026-10-07", {"day": ("Wednesday", "Day"), "week": ("5–11 Oct", "Week")}),
    (1470, None, "2026-09-15", {"month": ("September", "Month"), "week": ("14–20 Sep", "Week")}),
    (1470, None, "2026-05-27", {"week": ("25–31 May", "Week"), "month": ("May", "Month")}),
    (1470, None, "2026-04-30", {"week": ("27 Apr–May", "Week")}),
    # 1470 px, a column open: the other six have 152 px
    (1470, "week", "2026-10-07", {"day": ("Wed", "Day"), "month": ("October", "Month")}),
    (1470, "day", "2026-09-15", {"month": ("Sep", "Month"), "week": ("14–20 Sep", "Week")}),
    (1470, "day", "2026-05-27", {"week": ("25–31", "Week · May"), "month": ("May", "Month")}),
    (1470, "day", "2026-04-30", {"week": ("Apr–May", "Week")}),
    (1470, "month", "2026-12-23", {"week": ("21–27 Dec", "Week")}),
    # a week inside one month, outside the current year, carries its month and the year in the kind line
    (1470, "day", "2027-05-26", {"week": ("24–30", "Week · May ’27"), "month": ("May", "Month · ’27")}),
    # the desktop app's first window, 1320 px, nothing open: 163 px
    (1320, None, "2026-10-07", {"day": ("Wed", "Day"), "week": ("5–11 Oct", "Week")}),
    (1320, None, "2026-09-15", {"month": ("September", "Month"), "week": ("14–20 Sep", "Week")}),
    (1320, None, "2026-05-27", {"week": ("25–31 May", "Week")}),
    (1320, None, "2026-04-30", {"week": ("Apr–May", "Week")}),
    # 1320 px with a column open: 134 px
    (1320, "quarter", "2026-09-15", {"month": ("Sep", "Month"), "week": ("14–20", "Week · Sep")}),
    (1320, "quarter", "2026-05-27", {"week": ("25–31", "Week · May")}),
    (1320, "quarter", "2026-12-23", {"week": ("21–27", "Week · Dec")}),
    (1320, "quarter", "2026-10-07", {"day": ("Wed", "Day")}),
    (1320, "quarter", "2027-12-23", {"week": ("20–26", "Week · Dec ’27"), "month": ("Dec", "Month · ’27")}),
    # where the shortest form is wider than the room and takes the spill: "Apr–May", and the kind lines of March, May and
    # November in another year
    (1320, "quarter", "2026-04-30", {"week": ("Apr–May", "Week")}),
    (1320, "quarter", "2027-03-24", {"week": ("22–28", "Week · Mar ’27")}),
    (1320, "quarter", "2027-05-26", {"week": ("24–30", "Week · May ’27")}),
    (1320, "quarter", "2027-11-24", {"week": ("22–28", "Week · Nov ’27")}),
)


def test_a_name_is_never_cut_where_the_room_is_short(ui_f2: UiSession) -> None:
    """In every layout above neither a name nor a kind shows an ellipsis, and each name takes the form the room allows."""
    wrong: list[str] = []
    for width, opened, anchor, expected in LAYOUTS:
        page = _open(ui_f2, NOW, anchor, width=width)
        if opened:
            expand_column(page, opened)
        names = _wait_for_names(page, expected)
        where = f"{width} px, {opened or 'nothing'} open, {anchor}"
        for vertical, want in expected.items():
            if names[vertical] != want:
                wrong.append(f"{where}: {vertical} {names[vertical]!r} (want {want!r})")
        if cut := _cut(page):
            wrong.append(f"{where}: cut with an ellipsis: {cut} ({[names[c.split()[0]] for c in cut]})")
    assert not wrong, "\n".join(wrong)


def test_the_forms_follow_the_window_when_it_is_resized(ui_f2: UiSession) -> None:
    """The room is read again when the window changes: "Wednesday" in 184 px, "Wed" in 163, and back."""
    page = _open(ui_f2, NOW, "2026-10-07", width=1470)
    assert _wait_for_names(page, {"day": ("Wednesday", "Day")})["day"] == ("Wednesday", "Day")
    page.set_viewport_size({"width": 1320, "height": 820})
    assert _wait_for_names(page, {"day": ("Wed", "Day")})["day"] == ("Wed", "Day")
    assert _cut(page) == []
    page.set_viewport_size({"width": 1470, "height": 820})
    assert _wait_for_names(page, {"day": ("Wednesday", "Day")})["day"] == ("Wednesday", "Day")


def test_the_cut_check_can_fail(ui_f2: UiSession) -> None:
    """Negative control: the checks above read each title's `scrollWidth` against its `clientWidth`. In a window so narrow
    that even the shortest form of "’26–’28", which has no shorter one, does not fit beside an open column (94 px), the
    board still ends a name in "…", and the check says so."""
    page = _open(ui_f2, NOW, width=1000)
    expand_column(page, "week")
    names = _wait_for_names(page, {"week": ("5–11 Oct", "Week")})
    assert _cut(page) != [], f"nothing is cut at 1000 px beside an open column, which the check should see: {names}"


# A page cannot ask which frames it drew, and a reading taken between frames can land between a change to the page and the
# frame that draws it, which is a state nobody saw. So the log is written where the browser itself says what changed: a
# ResizeObserver, called in a frame's own work right after the layout, and a MutationObserver, called when the words are
# written, each entry carrying the number of the frame it was made in.
_START = """(ms) => {
  window.__log = new Promise((resolve) => {
    const titles = () => [...document.querySelectorAll('[data-role="column-strip"] > [data-vertical] .t-title')];
    const columnOf = (title) => title.closest('[data-vertical]');
    const log = [];
    let frame = 0;
    const count = () => { frame += 1; requestAnimationFrame(count); };
    const note = (kind, title, room) => log.push({
      kind, frame, vertical: columnOf(title).dataset.vertical, text: title.textContent,
      cut: title.scrollWidth > title.clientWidth, moving: columnOf(title).getAnimations().length > 0, room,
    });
    const rooms = new ResizeObserver((entries) => entries.forEach(({ target, contentRect }) => note('room', target, contentRect.width)));
    const words = new MutationObserver((records) => records.forEach(({ target }) => note('words', target.nodeType === 1 ? target : target.parentElement, null)));
    titles().forEach((title) => { rooms.observe(title); words.observe(title, { childList: true, characterData: true, subtree: true }); });
    requestAnimationFrame(count);
    setTimeout(() => { rooms.disconnect(); words.disconnect(); resolve(log); }, ms);
  });
}"""


def _record(page: Page, act, ms: int = 1000) -> list[dict]:
    """The log of what the headers do while `act` runs: `room` entries when a title's layout width changes (the first is
    the title as it stands) and `words` entries when its words are written, each with the words, whether they are cut,
    whether the column is being animated, and the frame it happened in."""
    page.evaluate(_START, ms)
    page.wait_for_timeout(150)
    act()
    page.mouse.move(2, 2)
    log = page.evaluate("() => window.__log")
    page.wait_for_timeout(300)
    return log


@pytest.mark.parametrize("ui_reduced_motion", ["no-preference"], indirect=True)
def test_the_words_are_chosen_in_the_frame_the_layout_changes(ui_f2: UiSession) -> None:
    """A goal opened in the Month column widens it and narrows the other six in one movement (lib/familyMotion.ts), and a
    click on its header puts them back at once. Day's "Wednesday" becomes "Wed" in the very frame its column's width
    changes, and the movement starts, and back: written once, never in the middle of a movement, and at no moment a title
    is cut."""
    page = _open(ui_f2, SATURDAY, "2026-08-05")  # a Wednesday of the week Saturday 8 Aug is in
    page.wait_for_selector('[data-goal-id="SYNSCH01"]')
    assert _names(page)["day"] == ("Wednesday", "Day")

    for label, act, after in (
        ("opening a goal", lambda: page.locator('[data-goal-id="SYNSCH01"] .goal-card__title').first.click(), "Wed"),
        ("closing the column", lambda: page.locator('[data-vertical="month"] .pattern-vertical-board__header').first.click(), "Wednesday"),
    ):
        log = _record(page, act)
        assert not [e for e in log if e["cut"]], f"{label}: a title is cut: {[e for e in log if e['cut']]}"
        written = [e for e in log if e["kind"] == "words"]
        assert [(e["vertical"], e["text"]) for e in written] == [("day", after)], f"{label}: the words written: {written}"
        # Day's room as the browser reported it: as it stood, then as the layout changed it (a 64th of a pixel's rounding
        # when the movement lets go of the column is not a change)
        day_rooms = [e for e in log if e["kind"] == "room" and e["vertical"] == "day"]
        changes = [e for i, e in enumerate(day_rooms) if i == 0 or abs(e["room"] - day_rooms[i - 1]["room"]) > 0.5]
        assert len(changes) == 2, f"{label}: Day's room changed {len(changes) - 1} times: {day_rooms}"
        assert written[0]["frame"] == changes[1]["frame"], f"{label}: the words were not written in the frame the layout changed in: {log}"
        if label == "opening a goal":
            assert written[0]["moving"], f"{label}: the words were written before the movement started"


def test_the_columns_accessible_name_says_the_full_name(ui_f2: UiSession) -> None:
    """Kind first, as it reads on the screen, then the name, whole and with whole years, whichever form is on screen."""
    page = _open(ui_f2, NOW)
    expected = {
        "day": "Day, Today",
        "week": "Week, 5–11 Oct",
        "month": "Month, October",
        "quarter": "Quarter, Q4",
        "year": "Year, 2026",
        "decade": "Three years, 2026–2028",
        "life": "Life, All time",
    }
    for vertical, name in expected.items():
        column = page.locator(f"{STRIP} > [data-vertical='{vertical}']")
        expect(column).to_have_role("group")
        expect(column).to_have_accessible_name(name)
    # What is read is what is seen, where the screen writes the same words: the kind, then the name.
    for vertical, (big, small) in _names(page).items():
        if vertical not in ("year", "decade"):
            assert page.get_by_role("group", name=f"{small}, {big}", exact=True).count() == 1, vertical

    page = _open(ui_f2, NOW, "2027-01-04")
    expect(page.locator(f"{STRIP} > [data-vertical='month']")).to_have_accessible_name("Month 2027, January")
    expect(page.locator(f"{STRIP} > [data-vertical='year']")).to_have_accessible_name("Year, 2027")

    # The long name is the accessible name in a column that shows a shorter one, and in the heading as well.
    page = _open(ui_f2, NOW, "2029-04-30")
    week = page.locator(f"{STRIP} > [data-vertical='week']")
    assert _names(page)["week"] == ("30 Apr–May", "Week · ’29")
    expect(week).to_have_accessible_name("Week 2029, 30 Apr–6 May")
    expect(week.locator(".t-title")).to_have_accessible_name("30 Apr–6 May")
    expand_column(page, "week")
    expect(week).to_have_accessible_name("Week 2029, 30 Apr–6 May")

    page = _open(ui_f2, NOW, "2026-04-30", width=1470)
    expand_column(page, "day")
    _wait_for_names(page, {"week": ("Apr–May", "Week")})
    week = page.locator(f"{STRIP} > [data-vertical='week']")
    expect(week).to_have_accessible_name("Week, 27 Apr–3 May")
    expect(week.locator(".t-title")).to_have_accessible_name("27 Apr–3 May")


def _step(page: Page, vertical: str, control: str, key: str) -> None:
    """One click on one of a column's side bars, and the board settled on the period `key` (the swap's 350 ms done)."""
    column = page.locator(f"{STRIP} > [data-vertical='{vertical}']")
    column.locator(f'[data-cap="{control}"]').click()
    page.wait_for_selector(f"{STRIP} > [data-vertical='{vertical}'][data-period-key='{key}']")
    expect(column.locator('[data-role="period-slide"]')).to_have_count(1)


def test_paging_a_column_renames_it(ui_f2: UiSession) -> None:
    """The names follow the period the side bars page to, not only the one a board opens on: Day goes from today to a
    weekday of this week and on to a date next week."""
    page = _open(ui_f2, SATURDAY)
    activate_column(page, "day")
    assert _names(page)["day"] == ("Today", "Day")
    _step(page, "day", "period-next", "2026-08-09")
    assert _names(page)["day"] == ("Sunday", "Day")
    _step(page, "day", "period-next", "2026-08-10")
    assert _names(page)["day"] == ("10 Aug", "Day")
    _step(page, "day", "period-prev", "2026-08-09")
    assert _names(page)["day"] == ("Sunday", "Day")


def test_paging_a_wide_column_keeps_its_long_name(ui_f2: UiSession) -> None:
    """The wide column stays wide while it pages, so a week across two months says its last day each time it comes
    round: 27 Apr–3 May, then 4–10 May, then 27 Apr–3 May again."""
    page = _open(ui_f2, NOW, "2026-04-27")
    activate_column(page, "week")  # the header click widens it
    assert _wait_for_names(page, {"week": ("27 Apr–3 May", "Week")})["week"] == ("27 Apr–3 May", "Week")
    _step(page, "week", "period-next", "2026-W19")
    assert _names(page)["week"] == ("4–10 May", "Week")
    _step(page, "week", "period-prev", "2026-W18")
    assert _names(page)["week"] == ("27 Apr–3 May", "Week")
    expect(page.locator(f"{STRIP} > [data-vertical='week']")).to_have_accessible_name("Week, 27 Apr–3 May")


def test_the_floating_column_in_the_spans_is_wide_and_says_its_long_name(ui_f2: UiSession) -> None:
    """Moving a week goal opens the months with the goal's own column floating wide over them (lib/spans.ts): a column
    drawn wide, though it is not the expanded one, so a week across two months says its last day there."""
    anchor = "2026-04-30"  # in the week Mon 27 Apr – Sun 3 May
    response = httpx.post(
        f"{ui_f2.backend.base_url}/api/goals",
        json={"title": "SYN names week goal", "vertical": "week", "anchor_date": anchor},
        headers={"Authorization": f"Bearer {ui_f2.backend.token}"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    goal_id = response.json()["id"]

    page = _open(ui_f2, NOW, anchor)
    assert _names(page)["week"] == ("27 Apr–May", "Week"), "narrow on the board"
    page.wait_for_selector(f'[data-goal-id="{goal_id}"]')
    at = _grab(page, goal_id)
    _glide(page, at, _centre(page, '[data-role="column-dots"][data-dots-vertical="month"]'))
    expect(page.locator(SPANS)).to_have_count(1, timeout=5000)
    floating = page.locator('[data-role="spans-floating"] [data-vertical="week"]')
    expect(floating.locator(".t-title")).to_have_text("27 Apr–3 May")
    expect(floating.locator(".t-caption")).to_have_text("Week")
    expect(floating).to_have_accessible_name("Week, 27 Apr–3 May")
    page.keyboard.press("Escape")
    page.mouse.up()
    expect(page.locator(SPANS)).to_have_count(0, timeout=5000)
