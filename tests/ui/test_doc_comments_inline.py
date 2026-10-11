"""Comments in a document's text (docs/design/doc-comments-inline.md): a comment sits on the words it is about and opens right
over them, like a popover; above the field a pill counts the open comments, and opens them as a list; with none open it
reads how many are resolved. The comments column on the right is a goal's alone now. `test_doc_check_again.py` has the
rest of the design: Check again, and what the agent rewrote.

`ui_f2` throughout: nothing here needs an agent. Every document and every thread is made through `verticals.core`, as
`test_comments_panel.py` makes them, and the document is opened as a person opens it, from the Documents desk. The helpers
are `tests/ui/doc_comments.py`."""

from __future__ import annotations

import psycopg
from playwright.sync_api import expect

from verticals.core import comments as core_comments

from tests.ui.conftest import UiSession
from tests.ui.doc_comments import (
    AGAIN, BODY, CARD, COUNT, DOC, FOOT, LIST, LONG, MARK, OWNER, PILLS, PLAN, SHORT,
    _card, _doc, _fresh_open, _open, _rect, _select, _server_threads, _settled, _thread, _until,
)
from tests.ui.views import show_tags, tick


def test_a_comment_opens_over_its_words(ui_f2: UiSession) -> None:
    """The words are marked; a press on them opens the comment right under them, in the document, not in a column on the
    window's edge. Esc, or a press elsewhere on the page, closes it. A resolved comment's words are plain text again."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/words.md", "SYN Inline Words", SHORT)
        open_thread = _thread(conn, doc, "the sample board", "Say which board.")
        core_comments.add_message(conn, owner=OWNER, thread_id=open_thread, body="The sample one.", author="agent")
        resolved = _thread(conn, doc, "then the documents", "Done already.")
        core_comments.set_resolved(conn, owner=OWNER, thread_id=resolved, resolved=True)
    page.reload()
    _open(page, doc)

    marks = page.locator(f"{BODY} {MARK}")
    expect(marks).to_have_count(2, timeout=10000)
    words = page.locator(f'{BODY} {MARK}[data-thread-id="{open_thread}"]')
    assert words.evaluate("el => getComputedStyle(el).backgroundColor") != "rgba(0, 0, 0, 0)", "an open comment's words are not tinted"
    plain = page.locator(f'{BODY} {MARK}[data-thread-id="{resolved}"]')
    assert plain.evaluate("el => getComputedStyle(el).backgroundColor") == "rgba(0, 0, 0, 0)", "a resolved comment's words stay tinted"
    expect(page.locator(CARD)).to_have_count(0)

    words.click()
    card = _card(page)
    # In the document, and the column on the right is nowhere.
    expect(page.locator(f'{DOC} [data-role="doc-detail"] {CARD}')).to_have_count(1)
    expect(page.locator('[data-role="comments-panel"]')).to_have_count(0)
    expect(page.locator(BODY)).to_have_attribute("contenteditable", "false")
    assert "is-active" in (words.get_attribute("class") or ""), "the words are not lit while their comment is open"

    # Right under the words, from their first letter, inside the window.
    mark, box, win = _rect(page, f'{BODY} {MARK}[data-thread-id="{open_thread}"]'), _rect(page, CARD), _rect(page, DOC)
    gap = box["y"] - (mark["y"] + mark["h"])
    assert 0 <= gap <= 16, f"the comment stands {gap} px under its words"
    assert mark["x"] - 14 <= box["x"] <= mark["x"] + 2, (mark, box)
    assert win["x"] <= box["x"] and box["right"] <= win["right"], "the comment runs out of the window"

    # What was said, in order, the agent's marked as the agent's.
    messages = card.locator('[data-role="comment-message"]')
    expect(messages).to_have_count(2)
    expect(messages.nth(0)).to_contain_text("Say which board.")
    expect(messages.nth(1)).to_contain_text("The sample one.")
    expect(messages.nth(1)).to_have_attribute("data-author", "agent")
    expect(messages.nth(0)).to_have_attribute("data-author", "human")

    # A press on the same words closes it; Esc closes it and the window stays.
    words.click()
    expect(page.locator(CARD)).to_have_count(0)
    words.click()
    _card(page)
    page.keyboard.press("Escape")
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator(DOC)).to_have_count(1)
    assert "is-active" not in (words.get_attribute("class") or "")

    # A press elsewhere in the document closes it too (and starts the writing it was a press for).
    words.click()
    _card(page)
    page.locator(f"{BODY} p").first.click(position={"x": 4, "y": 4})
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator(BODY)).to_have_attribute("contenteditable", "true")


def test_words_selected_are_commented_where_they_stand(ui_f2: UiSession) -> None:
    """Select words, press Comment: the field to write in opens under them, the words stay marked while it is open, Enter
    makes the comment on exactly those words, and the count above the field says one. Esc leaves nothing behind."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/new.md", "SYN Inline New", SHORT)
    page.reload()
    _open(page, doc)
    expect(page.locator(PILLS)).to_have_count(0)  # no comments, nothing to count

    phrase = "their comments live in a column on the right"
    _select(page, phrase)
    page.locator('[data-cap="comment-selection"]').click()
    card = _card(page)
    expect(card).to_have_attribute("data-kind", "new")
    draft = page.locator(f'{BODY} {MARK}[data-thread-id="draft"]')
    expect(draft).to_have_text(phrase)
    expect(card.locator('[data-role="comment-field"]')).to_be_focused()
    expect(page.locator('[data-role="comments-panel"]')).to_have_count(0)

    # Esc: nothing was written, nothing is left.
    page.keyboard.press("Escape")
    expect(page.locator(CARD)).to_have_count(0)
    expect(draft).to_have_count(0)
    assert _server_threads(session, doc) == []

    _select(page, phrase)
    page.locator('[data-cap="comment-selection"]').click()
    card = _card(page)
    card.locator('[data-role="comment-field"]').fill("Say which place, then.")
    page.keyboard.press("Enter")
    expect(page.locator(CARD)).to_have_count(0, timeout=10000)

    threads = _server_threads(session, doc)
    assert len(threads) == 1 and threads[0]["anchor"]["quote"] == phrase, threads
    assert [m["body"] for m in threads[0]["messages"]] == ["Say which place, then."]
    assert threads[0]["messages"][0]["author"] == "human"
    expect(page.locator(f"{BODY} {MARK}")).to_have_text(phrase, timeout=10000)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)  # no agent on this build
    expect(page.locator('[data-role="comments-panel"]')).to_have_count(0)


