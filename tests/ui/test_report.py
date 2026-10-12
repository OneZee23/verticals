"""A report from pictures, its task, and what can be done with it (docs/design/bug-reports.md): something is wrong, or could be
better. The person drops pictures on the window, says what they see and what they want and presses ↵. The words say which kind
it is and what the task is called, and the agent tells (here the stand-in agent, by the words); the person picks and names
nothing. A bug carries the last lines of the app's and the agent's logs, a request none, and with no agent, or one that cannot
tell, it is a request. The report comes first, a document with the person's words as they wrote them, the pictures and the app's
version, and its task is made with it, at once, named by its result; the answer shows both as chips. Above the field stand two pills: Send to developers, a link that opens a GitHub issue filled in with the report (never
with the board) and labelled for its kind, and Improve it, which asks the agent for a design document in the same task. F2
behind the desktop gateway and its stand-in agent; the browser clock pinned to 2026-08-08. Nothing here opens a real issue or
sends mail: the links are read, not followed."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg
import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import F2_OWNER, UiSession
from tests.ui.report_support import ANSWER, FIELD, ITEM, drop, files
from tests.ui.test_agent_conversation import ui_agent  # noqa: F401  (the fixture)
from tests.ui.views import switch_view

DOC_CHIP = f"{ANSWER} [data-role='doc-chip']"
GOAL_CHIP = f"{ANSWER} [data-role='goal-chip']"
SEND = '[data-role="report-send"]'
IMPROVE = '[data-role="report-improve"]'
WORDS = "I dragged the card to Friday and it jumped back"
# What the person would like instead of what went wrong: the stand-in agent tells it is a request by "I'd like".
WISH = "I'd like the card to snap to Friday when I drop it near it"
# The task's name by its result, which the stand-in agent gives for each of the two wordings (tests/ui/fake_agent/claude).
RESULT = "A card dragged to Friday stays there"
WISHED = "A card dropped near Friday snaps to it"
ISSUES = "https://github.com/konstantinopolskii/verticals/issues/new"
KIND = "/__chat/report-kind"
FACTS = "/__report/facts"
# Private to the sample board: a goal's title, a document's words, a private goal. None may come out in a report.
PRIVATE = ["Draft the outline", "Dentist on Friday", "quarterly numbers"]

API_LOG = """\
2026-10-12T03:30:01+0400 level=WARNING logger=verticals.api.errors refused ValidationError: status=422 code=validation_error path=/api/goals/AB12CD34 detail=title 'Draft the outline' is taken
2026-10-12T03:30:02+0400 level=ERROR logger=verticals.api.errors unhandled exception on POST /api/goals
Traceback (most recent call last):
  File "/Users/anna/app/verticals/api/routes_goals.py", line 130, in post_goal
    goals.create(conn, title="Draft the outline")
psycopg.errors.NotNullViolation: null value in column "owner" violates not-null constraint
DETAIL:  Failing row contains (AB12CD34, Draft the outline, Dentist on Friday, quarterly numbers).
2026-10-12T03:30:03+0400 level=WARNING logger=verticals.mcp.tools call_tool update: refused ValidationError: unknown tag 'quarterly numbers'
"""


def _plant_the_logs(tmp_path: Path) -> None:
    (tmp_path / "desktop-state" / "api.log").write_text(API_LOG)
    (tmp_path / "desktop-state" / "app.log").write_text("[desktop] loading the sample board\nVerticals desktop is up\n")


def _say(page: Page, count: int, words: str = WORDS) -> None:
    drop(page, files(count))
    expect(page.locator(ITEM)).to_have_count(count)
    page.locator(FIELD).fill(words)
    page.keyboard.press("Enter")


def _reports(dsn: str) -> list[tuple]:
    """Every report: its path, title, text, and the goal that holds it (id, title, date column)."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        return conn.execute(
            "SELECT d.id, d.path, d.title, d.body, g.id, g.title, g.vertical FROM docs d"
            " JOIN goal_doc_links l ON l.doc_id = d.id AND l.owner = d.owner"
            " JOIN goals g ON g.id = l.goal_id AND g.owner = l.owner"
            " WHERE d.owner = %s AND (d.path LIKE 'reports/bugs/%%' OR d.path LIKE 'reports/requests/%%') ORDER BY d.created_at",
            (F2_OWNER,)).fetchall()


