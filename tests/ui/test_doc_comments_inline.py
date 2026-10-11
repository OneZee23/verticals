"""Comments in a document's text (docs/design/doc-comments-inline.md): a comment sits on the words it is about and opens right
over them, like a popover; above the field a pill counts the open comments, and Check again hands the comments and the
edits to the agent in place of the "Ready?" pill; what the agent rewrote is lit green. The comments column on the right is a
goal's alone now.

`ui_f2` for what needs no agent, `ui_agent` (the fake agent behind the real gateway, `tests/ui/fake_agent/claude`) for Check
again. Every document and every thread is made through `verticals.core`, as `test_comments_panel.py` makes them, and the
document is opened as a person opens it, from the Documents desk. The fake agent works for a second and a half after a
Check again, which is the time the test has to write the document as the real agent would."""

from __future__ import annotations

import json
from datetime import date

import httpx
import psycopg
from playwright.sync_api import Page, expect

from verticals.core import comments as core_comments, docs as core_docs, goals as core_goals

from tests.ui.conftest import UiSession
from tests.ui.test_agent_conversation import ui_agent  # noqa: F401  (the fixture)
from tests.ui.views import open_page, show_tags, switch_view, tick

OWNER = "t1"
DOC = '.vt-window[data-window="doc"]'
BODY = f"{DOC} [data-role='doc-body']"
FRONT_BODY = '.vt-window--front [data-role="doc-body"]'
PANE_BODY = '[data-cap="docs"] [data-role="doc-body"]'
CARD = '[data-role="comment-card"]'
MARK = "mark.comment-highlight"
PILLS = '[data-role="doc-check"]'
COUNT = '[data-role="doc-comments-count"]'
AGAIN = '[data-role="doc-check-again"]'
LIST = '[data-role="doc-comments-list"]'
FOOT = 168  # the window's white fade at rest (WindowStack.vue): the text stands above it
ANCHOR = date(2026, 8, 8)

SHORT = (
    "The release moves the sample board to its new look. We ship the field first, then the windows, then the documents.\n\n"
    "The risk is that their comments live in a column on the right. We should pick one place and say so in the notes."
)
FILLER = "\n\n".join(f"SYN paragraph {n}: a line of the plan that runs on a little, to fill the page with something to scroll past." for n in range(40))
LONG = f"The first words of the plan stand at the top.\n\n{FILLER}\n\nThe last words of the plan stand at the very end."

RECT = """(sel) => {
  const el = document.querySelector(sel)
  if (!el) return null
  const b = el.getBoundingClientRect()
  return { x: b.x, y: b.y, w: b.width, h: b.height, right: b.right, bottom: b.bottom }
}"""


def _doc(conn: psycopg.Connection, path: str, title: str, body: str) -> str:
    return core_docs.create(conn, owner=OWNER, path=path, title=title, body=body).doc.id


def _thread(conn: psycopg.Connection, doc: str, quote: str | None, body: str, author: str = "human") -> str:
    anchor = {"quote": quote, "prefix": "", "suffix": ""} if quote else None
    return core_comments.create_thread(conn, owner=OWNER, doc_id=doc, body=body, author=author, anchor=anchor).thread.id


def _rect(page: Page, selector: str) -> dict[str, float]:
    box = page.evaluate(RECT, selector)
    assert box is not None, f"{selector} is not on the page"
    return box


def _open(page: Page, doc_id: str) -> None:
    """The document as a window, from the desk, with its comments marked."""
    switch_view(page, "docs")
    page.mouse.move(8, 8)
    open_page(page, doc_id)
    page.wait_for_timeout(300)


def _select(page: Page, phrase: str, where: str = FRONT_BODY) -> None:
    """Selects `phrase` in the open document's text and lets the app read it as it reads a drag's end (`mouseup`), as
    `test_comments_panel.py::_select_phrase` does. `where` is the text's own selector: the front window's, or Documents'."""
    page.evaluate(
        """([phrase, where]) => {
             const container = document.querySelector(where)
             const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
             let node
             while ((node = walker.nextNode())) {
               const idx = node.textContent.indexOf(phrase)
               if (idx !== -1) {
                 window.getSelection().setBaseAndExtent(node, idx, node, idx + phrase.length)
                 container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }))
                 return
               }
             }
             throw new Error('phrase not found: ' + phrase)
           }""",
        [phrase, where],
    )


def _card(page: Page):
    """The card once it stands; the clock moves on so a press inside it is not dropped (`views.tick`)."""
    card = page.locator(CARD)
    expect(card).to_be_visible(timeout=10000)
    tick(page)
    return card


