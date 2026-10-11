"""The desktop chat gateway's own rules for the turns the app starts (Inbox and Documents redesign, final page): the
morning report reads the owner's other tools but never changes anything there, and Replan reaches the agent with the
plans it was clicked on. Also what a Claude turn may reach under each permission mode."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _chat():
    spec = importlib.util.spec_from_file_location("verticals_desktop_chat", ROOT / "desktop" / "chat" / "chat.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_morning_turn_reads_other_tools_and_changes_nothing_there() -> None:
    chat = _chat()
    for tool in ("mcp__google-calendar__list-events", "mcp__telethon__fetch_history", "mcp__coin-prod__search_base",
                 "mcp__mail__searchThreads", "mcp__coin-account__get_transcript"):
        assert chat.reads_only(tool), tool
    for tool in ("mcp__telethon__send_reply", "mcp__telethon__mark_read", "mcp__google-calendar__create-event",
                 "mcp__google-calendar__delete-event", "mcp__telethon__react", "mcp__mail__createDraft"):
        assert not chat.reads_only(tool), tool


def test_the_morning_prompt_carries_the_skill_and_its_two_references() -> None:
    prompt = _chat().MORNING_PROMPT
    assert prompt.startswith("## This turn: the morning report")
    assert "reports/morning/<YYYY-MM-DD>.md" in prompt
    assert "## Reference: source reconciliation" in prompt and "## Reference: report contract" in prompt


def test_replan_reaches_the_agent_with_its_plans_and_how_to_write_the_document() -> None:
    chat = _chat()
    context = chat.format_context({"today": "2026-10-07", "replan": {
        "column": "year", "plans": [{"id": "SYNPLN01", "title": "Plan to sort"}, {"id": "SYNPLN02", "title": "Another"}]}})
    assert 'The owner clicked Replan on 2 plans that carried over into year: "Plan to sort" (id SYNPLN01)' in context
    assert "replan/<today>.md" in context and "Goal | Summary | Next step | Your comment" in context
    assert "Replan" not in chat.format_context({"today": "2026-10-07"})


class _Proc:
    def __init__(self, args, cwd, env, handle, exited):
        self.args, self.sent = args, []

    def send(self, message):
        self.sent.append(message)


class _Session:
    def __init__(self):
        self.asked = []

    def ask(self, agent, key, title, body, options, tool=None, tool_input=None):
        self.asked.append(title)
        self.write = (tool, tool_input)

    def emit(self, event):
        pass


def _claude(settings):
    """A Claude agent started the way a message starts it: its settings come through the gateway's own clean."""
    chat = _chat()
    chat.JsonProcess, chat.which = _Proc, lambda provider: "claude"
    session = _Session()
    host = types.SimpleNamespace(claude_mcp=Path("mcp.json"), workdir=Path("."))
    return chat.ClaudeAgent(host, session, chat.clean_settings(settings), None), session


def _system_prompt(agent) -> str:
    args = agent.proc.args
    return args[args.index("--append-system-prompt") + 1]


def test_an_ask_for_a_verticals_write_carries_the_write_so_the_card_can_say_what_changes() -> None:
    """Fix 6 (docs/design/agent-fixes.md): the app drew only the tool's name; the ask now carries the write as the agent
    called it, for web lib/askDetail.ts. A tool of another server or a shell command carries its own name and inputs too."""
    agent, session = _claude({"permission": "manual"})
    _tool(agent, "mcp__verticals__schedule", {"id": "SYN00001", "vertical": "day", "anchor_date": "2026-10-12"})
    assert session.write == ("schedule", {"id": "SYN00001", "vertical": "day", "anchor_date": "2026-10-12"})
    _tool(agent, "Bash", {"command": "ls"})
    assert session.write == ("Bash", {"command": "ls"})


def _tool(agent, name, tool_input=None):
    agent.handle({"type": "control_request", "request_id": f"r-{name}",
                  "request": {"subtype": "can_use_tool", "tool_name": name, "input": tool_input or {}}})


def _bash(agent):
    _tool(agent, "Bash", {"command": "ls"})


def _flag(agent, name):
    args = agent.proc.args
    return args[args.index(name) + 1]


def _decision(agent):
    return agent.proc.sent[-1]["response"]["response"]["behavior"]


