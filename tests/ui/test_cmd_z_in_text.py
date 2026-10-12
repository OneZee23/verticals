"""Inside text, ⌘Z is the text's own (docs/design/board-undo.md): where a person types, the key undoes the typing and takes back no
change on the board. One scenario for every place in the app where one types: the field, a title being renamed, a goal's
notes, a document's body in its window, the Inbox's write field and a step being added to an open goal.

Each starts with a change on the board (a tick, which ⌘Z would take back anywhere else), types, presses the key, and checks that
the typing is undone, the tick stands and no write went out but the notes' and the document's own saves of what they hold.
The reply box of a comment comes with the comments PR (#45) and is not here."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

import psycopg
import pytest
from playwright.sync_api import Locator, Page, expect

from verticals.core import docs as core_docs, goals as core_goals
from tests.ui.conftest import UiSession
from tests.ui.test_board_undo import TICK, board
from tests.ui.undo_helpers import goal, keys, wait_for, write_log, writes
from tests.ui.views import FIELD, open_page, switch_view

TYPED = "typed words for the key"
GOAL = "SYNCOL06"


def text_of(el: Locator) -> str:
    """What an element holds, whether it is a field or a contenteditable."""
    return el.evaluate("e => 'value' in e ? e.value : e.innerText")


def the_field(session: UiSession, conn: psycopg.Connection) -> Locator:
    session.page.keyboard.press("Control+k")  # the field opens with the key, wherever the pointer is
    expect(session.page.locator(FIELD)).to_be_focused()
    return session.page.locator(FIELD)


def a_title_being_renamed(session: UiSession, conn: psycopg.Connection) -> Locator:
    page = session.page
    title = f'[data-goal-id="{GOAL}"] [data-cap="edit-title"]'
    page.click(f'[data-goal-id="{GOAL}"] > [data-cap=reorder]')
    page.wait_for_selector(title, timeout=5000)
    page.click(title)
    editor = page.locator(f"{title}:is(textarea)")
    expect(editor).to_be_focused()
    return editor


def a_goals_notes(session: UiSession, conn: psycopg.Connection) -> Locator:
    page = session.page
    page.locator(f'[data-goal-id="{GOAL}"] > .goal-card__row .goal-card__title').click()
    expect(page.locator(f'[data-goal-id="{GOAL}"].goal-card--detail-open')).to_be_visible()
    notes = page.locator(f'.goal-card--detail-open[data-goal-id="{GOAL}"] + .goal-card__children--open [data-cap="edit-body"]')
    notes.click()
    expect(notes).to_have_attribute("contenteditable", "true")
    return notes


def a_documents_body_in_its_window(session: UiSession, conn: psycopg.Connection) -> Locator:
    page = session.page
    doc = core_docs.create(conn, owner="t1", path="syn-cmdz/doc.md", title="Typing", body="Some words to type after.").doc.id
    page.reload()
    board(session)
    switch_view(page, "docs")
    open_page(page, doc)
    body = page.locator('.vt-window[data-window="doc"] [data-role="doc-body"]')
    body.click()
    page.keyboard.press("End")
    return body


def the_inboxs_write_field(session: UiSession, conn: psycopg.Connection) -> Locator:
    page = session.page
    page.clock.set_fixed_time(datetime.now(timezone.utc))
    page.reload()
    switch_view(page, "inbox")
    page.keyboard.press("Control+k")
    expect(page.locator(FIELD)).to_be_focused()
    return page.locator(FIELD)


def a_step_being_added(session: UiSession, conn: psycopg.Connection) -> Locator:
    page = session.page
    page.locator(f'[data-goal-id="{GOAL}"] > .goal-card__row .goal-card__title').click()
    expect(page.locator(f'[data-goal-id="{GOAL}"].goal-card--detail-open')).to_be_visible()
    page.locator('[data-role="subgoal-add"]').click()
    editor = page.locator('[data-role="subgoal-add-editor"]')
    expect(editor).to_be_focused()
    return editor


# Where each place's own saving of what it holds may write; nothing else may.
PLACES: dict[str, tuple[Callable[[UiSession, psycopg.Connection], Locator], re.Pattern[str] | None]] = {
    "the field": (the_field, None),
    "a title being renamed": (a_title_being_renamed, None),
    "a goal's notes": (a_goals_notes, re.compile(rf"PATCH /goals/{GOAL} 200 \{{\"body\"")),
    "a document's body in its window": (a_documents_body_in_its_window, re.compile(r"PATCH /docs/\S+ 200")),
    "the Inbox's write field": (the_inboxs_write_field, None),
    "a step being added": (a_step_being_added, None),
}


@pytest.mark.parametrize("place", list(PLACES))
def test_cmd_z_inside_text_is_the_texts_own(ui_f2: UiSession, place: str) -> None:
    session = ui_f2
    page = board(session)
    undo, redo = keys(page)
    reach, own_save = PLACES[place]
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        session.gestures.click(TICK)  # a change on the board, which ⌘Z would take back anywhere but in text
        wait_for(page, lambda: goal(conn, "SYNCOL01")[4], True, "the tick is stored")
        wait_for(page, lambda: len(writes(session)), 1, "the tick is logged")

        target = reach(session, conn)
        held = text_of(target)
        start = len(session.request_log)
        page.keyboard.type(TYPED)
        assert TYPED in text_of(target), f"{place}: the words were typed"

        page.keyboard.press(undo)
        page.wait_for_timeout(300)
        assert text_of(target) == held, f"{place}: the typing is undone, by the text's own ⌘Z (got {text_of(target)!r})"
        assert goal(conn, "SYNCOL01")[4] is True, f"{place}: the tick on the board stands"
        page.keyboard.press(redo)  # and ⇧⌘Z types it again, in the text
        page.wait_for_timeout(300)
        assert TYPED in text_of(target), f"{place}: ⇧⌘Z plays the typing again (got {text_of(target)!r})"
        assert goal(conn, "SYNCOL01")[4] is True
        page.wait_for_timeout(1500)  # what a place saves of its own is on its way by now
        sent = [line for line in write_log(session, start)]
        stray = [line for line in sent if not (own_save and own_save.search(line))]
        assert stray == [], f"{place}: no write goes out for the key: {stray}"
        assert goal(conn, "SYNCOL01")[4] is True
