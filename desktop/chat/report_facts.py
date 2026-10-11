"""What a report carries from the app itself (docs/design/bug-reports.md): its version, the Mac it runs on, and the last
lines of its logs, with every word of the person's board left out.

A report goes to a public issue once the person sends it, and a log is written by code that was never asked to keep the
board out of it: a database error quotes the row it refused, a refused write names what was refused. So an entry is kept
only when it has a shape this file knows, and only the parts of that shape that hold no words of the board: an event's name,
its flags and counts, a status code, the route a request took (never the goal or document it named), the kind of an error.
What a title, a document's words, a tool's answer or an error's own message could hold is left out, and an entry of a shape
nobody here knows is left out whole. The gateway's own log (`agent.log`, chat.py's `log_line`) is written without content to
begin with; it goes through the same filter, which also keeps another server's tool names (the person's own connections) and
the Mac's user name out. The number of entries left out is told with the lines, so a report never looks cleaner than it is.

Every function here is pure over the files it is given, so tests/static/test_report_facts.py plants private words in sample
logs and reads what comes out."""
from __future__ import annotations

import plistlib
import platform
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

APP_BUNDLE_ID = "app.verticals.desktop"
# Per file: the launcher's own notes are few; the API's warnings and errors are what a report is usually about.
APP_LOGS = (("app", "app.log", 8), ("api", "api.log", 12))
AGENT_LOG, AGENT_LINES = "agent.log", 20
# How far back a log is read for its last lines: a window of the file's end, then the rotated file behind it.
WINDOW = 128 * 1024
LINE_CHARS = 240

# An entry of a log as it comes out of a cleaner: its safe line, or None when it was left out.
Entries = list[str | None]


# ---------------------------------------------------------------- version