def test_verticals_only_is_the_default_and_keeps_claude_to_the_board() -> None:
    assert _chat().clean_settings({})["permission"] == "board"
    agent, session = _claude({"permission": "board"})
    args = agent.proc.args
    assert args[args.index("--tools") + 1] == "" and "--strict-mcp-config" in args and "--add-dir" not in args
    assert args[args.index("--permission-mode") + 1] == "manual"
    _bash(agent)
    assert not session.asked and agent.proc.sent[-1]["response"]["response"]["behavior"] == "deny"


def test_another_mode_gives_claude_its_tools_and_asks_in_the_chat() -> None:
    agent, session = _claude({"permission": "manual"})
    args = agent.proc.args
    assert "--tools" not in args and "--strict-mcp-config" not in args
    assert args[args.index("--add-dir") + 1] == str(Path.home())
    assert "Claude Code's own tools" in args[args.index("--append-system-prompt") + 1]
    _bash(agent)
    assert session.asked == ["Allow Claude to use Bash?"]


def test_the_morning_turn_keeps_its_own_rules_in_any_mode() -> None:
    agent, session = _claude({"permission": "bypassPermissions", "sources": "connected"})
    args = agent.proc.args
    assert args[args.index("--tools") + 1] == "" and "--add-dir" not in args
    _bash(agent)
    assert not session.asked and agent.proc.sent[-1]["response"]["response"]["behavior"] == "deny"


def test_the_settings_clean_lets_the_morning_turns_sources_through() -> None:
    """Fix 1 (docs/design/agent-fixes.md): the clean dropped `sources`, so no morning turn ever had its own rules."""
    chat = _chat()
    assert chat.clean_settings({"sources": "connected"})["sources"] == "connected"
    for other in ("everything", "", None, True, ["connected"]):
        assert "sources" not in chat.clean_settings({"sources": other}), other
    assert "sources" not in chat.clean_settings({})


def test_the_morning_guide_reaches_the_agent_the_app_asks() -> None:
    """Fix 1: the settings the app sends for the morning ask (web lib/morning.ts) give that turn the morning guide, with
    the report contract; any other turn keeps the board prompt."""
    agent, _ = _claude({"permission": "manual", "sources": "connected"})
    prompt = _system_prompt(agent)
    assert "## This turn: the morning report" in prompt and "## Reference: report contract" in prompt
    assert "## This turn: the morning report" not in _system_prompt(_claude({"permission": "manual"})[0])


def test_codex_gets_the_morning_guide_in_the_same_turn() -> None:
    """Fix 1: the morning turn is asked of whichever agent is chosen, so Codex gets the guide too, under its own server name."""
    chat = _chat()
    morning = chat.codex_instructions(chat.clean_settings({"provider": "codex", "sources": "connected"}))
    assert "## This turn: the morning report" in morning and 'server "verticals_desktop"' in morning
    assert "## This turn: the morning report" not in chat.codex_instructions(chat.clean_settings({"provider": "codex"}))


def test_the_app_ships_every_skill_the_chat_reads() -> None:
    """Fix 1: the chat reads the operator skill and, for the morning turn, the morning-report skill from the folder it
    runs in; the app's bundle copies both, or the guide silently shrinks to the few lines of prompt-morning.md."""
    spec = importlib.util.spec_from_file_location("verticals_bundle", ROOT / "desktop" / "macos" / "bundle.py")
    assert spec and spec.loader
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    chat = _chat()
    for skill in (chat.SKILL, chat.MORNING_SKILL):
        assert skill.name in bundle.SKILLS, skill.name
        assert (ROOT / ".agents" / "skills" / skill.name / "SKILL.md").is_file()


def test_the_morning_turn_asks_first_whatever_mode_the_chat_is_in() -> None:
    """Fix 4: a chat set to "Bypass permissions" or "Auto" made its own decisions for every tool, so the morning turn,
    which nobody watches, could send or delete in the owner's other tools. In the morning turn the mode is always the
    ask-first one, and each tool of another server comes to the gateway to be judged."""
    for mode in ("manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions", "board"):
        agent, _ = _claude({"permission": mode, "sources": "connected"})
        assert _flag(agent, "--permission-mode") == "manual", mode
        assert _flag(agent, "--tools") == "" and "--add-dir" not in agent.proc.args, mode
    # Any other turn keeps the mode the owner chose.
    assert _flag(_claude({"permission": "bypassPermissions"})[0], "--permission-mode") == "bypassPermissions"


