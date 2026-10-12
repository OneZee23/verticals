"""The Documents back link never lies on the document it leads out of.

A document opened by its address (`#doc/<id>`: a reload, a link, Back) takes the whole Documents view, with a back link to
the desk, "Documents", at the panel's top left (`DocsView.vue`). The link was set in that corner out of the flow, where the
document's own head starts (its path on the left; Comments, History, Delete and × on the right) and where the history's
toolbar starts, so nothing made room for it and it was drawn over whatever stood there. At a phone's width it also covered
half of Comments, and a tap on that half left the document.

A document opened by a click on its page in the desk is a window with a head of its own (the facts, its versions and ×;
S3.P4) and never meets the link: that way stays as it is.

Each part is measured by its box on the page and by what the pointer would hit at its middle, at the app's usual width
(`conftest.VIEWPORT`) and at 390 px (S-76's phone)."""

from __future__ import annotations

import psycopg
import pytest
from playwright.sync_api import Page, expect

from verticals.core import docs as core_docs
from tests.ui.conftest import VIEWPORT, UiSession
from tests.ui.views import open_page, switch_view

PHONE = {"width": 390, "height": 844}
WIDTHS = [pytest.param(VIEWPORT, id="1458"), pytest.param(PHONE, id="390")]

PATH = "syn-backlink/notes.md"
TITLE = "SYN Back Link"
BODY = "SYN a few words, so the document has something to show under its head."

BACK = '[data-role="docs-back"]'
HEAD = {
    "path": '[data-cap="docs"] [data-role="doc-path"]',
    "Comments": '[data-cap="docs"] [data-cap="open-comments"]',
    "History": '[data-cap="docs"] [data-role="doc-history-trigger"]',
    "Delete": '[data-cap="docs"] [data-role="doc-delete"]',
    "close": '[data-cap="docs"] [data-role="doc-close"]',
}
TITLE_AND_BODY = {
    "title": '[data-cap="docs"] [data-role="doc-title"]',
    "body": '[data-cap="docs"] [data-role="doc-body"]',
}
HISTORY = {
    "History label": '[data-role="docs-history"] .docs-history__toolbar > :first-child',
    "close history": '[data-role="docs-history-close"]',
    "first revision": '[data-role="docs-history-row"]:first-child',
}
WINDOW = '.vt-window[data-window="doc"]'
WINDOW_HEAD = {
    "facts": f'{WINDOW} [data-role="doc-facts"]',
    "close": f'{WINDOW} [aria-label="Close"]',
    "title": f'{WINDOW} [data-role="doc-title"]',
}


def _seed(session: UiSession) -> str:
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc_id = core_docs.create(conn, owner="t1", path=PATH, title=TITLE, body=BODY).doc.id
        # A second revision, so its history has rows to show.
        core_docs.save(conn, owner="t1", id=doc_id, expected_revision=1, body=f"{BODY} Edited.")
    return doc_id


def _open_by_address(session: UiSession, viewport: dict, doc_id: str) -> Page:
    """A real boot at `viewport` on `#doc/<id>` (the `about:blank` hop, as `test_docs_view.py::_open_by_address`)."""
    page = session.page
    page.set_viewport_size(viewport)
    page.goto("about:blank")
    page.goto(f"{session.base_url}/#doc/{doc_id}")
    expect(page.locator('[data-cap="docs"] [data-role="doc-detail"]')).to_be_visible(timeout=10000)
    expect(page.locator('[data-role="doc-title"]')).to_have_text(TITLE, timeout=10000)
    page.evaluate("document.fonts.ready.then(() => true)")
    return page


def _boxes(page: Page, parts: dict[str, str]) -> dict[str, dict[str, float]]:
    boxes: dict[str, dict[str, float]] = {}
    for name, selector in parts.items():
        part = page.locator(selector)
        expect(part, f"{name} ({selector}) is on the page").to_have_count(1)
        expect(part, f"{name} is visible").to_be_visible()
        box = part.bounding_box()
        assert box is not None, f"{name} has no box"
        boxes[name] = box
    return boxes


