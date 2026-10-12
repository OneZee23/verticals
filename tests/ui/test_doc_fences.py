"""Fenced blocks in a document (`web/src/lib/bodyMarkdown.ts`; Sources, docs/design/sources.md) through Chromium, live HTTP
and real Postgres.

A source's check is a fenced block in its document: three backticks and a name, the lines, three backticks. The document
view used to show it as raw lines with the backticks, which read as broken, and wrote it back through its inline rules, which
bent some characters (`_word_` became `*word*`). Now a fence is one block of its own: set quietly (the kit's block-code
rail, the body's one typeface), not editable, and written back exactly as it was, so a plain save of the text around it
never changes what it says, and a check's hash never moves.
"""

from __future__ import annotations

import httpx
import psycopg
from playwright.sync_api import expect

from tests.ui.conftest import UiSession
from tests.ui.views import tick
from verticals.core import docs as core_docs
from verticals.core import source_checks as sc

OWNER = "t1"
BODY_SAVE_SETTLE_MS = 1500  # BODY_SAVE_DEBOUNCE_MS (1000) in DocDetail.vue, plus round-trip slack
BODY = '[data-cap="docs"] [data-role="doc-body"]'

# Lines a careless editor bends: emphasis markers, a link, a backtick pair, lines that start like a heading, a list item and a
# table row, indentation, trailing spaces, an empty line inside, a tab, a long line, other scripts.
RISKY = [
    '{',
    '  "kind": "http",',
    '  "say": "_{v}_ waiting, *very* many, `x`, [a](https://example.test/a_b_c)",',
    '# not a heading',
    '- not a list item',
    '| not | a | table |',
    '    four spaces in, and trailing spaces   ',
    '',
    '\ta tab, then Cyrillic: очередь, and a long line ' + 'x' * 200,
    '}',
]


def _doc(conn: psycopg.Connection, path: str, body: str, title: str = "Fences") -> str:
    return core_docs.create(conn, owner=OWNER, path=path, title=title, body=body).doc.id


def _open(session: UiSession, doc_id: str) -> None:
    session.page.goto("about:blank")
    session.page.goto(f"{session.base_url}/#doc/{doc_id}")
    expect(session.page.locator('[data-cap="docs"] [data-role="doc-detail"]')).to_be_visible(timeout=10000)


def _saved(session: UiSession, doc_id: str) -> dict:
    resp = httpx.get(f"{session.backend.base_url}/api/docs/{doc_id}", headers={"Authorization": f"Bearer {session.backend.token}"}, timeout=10)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _type_after(session: UiSession, paragraph: str, words: str) -> None:
    page = session.page
    tick(page)
    page.locator(f"{BODY} p", has_text=paragraph).first.click()
    page.keyboard.press("End")
    page.keyboard.type(words)
    page.wait_for_timeout(BODY_SAVE_SETTLE_MS)


def test_a_fenced_block_is_a_quiet_block_with_its_lines_as_written(ui_f2: UiSession) -> None:
    session = ui_f2
    page = session.page
    lines = "\n".join(RISKY)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc_id = _doc(conn, "syn-fences/one.md", f"Words before it.\n\n```check\n{lines}\n```\n\nWords after it.")

    _open(session, doc_id)
    body = page.locator(BODY)
    block = body.locator('pre[data-md-fence="check"]')
    expect(block).to_have_count(1, timeout=10000)
    expect(block).to_have_attribute("contenteditable", "false")
    assert block.locator("code").text_content() == lines, "the lines, exactly, with no backticks and nothing bent"
    assert "```" not in body.inner_text(), "no fence marks on the page"
    # Set as a block of its own, in the app's one typeface, kept as written and scrolled sideways, never wrapped.
    style = block.evaluate("""el => { const s = getComputedStyle(el), c = getComputedStyle(el.querySelector('code')),
        p = getComputedStyle(el.parentElement.querySelector('p'));
      return { white: s.whiteSpace, rule: s.borderLeftWidth, family: s.fontFamily, codeFamily: c.fontFamily, proseFamily: p.fontFamily,
               size: s.fontSize, proseSize: p.fontSize, tag: el.tagName } }""")
    assert style["white"] == "pre" and style["rule"] == "4px" and style["tag"] == "PRE"
    assert style["family"] == style["codeFamily"] == style["proseFamily"], "one typeface"
    assert float(style["size"][:-2]) < float(style["proseSize"][:-2]), "a size down from the words around it"
    expect(body.locator("p", has_text="Words before it.")).to_have_count(1)
    expect(body.locator("p", has_text="Words after it.")).to_have_count(1)