def app_version(app_root: Path) -> str:
    """The app's version: from the bundle's Info.plist when this runs inside Verticals.app (the repository's layout is
    mirrored in Contents/Resources, so the plist is one folder up), else the checkout's commit."""
    try:
        info = plistlib.loads((app_root.parent / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") == APP_BUNDLE_ID and info.get("CFBundleShortVersionString"):
            return str(info["CFBundleShortVersionString"])
    except (OSError, ValueError, plistlib.InvalidFileException):
        pass
    try:
        done = subprocess.run(["git", "-C", str(app_root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=3)
        commit = done.stdout.strip()
        if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", commit):
            return f"from source ({commit})"
    except (OSError, subprocess.SubprocessError):
        pass
    return "from source"


def system_line() -> str:
    """The Mac, as a bug report names it: "macOS 15.2 (arm64)"."""
    mac = platform.mac_ver()[0]
    return f"macOS {mac} ({platform.machine()})" if mac else f"{platform.system()} {platform.release()} ({platform.machine()})"


# ---------------------------------------------------------------- scrubbing and reading

_HOME = re.compile(r"(?:/Users|/home)/[^/\s\"']+")
_EMAIL = re.compile(r"[^\s@<>\"'()]+@[^\s@<>\"'()]+\.[A-Za-z]{2,}")
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{32,}")


def scrub(text: str, limit: int = LINE_CHARS) -> str:
    """One line made safe to show: the home folder (and with it the Mac's user name) becomes `~`, an address or a long token
    becomes a word saying what it was, control characters and runs of spaces go, and the line is cut at `limit`."""
    text = _HOME.sub("~", text)
    text = _EMAIL.sub("[email]", text)
    text = _TOKEN.sub("[token]", text)
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


_CUT = re.compile(r"[\"'`/\\@]")


def plain(text: str, limit: int) -> str:
    """The plain words at the start of a message of someone else's: cut where a quotation, a path or an address begins, so a
    title or a file's name that an error repeats never comes out, and told as cut with an ellipsis."""
    head = _CUT.split(text, 1)[0]
    return scrub(head, limit).rstrip() + (" …" if head != text else "")


def _tail(path: Path, window: int = WINDOW) -> list[str]:
    """The lines at the end of a file, oldest first, from its last `window` bytes. A line cut by the window is dropped."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - window))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[1:] if size > window and lines else lines


def _rotated(path: Path) -> list[Path]:
    """The file and the rotated ones behind it (`agent.log`, `agent.log.1`, `agent.log.2`), newest first."""
    return [path, *(path.with_name(f"{path.name}.{n}") for n in (1, 2))]


def shown(entries: Entries, count: int) -> tuple[list[str], int]:
    """The last `count` kept lines, oldest first, and how many entries were left out among the ones it looked through (an
    entry before the first line shown is not counted: the report does not show that far back)."""
    lines: list[str] = []
    left = 0
    for entry in reversed(entries):
        if len(lines) >= count:
            break
        if entry is None:
            left += 1
        else:
            lines.append(entry)
    return lines[::-1], left


# ---------------------------------------------------------------- the gateway's log (chat.py `log_line`)

_AGENT_LINE = re.compile(r"^(?P<at>\d{4}-\d\d-\d\dT[\d:]+[+-]\d{4}) (?P<kind>[a-z_]+)(?: (?P<rest>.*))?$")
_AGENT_KINDS = {"gateway", "send", "agent_start", "turn_start", "tool", "tool_error", "goal_bound", "permission",
                "permission_done", "done", "exit", "refused", "turn_failed_to_start"}
# `key=value` fields that hold flags, counts and names of kinds, never words.
_AGENT_FIELDS = {"provider", "permission", "morning", "chars", "mode", "queued", "session", "resume", "handoff", "model",
                 "effort", "name", "id", "tool", "value", "error", "ms", "code", "pid"}
_FREE_KINDS = {"refused", "turn_failed_to_start"}  # the gateway's own message, or an OS error, then `session=`


def clean_agent_line(line: str) -> str | None:
    """A line of agent.log made safe, or None when its shape is not one the gateway writes."""
    found = _AGENT_LINE.match(line.strip())
    if not found or found["kind"] not in _AGENT_KINDS:
        return None
    at, kind, rest = found["at"], found["kind"], found["rest"] or ""
    if kind in _FREE_KINDS:
        message, _, session = rest.rpartition(" session=")
        return f"{at} {kind} {plain(message or rest, 100)}" + (f" session={scrub(session, 16)}" if message and session else "")
    rest, _, detail = rest.partition(" detail=")
    parts = []
    for token in rest.split():
        key, equals, value = token.partition("=")
        if not equals:
            if re.fullmatch(r"[a-z_]{1,20}", token):
                parts.append(token)
            continue
        if key not in _AGENT_FIELDS:
            continue
        # Another server's tool is named `mcp__<server>__<tool>`: which servers the person connects is theirs to say.
        parts.append(f"{key}=[another server's tool]" if "__" in value else f"{key}={scrub(value, 40)}")
    out = f"{at} {kind}" + (f" {' '.join(parts)}" if parts else "")
    if detail:
        out += f" detail={plain(detail, 100)}"
    return out


def clean_agent_lines(lines: list[str]) -> Entries:
    return [clean_agent_line(line) for line in lines if line.strip()]


# ---------------------------------------------------------------- the server's logs (api.log, mcp.log) and the launcher's

_SERVER_HEAD = re.compile(r"^(?P<at>\d{4}-\d\d-\d\dT[\d:]+[+-]\d{4}) level=(?P<level>[A-Z]+) logger=(?P<logger>[\w.]+) (?P<msg>.*)$")
# Words of a route; any other segment of a path is the id of a goal, a document or a thread, and shows as {id}.
_ROUTE_WORDS = {"api", "goals", "docs", "desk", "history", "restore", "comments", "messages", "resolve", "schedule", "parent",
                "park", "due_ack", "board", "spans", "undated", "search", "events", "privacy", "tags", "morning", "mcp",
                "healthz"}


def _route(path: str) -> str:
    return "/" + "/".join(seg if seg in _ROUTE_WORDS else "{id}" for seg in path.split("?")[0].strip("/").split("/"))


# The messages the API and MCP server write (api/errors.py, api/app.py, mcp/tools.py, mcp/server.py), each with what of it
# holds no words. The rest of the line (a refused write's detail, a database error, an exception's text) is dropped.
_SERVER_MESSAGES: tuple[tuple[re.Pattern[str], Callable[[tuple[str, ...]], str]], ...] = (
    (re.compile(r"^(refused \w+): status=(\d+) code=([\w-]+) path=(\S+)"), lambda g: f"{g[0]}: status={g[1]} code={g[2]} path={_route(g[3])}"),
    (re.compile(r"^(unhandled exception on [A-Z]+) (\S+)"), lambda g: f"{g[0]} {_route(g[1])}"),
    (re.compile(r"^(unmapped VerticalError subtype \w+)"), lambda g: g[0]),
    (re.compile(r"^(database unavailable)"), lambda g: g[0]),
    (re.compile(r"^(healthz: database unavailable|healthz: schema_version missing)"), lambda g: g[0]),
    (re.compile(r"^call_tool (\w+): (unknown tool)"), lambda g: f"call_tool {g[0]}: {g[1]}"),
    (re.compile(r"^call_tool (\w+): owner=\S+ is_error=(True|False)"), lambda g: f"call_tool {g[0]}: is_error={g[1]}"),
    (re.compile(r"^call_tool (\w+): (refused \w+)"), lambda g: f"call_tool {g[0]}: {g[1]}"),
    (re.compile(r"^call_tool (\w+): (database unavailable)"), lambda g: f"call_tool {g[0]}: {g[1]}"),
    (re.compile(r"^call_tool (\w+): (unhandled \w+)"), lambda g: f"call_tool {g[0]}: {g[1]}"),
    (re.compile(r"^(verticals mcp server starting: transport=\w+)"), lambda g: g[0]),
)
_FRAME = re.compile(r'^\s+File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
_EXCEPTION = re.compile(r"^(?P<cls>[A-Za-z_][\w.]*(?:Error|Exception|Violation|Exit|Interrupt|Refused|Mismatch|Timeout|Failure))\b")


def _traceback(lines: list[str]) -> str | None:
    """What a traceback tells without quoting anything: the exception's class and where it was raised from in the app's own code
    (file name, line, function; the innermost frame when none is the app's). The frames' source lines and the exception's
    message are dropped."""
    frame = own = cls = None
    for line in lines:
        if found := _FRAME.match(line):
            frame = f"{Path(found['file']).name}:{found['line']} in {found['func']}"
            if re.search(r"/(?:verticals|desktop)/", found["file"]):
                own = frame
        elif found := _EXCEPTION.match(line):
            cls = found["cls"]
    frame = own or frame
    if not frame and not cls:
        return None
    return " · ".join(part for part in (cls, frame) if part)


def clean_server_lines(lines: list[str]) -> Entries:
    """The entries of a server log (api.log, mcp.log), oldest first: a record is its header line and the lines under it (a
    traceback). A record of a known message is kept as that message without its words, with its traceback told in a few
    words; any other record is left out."""
    out: Entries = []
    head: re.Match[str] | None = None
    more: list[str] = []

    def close() -> None:
        if head is None:
            return
        for pattern, shape in _SERVER_MESSAGES:
            if found := pattern.match(head["msg"]):
                trace = _traceback(more)
                out.append(scrub(f"{head['at']} {head['level']} {shape(found.groups())}") + (f" ({scrub(trace, 120)})" if trace else ""))
                return
        out.append(None)
    for line in lines:
        found = _SERVER_HEAD.match(line)
        if found:
            close()
            head, more = found, []
        elif head is not None and line.strip():
            more.append(line)
        elif line.strip():
            out.append(None)  # a line under no header: uvicorn's own, a banner, a stack from a thread
    close()
    return out


_LAUNCHER_KEEP = (
    re.compile(r"^\[desktop\] .+"),
    re.compile(r"^Verticals desktop is up$"),
    re.compile(r"^Exception in thread [\w\- ()]+:$"),
    re.compile(r"^\s*(UI|MCP \(streamable HTTP\)):\s+http://127\.0\.0\.1:\d+/\S*$"),
)
_TRACE_START = re.compile(r"^Traceback \(most recent call last\):")


def clean_launcher_lines(lines: list[str]) -> Entries:
    """The entries of the launcher's own notes (app.log), oldest first: its fixed lines kept with paths scrubbed, a traceback
    told by the exception's class and its innermost frame, everything else left out."""
    out: Entries = []
    trace: list[str] | None = None

    def close() -> None:
        nonlocal trace
        if trace is not None:
            told = _traceback(trace)
            out.append(scrub(f"traceback: {told}") if told else None)
        trace = None
    for line in lines:
        if _TRACE_START.match(line):
            close()
            trace = [line]
            continue
        if trace is not None:
            if not line.strip():
                close()
                continue
            if line[:1] in " \t" or _EXCEPTION.match(line) or line.startswith(("During handling", "The above exception")):
                trace.append(line)
                continue
            close()
        if any(pattern.match(line) for pattern in _LAUNCHER_KEEP):
            out.append(scrub(line))
        elif line.strip():
            out.append(None)
    close()
    return out


# ---------------------------------------------------------------- what the app collects for a report

def collect(state_dir: Path, app_root: Path) -> dict:
    """The facts for a report, as the page's `GET /__report/facts` returns them. Nothing here reads the board."""
    app: list[str] = []
    app_left = 0
    for label, name, count in APP_LOGS:
        cleaner = clean_launcher_lines if label == "app" else clean_server_lines
        lines, left = shown(cleaner(_tail(state_dir / name)), count)
        app += [f"{label}: {line}" for line in lines]
        app_left += left
    # The newest lines of agent.log, and of the rotated files behind it when it has just been rotated.
    entries: Entries = []
    for path in _rotated(state_dir / AGENT_LOG):
        entries = clean_agent_lines(_tail(path)) + entries
        if sum(entry is not None for entry in entries) >= AGENT_LINES:
            break
    agent, agent_left = shown(entries, AGENT_LINES)
    return {"version": app_version(app_root), "system": system_line(),
            "appLog": app, "appLeftOut": app_left, "agentLog": agent, "agentLeftOut": agent_left}