def _link(page: Page) -> tuple[str, dict[str, str]]:
    href = page.locator(SEND).get_attribute("href") or ""
    query = {key: values[0] for key, values in parse_qs(urlsplit(href).query, keep_blank_values=True).items()}
    return href, query


def _the_board_titles(page: Page) -> list[str]:
    return [t.strip() for t in page.locator(".goal-card__title-text").all_inner_texts() if len(t.strip()) >= 6]


def _asked(session: UiSession, route: str) -> list[str]:
    """The addresses the page fetched that end with `route`."""
    return [r["url"] for r in session.request_log if route in r["url"]]


def test_a_bug_and_its_task_come_at_once_with_the_logs(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    board = _the_board_titles(page)
    assert board
    _plant_the_logs(tmp_path)
    sent_before = sum(1 for r in session.request_log if r["url"].endswith("/__chat/send"))

    drop(page, files(2))
    expect(page.locator(ITEM)).to_have_count(2)
    page.locator(FIELD).fill(WORDS)
    with page.expect_request(lambda r: r.url.endswith(KIND)) as asked:
        page.keyboard.press("Enter")

    # The agent was asked one thing, which kind it is, with the words and the person's own settings, and nothing else.
    assert sorted(json.loads(asked.value.post_data or "{}")) == ["settings", "words"]
    assert json.loads(asked.value.post_data)["words"] == WORDS
    assert asked.value.response().json() == {"kind": "bug", "name": RESULT}
    # The report is the task's first document, made with it: one of each, linked, the task with no date (it waits in the Inbox).
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    expect(page.locator(GOAL_CHIP)).to_have_count(1)
    ((doc_id, path, title, body, goal_id, goal_title, vertical),) = _reports(session.backend.dsn)
    assert re.fullmatch(r"reports/bugs/\d{4}-\d\d-\d\d-\d{6}\.md", path), path
    assert re.fullmatch(r"Report — \d{1,2} \w+ \d{4}, \d\d:\d\d", title), title
    # The task is named by its result; the report keeps the person's words as they wrote them, first.
    assert goal_title == RESULT and vertical is None and body.startswith(WORDS)
    # The answer says what is in it, and shows both as chips: the document's name and the task's, where it is and when.
    expect(page.locator(ANSWER)).to_contain_text("Report made with 2 pictures and the last log lines.")
    expect(page.locator(f"{DOC_CHIP} .doc-chip__name")).to_have_text(title)
    expect(page.locator(f"{GOAL_CHIP} .goal-chip__name")).to_have_text(RESULT)
    expect(page.locator(f"{GOAL_CHIP} [data-role='goal-chip-when']")).to_have_text("Inbox · made just now")
    # The pictures have left the field, and no conversation was started: the agent only sorted and named.
    expect(page.locator(ITEM)).to_have_count(0)
    expect(page.locator(".circle-field")).to_have_attribute("data-state", "answer")
    assert sum(1 for r in session.request_log if r["url"].endswith("/__chat/send")) == sent_before
    assert _asked(session, FACTS) and not any(url.endswith("logs=0") for url in _asked(session, FACTS))

    # The document: their words first, then the pictures, the version, the logs.
    assert body.startswith(WORDS)
    assert len(re.findall(r"!\[Picture [12]\]\(data:image/jpeg;base64,[A-Za-z0-9+/=]+\)", body)) == 2
    assert len(body.encode()) < 512 * 1024
    assert re.search(r"^Verticals .+, .+$", body, re.M), "the version"
    assert "## Agent log\n`" in body and "gateway start pid=" in body
    assert "## App log\n`" in body
    assert "api: 2026-10-12T03:30:01+0400 WARNING refused ValidationError: status=422 code=validation_error path=/api/goals/{id}" in body
    assert "api: 2026-10-12T03:30:02+0400 ERROR unhandled exception on POST /api/goals (psycopg.errors.NotNullViolation · routes_goals.py:130 in post_goal)" in body
    assert "app: [desktop] loading the sample board" in body
    # Nothing of the board, and nothing a log quoted from it, is in the report.
    for word in [*PRIVATE, *board]:
        assert word not in body, word
    assert "/Users/" not in body

    # It waits in the Inbox, and the document is among the Documents.
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM goals WHERE owner = %s AND id = %s AND vertical IS NULL AND parent_id IS NULL",
                            (F2_OWNER, goal_id)).fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM docs WHERE owner = %s AND id = %s", (F2_OWNER, doc_id)).fetchone() == (1,)