def test_the_morning_turn_reads_elsewhere_and_writes_in_verticals_only_what_the_report_needs() -> None:
    """Fix 4: outside Verticals only a tool named for reading runs; in Verticals the report's writes run by themselves
    and any other write is asked of the owner in the chat."""
    agent, session = _claude({"permission": "bypassPermissions", "sources": "connected"})
    allowed = _flag(agent, "--allowedTools").split(",")
    for tool in ("doc_create", "doc_save", "doc_link", "board", "doc_get"):
        assert f"mcp__verticals__{tool}" in allowed, tool
    # The report's task is the server's (core/morning.py): the agent neither makes it nor moves it without asking.
    for tool in ("create", "schedule", "delete", "update", "reparent", "doc_delete"):
        assert f"mcp__verticals__{tool}" not in allowed, tool
    _tool(agent, "mcp__google-calendar__list-events")
    assert _decision(agent) == "allow"
    for write in ("mcp__telethon__send_message", "mcp__telethon__mark_read", "mcp__google-calendar__delete-event"):
        _tool(agent, write)
        assert _decision(agent) == "deny", write
    assert not session.asked
    _tool(agent, "mcp__verticals__delete", {"id": "SYN00001"})
    assert session.asked == ["Allow Claude to use delete?"]


def test_the_morning_turn_of_codex_reads_whatever_mode_the_chat_is_in() -> None:
    """Fix 4, Codex: its sandbox is read-only in the morning turn (it can reach only Verticals, and its files not at all)."""
    chat = _chat()
    for mode in ("full-access", "auto-review", "default", "read-only"):
        settings = chat.clean_settings({"provider": "codex", "permission": mode, "sources": "connected"})
        assert chat.codex_mode(settings) == "read-only", mode
        assert chat.codex_policy(chat.codex_mode(settings), "/work")["sandboxPolicy"]["type"] == "readOnly", mode
    assert chat.codex_mode(chat.clean_settings({"provider": "codex", "permission": "full-access"})) == "full-access"
    assert chat.codex_mode(chat.clean_settings({"provider": "codex"})) == "auto-review"


def test_the_agents_instructions_agree_with_themselves() -> None:
    """Fix 5 (docs/design/agent-fixes.md): one length in every turn, goals by title and not by ID, and the board as it is."""
    prompt = _chat().PROMPT
    # One length: one or two short paragraphs, and a document for anything longer.
    assert "one or two short paragraphs" in prompt and "document" in prompt.split("one or two short paragraphs", 1)[1][:200]
    # Goals by title: nothing tells the agent to report IDs.
    assert "by title" in prompt and "exact IDs" not in prompt and "Report exact" not in prompt
    # Seven columns, not a ladder of five rungs.
    assert "Life → Year → Quarter → Week → Day" not in prompt
    for column in ("Life", "3 years", "Year", "Quarter", "Month", "Week", "Day", "Inbox"):
        assert column in prompt.split("The user talks to you", 1)[0], column


def test_the_text_the_owner_selected_reaches_the_agent_in_its_context() -> None:
    """Fix 5: the prompt promises "any text they selected", so the context carries it, cut at 2000 characters."""
    chat = _chat()
    context = chat.format_context({"today": "2026-10-11", "selection": "The second paragraph of the plan"})
    assert "Selected text: The second paragraph of the plan" in context
    assert len(chat.format_context({"today": "2026-10-11", "selection": "x" * 5000}).split("Selected text: ")[1]) == 2000
    assert "Selected text" not in chat.format_context({"today": "2026-10-11"})


SESSION = "5d2c3c3e-1b1a-4c8e-9e1f-0a6f3e3c9b01"


