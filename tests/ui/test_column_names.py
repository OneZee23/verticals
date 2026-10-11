"""Each column is named by its period, its kind small above it (docs/design/column-names.md).

The names are a pure function of the board's anchor and of "now", and the web app has no unit-test runner, so these
cases drive the real board the way `test_url_history.py` does: the clock is pinned with `page.clock.set_fixed_time`
(never the real date) and the board is opened at an anchor by its own address, `/h/<date>`. One session walks many
cases, because a session (backend, static server, browser) costs more than a page load.

Read for every column: the big name is `.t-title`, the small kind above it `.t-caption`.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.ui.conftest import UiSession, activate_column, expand_column

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
_CUT = f"""() => [...document.querySelectorAll('{STRIP} > [data-vertical]')]
  .filter((col) => {{ const t = col.querySelector('.t-title'); return t.scrollWidth > t.clientWidth; }})
  .map((col) => col.dataset.vertical)"""


def _open(session: UiSession, now: str, anchor: str | None = None) -> Page:
    """The board as it stands at `now`, on `anchor` (or on today)."""
    page = session.page
    page.clock.set_fixed_time(now)
    page.goto(f"{session.base_url}/h/{anchor}" if anchor else f"{session.base_url}/")
    page.wait_for_selector(f'[data-vertical="day"][data-period-key="{anchor or now[:10]}"] .column-header')
    page.evaluate("() => document.fonts.ready")
    return page


def _names(page: Page) -> dict[str, tuple[str, str]]:
    """`{vertical: (name, kind)}`: what each column's header says, big and small."""
    return {vertical: (name, kind) for vertical, (name, kind) in page.evaluate(_READ).items()}


def _cut(page: Page) -> list[str]:
    """The columns whose name is wider than its room, so the ellipsis shows."""
    return page.evaluate(_CUT)


def test_the_seven_names_at_now(ui_f2: UiSession) -> None:
    """At now the seven names are Today, 5–11 Oct, October, Q4, 2026, 2026–2028, All time, their kinds above them
    Day, Week, Month, Quarter, Year, Three years, Life; in the type the board already has."""
    page = _open(ui_f2, NOW)
    names = _names(page)
    assert list(names) == list(VERTICALS)
    assert [names[v][0] for v in VERTICALS] == ["Today", "5–11 Oct", "October", "Q4", "2026", "2026–2028", "All time"]
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


# Every month pair a week can cross, one real week each: (an anchor in it, narrow name, wide name). The anchors are the
# week's Sunday, its Monday, a month's last day or something between, so the anchor lies on both sides of the boundary.
# The last row is the design's own example, "30 Apr–May" and "30 Apr–6 May".
MONTH_PAIRS = (
    ("2026-02-01", "26 Jan–Feb", "26 Jan–1 Feb"),
    ("2026-02-28", "23 Feb–Mar", "23 Feb–1 Mar"),
    ("2026-03-30", "30 Mar–Apr", "30 Mar–5 Apr"),
    ("2026-04-30", "27 Apr–May", "27 Apr–3 May"),
    ("2027-05-31", "31 May–Jun", "31 May–6 Jun"),
    ("2026-07-05", "29 Jun–Jul", "29 Jun–5 Jul"),
    ("2026-07-31", "27 Jul–Aug", "27 Jul–2 Aug"),
    ("2026-08-31", "31 Aug–Sep", "31 Aug–6 Sep"),
    ("2026-10-04", "28 Sep–Oct", "28 Sep–4 Oct"),
    ("2026-10-31", "26 Oct–Nov", "26 Oct–1 Nov"),
    ("2026-12-02", "30 Nov–Dec", "30 Nov–6 Dec"),
    ("2026-12-31", "28 Dec–Jan", "28 Dec–3 Jan"),
    ("2029-04-30", "30 Apr–May", "30 Apr–6 May"),
)


