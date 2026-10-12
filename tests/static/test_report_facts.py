"""What a report carries from the app itself (docs/design/bug-reports.md, desktop/chat/report_facts.py): its version and the
last lines of its logs. The report goes to a public issue, so these tests plant a goal's title, a document's words, a
private goal, the Mac's user name and another server's tool in sample logs, and read what comes out: none of them, and the
shape of what happened. Sample data only: the names below are made up for these tests."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Words that must never come out: a goal's title, a private goal's, a document's words, the Mac's user name, a connected tool.
PRIVATE = ["Quarterly plan for Acme", "acme-secret", "Dentist on Friday", "salary review", "anna", "telethon",
           "Failing row contains", "owner@example.com"]


def _facts():
    spec = importlib.util.spec_from_file_location("verticals_report_facts", ROOT / "desktop" / "chat" / "report_facts.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AGENT_LOG = """\
2026-10-12T03:21:07+0400 gateway start pid=4242
2026-10-12T03:21:09+0400 send provider=claude permission=board morning=False chars=57 mode=send queued=False session=1a2b3c4d
2026-10-12T03:21:09+0400 agent_start provider=claude resume=False handoff=0 session=1a2b3c4d
2026-10-12T03:21:10+0400 turn_start provider=claude model=claude-sonnet-5-5 effort=medium session=1a2b3c4d
2026-10-12T03:21:11+0400 tool name=update session=1a2b3c4d
2026-10-12T03:21:11+0400 tool name=mcp__telethon__send_message session=1a2b3c4d
2026-10-12T03:21:12+0400 tool_error id=toolu_01ABCDEFGHIJKLMNOPQRSTUV session=1a2b3c4d
2026-10-12T03:21:12+0400 permission tool=mcp__telethon__send_message session=1a2b3c4d
2026-10-12T03:21:13+0400 done error=True ms=3200 session=1a2b3c4d detail=API Error: 529 overloaded for "Quarterly plan for Acme" at /Users/anna/Documents/salary review.md, write to owner@example.com
2026-10-12T03:21:14+0400 refused Empty message session=1a2b3c4d
2026-10-12T03:21:14+0400 turn_failed_to_start [Errno 2] No such file or directory: '/Users/anna/.local/bin/claude' session=1a2b3c4d
2026-10-12T03:21:15+0400 title=Dentist on Friday unknown_shape something else
Quarterly plan for Acme and its private goal Dentist on Friday, not a log line at all
2026-10-12T03:21:16+0400 exit code=1 session=1a2b3c4d detail=stack: Error at /Users/anna/app/claude.js:12
"""

API_LOG = """\
2026-10-12T03:30:01+0400 level=WARNING logger=verticals.api.errors refused ValidationError: status=422 code=validation_error path=/api/goals/AB12CD34 detail=title 'Quarterly plan for Acme' is taken
2026-10-12T03:30:02+0400 level=ERROR logger=verticals.api.errors unhandled exception on POST /api/goals
Traceback (most recent call last):
  File "/Users/anna/app/verticals/api/routes_goals.py", line 130, in post_goal
    goals.create(conn, title="Quarterly plan for Acme")
  File "/Users/anna/app/.venv/lib/python3.12/site-packages/psycopg/cursor.py", line 97, in execute
    raise ex.with_traceback(None)
psycopg.errors.NotNullViolation: null value in column "owner" of relation "goals" violates not-null constraint
DETAIL:  Failing row contains (AB12CD34, Quarterly plan for Acme, Dentist on Friday, acme-secret).
2026-10-12T03:30:03+0400 level=WARNING logger=verticals.mcp.tools call_tool update: refused ValidationError: unknown tag 'acme-secret'
2026-10-12T03:30:04+0400 level=INFO logger=verticals.mcp.tools call_tool goal: owner=anna is_error=False
2026-10-12T03:30:05+0400 level=WARNING logger=verticals.api.errors refused NotFound: status=404 code=not_found path=/api/docs/reports/salary-review.md/history detail=no doc salary review
2026-10-12T03:30:06+0400 level=WARNING logger=somebody.else a message nobody here knows about Quarterly plan for Acme
INFO:     127.0.0.1:50000 - "GET /api/search?q=Quarterly%20plan HTTP/1.1" 200 OK
"""

APP_LOG = """\
[desktop] loading the sample board
Verticals desktop is up
  UI:  http://127.0.0.1:8288/
  MCP (streamable HTTP): http://127.0.0.1:8281/mcp
  Private JSON config: /Users/anna/Library/Application Support/Verticals/mcp.json
  Authentication stays in that owner-only file; do not share it.