def test_the_gateway_keeps_a_log_of_the_agents_side_with_nothing_private_in_it(scratch_dir) -> None:
    """Fix 7 (docs/design/agent-fixes.md): what the agent was asked to be and did, in lines a bug report can carry, so it
    holds event kinds, tool names, flags, durations and exit details, never your words, the agent's, a tool's inputs or
    results, a title, an ID or the token."""
    chat = _chat()
    gateway = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok-secret-0451")
    try:
        session = gateway.session(SESSION)
        session.emit({"t": "user", "text": "private words from the owner", "provider": "claude"})
        session.emit({"t": "turn_start", "provider": "claude", "model": "model-x", "effort": "medium"})
        session.emit({"t": "tool", "id": "tool-1", "name": "schedule", "title": "schedule",
                      "input": {"id": "SYN00001", "title": "private title", "anchor_date": "2031-03-14"}})
        session.emit({"t": "tool_result", "id": "tool-1", "error": True, "summary": "no goal SYN00001 private title"})
        session.emit({"t": "text", "text": "private answer words"})
        session.emit({"t": "permission", "requestId": "r1", "title": "Allow Claude to use schedule?",
                      "body": "private body", "options": [], "tool": "schedule", "input": {"id": "SYN00001"}})
        session.emit({"t": "permission_done", "requestId": "r1", "value": "accept"})
        session.emit({"t": "done", "error": True, "detail": "API Error: overloaded", "ms": 1234, "at": 1.0})
        session.emit({"t": "exit", "code": 1, "detail": "claude: not logged in"})
    finally:
        gateway.shutdown()
    lines = (scratch_dir / "agent.log").read_text().splitlines()
    text = "\n".join(lines)
    assert any("turn_start" in line and "provider=claude" in line and "model=model-x" in line for line in lines), text
    assert any(line.split(" ", 1)[1].startswith("tool name=schedule") for line in lines) and any("tool_error" in line for line in lines), text
    assert any("permission tool=schedule" in line for line in lines) and any("permission_done value=accept" in line for line in lines)
    assert any("done error=True ms=1234" in line and "API Error: overloaded" in line for line in lines), text
    assert any("exit code=1" in line and "not logged in" in line for line in lines), text
    assert all(line[:4].isdigit() for line in lines), "every line starts with its time"
    for private in ("private words", "private answer words", "private title", "private body", "SYN00001", "tok-secret-0451",
                    "2031-03-14", str(Path.home()), str(scratch_dir)):
        assert private not in text, private


def test_the_log_rotates_and_stays_small(scratch_dir) -> None:
    chat = _chat()
    log = chat.open_log(scratch_dir, max_bytes=400, backups=2)
    for n in range(200):
        log.info("tool name=schedule number=%d", n)
    for handler in log.handlers:
        handler.close()
    names = sorted(path.name for path in scratch_dir.iterdir() if path.name.startswith("agent.log"))
    assert names == ["agent.log", "agent.log.1", "agent.log.2"]
    assert all(path.stat().st_size <= 400 + 80 for path in scratch_dir.iterdir() if path.name.startswith("agent.log"))
    assert "number=199" in (scratch_dir / "agent.log").read_text()  # the newest lines stay


def test_a_log_that_cannot_be_opened_stops_nothing(scratch_dir) -> None:
    """The log is for bug reports; it never decides whether the chat starts."""
    chat = _chat()
    (scratch_dir / "agent.log").mkdir()  # a place nothing can be written to
    gateway = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok")
    try:
        gateway.log.info("tool name=schedule")  # says nothing, and does not fail
        assert not gateway.log.handlers
        assert (scratch_dir / "chat-mcp.json").exists()  # the gateway started
    finally:
        gateway.shutdown()


def test_a_refused_message_is_in_the_log_with_its_reason(scratch_dir) -> None:
    """The reason a message never went (the CLI missing, an empty message) is exactly what a bug report needs."""
    chat = _chat()
    chat.which = lambda provider: None
    gateway = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok")
    try:
        for text in ("   ", "hello"):
            try:
                gateway.send(SESSION, text, {}, {"provider": "claude", "permission": "board"})
            except chat.ChatError:
                pass
    finally:
        gateway.shutdown()
    log = (scratch_dir / "agent.log").read_text()
    assert "refused" in log and "Empty message" in log and "Claude Code is not installed" in log
    assert "hello" not in log


def test_the_goal_a_create_result_names_is_read_from_its_words() -> None:
    """docs/design/agent-chips.md: the gateway reads the goal a conversation made from what the Verticals server's `create`
    answers ("Created 'Title' [ID]", then the steps made and a replay); tests/mcp/test_create.py pins those words."""
    chat = _chat()
    for words, goal in (
        ("Created 'Plan the review' [AB12CD34]", "AB12CD34"),
        ("Created 'Fix [the bug]' [SYN00001]", "SYN00001"),
        ('Created "It\'s a plan" [SYN00002] + 3 descendant(s)', "SYN00002"),
        ("Created 'Plan' [SYN00003] (replayed)", "SYN00003"),
        ("Created 'Plan' [SYN00004] + 2 descendant(s) (replayed)", "SYN00004"),
        ("  Created 'Plan' [SYN00005]\n", "SYN00005"),
        ('{"goal": {"id": "SYN00007", "title": "Plan", "children": 3}, "children": [], "replayed": false}', "SYN00007"),
        ('{"goal": {"id": "SYN00008", "title": "A plan that was cut at fifteen hundred charac', "SYN00008"),
    ):
        assert chat.made_goal(words) == goal, words
    for words in ("ok", "", None, "Created 'Plan'", "Updated 'Plan' [SYN00006]", "Created 'Plan' [SYN00006] and more",
                  '{"goals": [{"id": "SYN00006"}]}', '{"goal": {"title": "No id"}}'):
        assert chat.made_goal(words) is None, words