def test_the_count_stands_above_the_field_and_opens_the_list(ui_f2: UiSession) -> None:
    """A pill with the number of open comments, centred over the circle and clear of its tags; it opens all the comments as a
    list over the field, the open ones first and the resolved after; a click on one takes the window to its words and
    opens it there, under them, or over them where the text ends."""
    session = ui_f2
    page = session.page
    page.set_viewport_size({"width": 1470, "height": 923})
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/list.md", "SYN Inline List", LONG)
        first = _thread(conn, doc, "The first words of the plan", "Start with the decision.")
        middle = _thread(conn, doc, "SYN paragraph 20", "Is this one needed?")
        last = _thread(conn, doc, "The last words of the plan", "End on the next step.")
        core_comments.add_message(conn, owner=OWNER, thread_id=last, body="Which step?", author="agent")
        whole = _thread(conn, doc, None, "A note on the whole page.")
        done = _thread(conn, doc, "SYN paragraph 7", "Cut this one.")
        core_comments.set_resolved(conn, owner=OWNER, thread_id=done, resolved=True)
    page.reload()
    _open(page, doc)

    count = page.locator(f"{PILLS} {COUNT}")
    expect(count).to_have_text("4 comments", timeout=10000)
    pills, circle = _rect(page, PILLS), _rect(page, ".circle-field__shape")
    assert pills["bottom"] <= circle["y"] - 8, f"the pills touch the circle: {pills} {circle}"
    assert circle["y"] - pills["bottom"] <= 40, f"the pills stand far from the circle: {pills} {circle}"
    assert abs((pills["x"] + pills["w"] / 2) - (circle["x"] + circle["w"] / 2)) <= 2, "the pills are not over the circle's middle"
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)

    # Pointed at, the field brings its tags: the pills rise clear of them.
    show_tags(page)
    _until(page, lambda: _rect(page, PILLS)["bottom"] <= _rect(page, ".circle-tags")["y"] - 4)
    page.mouse.move(8, 8)

    count.click()
    list_ = page.locator(LIST)
    expect(list_).to_be_visible(timeout=10000)
    rows = list_.locator('[data-role="doc-comments-row"]')
    expect(rows).to_have_count(5)
    assert rows.evaluate_all("els => els.map((el) => el.dataset.threadId)") == [first, middle, last, whole, done]
    expect(rows.nth(0)).to_contain_text("The first words of the plan")
    expect(rows.nth(0)).to_contain_text("Start with the decision.")
    expect(rows.nth(2)).to_contain_text("Which step?")  # the latest word is the agent's
    expect(rows.nth(3)).to_contain_text("Whole document")
    expect(list_).to_contain_text("Resolved")
    listed, circle = _rect(page, LIST), _rect(page, ".circle-field__shape")
    assert listed["bottom"] <= _rect(page, f"{PILLS} {COUNT}")["y"], "the list stands over the pill, not on it"
    assert abs((listed["x"] + listed["w"] / 2) - (circle["x"] + circle["w"] / 2)) <= 2, "the list is not on the circle's axis"
    expect(count).to_have_attribute("aria-expanded", "true")

    # A click on the one in the middle of the page: the list goes, the window scrolls to its words, the comment is open under them.
    scroller = page.locator(f"{DOC} .vt-window__body")
    assert scroller.evaluate("el => el.scrollTop") == 0
    rows.nth(1).click()
    expect(page.locator(LIST)).to_have_count(0)
    card = _card(page)
    expect(card).to_have_attribute("data-thread-id", middle)
    _settled(page, CARD)
    assert scroller.evaluate("el => el.scrollTop") > 800, "the window did not go to the words"
    win = _rect(page, DOC)
    words, shown = _rect(page, f'{BODY} {MARK}[data-thread-id="{middle}"]'), _rect(page, CARD)
    assert words["y"] >= win["y"] + 52, f"the words are under the head: {words}"
    assert shown["bottom"] <= win["bottom"] - FOOT + 1, f"the comment is under the fade: {shown}"
    assert 0 <= shown["y"] - (words["y"] + words["h"]) <= 16, (words, shown)

    # The words at the very end of the text: no room under them above the fade, so the comment stands over them.
    page.keyboard.press("Escape")
    expect(page.locator(CARD)).to_have_count(0)
    count.click()
    page.locator(f"{LIST} [data-role='doc-comments-row']").nth(2).click()
    card = _card(page)
    expect(card).to_have_attribute("data-thread-id", last)
    _settled(page, CARD)
    words, shown = _rect(page, f'{BODY} {MARK}[data-thread-id="{last}"]'), _rect(page, CARD)
    assert 0 <= words["y"] - (shown["y"] + shown["h"]) <= 16, f"the comment is not over the words at the end: {words} {shown}"
    assert shown["y"] >= win["y"] + 52, f"the comment is under the head: {shown}"
    page.keyboard.press("Escape")

    # The list closes with Esc and with a press elsewhere; a whole-document comment opens under the title.
    count.click()
    expect(page.locator(LIST)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(LIST)).to_have_count(0)
    expect(page.locator(DOC)).to_have_count(1)
    count.click()
    page.locator(f"{LIST} [data-role='doc-comments-row']").nth(3).click()
    card = _card(page)
    expect(card).to_have_attribute("data-thread-id", whole)
    _settled(page, CARD)
    title, whole_box = _rect(page, f"{DOC} [data-role='doc-title']"), _rect(page, CARD)
    assert 0 <= whole_box["y"] - (title["y"] + title["h"]) <= 24, (title, whole_box)
    assert scroller.evaluate("el => el.scrollTop") < 200, "a comment on the whole page did not take the window to its title"
    count.click()
    expect(page.locator(LIST)).to_be_visible()
    page.locator(f"{DOC} .doc-detail__title").click()
    expect(page.locator(LIST)).to_have_count(0)