def test_a_request_and_its_task_come_at_once_with_no_logs(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    board = _the_board_titles(page)
    _plant_the_logs(tmp_path)

    _say(page, 2, WISH)

    # The same two things come, in the requests' folder, and the answer says what is in it: the pictures, and no log lines.
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    expect(page.locator(GOAL_CHIP)).to_have_count(1)
    ((_, path, title, body, _, goal_title, vertical),) = _reports(session.backend.dsn)
    assert re.fullmatch(r"reports/requests/\d{4}-\d\d-\d\d-\d{6}\.md", path), path
    assert goal_title == WISHED and vertical is None
    expect(page.locator(ANSWER)).to_contain_text("Report made with 2 pictures.")
    expect(page.locator(ANSWER)).not_to_contain_text("log lines")
    expect(page.locator(f"{DOC_CHIP} .doc-chip__name")).to_have_text(title)
    # What they would like, the pictures and the version; not a line of any log, though the logs have lines. The gateway was
    # told to open none.
    assert body.startswith(WISH)
    assert len(re.findall(r"!\[Picture [12]\]\(data:image/jpeg;base64,", body)) == 2
    assert re.search(r"^Verticals .+, .+$", body, re.M)
    prose = "\n".join(line for line in body.split("\n") if not line.startswith("![Picture"))
    assert "## App log" not in body and "## Agent log" not in body and "log" not in prose.lower()
    assert "gateway start" not in body and "ValidationError" not in body and "loading the sample board" not in body
    assert _asked(session, FACTS) and all(url.endswith("?logs=0") for url in _asked(session, FACTS))
    for word in [*PRIVATE, *board]:
        assert word not in body, word


def test_while_the_report_is_made_the_line_turns_with_no_step_of_a_conversation(ui_agent: UiSession) -> None:  # noqa: F811
    """While the report is made the line turns, as while the agent works, in the field as wide as its pictures; the step of a
    conversation (AgentStep.vue, docs/design/morning-quality.md) stays out, since no conversation is working: the agent is
    only asked the kind and the name. `[slow]` keeps the stand-in agent at it for a second and a half."""
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")

    _say(page, 2, f"{WORDS} [slow]")

    expect(page.locator(".circle-field")).to_have_attribute("data-state", "working")
    expect(page.locator(".circle-field__pivot")).to_have_class(re.compile(r"\bis-turning\b"))
    assert page.locator('[data-role="agent-step"]').count() == 0, "no step: no conversation is working"
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)


