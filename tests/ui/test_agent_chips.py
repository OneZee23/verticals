"""What the agent made or changed stands under its words as chips (docs/design/agent-chips.md): a goal by its square, its
title and one grey line of where it is and when, a document by its first page, in one form, in the field's answer and in
the agent's balloon. The agent is the fake one behind the real desktop gateway, as in `test_agent_conversation.py`, which
has the basic scenarios (the chip in the field and in the conversation, the window it opens, and a fresh conversation in
which the agent makes a task becoming that task's); here are the details of the chip."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from playwright.sync_api import Page, expect

from verticals.core import docs as core_docs

from tests.ui.conftest import F2_OWNER, UiSession
from tests.ui.test_agent_conversation import (  # noqa: F401  (the fixture, and the scenarios' own words)
    AGENT_BALLOON, ANSWER, DOC_CHIP, GOAL_CHIP, NOW, _answered, _send, close_the_conversation, goal_made, ui_agent,
)

YESTERDAY = NOW - timedelta(hours=25)


def test_the_chip_line_says_where_the_goal_is_and_when_it_was_made_or_changed(ui_agent: UiSession) -> None:
    """Where: the period the goal stands in when it is the one it is now ("Today", "Week"), else the period as the board's
    cards write it; the Inbox, Life, a step. When: made until something changed it, then changed, as long ago as that was.
    A finished goal's square is ticked."""
    dsn = ui_agent.backend.dsn
    value = goal_made(dsn, "SYN value in blue", vertical="life", day="2026-01-01", color="#278dea")
    today = goal_made(dsn, "SYN made today")
    cases = [
        (today, "Today · made just now", False),
        (goal_made(dsn, "SYN changed this week", vertical="week", day="2026-08-05", made=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
                   changed=NOW - timedelta(minutes=2)), "Week · changed 2 min ago", False),
        (goal_made(dsn, "SYN a month ahead", vertical="month", day="2026-09-15", made=NOW - timedelta(hours=3), parent=value),
         "September · made 3 h ago", False),
        (goal_made(dsn, "SYN next week", vertical="week", day="2026-08-12", made=NOW - timedelta(minutes=1)),
         "10–16 Aug · made 1 min ago", False),
        (goal_made(dsn, "SYN another day", day="2026-08-10", made=YESTERDAY), "Mon 10 Aug · made yesterday", False),
        (goal_made(dsn, "SYN in the Inbox", vertical=None, day=None, made=datetime(2026, 8, 3, 10, tzinfo=timezone.utc)),
         "Inbox · made 3 Aug", False),
        (goal_made(dsn, "SYN a life goal", vertical="life", day="2026-01-01", made=datetime(2025, 3, 2, 12, tzinfo=timezone.utc)),
         "Life · made 2 Mar 2025", False),
        (goal_made(dsn, "SYN a step", vertical=None, day=None, parent=today), "Step · made just now", False),
        (goal_made(dsn, "SYN finished", done=True), "Today · made just now", True),
    ]
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{today}"]')
    links = "\n".join(f"[words of link {n}](#goal/{goal})" for n, (goal, _, _) in enumerate(cases))
    _send(page, f"[say] Here they are.\n{links}")
    _answered(page, "Here they are.")
    for goal, line, ticked in cases:
        chip = page.locator(f'{AGENT_BALLOON} {GOAL_CHIP}[data-goal-id="{goal}"]')
        expect(chip.locator('[data-role="goal-chip-when"]')).to_have_text(line)
        square = chip.locator('[data-role="goal-chip-square"]')
        if ticked:
            expect(square).to_have_class(re.compile(r"\bis-done\b"))
        else:
            expect(square).not_to_have_class(re.compile(r"\bis-done\b"))
    # The title is the goal's own, not the words of the link that brought it.
    expect(page.locator(f'{AGENT_BALLOON} {GOAL_CHIP}[data-goal-id="{today}"] .goal-chip__name')).to_have_text("SYN made today")
    # A goal the board is not showing (September) still has the colour of its value: the blue square of the palette.
    ahead = page.locator(f'{AGENT_BALLOON} {GOAL_CHIP}[data-goal-id="{cases[2][0]}"] [data-role="goal-chip-square"]')
    expect(ahead).to_have_css("background-color", "rgb(181, 214, 242)")