Ctrl-C stops everything; data stays in /Users/anna/Library/Application Support/Verticals.
Exception in thread Thread-3 (serve):
Traceback (most recent call last):
  File "/Applications/Verticals.app/Contents/Resources/desktop/chat/chat.py", line 640, in start_turn
    agent = AGENT_CLASSES[provider](self, s, settings, resume)
KeyError: 'Quarterly plan for Acme'
[desktop] stopping
"""


def _state(tmp: Path) -> Path:
    state = tmp / "state"
    state.mkdir()
    (state / "agent.log").write_text(AGENT_LOG)
    (state / "api.log").write_text(API_LOG)
    (state / "app.log").write_text(APP_LOG)
    return state


def _nothing_private(text: str) -> None:
    for word in PRIVATE:
        assert not re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text, re.IGNORECASE), f"{word!r} came out: {text}"


def test_nothing_of_the_board_or_the_mac_comes_out_of_any_log(scratch_dir: Path) -> None:
    facts = _facts().collect(_state(scratch_dir), ROOT)
    _nothing_private(json.dumps(facts, ensure_ascii=False))


def test_the_agents_log_keeps_what_happened_and_drops_what_was_said(scratch_dir: Path) -> None:
    facts = _facts().collect(_state(scratch_dir), ROOT)
    lines = facts["agentLog"]
    assert "2026-10-12T03:21:09+0400 send provider=claude permission=board morning=False chars=57 mode=send queued=False session=1a2b3c4d" in lines
    assert "2026-10-12T03:21:11+0400 tool name=update session=1a2b3c4d" in lines
    # Another server's tool is the person's own connection: its name is not told.
    assert "2026-10-12T03:21:11+0400 tool name=[another server's tool] session=1a2b3c4d" in lines
    # An error's own words stop where a quotation, a path or an address begins: a title or a file's name it repeats is not told.
    assert "2026-10-12T03:21:13+0400 done error=True ms=3200 session=1a2b3c4d detail=API Error: 529 overloaded for …" in lines
    assert "2026-10-12T03:21:16+0400 exit code=1 session=1a2b3c4d detail=stack: Error at …" in lines
    # A message of the gateway's own is kept; an OS error loses its path, and with it the Mac's user name.
    assert "2026-10-12T03:21:14+0400 refused Empty message session=1a2b3c4d" in lines
    assert "2026-10-12T03:21:14+0400 turn_failed_to_start [Errno 2] No such file or directory: … session=1a2b3c4d" in lines
    # A shape the gateway never writes is left out, and so is a line that is no log line: two entries, told.
    assert not any("unknown_shape" in line for line in lines)
    assert facts["agentLeftOut"] == 2


def test_the_servers_log_keeps_the_route_and_the_kind_of_error_and_nothing_a_database_quoted(scratch_dir: Path) -> None:
    facts = _facts().collect(_state(scratch_dir), ROOT)
    lines = [line for line in facts["appLog"] if line.startswith("api: ")]
    assert "api: 2026-10-12T03:30:01+0400 WARNING refused ValidationError: status=422 code=validation_error path=/api/goals/{id}" in lines
    # The route is told, never the goal or document it named; a path with a document's name in it shows as ids too.
    assert "api: 2026-10-12T03:30:05+0400 WARNING refused NotFound: status=404 code=not_found path=/api/docs/{id}/{id}/history" in lines
    crash = next(line for line in lines if "unhandled exception" in line)
    assert crash == ("api: 2026-10-12T03:30:02+0400 ERROR unhandled exception on POST /api/goals "
                     "(psycopg.errors.NotNullViolation · routes_goals.py:130 in post_goal)")
    assert "api: 2026-10-12T03:30:03+0400 WARNING call_tool update: refused ValidationError" in lines
    assert "api: 2026-10-12T03:30:04+0400 INFO call_tool goal: is_error=False" in lines
    # A message nobody here knows is left out, whatever logger wrote it.
    assert not any("somebody" in line or "nobody" in line for line in lines)
    assert facts["appLeftOut"] >= 1


def test_the_launchers_log_keeps_its_own_notes_and_a_traceback_told_without_its_words(scratch_dir: Path) -> None:
    facts = _facts().collect(_state(scratch_dir), ROOT)
    lines = [line for line in facts["appLog"] if line.startswith("app: ")]
    assert lines == [
        "app: [desktop] loading the sample board",
        "app: Verticals desktop is up",
        "app: UI: http://127.0.0.1:8288/",
        "app: MCP (streamable HTTP): http://127.0.0.1:8281/mcp",
        "app: Exception in thread Thread-3 (serve):",
        "app: traceback: KeyError · chat.py:640 in start_turn",
        "app: [desktop] stopping",
    ]


def test_each_log_shows_its_last_lines_and_no_more(scratch_dir: Path) -> None:
    state = scratch_dir / "long"
    state.mkdir()
    (state / "agent.log").write_text("".join(
        f"2026-10-12T03:{n // 60:02d}:{n % 60:02d}+0400 tool name=update session=1a2b3c4d\n" for n in range(300)))
    facts = _facts().collect(state, ROOT)
    assert len(facts["agentLog"]) == 20
    assert facts["agentLog"][-1].startswith("2026-10-12T03:04:59+0400") and facts["agentLog"][0].startswith("2026-10-12T03:04:40+0400")
    assert facts["appLog"] == [] and facts["appLeftOut"] == 0 and facts["agentLeftOut"] == 0


def test_a_rotated_agent_log_fills_up_what_a_fresh_one_lacks(scratch_dir: Path) -> None:
    state = scratch_dir / "rotated"
    state.mkdir()
    (state / "agent.log.1").write_text("".join(f"2026-10-11T22:00:{n:02d}+0400 tool name=goal session=aaaaaaaa\n" for n in range(30)))
    (state / "agent.log").write_text("".join(f"2026-10-12T03:00:{n:02d}+0400 tool name=board session=bbbbbbbb\n" for n in range(5)))
    lines = _facts().collect(state, ROOT)["agentLog"]
    assert len(lines) == 20 and lines[-1].endswith("name=board session=bbbbbbbb")
    assert sum("name=board" in line for line in lines) == 5 and sum("name=goal" in line for line in lines) == 15


def test_no_log_at_all_is_an_empty_list_not_an_error(scratch_dir: Path) -> None:
    facts = _facts().collect(scratch_dir / "nowhere", ROOT)
    assert facts["appLog"] == [] and facts["agentLog"] == []
    assert facts["version"] and facts["system"]


def test_a_request_takes_no_log_at_all(scratch_dir: Path) -> None:
    # A request (docs/design/bug-reports.md) carries the version and the Mac and no log: none is opened, whatever it holds.
    state = _state(scratch_dir)
    facts = _facts().collect(state, ROOT, logs=False)
    assert facts["appLog"] == [] and facts["agentLog"] == [] and facts["appLeftOut"] == 0 and facts["agentLeftOut"] == 0
    assert facts["version"] and facts["system"]
    assert _facts().collect(state, ROOT)["agentLog"], "the same state does have lines when logs are asked for"


def test_a_log_is_read_from_its_end_only(scratch_dir: Path) -> None:
    """A log can be megabytes: only the last window of it is read, and the line the window cuts is dropped."""
    facts = _facts()
    path = scratch_dir / "agent.log"
    path.write_text("x" * 50 + "\n" + "".join(f"2026-10-12T03:00:{n % 60:02d}+0400 tool name=goal session=cccccccc\n" for n in range(40)))
    lines = facts._tail(path, window=300)
    assert 3 <= len(lines) <= 5 and all(line.startswith("2026-10-12T03:") for line in lines)
    assert facts._tail(scratch_dir / "missing.log") == []


def test_the_version_is_the_bundles_when_it_runs_in_the_app(scratch_dir: Path) -> None:
    facts = _facts()
    contents = scratch_dir / "Verticals.app" / "Contents"
    (contents / "Resources").mkdir(parents=True)
    plist = {"CFBundleIdentifier": "app.verticals.desktop", "CFBundleShortVersionString": "0.4", "CFBundleVersion": "0.4"}
    (contents / "Info.plist").write_bytes(plistlib.dumps(plist))
    assert facts.app_version(contents / "Resources") == "0.4"
    # Another app's plist next to the code is not the app's version.
    (contents / "Info.plist").write_bytes(plistlib.dumps({**plist, "CFBundleIdentifier": "com.example.other"}))
    assert facts.app_version(contents / "Resources").startswith("from source")
    # From a checkout the commit says which code it is.
    assert facts.app_version(ROOT).startswith("from source")


def test_scrub_masks_the_users_folder_addresses_and_long_tokens(scratch_dir: Path) -> None:
    scrub = _facts().scrub
    assert scrub("/Users/anna/Library/x /home/bob/y") == "~/Library/x ~/y"
    assert scrub("mail anna.k@example.com now") == "mail [email] now"
    assert scrub("token " + "a1" * 20) == "token [token]"
    assert scrub("a\x00b\tc  d") == "a b c d"
    assert len(scrub("word " * 200)) == 240 and scrub("word " * 200).endswith("…")