def test_the_pills_the_list_and_the_card_stay_on_a_phone_screen(ui_f2: UiSession) -> None:
    """390 x 844: the pair is whole and clear of the screen's edges, the list opens inside it, so does a comment's card, and
    the page gets no sideways scroll."""
    session = ui_f2
    page = session.page
    page.set_viewport_size({"width": 390, "height": 844})
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/phone.md", "SYN Inline Phone", SHORT)
        late = _thread(conn, doc, "pick one place and say so in the notes", "Which place?")
        _thread(conn, doc, "The release moves", "A comment at the left edge, with words long enough to wrap onto a second and a third line.")
    page.reload()
    _open(page, doc)
    count = page.locator(f"{PILLS} {COUNT}")
    expect(count).to_have_text("2 comments", timeout=10000)
    screen = {"x": 0, "right": 390}

    def inside(selector: str) -> None:
        box = _rect(page, selector)
        assert box["x"] >= screen["x"] - 0.5 and box["right"] <= screen["right"] + 0.5, f"{selector} leaves the screen: {box}"

    inside(PILLS)
    count.click()
    expect(page.locator(LIST)).to_be_visible(timeout=10000)
    inside(LIST)
    page.locator(f"{LIST} [data-role='doc-comments-row']").nth(0).click()
    expect(_card(page)).to_have_attribute("data-thread-id", late)
    _settled(page, CARD)
    inside(CARD)
    page.keyboard.press("Escape")
    expect(page.locator(CARD)).to_have_count(0)
    # The one at the left edge, opened by a press on its words.
    tick(page)
    page.locator(f"{BODY} {MARK}").first.click()
    expect(_card(page)).not_to_have_attribute("data-thread-id", late)
    _settled(page, CARD)
    inside(CARD)
    assert page.evaluate("() => document.documentElement.scrollWidth") <= 391, "the page scrolls sideways"


