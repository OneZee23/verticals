"""Check again in a document (docs/design/doc-comments-inline.md): a black pill beside the count of its comments, which took the
place of "Ready?". It hands the comments and the edits to the agent in one message, the agent answers in the field in two
lines, and what it rewrote is lit green in the document. It is offered for what waits: an edit or a comment of this session,
and any open comment whose last word is the person's, which a reload keeps; the comments the agent answered stop counting
once its turn is over.

`ui_agent`: the fake agent (`tests/ui/fake_agent/claude`) behind the real gateway. It works for a second and a half after a
Check again, which is the time a test has to write the document and its replies as the real agent would, through the same
database. The helpers are `tests/ui/doc_comments.py`."""

from __future__ import annotations

import json
from datetime import date

import psycopg
from playwright.sync_api import expect

from verticals.core import comments as core_comments, docs as core_docs, goals as core_goals

from tests.ui.conftest import UiSession
from tests.ui.doc_comments import (
    AGAIN, BODY, COUNT, LIST, MARK, OWNER, PANE_BODY, PILLS, PLAN,
    _api, _card, _comment_on, _doc, _fresh_open, _hand_over, _open, _rect, _say, _server_threads, _thread, _until,
)
from tests.ui.test_agent_conversation import ui_agent  # noqa: F401  (the fixture)
from tests.ui.views import tick

ANCHOR = date(2026, 8, 8)


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
    # The comment was made before this page was opened and nobody has answered it: it is there to hand over from the first look.
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)

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

    # The agent's hands: while it works, the document changes under it and it answers both comments (the real agent writes
    # through the same database).
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        current = core_docs.get(conn, owner=OWNER, id=doc)
        core_docs.save(conn, owner=OWNER, id=doc, expected_revision=current.revision, body=current.body.replace(old, new))
        for thread in _server_threads(session, doc):
            core_comments.add_message(conn, owner=OWNER, thread_id=thread["id"], body="Done.", author="agent")

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
    # Not the pill again: the agent's own revision is not an edit of the owner's, and it answered both comments.
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments")

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


def test_check_again_is_there_after_a_reload_for_a_comment_nobody_answered(ui_agent: UiSession) -> None:
    """The comments are on the server, so a fresh page load knows which ones nobody has answered: the person's last word on
    an open comment is something to hand over, whenever it was written. One the agent answered, and one resolved, are not."""
    session = ui_agent
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/reload.md", "SYN Inline Reload", PLAN)
        answered = _thread(conn, doc, "ship on Wednesday", "Can this move to Thursday?")
        core_comments.add_message(conn, owner=OWNER, thread_id=answered, body="Moved.", author="agent")
        done = _thread(conn, doc, "and then we rest", "Cut this.")
        core_comments.set_resolved(conn, owner=OWNER, thread_id=done, resolved=True)
    _fresh_open(session, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("1 comment", timeout=10000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)  # answered, resolved: nothing waits

    # The person's reply, written outside this page: after a fresh load it waits.
    _say(session, answered, "Thursday is too late as well.", "human")
    _fresh_open(session, doc)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)
    assert f"(#doc/{doc})" in _hand_over(page)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)  # the pill goes at the press


def test_check_again_goes_when_the_agent_answered_and_comes_back_with_a_new_reply(ui_agent: UiSession) -> None:
    """The comments the agent answered stop counting once its turn is over, so the pill goes; a comment it did not answer
    keeps it; a new reply of the person's brings it back."""
    session = ui_agent
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/answers.md", "SYN Inline Answers", PLAN)
        first = _thread(conn, doc, "ship on Wednesday", "Can this move to Thursday?")
        second = _thread(conn, doc, "The notes close the page", "Add the date here.")
    _fresh_open(session, doc)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments", timeout=10000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)

    # A turn in which the agent answers the first comment only: the second keeps the pill.
    _hand_over(page)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    _say(session, first, "Moved to Thursday.", "agent")
    expect(page.locator('[data-role="circle-answer"]')).to_be_visible(timeout=15000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)

    # A turn in which it answers the second: nothing waits, the pill goes and the count stays.
    _hand_over(page)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    _say(session, second, "Added.", "agent")
    expect(page.locator('[data-role="circle-answer"]')).to_be_visible(timeout=15000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0, timeout=10000)
    expect(page.locator(f"{PILLS} {COUNT}")).to_have_text("2 comments")
    page.wait_for_timeout(500)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_count(0)  # and it does not come back by itself

    # The person writes on the second again: it waits for the agent once more.
    tick(page)
    page.locator(f'{BODY} {MARK}[data-thread-id="{second}"]').click()
    card = _card(page)
    card.locator('[data-role="comment-field"]').fill("Say which date.")
    page.keyboard.press("Enter")
    expect(card.locator('[data-role="comment-message"]')).to_have_count(3, timeout=10000)
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)


