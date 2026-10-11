"""The shared parts of the two suites for comments in a document's text (docs/design/doc-comments-inline.md):
`test_doc_comments_inline.py` (the words, the card, the count and the list) and `test_doc_check_again.py` (Check again, what
the agent rewrote, and what waits for it). The selectors, the sample texts, and the helpers that make a document and its
threads through `verticals.core` (as `test_comments_panel.py` does), open the document as a person opens it, select words
in it, and wait on the server."""

from __future__ import annotations

import json

import httpx
import psycopg
from playwright.sync_api import Page, expect

from verticals.core import comments as core_comments, docs as core_docs

from tests.ui.conftest import UiSession
from tests.ui.views import open_page, switch_view, tick

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
SHORT = (
    "The release moves the sample board to its new look. We ship the field first, then the windows, then the documents.\n\n"
    "The risk is that their comments live in a column on the right. We should pick one place and say so in the notes."
)
FILLER = "\n\n".join(f"SYN paragraph {n}: a line of the plan that runs on a little, to fill the page with something to scroll past." for n in range(40))
LONG = f"The first words of the plan stand at the top.\n\n{FILLER}\n\nThe last words of the plan stand at the very end."
PLAN = "The plan is short.\n\nWe will ship on Wednesday, and then we rest.\n\nThe notes close the page."
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


def _say(session: UiSession, thread: str, body: str, author: str) -> None:
    """What the agent (or the person, from outside this page) writes on a comment, through the same database."""
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        core_comments.add_message(conn, owner=OWNER, thread_id=thread, body=body, author=author)


def _fresh_open(session: UiSession, doc: str) -> None:
    """A page load of the app's own address, then the document opened as a person opens it: what the page knows is what the
    server has."""
    page = session.page
    page.goto("about:blank")
    page.goto(f"{session.base_url}/")
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)


def _hand_over(page: Page):
    """Presses Check again and returns the message that went."""
    with page.expect_request(lambda request: request.url.endswith("/__chat/send") and request.method == "POST") as sent:
        page.locator(f"{PILLS} {AGAIN}").click()
    return json.loads(sent.value.post_data or "{}")["text"]