def test_the_count_reads_resolved_when_the_last_open_comment_is_resolved(ui_f2: UiSession) -> None:
    """The way to resolved comments stays: while the document has any comment the pill is there, and with none open it
    reads "2 resolved", in grey and with no dot (the dot is the yellow of marked words; resolved words are not marked). It
    opens a list of the resolved ones, one of which can be opened again."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/resolved.md", "SYN Inline Resolved", PLAN)
        first = _thread(conn, doc, "ship on Wednesday", "Can this move to Thursday?")
        second = _thread(conn, doc, "The notes close the page", "Add the date here.")
    _fresh_open(session, doc)
    count = page.locator(f"{PILLS} {COUNT}")
    expect(count).to_have_text("2 comments", timeout=10000)
    expect(count.locator(".doc-check__dot")).to_have_count(1)

    def resolve(thread: str) -> None:
        tick(page)
        page.locator(f'{BODY} {MARK}[data-thread-id="{thread}"]').click()
        _card(page).locator('[data-role="comment-resolve"]').click()
        expect(page.locator(CARD)).to_have_count(0, timeout=10000)

    resolve(first)
    expect(count).to_have_text("1 comment", timeout=10000)
    resolve(second)
    expect(count).to_have_text("2 resolved", timeout=10000)
    expect(count).to_have_attribute("aria-label", "2 resolved comments")
    expect(count.locator(".doc-check__dot")).to_have_count(0)
    assert count.evaluate("el => getComputedStyle(el).color") == "rgba(0, 0, 0, 0.6)", "the words of a pill with only resolved comments are not grey"
    expect(page.locator(f"{BODY} {MARK}[data-resolved]")).to_have_count(2)  # marked for the list, plain to the eye

    # Its list is the resolved ones, under their heading.
    count.click()
    listed = page.locator(LIST)
    expect(listed).to_be_visible(timeout=10000)
    rows = listed.locator('[data-role="doc-comments-row"]')
    expect(rows).to_have_count(2)
    expect(listed).to_contain_text("Resolved")
    assert rows.evaluate_all("els => els.map((el) => el.dataset.threadId)") == [first, second]
    expect(rows.nth(0)).to_contain_text("ship on Wednesday")

    # One of them opened again is an open comment again: the pill reads it, with its dot.
    rows.nth(0).click()
    card = _card(page)
    expect(card.locator('[data-role="comment-resolve"]')).to_have_text("Unresolve")
    card.locator('[data-role="comment-resolve"]').click()
    expect(count).to_have_text("1 comment", timeout=10000)
    expect(count.locator(".doc-check__dot")).to_have_count(1)
    expect(count).not_to_have_attribute("aria-label", "2 resolved comments")


def test_a_reply_and_a_resolve_happen_in_the_card(ui_f2: UiSession) -> None:
    """A reply is written in the card; Resolve takes the comment off the page and out of the count, and the list keeps it
    under Resolved, where it can be unresolved."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/reply.md", "SYN Inline Reply", SHORT)
        one = _thread(conn, doc, "the sample board", "Which board?")
        _thread(conn, doc, "say so in the notes", "Where in the notes?")
    page.reload()
    _open(page, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments", timeout=10000)

    page.locator(f'{BODY} {MARK}[data-thread-id="{one}"]').click()
    card = _card(page)
    card.locator('[data-role="comment-field"]').fill("The one in the sample data.")
    page.keyboard.press("Enter")
    expect(card.locator('[data-role="comment-message"]')).to_have_count(2, timeout=10000)
    expect(card.locator('[data-role="comment-field"]')).to_have_value("")
    assert [m["body"] for m in _server_threads(session, doc)[0]["messages"]] == ["Which board?", "The one in the sample data."]

    card.locator('[data-role="comment-resolve"]').click()
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    plain = page.locator(f'{BODY} {MARK}[data-thread-id="{one}"]')
    assert plain.evaluate("el => getComputedStyle(el).backgroundColor") == "rgba(0, 0, 0, 0)"
    assert _server_threads(session, doc)[0]["resolved_at"] is not None

    page.locator(f"{PILLS} {COUNT}").click()
    rows = page.locator(f'{LIST} [data-role="doc-comments-row"]')
    expect(rows).to_have_count(2)
    rows.nth(1).click()
    card = _card(page)
    expect(card).to_have_attribute("data-thread-id", one)
    toggle = card.locator('[data-role="comment-resolve"]')
    expect(toggle).to_have_text("Unresolve")
    toggle.click()
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments", timeout=10000)
    assert _server_threads(session, doc)[0]["resolved_at"] is None


def test_a_comment_whose_words_are_gone_opens_under_the_title_with_its_quote(ui_f2: UiSession) -> None:
    """The words a comment was about can be rewritten away. It is still in the list and still opens: under the title, with
    its words quoted, and it says they are no longer in the text."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/gone.md", "SYN Inline Gone", SHORT)
        gone = _thread(conn, doc, "words that were cut", "Why cut it?")
    page.reload()
    _open(page, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    expect(page.locator(f"{BODY} {MARK}")).to_have_count(0)
    page.locator(f"{PILLS} {COUNT}").click()
    page.locator(f'{LIST} [data-role="doc-comments-row"]').first.click()
    card = _card(page)
    expect(card).to_have_attribute("data-thread-id", gone)
    expect(card).to_contain_text("words that were cut")
    expect(card).to_contain_text("no longer in the text")
    title, box = _rect(page, f"{DOC} [data-role='doc-title']"), _rect(page, CARD)
    assert 0 <= box["y"] - (title["y"] + title["h"]) <= 24, (title, box)


def test_the_head_of_a_document_window_has_no_comments_and_the_column_is_gone(ui_f2: UiSession) -> None:
    """The head keeps its facts and its versions; the count is above the field, once. No column on the window's right edge
    opens for a document, whichever way the document is reached: the window, or Documents by its address."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/head.md", "SYN Inline Head", SHORT)
        thread = _thread(conn, doc, "the sample board", "Which board?")
    page.reload()
    _open(page, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    head = page.locator(f'{DOC} [data-role="doc-facts"]')
    expect(head).to_contain_text("edited")
    expect(page.locator(f'{DOC} [data-role="doc-comments"]')).to_have_count(0)
    assert "comment" not in (head.text_content() or ""), "the head counts the comments the field's pill counts"

    # The document in Documents itself: no Comments button in its header, the same words and card, the same pill.
    page.goto("about:blank")
    page.goto(f"{session.base_url}/#doc/{doc}")
    expect(page.locator('[data-cap="docs"] [data-role="doc-path"]')).to_be_visible(timeout=10000)
    expect(page.locator('[data-cap="open-comments"]')).to_have_count(0)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    page.locator(f'[data-cap="docs"] {MARK}[data-thread-id="{thread}"]').click()
    _card(page)
    expect(page.locator('[data-cap="docs"] [data-role="doc-detail"] ' + CARD)).to_have_count(1)
    expect(page.locator('[data-role="comments-panel"]')).to_have_count(0)


def test_no_pills_without_a_document_in_front(ui_f2: UiSession) -> None:
    """The pills belong to the document in front: none on the board, none over a goal's window, gone with the window."""
    session = ui_f2
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/front.md", "SYN Inline Front", SHORT)
        _thread(conn, doc, "the sample board", "Which board?")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    expect(page.locator(PILLS)).to_have_count(0)
    _open(page, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    page.locator(f"{DOC} [aria-label='Close']").click()
    expect(page.locator(DOC)).to_have_count(0)
    expect(page.locator(PILLS)).to_have_count(0)