def test_a_goal_chip_and_a_document_chip_are_one_form(ui_agent: UiSession) -> None:
    """The goal chip wears the document chip's numbers: the same row, gap, corners, and the same two lines of type, in the
    same colours; the chips stand in the order the message links them, on one left edge."""
    with psycopg.connect(ui_agent.backend.dsn, autocommit=True) as conn:
        doc = core_docs.create(conn, owner=F2_OWNER, path="reports/syn-form.md", title="SYN form report").doc.id
    goal = goal_made(ui_agent.backend.dsn, "SYN form task")
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{goal}"]')
    _send(page, f"[say] Made both.\n[SYN form task](#goal/{goal})\n[SYN form report](#doc/{doc})")
    _answered(page, "Made both.")
    chips = page.locator(f"{AGENT_BALLOON} [data-role='agent-chips'] > button")
    expect(chips).to_have_count(2)
    assert chips.evaluate_all("els => els.map(el => el.dataset.role)") == ["goal-chip", "doc-chip"]
    style = """(el, parts) => Object.fromEntries(parts.map(part => [part, getComputedStyle(el)[part]]))"""
    row = ["display", "alignItems", "columnGap", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopLeftRadius",
           "boxShadow", "backgroundColor", "color", "textAlign"]
    type_ = ["fontFamily", "fontWeight", "fontSize", "lineHeight", "color"]
    goal_chip, doc_chip = page.locator(GOAL_CHIP), page.locator(DOC_CHIP)
    assert goal_chip.evaluate(style, row) == doc_chip.evaluate(style, row)
    assert goal_chip.locator(".goal-chip__name").evaluate(style, type_) == doc_chip.locator(".doc-chip__name").evaluate(style, type_)
    assert goal_chip.locator(".goal-chip__when").evaluate(style, type_) == doc_chip.locator(".doc-chip__when").evaluate(style, type_)
    name = goal_chip.locator(".goal-chip__name").evaluate(style, type_)
    assert (name["fontWeight"], name["fontSize"], name["lineHeight"]) == ("500", "15px", "22px")
    when = goal_chip.locator(".goal-chip__when").evaluate(style, type_)
    assert (when["fontWeight"], when["fontSize"], when["lineHeight"], when["color"]) == ("400", "13px", "22px", "rgba(255, 255, 255, 0.5)")
    boxes = [goal_chip.bounding_box(), doc_chip.bounding_box()]
    assert boxes[0] and boxes[1] and abs(boxes[0]["x"] - boxes[1]["x"]) < 0.5 and boxes[0]["y"] < boxes[1]["y"]


COLUMNS = """(scope) => {
  const root = document.querySelector(scope)
  const box = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } }
  const goal = root.querySelector('[data-role="goal-chip"]'), doc = root.querySelector('[data-role="doc-chip"]')
  return {
    goal: goal && { chip: box(goal), name: box(goal.querySelector('.goal-chip__name')), column: box(goal.querySelector('.goal-chip__page')),
                    square: box(goal.querySelector('[data-role="goal-chip-square"]')) },
    doc: doc && { chip: box(doc), name: box(doc.querySelector('.doc-chip__name')), page: box(doc.querySelector('.doc-chip__page')) },
  }
}"""


def _the_columns(page: Page, scope: str, *, with_doc: bool) -> None:
    """One anatomy for every chip, read off one snapshot of the page: the document chip's first page is a 50 px column and
    its title starts 14 px after it, at 64; the goal chip has that column too, with the board's 16 px square in the middle of
    it and level with the title's first line, and its title starts at 64 as well."""
    seen = page.evaluate(COLUMNS, scope)
    goal = seen["goal"]
    assert goal, "no goal chip in " + scope
    near = {"abs": 0.5}
    assert goal["name"]["x"] - goal["chip"]["x"] == pytest.approx(64, **near), "the goal's title starts at 64, as a document's does"
    assert goal["column"] and goal["column"]["w"] == pytest.approx(50, **near), "the goal chip has the document chip's 50 px column"
    assert (goal["square"]["w"], goal["square"]["h"]) == pytest.approx((16, 16), **near)
    assert goal["square"]["x"] + goal["square"]["w"] / 2 - goal["chip"]["x"] == pytest.approx(25, **near), "the square is in the middle of the column"
    assert goal["square"]["y"] + goal["square"]["h"] / 2 == pytest.approx(goal["name"]["y"] + 11, **near), "level with the title's first line"
    if with_doc:
        doc = seen["doc"]
        assert doc, "no document chip in " + scope
        assert doc["page"]["w"] == pytest.approx(50, **near)
        assert doc["name"]["x"] - doc["chip"]["x"] == pytest.approx(64, **near)
        assert goal["name"]["x"] == pytest.approx(doc["name"]["x"], **near), "stacked, the two titles start at one x"