def test_a_fence_with_no_closing_line_is_just_text_as_before(ui_f2: UiSession) -> None:
    session = ui_f2
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc_id = _doc(conn, "syn-fences/open.md", "Before.\n\n```check\n{ never closed")

    _open(session, doc_id)
    expect(session.page.locator(f"{BODY} p", has_text="never closed")).to_have_count(1, timeout=10000)
    expect(session.page.locator(f"{BODY} pre")).to_have_count(0)


def test_a_plain_save_of_the_words_around_a_fence_writes_the_fence_back_exactly(ui_f2: UiSession) -> None:
    """The risky lines above come back byte for byte, whichever side of the fence is edited, and with two fences and one at
    the very start or end of the document."""
    session = ui_f2
    lines = "\n".join(RISKY)
    other = '{"kind": "dns", "host": "example.test"}'
    cases = {
        "after the words before it": (f"Words before it.\n\n```check\n{lines}\n```\n\nWords after it.", "Words before it.", " Edited."),
        "after the words after it": (f"Words before it.\n\n```check\n{lines}\n```\n\nWords after it.", "Words after it.", " Edited."),
        "two fences": (f"First.\n\n```check\n{lines}\n```\n\nBetween.\n\n```json\n{other}\n```\n\nLast.", "Between.", " Edited."),
        "a fence first": (f"```check\n{lines}\n```\n\nAfter it.", "After it.", " Edited."),
        "a fence last": (f"Before it.\n\n```check\n{lines}\n```", "Before it.", " Edited."),
    }
    for name, (body, paragraph, words) in cases.items():
        with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
            doc_id = _doc(conn, f"syn-fences/{name.replace(' ', '-')}.md", body, title=name)
        _open(session, doc_id)
        expect(session.page.locator(f'{BODY} pre[data-md-fence]').first).to_be_visible(timeout=10000)
        _type_after(session, paragraph, words)
        saved = _saved(session, doc_id)
        assert saved["revision"] > 1, f"{name}: the edit was saved"
        assert saved["body"] == body.replace(paragraph, paragraph + words), f"{name}: the fence came back as it was\n{saved['body']}"


def test_clicking_the_block_and_typing_cannot_change_what_it_says(ui_f2: UiSession) -> None:
    session = ui_f2
    page = session.page
    lines = "\n".join(RISKY)
    body = f"Words before it.\n\n```check\n{lines}\n```\n\nWords after it."
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc_id = _doc(conn, "syn-fences/click.md", body)

    _open(session, doc_id)
    block = page.locator(f'{BODY} pre[data-md-fence="check"]')
    expect(block).to_be_visible(timeout=10000)
    tick(page)
    block.locator("code").click()
    page.keyboard.type("zzz")
    page.keyboard.press("Backspace")
    page.keyboard.press("Delete")
    page.wait_for_timeout(BODY_SAVE_SETTLE_MS)
    assert block.locator("code").text_content() == lines, "the block is read, never typed over"
    saved = _saved(session, doc_id)["body"]
    assert f"```check\n{lines}\n```" in saved, "and whatever else the keys did, the fence is as it was"


def test_a_sources_check_keeps_its_hash_through_a_plain_save_of_its_text(ui_f2: UiSession) -> None:
    """The case that matters: the check inside a source document, with the lines the editor used to bend, still reads as the
    same check (the same hash) after the document's words are edited and saved."""
    session = ui_f2
    check = {"kind": "cmd", "argv": ["/bin/df", "-k", "/"], "parse": r"\s(\d+)%\s", "max": 90, "say": "_{v}_% of the *disk* is `used`"}
    body = sc.build_body(gives="How full the disk is.", how="Read the percent.", since="today", check=sc.Check.from_dict(check), fixes=["Free some space."])
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc_id = _doc(conn, "sources/disk.md", body, title="Disk")

    _open(session, doc_id)
    expect(session.page.locator(f'{BODY} pre[data-md-fence="check"]')).to_have_count(1, timeout=10000)
    _type_after(session, "How full the disk is.", " Edited.")
    saved = _saved(session, doc_id)
    assert "How full the disk is. Edited." in saved["body"]
    assert sc.parse_check(saved["body"]).hash == sc.Check.from_dict(check).hash, saved["body"]