def _comment_on(page: Page, phrase: str, words: str, where: str = FRONT_BODY) -> None:
    """The owner's way: select the words, press Comment, write, Enter."""
    _select(page, phrase, where)
    page.locator('[data-cap="comment-selection"]').click()
    card = _card(page)
    card.locator('[data-role="comment-field"]').fill(words)
    page.keyboard.press("Enter")
    expect(page.locator(CARD)).to_have_count(0, timeout=10000)


def _server_threads(session: UiSession, doc_id: str) -> list[dict]:
    resp = httpx.get(
        f"{session.backend.base_url}/api/docs/{doc_id}/comments",
        headers={"Authorization": f"Bearer {session.backend.token}"}, timeout=10,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["threads"]


def _until(page: Page, read, timeout_ms: int = 10_000):
    """Polls `read()` until it gives something truthy and returns it (a wait for the server, not a fixed pause); fails with
    the last thing it gave after `timeout_ms`."""
    waited, got = 0, read()
    while not got and waited < timeout_ms:
        page.wait_for_timeout(100)
        waited += 100
        got = read()
    assert got, f"nothing after {timeout_ms} ms: {got!r}"
    return got


def _settled(page: Page, selector: str, timeout_ms: int = 5_000) -> dict[str, float]:
    """The box of `selector` once it has stopped moving (two reads 50 ms apart agree): a glide or a scroll has ended."""
    last, waited = None, 0
    while waited <= timeout_ms:
        now = _rect(page, selector)
        if now == last:
            return now
        last = now
        page.wait_for_timeout(50)
        waited += 50
    raise AssertionError(f"{selector} kept moving for {timeout_ms} ms: {last}")


def _api(session: UiSession, path: str) -> httpx.Response:
    return httpx.get(
        f"{session.backend.base_url}{path}", headers={"Authorization": f"Bearer {session.backend.token}"}, timeout=10,
    )


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


def test_check_again_takes_the_place_of_ready_and_lights_what_the_agent_rewrote(ui_agent: UiSession) -> None:
    """A comment in an open document: beside the count, a black Check again, and the circle never asks "Ready?". Pressed, it
    hands the comments and the edits to the agent in one message that links the document; the agent answers in the field in
    two lines, and once it has finished the words it rewrote are lit green in the document, those and only those, until
    the owner writes in it."""
    session = ui_agent
    page = session.page
    old, new = "ship on Wednesday", "ship on Thursday"
    body = "The plan is short.\n\nWe will ship on Wednesday, and then we rest.\n\nThe notes close the page."
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/again.md", "SYN Inline Again", body)
        _thread(conn, doc, old, "Can this move to Thursday?")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    # Nothing new since the page was opened: nothing to hand over yet.
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)

    _comment_on(page, "The notes close the page", "Add the date here.")
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments")
    assert again.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(0, 0, 0)", "Check again is not the field's black"
    # "Ready?" is gone: no pill in the circle, no state for it.
    expect(page.locator(".circle-field__go")).to_have_count(0)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "rest")
    pills, circle = _rect(page, PILLS), _rect(page, ".circle-field__shape")
    assert abs((pills["x"] + pills["w"] / 2) - (circle["x"] + circle["w"] / 2)) <= 2, "the pair is not over the circle's middle"

    with page.expect_request(lambda request: request.url.endswith("/__chat/send") and request.method == "POST") as sent:
        again.click()
    asked = json.loads(sent.value.post_data or "{}")
    assert asked["text"].startswith("Check again"), asked["text"]
    assert f"(#doc/{doc})" in asked["text"], "the message does not link the document"
    assert "two short lines" in asked["text"]
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    expect(page.locator('[data-role="agent-conversation"]')).to_have_count(0)

    # The agent's hands: while it works, the document changes under it (the real agent writes through the same database).
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        current = core_docs.get(conn, owner=OWNER, id=doc)
        core_docs.save(conn, owner=OWNER, id=doc, expected_revision=current.revision, body=current.body.replace(old, new))

    answer = page.locator('[data-role="circle-answer"]')
    expect(answer).to_contain_text("Changed the words you commented on.", timeout=15000)
    assert _rect(page, ".circle-field__shape")["h"] <= 100, "the answer takes more than two lines"
    lit = page.locator(f"{BODY} mark.doc-rewritten")
    expect(lit).to_have_count(1, timeout=10000)
    expect(lit).to_have_text("Thursday")
    expect(page.locator(BODY)).to_contain_text(new)
    assert lit.evaluate("el => getComputedStyle(el).backgroundColor") != "rgba(0, 0, 0, 0)", "the rewritten words are not lit"
    # The window shows the saved copy, and a later edit of the owner's does not run into the agent's revision (409).
    assert page.locator(BODY).inner_text().count("Wednesday") == 0
    # Not the pill again: the agent's own revision is not an edit of the owner's.
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)

    # Writing in the document puts the light out.
    page.locator(f"{BODY} p").first.click(position={"x": 4, "y": 4})
    expect(page.locator(BODY)).to_have_attribute("contenteditable", "true")
    expect(page.locator(f"{BODY} mark.doc-rewritten")).to_have_count(0)
    page.keyboard.type(" Really.")
    page.mouse.click(30, 460)  # leaves the text: the edit is saved
    saved = _until(page, lambda: (lambda got: got.json() if got.status_code == 200 and "Really." in got.json()["body"] else None)(_api(session, f"/api/docs/{doc}")))
    assert new in saved["body"], saved
    assert not session.bad_responses, session.bad_responses  # no 409: the window had taken the agent's revision