def test_a_week_across_two_months_names_its_end_only_where_there_is_room(ui_f2: UiSession) -> None:
    """"30 Apr–May" in a narrow column, "30 Apr–6 May" in a wide one: all twelve pairs. A week inside one month stays
    "5–11 Oct" in both."""
    wrong: list[str] = []
    for anchor, narrow, wide in MONTH_PAIRS:
        page = _open(ui_f2, NOW, anchor)
        found_narrow = _names(page)["week"][0]
        cut = _cut(page)
        expand_column(page, "week")
        found_wide = _names(page)["week"][0]
        if (found_narrow, found_wide) != (narrow, wide):
            wrong.append(f"{anchor}: narrow {found_narrow!r} (want {narrow!r}), wide {found_wide!r} (want {wide!r})")
        if cut:
            wrong.append(f"{anchor}: cut off in the narrow columns {cut}")
    assert not wrong, "\n".join(wrong)

    page = _open(ui_f2, NOW, "2026-10-07")
    assert _names(page)["week"][0] == "5–11 Oct"
    expand_column(page, "week")
    assert _names(page)["week"][0] == "5–11 Oct"


def test_every_name_fits_the_narrow_column(ui_f2: UiSession) -> None:
    """The names are set in the board's title type, which does not shrink: a name the narrow column cannot hold shows
    an ellipsis. The design measured the narrowest room, 184 px (a 1470 px window), and the widest month pair,
    "30 Apr–May", at 179 px. This measures every label there can be, in the font as the app loads it, so a font or a
    size change cannot cut a name without this saying so."""
    page = _open(ui_f2, NOW)
    page.wait_for_function("() => document.fonts.status === 'loaded'", timeout=5000)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    last_day = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # February at its longest
    pairs = [
        f"{start} {months[m]}–{months[(m + 1) % 12]}"
        for m in range(12)
        for start in range(last_day[m] - (6 if m == 1 else 5), last_day[m] + 1)
    ]
    labels = {
        "month pairs": pairs,
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                   "November", "December"],
        "week in one month": [f"{a}–{a + 6} {months[m]}" for m in range(12) for a in range(1, last_day[m] - 5)],
        "dates": [f"{d} {months[m]}" for m in range(12) for d in range(1, last_day[m] + 1)],
        "the rest": ["Today", "All time", "Q1", "Q2", "Q3", "Q4", "2025", "2026", "2027", "2028", "2029", "2026–2028",
                     "2023–2025", "2029–2031"],
    }
    measured = page.evaluate(
        """(labels) => {
          const title = document.querySelector('[data-vertical="week"] .t-title');
          const probe = title.cloneNode(false);
          probe.style.cssText = 'position:absolute;visibility:hidden;display:inline-block;width:auto;max-width:none;'
            + 'overflow:visible;text-overflow:clip';
          title.parentElement.appendChild(probe);
          const widths = {};
          for (const [family, texts] of Object.entries(labels)) {
            widths[family] = Math.max(...texts.map((text) => { probe.textContent = text; return probe.getBoundingClientRect().width; }));
          }
          probe.remove();
          return {
            widths,
            room: title.getBoundingClientRect().width,
            faces: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family),
          };
        }""",
        labels,
    )
    assert any("Commissioner" in face for face in measured["faces"]), f"measured without the title font: {measured['faces']}"
    room = min(measured["room"], 184)  # the design's figure, or less where the window is narrower
    too_wide = {family: round(width, 1) for family, width in measured["widths"].items() if width > room}
    assert not too_wide, f"wider than the narrow column's {room:.1f} px: {too_wide}"
    assert measured["widths"]["month pairs"] > 170, "the measure is too small to be the title type"


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
# columns the year touches; a period outside 2026 carries its year in the kind line, "Month · 2027", and a week that
# touches 2026 is still this year's.
YEAR_EDGES = (
    ("2025-12-31", {
        "day": ("31 Dec", "Day · 2025"),
        "week": ("29 Dec–Jan", "Week"),  # Mon 29 Dec 2025 – Sun 4 Jan 2026 reaches into 2026
        "month": ("December", "Month · 2025"),
        "quarter": ("Q4", "Quarter · 2025"),
        "year": ("2025", "Year"),
        "decade": ("2023–2025", "Three years"),
    }),
    ("2026-12-31", {
        "day": ("31 Dec", "Day"),
        "week": ("28 Dec–Jan", "Week"),
        "month": ("December", "Month"),
        "quarter": ("Q4", "Quarter"),
        "year": ("2026", "Year"),
        "decade": ("2026–2028", "Three years"),
    }),
    ("2027-01-01", {
        "day": ("1 Jan", "Day · 2027"),
        "week": ("28 Dec–Jan", "Week"),  # the same week as 31 Dec: Mon 28 Dec 2026 – Sun 3 Jan 2027
        "month": ("January", "Month · 2027"),
        "quarter": ("Q1", "Quarter · 2027"),
        "year": ("2027", "Year"),
        "decade": ("2026–2028", "Three years"),
    }),
    ("2027-01-04", {
        "day": ("4 Jan", "Day · 2027"),
        "week": ("4–10 Jan", "Week · 2027"),
        "month": ("January", "Month · 2027"),
        "quarter": ("Q1", "Quarter · 2027"),
        "year": ("2027", "Year"),
        "decade": ("2026–2028", "Three years"),
    }),
    ("2028-12-31", {
        "day": ("31 Dec", "Day · 2028"),
        "week": ("25–31 Dec", "Week · 2028"),
        "month": ("December", "Month · 2028"),
        "quarter": ("Q4", "Quarter · 2028"),
        "year": ("2028", "Year"),
        "decade": ("2026–2028", "Three years"),
    }),
    ("2029-01-01", {
        "day": ("1 Jan", "Day · 2029"),
        "week": ("1–7 Jan", "Week · 2029"),
        "month": ("January", "Month · 2029"),
        "quarter": ("Q1", "Quarter · 2029"),
        "year": ("2029", "Year"),
        "decade": ("2029–2031", "Three years"),
    }),
    # A week across New Year outside the current year takes the year it starts in.
    ("2027-12-30", {
        "week": ("27 Dec–Jan", "Week · 2027"),
    }),
)


