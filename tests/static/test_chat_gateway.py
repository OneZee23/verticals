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

    def ask(self, agent, key, title, body, options):
        self.asked.append(title)

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