def test_a_message_that_did_not_go_leaves_check_again_on_the_page(ui_agent: UiSession) -> None:
    """The pill goes at the press and stays away while the hand-over is under way; when the message is refused no turn will
    start, so it comes back and the comment is still there to hand over."""
    session = ui_agent
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/refused.md", "SYN Inline Refused", PLAN)
        _thread(conn, doc, "ship on Wednesday", "Can this move to Thursday?")
    _fresh_open(session, doc)
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    session.expects_network_failures = True  # the refused message is this test's own doing
    page.route("**/__chat/send", lambda route: route.abort())
    again.click()
    page.wait_for_timeout(500)  # longer than the pill's fade: a pill that went has gone from the page by now
    expect(again).to_have_count(1, timeout=10000)
    expect(again).to_have_text("Check again")
    assert page.locator(".circle-field").get_attribute("data-state") != "working"
    page.unroute("**/__chat/send")
    assert f"(#doc/{doc})" in _hand_over(page)  # and the next press goes


def test_an_open_list_stays_open_when_the_last_open_comment_is_resolved(ui_agent: UiSession) -> None:
    """The pill changes its words in place, and a list that is open stays open: with the list open, the agent answers and
    resolves the last open comment during its turn, and when the turn is over the pill reads "2 resolved" and the list
    shows both resolved comments."""
    session = ui_agent
    page = session.page
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/stays.md", "SYN Inline Stays", PLAN)
        old = _thread(conn, doc, "and then we rest", "Cut this.")
        core_comments.set_resolved(conn, owner=OWNER, thread_id=old, resolved=True)
        last = _thread(conn, doc, "ship on Wednesday", "Can this move to Thursday?")
    _fresh_open(session, doc)
    count = page.locator(f"{PILLS} {COUNT}")
    expect(count).to_have_text("1 comment", timeout=10000)
    _hand_over(page)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    count.click()
    listed = page.locator(LIST)
    expect(listed).to_be_visible(timeout=10000)
    expect(listed.locator('[data-role="doc-comments-row"]')).to_have_count(2)

    _say(session, last, "Moved to Thursday.", "agent")
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        core_comments.set_resolved(conn, owner=OWNER, thread_id=last, resolved=True)
    expect(page.locator('[data-role="circle-answer"]')).to_be_visible(timeout=15000)
    expect(count).to_have_text("2 resolved", timeout=10000)
    expect(listed).to_be_visible()
    rows = listed.locator('[data-role="doc-comments-row"]')
    expect(rows).to_have_count(2)
    assert rows.evaluate_all("els => els.map((el) => el.dataset.threadId)") == [old, last]
    expect(listed).to_contain_text("Resolved")


def test_a_double_press_on_check_again_hands_over_once(ui_agent: UiSession) -> None:
    """Words typed a moment ago are saved first, and for that moment the pill is still on the page: a second press in it
    must not send the message twice."""
    session = ui_agent
    page = session.page
    sent: list[str] = []
    page.on("request", lambda request: sent.append(request.url) if request.url.endswith("/__chat/send") and request.method == "POST" else None)
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/twice.md", "SYN Inline Twice", "The plan is short.\n\nWe will ship on Wednesday, and then we rest.")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)
    _comment_on(page, "ship on Wednesday", "Can this move to Thursday?")
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    page.locator(f"{BODY} p").first.click(position={"x": 4, "y": 4})
    expect(page.locator(BODY)).to_have_attribute("contenteditable", "true")
    page.keyboard.type(" More words, not saved yet.")
    again.dblclick()
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    page.wait_for_timeout(500)
    assert len(sent) == 1, sent
    saved = _until(page, lambda: (lambda got: got.json() if got.status_code == 200 and "More words" in got.json()["body"] else None)(_api(session, f"/api/docs/{doc}")))
    assert "More words, not saved yet." in saved["body"], "the words typed just before the press were not handed over saved"


def test_a_comment_made_while_the_agent_works_does_not_hide_its_rewrite(ui_agent: UiSession) -> None:
    """A comment is not a hand in the text: written during the agent's turn, it leaves the rewrite lit, and it is a new thing
    to hand over (Check again is back once the turn is over)."""
    session = ui_agent
    page = session.page
    old, new = "ship on Wednesday", "ship on Thursday"
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        doc = _doc(conn, "syn-inline/during.md", "SYN Inline During", "The plan is short.\n\nWe will ship on Wednesday, and then we rest.")
        _thread(conn, doc, old, "Can this move to Thursday?")
    page.reload()
    page.wait_for_selector(".goal-card__row")
    _open(page, doc)
    _comment_on(page, "The plan is short", "Say how short.")
    again = page.locator(f"{PILLS} {AGAIN}")
    expect(again).to_have_text("Check again", timeout=10000)
    again.click()
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working", timeout=10000)
    _comment_on(page, "and then we rest", "Rest is not a plan.")
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        current = core_docs.get(conn, owner=OWNER, id=doc)
        core_docs.save(conn, owner=OWNER, id=doc, expected_revision=current.revision, body=current.body.replace(old, new))
    expect(page.locator('[data-role="circle-answer"]')).to_contain_text("Changed the words you commented on.", timeout=15000)
    lit = page.locator(f"{BODY} mark.doc-rewritten")
    expect(lit).to_have_count(1, timeout=10000)
    expect(lit).to_have_text("Thursday")
    expect(page.locator(f"{PILLS} {AGAIN}")).to_have_text("Check again", timeout=10000)


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