def _overlap(a: dict[str, float], b: dict[str, float], tolerance: float = 0.5) -> bool:
    """Whether two boxes share more than their edge (a sub-pixel touch is not an overlap)."""
    return (
        a["x"] < b["x"] + b["width"] - tolerance and b["x"] < a["x"] + a["width"] - tolerance
        and a["y"] < b["y"] + b["height"] - tolerance and b["y"] < a["y"] + a["height"] - tolerance
    )


def _describe(box: dict[str, float]) -> str:
    return f'[x {box["x"]:.0f}-{box["x"] + box["width"]:.0f}, y {box["y"]:.0f}-{box["y"] + box["height"]:.0f}]'


def _assert_apart(boxes: dict[str, dict[str, float]]) -> None:
    names = list(boxes)
    hits = [
        f"{a} {_describe(boxes[a])} lies over {b} {_describe(boxes[b])}"
        for i, a in enumerate(names) for b in names[i + 1:] if _overlap(boxes[a], boxes[b])
    ]
    assert not hits, "parts drawn on top of each other: " + "; ".join(hits)


def _assert_nothing_over(page: Page, selectors: dict[str, str]) -> None:
    """The pointer at the middle of each part reaches the part itself, so a press on it does what it says."""
    for name, selector in selectors.items():
        covered_by = page.locator(selector).evaluate(
            """el => {
              const r = el.getBoundingClientRect()
              const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
              return top && !el.contains(top) ? (top.dataset?.role || top.getAttribute('class') || top.tagName) : null
            }"""
        )
        assert covered_by is None, f"the middle of {name} is covered by {covered_by!r}"


@pytest.mark.parametrize("viewport", WIDTHS)
def test_a_document_opened_by_its_address_keeps_the_back_link_off_its_head(ui_f2: UiSession, viewport: dict) -> None:
    page = _open_by_address(ui_f2, viewport, _seed(ui_f2))

    boxes = _boxes(page, {"back link": BACK, **HEAD, **TITLE_AND_BODY})
    assert boxes["path"]["width"] > 0, "the path has no width, so nothing could overlap it"
    _assert_apart(boxes)
    _assert_nothing_over(page, {"back link": BACK, **HEAD})

    # The link still does its job: back to the desk.
    page.locator(BACK).click()
    expect(page.locator('[data-role="docs-desk"]')).to_be_visible(timeout=10000)
    expect(page.locator(BACK)).to_have_count(0)


@pytest.mark.parametrize("viewport", WIDTHS)
def test_the_history_of_a_document_opened_by_its_address_keeps_the_back_link_off_its_toolbar(
    ui_f2: UiSession, viewport: dict,
) -> None:
    page = _open_by_address(ui_f2, viewport, _seed(ui_f2))
    page.locator(HEAD["History"]).click()
    expect(page.locator('[data-role="docs-history"]')).to_be_visible(timeout=10000)
    expect(page.locator('[data-role="docs-history-row"]')).to_have_count(2, timeout=10000)

    _assert_apart(_boxes(page, {"back link": BACK, **HISTORY}))
    _assert_nothing_over(page, {"back link": BACK, "close history": HISTORY["close history"]})


@pytest.mark.parametrize("viewport", WIDTHS)
def test_a_document_opened_by_a_click_in_documents_keeps_its_window_head(ui_f2: UiSession, viewport: dict) -> None:
    session = ui_f2
    page = session.page
    doc_id = _seed(session)
    page.set_viewport_size(viewport)
    page.reload()
    switch_view(page, "docs")
    open_page(page, doc_id)
    expect(page.locator(WINDOW_HEAD["title"])).to_have_text(TITLE, timeout=10000)
    page.evaluate("document.fonts.ready.then(() => true)")

    # A window, not the Documents panel: no back link and no path line (its head stands for them).
    expect(page.locator(BACK)).to_have_count(0)
    expect(page.locator(f'{WINDOW} [data-role="doc-path"]')).to_have_count(0)
    _assert_apart(_boxes(page, WINDOW_HEAD))
    _assert_nothing_over(page, {"close": WINDOW_HEAD["close"]})