def test_when_the_agent_cannot_tell_it_is_a_request(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    _plant_the_logs(tmp_path)
    words = "Something about Fridays [unclear]"

    _say(page, 1, words)

    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    ((_, path, _, body, _, goal_title, _),) = _reports(session.backend.dsn)
    # The agent's answer named neither, so the report is a request: its words, the picture and the version, and no logs.
    assert path.startswith("reports/requests/") and goal_title == words
    assert body.startswith(words) and "## App log" not in body and "## Agent log" not in body
    expect(page.locator(ANSWER)).to_contain_text("Report made with 1 picture.")
    # The gateway's log says what it was told and why, in words the report's own cleaner keeps.
    log = (tmp_path / "desktop-state" / "agent.log").read_text()
    assert re.search(r" report_kind result=request why=unclear named=no ms=\d+", log), log
    assert words not in log


def test_a_kind_with_no_name_leaves_the_task_with_the_persons_words(ui_agent: UiSession) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    words = f"{WORDS} [nameless]"

    drop(page, files(1))
    expect(page.locator(ITEM)).to_have_count(1)
    page.locator(FIELD).fill(words)
    with page.expect_request(lambda r: r.url.endswith(KIND)) as asked:
        page.keyboard.press("Enter")

    # The agent told the kind and no name, so it is a bug, with its logs, and the task is the person's words, as now.
    assert asked.value.response().json() == {"kind": "bug", "name": None}
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    ((_, path, _, body, _, goal_title, _),) = _reports(session.backend.dsn)
    assert path.startswith("reports/bugs/") and goal_title == words and body.startswith(words)
    expect(page.locator(f"{GOAL_CHIP} .goal-chip__name")).to_have_text(words)
    # The words are the task's title; with them written as they were, nothing says "result" where no one named one.
    assert RESULT not in body and RESULT not in goal_title


def test_the_page_of_a_report_chip_and_of_the_desk_shows_its_words_and_no_base64(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    """A report's pictures are data URLs in its text, and the page a document is drawn as cuts the text at a fixed length: the
    pictures, which stand between the words and the version, would fill it with base64 and push the rest out of it."""
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    _plant_the_logs(tmp_path)
    _say(page, 2)
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)

    # The chip's little page: the person's words, then what came after the pictures (the version), and not a character of data.
    chip = page.locator(f"{DOC_CHIP} .doc-page__text")
    expect(chip).to_contain_text(WORDS)
    expect(chip).to_contain_text("Verticals")
    assert "base64" not in chip.inner_text() and "data:image" not in chip.inner_text() and "/9j/" not in chip.inner_text()

    # The Documents desk draws the same page from the server's preview, cut the same way: the task's stack, with the report on top.
    switch_view(page, "docs")
    stack = page.locator(".docs-stack", has_text=RESULT)
    expect(stack).to_have_count(1)
    desk = stack.locator(".doc-page__text")
    expect(desk).to_contain_text(WORDS)
    expect(desk).to_contain_text("Verticals")
    assert "base64" not in desk.inner_text() and "data:image" not in desk.inner_text() and "/9j/" not in desk.inner_text()
    # And the document itself, opened, still has its pictures: the person's own view keeps them.
    stack.click()
    page.locator('[data-role="docs-open"] .docs-open__page').first.click()
    expect(page.locator('[data-role="doc-window"] img.goal-detail__body-image')).to_have_count(2)


def test_the_chips_open_what_they_name(ui_agent: UiSession) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    _say(page, 1)
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    page.locator(DOC_CHIP).click()
    expect(page.locator('.vt-window[data-window="doc"]')).to_have_count(1)
    # The document shows its words and its picture.
    expect(page.locator('[data-role="doc-window"]')).to_contain_text(WORDS)
    expect(page.locator('[data-role="doc-window"] img.goal-detail__body-image')).to_have_count(1)
    # The report in front keeps its two pills over the field.
    expect(page.locator(SEND)).to_be_visible()
    expect(page.locator(IMPROVE)).to_be_visible()


def test_a_report_works_with_no_gateway_and_says_nothing_it_does_not_know(ui_f2: UiSession) -> None:
    """The web build has no gateway: no version, no logs, no agent to tell the kind. The report and its task still come, as a
    request, and the issue can still be sent; Improve it needs an agent and is not offered."""
    session = ui_f2
    page = session.page
    page.wait_for_selector(".goal-card__row")
    _say(page, 1)
    expect(page.locator(DOC_CHIP)).to_have_count(1, timeout=15000)
    ((_, path, _, body, _, goal_title, _),) = _reports(session.backend.dsn)
    assert goal_title == WORDS and path.startswith("reports/requests/"), "nobody named it: the task takes the person's words"
    assert "Verticals " not in body and "## App log" not in body and "## Agent log" not in body
    assert not _asked(session, KIND), "no agent, so nobody was asked"
    expect(page.locator(SEND)).to_be_visible()
    expect(page.locator(IMPROVE)).to_have_count(0)


def test_send_to_developers_is_a_link_to_a_new_issue_with_the_report_and_nothing_else(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    board = _the_board_titles(page)
    _plant_the_logs(tmp_path)
    _say(page, 2)
    expect(page.locator(SEND)).to_be_visible(timeout=15000)

    href, query = _link(page)
    assert href.startswith(ISSUES + "?") and len(href) <= 6000
    # A bug carries the repository's own label for one; the title is the words, as they are.
    assert query["labels"] == "bug" and sorted(query) == ["body", "labels", "title"]
    # A link that opens in the browser, as a link does.
    assert page.locator(SEND).get_attribute("target") == "_blank"
    assert "noopener" in (page.locator(SEND).get_attribute("rel") or "")
    assert query["title"] == RESULT, "the issue is titled as its task is, by its result; the body starts with the person's words"
    text = query["body"]
    ((_, _, _, doc_body, _, _, _),) = _reports(session.backend.dsn)
    # What goes is the report's own text: its words, the version, the logs; the pictures are not in a link, and the issue says
    # how many there are and what to do.
    assert text.startswith(WORDS)
    assert re.search(r"^Verticals .+, .+$", text, re.M)
    assert "## Agent log\n`" in text and "gateway start pid=" in text and "path=/api/goals/{id}" in text
    assert "data:image" not in text and "base64" not in text and "![" not in text
    assert text.endswith("2 pictures: drag them into this box before you submit.")
    assert text.replace("\n\n2 pictures: drag them into this box before you submit.", "").strip() == "\n".join(
        line for line in doc_body.split("\n") if not line.startswith("![Picture")).replace("\n\n\n", "\n\n").strip()
    # Nothing from the board: no goal's title, no document's words, nothing a log quoted.
    for word in [*PRIVATE, *board]:
        assert word not in text and word not in unquote(href), word

    # Held with ⌥, the same pill is the email draft with the same text, addressed to no one (the repository publishes no address).
    page.keyboard.down("Alt")
    expect(page.locator(SEND)).to_have_text("Send by email")
    mail = page.locator(SEND).get_attribute("href") or ""
    page.keyboard.up("Alt")
    expect(page.locator(SEND)).to_have_text("Send to developers")
    assert mail.startswith("mailto:?subject=") and len(mail) <= 6000
    assert unquote(mail.split("&body=", 1)[1]) == text
    assert unquote(mail.split("?subject=", 1)[1].split("&", 1)[0]) == RESULT


def test_the_issue_for_a_request_reads_as_a_request_and_has_no_logs(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    board = _the_board_titles(page)
    _plant_the_logs(tmp_path)
    _say(page, 1, WISH)
    expect(page.locator(SEND)).to_be_visible(timeout=15000)

    href, query = _link(page)
    assert href.startswith(ISSUES + "?") and len(href) <= 6000
    # The repository's label for a request, and the words as the title; the text is the words, the version and the picture's line.
    assert query["labels"] == "enhancement" and sorted(query) == ["body", "labels", "title"]
    assert query["title"] == WISHED
    text = query["body"]
    assert text.startswith(WISH) and re.search(r"^Verticals .+, .+$", text, re.M)
    assert text.endswith("1 picture: drag it into this box before you submit.")
    assert "log" not in text.lower() and "gateway start" not in text and "ValidationError" not in text
    for word in [*PRIVATE, *board]:
        assert word not in text and word not in unquote(href), word
    # The email draft has the same text, and nothing of a log either.
    page.keyboard.down("Alt")
    expect(page.locator(SEND)).to_have_text("Send by email")
    mail = page.locator(SEND).get_attribute("href") or ""
    page.keyboard.up("Alt")
    assert unquote(mail.split("&body=", 1)[1]) == text


def test_a_click_on_send_to_developers_opens_the_issue_in_the_browser_and_nothing_is_sent(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    """The link is followed here only as far as the browser asks for it: the request is caught on its way and refused, so no
    page of GitHub is ever loaded and no issue is opened."""
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    asked: list[str] = []

    def refuse(route) -> None:
        asked.append(route.request.url)
        route.abort()

    page.context.route(re.compile(r"https://github\.com/.*"), refuse)
    _say(page, 1)
    expect(page.locator(SEND)).to_be_visible(timeout=15000)
    href, _ = _link(page)
    with page.context.expect_page() as popup:
        page.locator(SEND).click()
    popup.value.close()
    assert asked == [href], asked


def test_a_longer_report_gives_up_its_oldest_log_lines_first_to_fit_the_link(ui_agent: UiSession, tmp_path: Path) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    # An api.log whose lines are all kept, many of them, and words that leave the logs little room in a link.
    (tmp_path / "desktop-state" / "api.log").write_text("".join(
        f"2026-10-12T04:00:{n:02d}+0400 level=WARNING logger=verticals.api.errors refused ValidationError: "
        f"status=422 code=validation_error path=/api/goals/ID{n:04d}/schedule\n" for n in range(40)))
    words = ("I dragged the card to Friday and it jumped back. " * 80).strip()
    _say(page, 1, words)
    expect(page.locator(SEND)).to_be_visible(timeout=15000)
    href, query = _link(page)
    assert len(href) <= 6000, len(href)
    text = query["body"]
    ((_, _, _, doc_body, _, _, _),) = _reports(session.backend.dsn)
    # The document keeps every line it was given (the last 12 of the 40); the link drops the oldest ones and says how many.
    assert doc_body.count("/schedule`") == 12 and "04:00:28" in doc_body and "04:00:39" in doc_body
    cut = re.search(r"(\d+) older log lines? left out to fit this link\.", text)
    assert cut and 1 <= int(cut.group(1)) < 12, text[-400:]
    assert text.count("/schedule`") == 12 - int(cut.group(1))
    assert "04:00:39" in text and "04:00:28" not in text, "the newest stay, the oldest go"
    assert query["body"].startswith(words) and "The words were cut short" not in text


def test_words_too_long_for_a_link_are_cut_at_a_word_and_the_issue_says_so(ui_agent: UiSession) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    words = ("It jumped back. " * 700).strip()
    _say(page, 1, words)
    expect(page.locator(SEND)).to_be_visible(timeout=15000)
    href, query = _link(page)
    assert len(href) <= 6000, len(href)
    assert "The words were cut short to fit this link." in query["body"]
    assert query["body"].startswith("It jumped back.")
    assert len(query["title"]) <= 120 and query["title"].endswith("…")
    ((_, _, _, doc_body, _, goal_title, _),) = _reports(session.backend.dsn)
    assert doc_body.startswith(words), "the document keeps all of it"
    assert goal_title.endswith("…") and len(goal_title) <= 250


@pytest.mark.parametrize("words", [WORDS, WISH], ids=["a bug", "a request"])
def test_improve_it_adds_the_design_document_to_the_same_task(ui_agent: UiSession, words: str) -> None:  # noqa: F811
    session = ui_agent
    page = session.page
    page.wait_for_selector(".goal-card__row")
    _say(page, 1, words)
    expect(page.locator(IMPROVE)).to_be_visible(timeout=15000)
    ((doc_id, report_path, _, _, goal_id, goal_title, _),) = _reports(session.backend.dsn)

    with page.expect_request(lambda r: r.url.endswith("/__chat/send") and r.method == "POST") as sent:
        page.locator(IMPROVE).click()
    asked = json.loads(sent.value.post_data or "{}")
    # The agent is asked in the task's own conversation, with the report and the task named by their links.
    assert asked["text"].startswith("Improve it. [Report — ")
    assert f"(#doc/{doc_id})" in asked["text"] and f"(#goal/{goal_id})" in asked["text"]
    assert "Write the design document" in asked["text"] and "waiting for my comments" in asked["text"]
    assert asked["context"]["goal"] == {"id": goal_id, "title": goal_title}
    # While it works the pills stay away; the answer lands in the field with the design as a chip.
    expect(page.locator(IMPROVE)).to_have_count(0)
    expect(page.locator(ANSWER)).to_contain_text("Waiting for your comments", timeout=20000)
    expect(page.locator(f"{DOC_CHIP} .doc-chip__name")).to_contain_text("Design — ")
    # The design is in the same task, after the report: two documents, the report first.
    with psycopg.connect(session.backend.dsn, autocommit=True) as conn:
        linked = conn.execute(
            "SELECT d.path FROM goal_doc_links l JOIN docs d ON d.id = l.doc_id AND d.owner = l.owner"
            " WHERE l.owner = %s AND l.goal_id = %s ORDER BY d.created_at", (F2_OWNER, goal_id)).fetchall()
    assert [row[0] for row in linked] == [report_path, f"design/{goal_id}.md"]
    # The task has one conversation, which Discuss goes on with.
    conversations = page.request.get(f"{session.base_url}/__chat/goal?id={goal_id}").json()["conversations"]
    assert len(conversations) == 1
    # It is a design to comment on, not a report: the report's pills are not over the field for it.
    expect(page.locator(SEND)).to_have_count(0)
    page.locator(DOC_CHIP).click()
    expect(page.locator('.vt-window[data-window="doc"]')).to_have_count(1)
    expect(page.locator('[data-role="doc-window"]')).to_contain_text("Waiting for your comments")
    expect(page.locator(SEND)).to_have_count(0)
    expect(page.locator(IMPROVE)).to_have_count(0)