def test_a_goal_chips_title_starts_where_a_document_chips_title_starts(ui_agent: UiSession) -> None:
    """One anatomy for every chip (the owner's "consistent and universal"): the goal chip takes the document chip's columns,
    always, in the field's answer and in the conversation, and a goal chip alone too."""
    with psycopg.connect(ui_agent.backend.dsn, autocommit=True) as conn:
        doc = core_docs.create(conn, owner=F2_OWNER, path="reports/syn-columns.md", title="SYN columns report").doc.id
    title = "SYN a goal whose title is long enough to take a second line beside its square"
    goal = goal_made(ui_agent.backend.dsn, title)
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{goal}"]')
    # The field's answer: the goal chip above the document chip.
    _send(page, f"[slow] [say] Made both.\n[{title}](#goal/{goal})\n[SYN columns report](#doc/{doc})")
    close_the_conversation(page)
    answer = page.locator(ANSWER)
    expect(answer.locator(GOAL_CHIP)).to_have_count(1, timeout=10000)
    expect(answer.locator(DOC_CHIP)).to_have_count(1)
    _the_columns(page, ANSWER, with_doc=True)
    # The same message in the open conversation.
    page.locator(".circle-field__answer-words").click()
    expect(page.locator(f"{AGENT_BALLOON} {GOAL_CHIP}")).to_have_count(1)
    _the_columns(page, AGENT_BALLOON, with_doc=True)
    # A goal chip alone in the field keeps the column: nothing makes it a different chip.
    close_the_conversation(page)
    _send(page, f"[slow] [say] [{title}](#goal/{goal})")
    close_the_conversation(page)
    expect(answer.locator(GOAL_CHIP)).to_have_count(1, timeout=10000)
    expect(answer.locator(DOC_CHIP)).to_have_count(0)
    _the_columns(page, ANSWER, with_doc=False)


def test_a_chip_follows_its_goal_when_it_is_renamed_and_moved(ui_agent: UiSession) -> None:
    """The chip is not a copy of the goal as the agent left it: it says what the goal is now, where it is and that it
    changed, whether the board is showing it or not."""
    goal = goal_made(ui_agent.backend.dsn, "Plan the review")
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{goal}"]')
    _send(page, f"[say] Made it.\n[Plan the review](#goal/{goal})")
    _answered(page, "Made it.")
    chip = page.locator(f"{AGENT_BALLOON} {GOAL_CHIP}")
    expect(chip.locator('[data-role="goal-chip-when"]')).to_have_text("Today · made just now")
    api = {"Authorization": f"Bearer {ui_agent.backend.token}"}
    renamed = httpx.patch(f"{ui_agent.backend.base_url}/api/goals/{goal}", json={"title": "Plan the review again"}, headers=api, timeout=10)
    assert renamed.status_code == 200, renamed.text
    expect(chip.locator(".goal-chip__name")).to_have_text("Plan the review again", timeout=10000)
    expect(chip.locator('[data-role="goal-chip-when"]')).to_have_text("Today · changed just now")
    moved = httpx.put(f"{ui_agent.backend.base_url}/api/goals/{goal}/schedule", json={"vertical": "week", "anchor_date": "2026-08-12"},
                      headers=api, timeout=10)
    assert moved.status_code == 200, moved.text
    expect(chip.locator('[data-role="goal-chip-when"]')).to_have_text("10–16 Aug · changed just now", timeout=10000)