def test_check_again_in_documents_lights_the_rewrite_there_too(ui_agent: UiSession) -> None:
    """The document in Documents itself, not in a window: the same pair above the field, the same hand-over, and what the
    agent rewrote is lit in the page there."""
    session = ui_agent
    page = session.page
    old, new = "ship on Wednesday", "ship on Thursday"
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/pane.md", "SYN Inline Pane", "The plan is short.\n\nWe will ship on Wednesday, and then we rest.")
    page.goto("about:blank")
    page.goto(f"{session.base_url}/#doc/{doc}")
    expect(page.locator('[data-cap="docs"] [data-role="doc-path"]')).to_be_visible(timeout=10000)
    _comment_on(page, old, "Can this move to Thursday?", PANE_BODY)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    with page.expect_request(lambda request: request.url.endswith("/__chat/send") and request.method == "POST") as sent:
        again.click()
    assert f"(#doc/{doc})" in json.loads(sent.value.post_data or "{}")["text"]
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        current = core_docs.get(conn, owner=OWNER, id=doc)
        core_docs.save(conn, owner=OWNER, id=doc, expected_revision=current.revision, body=current.body.replace(old, new))
    expect(page.locator('[data-role="circle-answer"]')).to_contain_text("Changed the words you commented on.", timeout=15000)
    lit = page.locator(f"{PANE_BODY} mark.doc-rewritten")
    expect(lit).to_have_count(1, timeout=10000)
    expect(lit).to_have_text("Thursday")
    assert page.locator(PANE_BODY).inner_text().count("Wednesday") == 0


def test_an_edit_in_the_text_asks_for_a_check_too(ui_agent: UiSession) -> None:
    """Words written in the document, with no comment, are an edit to hand over: Check again shows without a count."""
    session = ui_agent
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/edit.md", "SYN Inline Edit", "One line of the plan.")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)
    expect(page.locator(PILLS)).to_have_count(0)
    page.locator(f"{BODY} p").first.click(position={"x": 4, "y": 4})
    expect(page.locator(BODY)).to_have_attribute("contenteditable", "true")
    page.keyboard.type(" And one more.")
    page.mouse.click(30, 460)  # leaves the text: the edit is saved
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_count(0)
    expect(page.locator(".circle-field__go")).to_have_count(0)
    with page.expect_request(lambda request: request.url.endswith("/__chat/send") and request.method == "POST") as sent:
        again.click()
    assert f"(#doc/{doc})" in json.loads(sent.value.post_data or "{}")["text"]


def test_check_again_on_a_morning_report_ends_its_task(ui_agent: UiSession) -> None:
    """As "Ready?" did: a morning report gone through has nothing left to wait for, so its open task is done."""
    session = ui_agent
    page = session.page
    path = "reports/morning/2026-08-08.md"
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, path, "Morning report — 8 August 2026", "A plan for the day.\n\nOne thing to decide.")
        task = core_goals.create(
            conn, owner=OWNER, title="Morning report", vertical="day", anchor_date=ANCHOR,
        ).goal.id
        core_goals.update(conn, owner=OWNER, id=task, body=f"[the report](doc:{path})")
        _thread(conn, doc, "One thing to decide", "Decide it for me.")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)
    _comment_on(page, "A plan for the day", "Start with this.")
    with page.expect_request(lambda request: request.url.endswith("/__chat/send") and request.method == "POST"):
        page.locator(f"{PILLS} {AGAIN}").click()
    done = _until(page, lambda: (lambda got: got.status_code == 200 and got.json()["done_at"])(_api(session, f"/api/goals/{task}")))
    assert done, "the report's task is still open"