OTHER_SESSION = "6e3d4d4f-2c2b-4d9f-8f20-1b7a4f4d0c12"


def _made(session, call, goal, title="Plan the review", error=False, tool="create") -> None:
    """What a session sees when the agent calls a tool: the call, then its result in the server's words."""
    session.emit({"t": "tool", "id": call, "name": tool, "title": tool, "input": {"title": title}})
    session.emit({"t": "tool_result", "id": call, "error": error,
                  "summary": "The user declined this action." if error else f"Created {title!r} [{goal}]"})


def test_a_conversation_about_no_goal_becomes_the_conversation_of_the_first_goal_the_agent_makes(scratch_dir) -> None:
    """The conversation is that goal's from then on: the gateway's record says so (Discuss with agent asks it), the app is
    told with a `goal` event, and a second goal made in it, a declined create or another tool changes nothing."""
    chat = _chat()
    gateway = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok-secret-0451")
    try:
        session = gateway.session(SESSION)
        _made(session, "t0", "SYN00009", error=True)       # the owner declined it
        _made(session, "t1", "SYN00009", tool="schedule")  # not a create
        assert gateway.goal_conversations("SYN00009") == [] and not [e for _, e in session.events if e["t"] == "goal"]
        _made(session, "t2", "SYN00001", "Plan the review")
        _made(session, "t3", "SYN00002", "Another one")
        assert [e for _, e in session.events if e["t"] == "goal"] == [{"t": "goal", "id": "SYN00001", "title": "Plan the review"}]
        assert [c["session"] for c in gateway.goal_conversations("SYN00001")] == [SESSION]
        assert gateway.goal_conversations("SYN00002") == []
        assert gateway.goal_conversations("SYN00001")[0]["title"] == "Plan the review"

        # A conversation that already belongs to a goal (Discuss with agent began it) keeps that goal.
        gateway.update(OTHER_SESSION, goal={"id": "SYN00010", "title": "Opened with Discuss"})
        _made(gateway.session(OTHER_SESSION), "t4", "SYN00011")
        assert [c["session"] for c in gateway.goal_conversations("SYN00010")] == [OTHER_SESSION]
        assert gateway.goal_conversations("SYN00011") == []
    finally:
        gateway.shutdown()
    # The log says a goal was bound, and not which: no title, no ID.
    log = (scratch_dir / "agent.log").read_text()
    assert log.count("goal_bound") == 1
    for private in ("SYN00001", "SYN00002", "SYN00009", "SYN00010", "SYN00011", "Plan the review", "Another one", "tok-secret-0451"):
        assert private not in log, private


def test_a_goal_made_in_a_conversation_survives_the_gateway_starting_again(scratch_dir) -> None:
    chat = _chat()
    first = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok")
    try:
        _made(first.session(SESSION), "t1", "SYN00001")
    finally:
        first.shutdown()
    second = chat.Chat(scratch_dir, "http://127.0.0.1:9/mcp", "tok")
    try:
        assert [c["session"] for c in second.goal_conversations("SYN00001")] == [SESSION]
    finally:
        second.shutdown()


def test_the_agent_is_told_to_link_what_it_made_and_to_name_the_rest_by_title() -> None:
    """docs/design/agent-chips.md: the chips come from the links in the agent's words, so the agent links what it made or
    changed, each on a line of its own, and names any other goal by its title."""
    prompt = " ".join(_chat().PROMPT.split())
    assert "Link each goal and each document you made or changed in a turn, once, each on a line of its own after your words" in prompt
    assert "goals as [title](#goal/<id>), documents as [title](#doc/<id>)" in prompt
    assert "The app draws those lines as chips under your words" in prompt
    assert "Mention any other goal by its title, with no link" in prompt
    assert "Link board dates inside a sentence as [label](/h/YYYY-MM-DD)" in prompt