def test_a_chip_for_a_goal_that_is_not_on_the_board_says_so_and_opens_nothing(ui_agent: UiSession) -> None:
    page = ui_agent.page
    page.wait_for_selector(".goal-card__row")
    _send(page, "[say] Made it.\n[The goal that was](#goal/SYNNOPE1)")
    _answered(page, "Made it.")
    chip = page.locator(f"{AGENT_BALLOON} {GOAL_CHIP}")
    expect(chip.locator('[data-role="goal-chip-when"]')).to_have_text("Not on the board")
    expect(chip.locator(".goal-chip__name")).to_have_text("The goal that was")  # the words of the link, which is all there is
    chip.click(force=True)  # it is marked disabled, which a click may not reach by the book; a person's can
    page.wait_for_timeout(300)
    expect(page.locator(".vt-window")).to_have_count(0)


def test_the_field_shows_three_chips_and_counts_the_rest_and_the_conversation_shows_them_all(ui_agent: UiSession) -> None:
    dsn = ui_agent.backend.dsn
    five = [(goal_made(dsn, f"SYN chip number {n}"), f"SYN chip number {n}") for n in range(5)]
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{five[0][0]}"]')
    # Linked as a numbered list, as a model may write it: the numbers go with the lines, the chips say them.
    _send(page, "[slow] [say] Made five.\n" + "\n".join(f"{n}. [{title}](#goal/{goal})" for n, (goal, title) in enumerate(five, start=1)))
    close_the_conversation(page)
    answer = page.locator(ANSWER)
    expect(answer.locator(GOAL_CHIP)).to_have_count(3, timeout=10000)
    expect(answer.locator(".circle-field__answer-words")).to_have_text("Made five.")
    more = answer.locator('[data-role="circle-answer-more"]')
    expect(more).to_have_text("2 more")
    # The shape holds all of it, 24 px below the last line, and stays on the screen.
    page.wait_for_function(
        """() => { const shape = document.querySelector('.circle-field__shape').getBoundingClientRect()
          const last = document.querySelector('[data-role="circle-answer-more"]').getBoundingClientRect()
          return Math.abs(shape.bottom - last.bottom - 24) <= 1 && shape.top >= 0 }""")
    page.locator(".circle-field__answer-words").click()
    expect(page.locator(f"{AGENT_BALLOON} {GOAL_CHIP}")).to_have_count(5)
    expect(page.locator(f"{AGENT_BALLOON} .agent-balloon__markdown")).to_have_text("Made five.")


def test_a_link_inside_a_sentence_stays_a_link_and_the_goal_is_a_chip_too(ui_agent: UiSession) -> None:
    goal = goal_made(ui_agent.backend.dsn, "Plan the review")
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{goal}"]')
    _send(page, f"[slow] [say] I moved [Plan the review](#goal/{goal}) to today.")
    close_the_conversation(page)
    expect(page.locator(f"{ANSWER} .circle-field__answer-words")).to_have_text("I moved Plan the review to today.", timeout=10000)
    expect(page.locator(f"{ANSWER} {GOAL_CHIP}")).to_have_count(1)
    page.locator(".circle-field__answer-words").click()
    message = page.locator(f"{AGENT_BALLOON} .agent-balloon__markdown")
    expect(message.locator("a[data-app-link]")).to_have_text("Plan the review")
    expect(page.locator(f"{AGENT_BALLOON} {GOAL_CHIP}")).to_have_count(1)


def test_an_answer_of_links_alone_is_its_chips_and_a_reader_who_cannot_see_it_is_told_their_names(ui_agent: UiSession) -> None:
    goal = goal_made(ui_agent.backend.dsn, "Plan the review")
    page = ui_agent.page
    page.reload()
    page.wait_for_selector(f'[data-goal-id="{goal}"]')
    _send(page, f"[slow] [say] [Plan the review](#goal/{goal})")
    close_the_conversation(page)
    answer = page.locator(ANSWER)
    expect(answer.locator(GOAL_CHIP)).to_have_count(1, timeout=10000)
    expect(answer.locator(".circle-field__answer-words")).to_have_count(0)
    expect(answer).to_have_attribute("aria-label", "Plan the review. Press any key to reply")
    # No words above it: 24 px to the chip from the black's top and from its bottom.
    page.wait_for_function(
        """() => { const shape = document.querySelector('.circle-field__shape').getBoundingClientRect()
          const chip = document.querySelector('[data-role="circle-answer"] [data-role="goal-chip"]').getBoundingClientRect()
          return Math.abs(chip.top - shape.top - 24) <= 1 && Math.abs(shape.bottom - chip.bottom - 24) <= 1 }""")