def test_a_period_outside_the_current_year_carries_the_year_in_the_kind_line(ui_f2: UiSession) -> None:
    """Day, Week, Month and Quarter carry it; Year and Three years are their years, and Life has none."""
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
    assert names["year"] == ("2027", "Year")
    assert _names(_open(ui_f2, now, "2026-12-31"))["day"] == ("Thursday", "Day · 2026")
    assert _names(_open(ui_f2, now, "2026-12-27"))["day"] == ("27 Dec", "Day · 2026")


def test_the_columns_accessible_name_says_the_same_words(ui_f2: UiSession) -> None:
    """Kind first, as it reads on the screen, then the name; the year the kind line carries stays in it."""
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
    # What is read is what is seen: the words of the two header lines.
    for vertical, (big, small) in _names(page).items():
        assert page.get_by_role("group", name=f"{small}, {big}", exact=True).count() == 1, vertical

    page = _open(ui_f2, NOW, "2027-01-04")
    expect(page.locator(f"{STRIP} > [data-vertical='month']")).to_have_accessible_name("Month 2027, January")

    # In a wide column the name is the longer one.
    page = _open(ui_f2, NOW, "2029-04-30")
    expect(page.locator(f"{STRIP} > [data-vertical='week']")).to_have_accessible_name("Week 2029, 30 Apr–May")
    expand_column(page, "week")
    expect(page.locator(f"{STRIP} > [data-vertical='week']")).to_have_accessible_name("Week 2029, 30 Apr–6 May")


def _step(page: Page, vertical: str, control: str, key: str) -> None:
    """One click on a column's own period control, and the board settled on the period `key` (the swap's 350 ms done)."""
    column = page.locator(f"{STRIP} > [data-vertical='{vertical}']")
    column.locator(f'[data-cap="{control}"]').click()
    page.wait_for_selector(f"{STRIP} > [data-vertical='{vertical}'][data-period-key='{key}']")
    expect(column.locator('[data-role="period-slide"]')).to_have_count(1)


def test_paging_a_column_renames_it(ui_f2: UiSession) -> None:
    """The names follow the period the controls page to, not only the one a board opens on: Day goes from today to a
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
    assert _names(page)["week"] == ("27 Apr–3 May", "Week")
    _step(page, "week", "period-next", "2026-W19")
    assert _names(page)["week"] == ("4–10 May", "Week")
    _step(page, "week", "period-prev", "2026-W18")
    assert _names(page)["week"] == ("27 Apr–3 May", "Week")
    expect(page.locator(f"{STRIP} > [data-vertical='week']")).to_have_accessible_name("Week, 27 Apr–3 May")
