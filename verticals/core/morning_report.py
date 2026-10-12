"""The morning report as a document (docs/design/morning-quality.md): the few places in it that code reads or writes.

The report is the agent's, written as one markdown document (`reports/morning/<day>.md`, desktop/chat/prompt-morning.md and the
morning-report skill say how). Four parts of it are read by code, because a miss in any of them is a number the owner should
never have to find by reading:

  * **The red block at the top,** a fenced block named `unread`: what could not be read, one line per source. The app draws a
    block with that name in red (`goal-detail__body-code[data-md-fence='unread']`).
  * **The check,** one paragraph under it (and, when something was not a pass, a short table): "Not checked yet", then the second
    agent's verdict. The gateway has the server write it (`core/morning_checks.py`), so the second agent only reads.
  * **The rows,** tables of tasks: Task | Purpose | Latest | Next action | Your comment. The first cell links the task as
    `[title](goal:<id>)`, a parent's in bold and a child's after a dash. The last cell is the owner's.
  * **The sources,** the last section: the time zone and one row for every source with its window and what became of its
    messages. The next morning starts each source where its window ended (`core/morning.py::cutoffs`), and a row whose counts do not
    add up is a message with no place.

Pure: no connection, no clock. A report that does not follow the shape is not refused here: every reader returns what it found
and why it found no more, and the server turns that into a failed check.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FOLDER = "reports/morning"
_PATH = re.compile(r"^reports/morning/(\d{4})-(\d{2})-(\d{2})\.md$")


def path_for(day: date) -> str:
    return f"{FOLDER}/{day.isoformat()}.md"


def day_of(path: str) -> date | None:
    """The day a report's path names, or None for any other path."""
    found = _PATH.match(path or "")
    if found is None:
        return None
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


# --- the ten checks --------------------------------------------------------------------------------------------------

PASS, FAIL, GAP = "pass", "fail", "gap"
RESULTS = (PASS, GAP, FAIL)  # worst last: a gap is never a pass, and a fail is worse than a gap

# Key, then the words the report shows for it, in the order of the checks. They are the owner's words and live in a file of their
# own (`morning_check_list.json`) rather than in this module's strings; the second agent answers by key
# (desktop/chat/prompt-check.md, which a test keeps in step with the list).
CHECKS: tuple[tuple[str, str], ...] = tuple(
    (item["key"], item["label"])
    for item in json.loads(Path(__file__).with_name("morning_check_list.json").read_text(encoding="utf-8"))
)
KEYS = tuple(key for key, _ in CHECKS)
LABEL = dict(CHECKS)

NOTE_LIMIT = 240


@dataclass(frozen=True)
class Outcome:
    """What one check found: pass, gap or fail, and one line saying why when it is not a pass."""

    result: str
    note: str = ""


def worse(a: Outcome, b: Outcome | None) -> Outcome:
    """The worse of two outcomes for one check; on a tie the first, so the second agent's own words stay."""
    if b is None or RESULTS.index(b.result) <= RESULTS.index(a.result):
        return a
    return b


def one_line(text: object, limit: int = NOTE_LIMIT) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


# --- markdown tables -------------------------------------------------------------------------------------------------

_DIVIDER = re.compile(r"^:?-{3,}:?$")
_FENCE_OPEN = re.compile(r"^```([^`]*)$")
_FENCE_CLOSE = re.compile(r"^[ \t]*```[ \t]*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_GOAL_LINK = re.compile(r"\]\(\s*goal:([^)\s]+)\s*\)")
_DOC_LINK = re.compile(r"\[([^\]]*)\]\(\s*(?:doc:([^)\s]+)|#doc/([A-Za-z0-9_-]+))\s*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def split_cells(line: str) -> list[str]:
    """A table row's cells as written (an escaped bar stays escaped), trimmed. The web reads a row the same way
    (`bodyMarkdown.ts::splitTableRow`), except that it drops the backslashes: `unescape` does that."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells, cell, escaped = [], "", False
    for ch in text:
        if escaped:
            cell += "\\" + ch
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "|":
            cells.append(cell.strip())
            cell = ""
        else:
            cell += ch
    cells.append((cell + ("\\" if escaped else "")).strip())
    return cells


def unescape(cell: str) -> str:
    """A cell as the owner reads it, and as the app saves it back: `\\x` is `x`."""
    return re.sub(r"\\(.)", r"\1", cell)


def escape(text: str) -> str:
    """Words into a cell: a bar is escaped and a line break is a space (the app's own serializer does the same)."""
    return " ".join(str(text).split()).replace("|", "\\|")


def plain(cell: str) -> str:
    """A cell's words with its links reduced to their labels and its emphasis marks taken off."""
    text = _LINK.sub(lambda m: m.group(1), unescape(cell))
    return text.replace("**", "").replace("*", "").strip()


def _fences(lines: Sequence[str]) -> list[tuple[int, int, str]]:
    """Every fenced block as (opening line, closing line, name). A fence with no closing line is not one."""
    out, at = [], 0
    while at < len(lines):
        opening = _FENCE_OPEN.match(lines[at])
        if opening:
            end = next((i for i in range(at + 1, len(lines)) if _FENCE_CLOSE.match(lines[i])), None)
            if end is not None:
                out.append((at, end, opening.group(1).strip()))
                at = end + 1
                continue
        at += 1
    return out


def _outside_fences(lines: Sequence[str]) -> set[int]:
    inside: set[int] = set()
    for start, end, _ in _fences(lines):
        inside.update(range(start, end + 1))
    return inside


@dataclass(frozen=True)
class Table:
    """A table in the document: where it is and its cells as written. `header` is the first line, `rows` the lines after the
    divider, each as (line index, cells)."""

    first: int
    header: tuple[str, ...]
    rows: tuple[tuple[int, tuple[str, ...]], ...]

    def column(self, *names: str, anywhere: bool = False) -> int | None:
        """The first column whose heading starts with any of `names` (case apart), or has one in it with `anywhere`."""
        for at, heading in enumerate(self.header):
            low = plain(heading).lower()
            if any((name in low) if anywhere else low.startswith(name) for name in names):
                return at
        return None


def tables(lines: Sequence[str], start: int = 0, stop: int | None = None) -> list[Table]:
    """Every table between two lines, outside fenced blocks."""
    stop = len(lines) if stop is None else stop
    skip = _outside_fences(lines)
    found, at = [], start
    while at < stop - 1:
        if at not in skip and "|" in lines[at] and (divider := split_cells(lines[at + 1])) and all(_DIVIDER.match(c) for c in divider):
            rows, i = [], at + 2
            while i < stop and lines[i].strip() and "|" in lines[i] and i not in skip:
                rows.append((i, tuple(split_cells(lines[i]))))
                i += 1
            found.append(Table(first=at, header=tuple(split_cells(lines[at])), rows=tuple(rows)))
            at = i
        else:
            at += 1
    return found


def with_cells(cells: Sequence[str]) -> str:
    """A row written again from its cells (each already escaped)."""
    return "| " + " | ".join(cells) + " |"


def section(lines: Sequence[str], name: str) -> tuple[int, int] | None:
    """The lines of the last section whose heading starts with `name` (case apart): from the line after the heading to the next
    heading of the same level or a higher one, or the end."""
    skip = _outside_fences(lines)
    found = None
    for at, line in enumerate(lines):
        match = _HEADING.match(line) if at not in skip else None
        if match and match.group(2).lower().startswith(name.lower()):
            level = len(match.group(1))
            end = len(lines)
            for i in range(at + 1, len(lines)):
                nxt = _HEADING.match(lines[i]) if i not in skip else None
                if nxt and len(nxt.group(1)) <= level:
                    end = i
                    break
            found = (at + 1, end)
    return found


# --- the red block ---------------------------------------------------------------------------------------------------


def unread(body: str) -> list[str] | None:
    """The lines of the first `unread` block, or None when the report has none: nothing was left unread."""
    lines = (body or "").split("\n")
    for start, end, name in _fences(lines):
        if name == "unread":
            return [line.strip() for line in lines[start + 1:end] if line.strip()]
    return None


def render_unread(lines: Sequence[str]) -> str:
    return "```unread\n" + "\n".join(one_line(line, 400) for line in lines) + "\n```"


# --- the sources section ---------------------------------------------------------------------------------------------

# The columns after Read are where the messages went (a task, the Inbox, done by newer news, put off by the owner, context, a
# gap: the skill names them). Code reads them by position and counts them: what was read is what was placed, whatever the
# columns are called.
_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("source", ("source",)), ("window", ("window",)), ("read", ("read", "messages", "items")),
)
_ZONE = re.compile(r"\btimes?\b[^.\n]*?\bin\s+([A-Za-z][A-Za-z_]*(?:/[A-Za-z0-9_+\-]+)+|UTC)\b", re.IGNORECASE)
_MOMENT = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")


@dataclass(frozen=True)
class SourceRow:
    """One source in the last section. `ref` is what its first cell links (a document's path or id), `name` its words, `counts`
    the numbers after Read, in the order of the columns (None for a cell that is not a number)."""

    name: str
    ref: str | None
    start: datetime | None
    end: datetime | None
    read: int | None
    counts: tuple[int | None, ...]
    problems: tuple[str, ...] = ()

    @property
    def placed(self) -> int | None:
        return None if not self.counts or any(v is None for v in self.counts) else sum(self.counts)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Sources:
    found: bool
    zone: str | None
    rows: tuple[SourceRow, ...]
    problems: tuple[str, ...] = field(default=())


def _count(cell: str) -> int | None:
    text = plain(cell).replace(" ", "").replace(" ", "").replace(",", "")
    return int(text) if re.fullmatch(r"\d{1,9}", text) else None


def _name_and_ref(cell: str) -> tuple[str, str | None]:
    link = _DOC_LINK.search(unescape(cell))
    return plain(cell), ((link.group(2) or link.group(3)) if link else None)


def parse_sources(body: str) -> Sources:
    """The last section, "Sources": its zone line and its table, one `SourceRow` for each row of it."""
    lines = (body or "").split("\n")
    span = section(lines, "Sources")
    if span is None:
        return Sources(found=False, zone=None, rows=(), problems=("The report has no Sources section.",))
    start, stop = span
    problems: list[str] = []
    zone_match = _ZONE.search("\n".join(lines[start:stop]))
    zone = zone_match.group(1) if zone_match else None
    tz = None
    if zone is None:
        problems.append("The Sources section does not say which time zone its times are in (\"Times in Europe/Berlin.\").")
    else:
        try:
            tz = ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            problems.append(f"The time zone {zone!r} is not one the app knows.")
    found = [t for t in tables(lines, start, stop) if t.column("source") is not None]
    if not found:
        return Sources(found=True, zone=zone, rows=(), problems=(*problems, "The Sources section has no table of sources."))
    table = found[0]
    at = {key: table.column(*names) for key, names in _COLUMNS}
    for key in ("source", "window", "read"):
        if at[key] is None:
            problems.append(f"The table of sources has no {key} column.")
    first_count = (at["read"] + 1) if at["read"] is not None else len(table.header)
    if first_count >= len(table.header):
        problems.append("The table of sources has no columns for where the messages went.")
    rows = []
    for _, cells in table.rows:
        def cell(key: str) -> str:
            i = at[key]
            return cells[i] if i is not None and i < len(cells) else ""
        name, ref = _name_and_ref(cell("source"))
        moments = _MOMENT.findall(cell("window"))
        start_at = end_at = None
        row_problems: list[str] = []
        if tz is not None and len(moments) == 2:
            try:
                start_at, end_at = (datetime.fromisoformat(f"{d} {t}").replace(tzinfo=tz) for d, t in moments)
            except ValueError:
                row_problems.append("a window time that is not a time")
        elif cell("window").strip(" -–—") and len(moments) != 2:
            row_problems.append("a window that is not two times (2026-10-11 18:40 – 2026-10-12 06:57)")
        counts = tuple(_count(cells[i]) if i < len(cells) else None for i in range(first_count, len(table.header)))
        rows.append(SourceRow(name=name, ref=ref, start=start_at, end=end_at, read=_count(cell("read")), counts=counts,
                              problems=tuple(row_problems)))
    return Sources(found=True, zone=zone, rows=tuple(rows), problems=tuple(problems))


# --- the check -------------------------------------------------------------------------------------------------------

PENDING = "Not checked yet: a second agent is reading it against the sources."
_CHECK_LINE = re.compile(r"^(Not checked|Checked against the sources)\b")
_CHECK_HEAD = ("Check", "Result", "What it found")


def render_unchecked(reason: str = "") -> str:
    """The report without a verdict because the check did not happen: it says why, in the place the verdict would be."""
    return "Not checked: " + (one_line(reason) if reason else "the second agent did not finish.")


def render_verdict(outcomes: Mapping[str, Outcome], fixed: Mapping[str, str] | Collection[str] = ()) -> str:
    """The second agent's verdict as the report shows it: a line that counts, and under it a row for each check that is not
    a pass, or that failed first and was fixed (`fixed` maps its key to what it found at first). Passes are only counted: a
    table of ten passes is ten words nobody needs."""
    keys = [key for key in KEYS if key in outcomes]
    passed = sum(1 for key in keys if outcomes[key].result == PASS)
    gaps = sum(1 for key in keys if outcomes[key].result == GAP)
    failed = sum(1 for key in keys if outcomes[key].result == FAIL)
    head = "Checked against the sources by a second agent: "
    if passed == len(keys):
        head += f"all {len(keys)} passed."
    else:
        parts = [f"{passed} of {len(keys)} passed"]
        if gaps:
            parts.append(f"{gaps} gap" + ("s" if gaps != 1 else ""))
        if failed:
            parts.append(f"{failed} failed")
        head += ", ".join(parts) + "."
    first = fixed if isinstance(fixed, Mapping) else dict.fromkeys(fixed, "")
    rows = []
    for key in keys:
        if outcomes[key].result != PASS:
            rows.append((key, outcomes[key].result, outcomes[key].note))
        elif key in first:
            rows.append((key, "fixed", f"Failed at first: {first[key]}" if first[key] else "Failed at first."))
    if not rows:
        return head
    table = [f"| {' | '.join(_CHECK_HEAD)} |", "| --- | --- | --- |"]
    for key, result, note in rows:
        word = {FAIL: "Failed", GAP: "Gap", "fixed": "Fixed"}[result]
        table.append(f"| {LABEL[key]} | {word} | {escape(one_line(note))} |")
    return head + "\n\n" + "\n".join(table)


def _check_span(lines: Sequence[str]) -> tuple[int, int] | None:
    skip = _outside_fences(lines)
    for at, line in enumerate(lines):
        if at in skip or not _CHECK_LINE.match(line):
            continue
        end = at + 1
        look = end
        while look < len(lines) and not lines[look].strip():
            look += 1
        if look + 1 < len(lines) and lines[look].lstrip().startswith("|") and tuple(plain(c) for c in split_cells(lines[look])) == _CHECK_HEAD:
            end = look + 2
            while end < len(lines) and lines[end].strip() and "|" in lines[end]:
                end += 1
        return at, end
    return None


def check_state(body: str) -> str | None:
    """"pending", "unchecked" or "checked" by the line under the red block, or None when the report has no such line."""
    lines = (body or "").split("\n")
    span = _check_span(lines)
    if span is None:
        return None
    first = lines[span[0]]
    return "checked" if first.startswith("Checked") else "pending" if first.startswith("Not checked yet") else "unchecked"


def set_check(body: str, block: str) -> str:
    """The report with its check block replaced by `block`, or put in under the red block (and at the very top when there is
    none) when the report has none. Nothing else in the document is touched."""
    lines = (body or "").split("\n")
    span = _check_span(lines)
    new = block.split("\n")
    if span is not None:
        after = lines[span[1]:]
        out = [*lines[:span[0]], *new, *([""] if after and after[0].strip() else []), *after]
    else:
        fences = _fences(lines)
        top = next(((s, e) for s, e, name in fences if name == "unread" and not "".join(lines[:s]).strip()), None)
        at = top[1] + 1 if top else 0
        # A blank line between the red block and the check, and one after the check.
        tail = lines[at:]
        while tail and not tail[0].strip():
            tail = tail[1:]
        out = [*lines[:at], *([""] if at else []), *new, "", *tail]
    return "\n".join(out)


# --- the rows --------------------------------------------------------------------------------------------------------

_CHILD = re.compile(r"^(?:–|—|↳)\s+")


@dataclass(frozen=True)
class TaskRow:
    """A task in a table of rows. `goal` is the id its first cell links, `comment` the owner's words in the last cell
    (the app's way of reading them, empty when the cell is empty or the placeholder `[]`)."""

    line: int
    goal: str | None
    title: str
    bold: bool
    child: bool
    cells: tuple[str, ...]
    comment_col: int
    next_col: int | None
    comment: str


def _is_rows(table: Table) -> bool:
    last = plain(table.header[-1]).lower() if table.header else ""
    return table.column("task", "goal") == 0 and "comment" in last


def task_rows(body: str) -> list[TaskRow]:
    """Every row of every table of tasks, in the order of the document. A table of tasks starts with Task (or Goal) and ends
    with the owner's comment cell."""
    lines = (body or "").split("\n")
    out = []
    for table in tables(lines):
        if not _is_rows(table):
            continue
        comment_col = len(table.header) - 1
        next_col = table.column("next", anywhere=True)
        for line, cells in table.rows:
            first = cells[0] if cells else ""
            goal = _GOAL_LINK.search(first)
            words = unescape(first).strip()
            out.append(TaskRow(
                line=line, goal=goal.group(1) if goal else None, title=_CHILD.sub("", plain(first)).strip(),
                bold=words.startswith("**") and words.endswith("**"), child=bool(_CHILD.match(words)), cells=cells,
                comment_col=comment_col, next_col=next_col,
                comment="" if comment_col >= len(cells) or plain(cells[comment_col]) in ("", "[]") else unescape(cells[comment_col]).strip(),
            ))
    return out


def closed_goals(body: str) -> list[str]:
    """The goals the "Closed since the last report" section links."""
    lines = (body or "").split("\n")
    span = section(lines, "Closed since")
    return [] if span is None else _GOAL_LINK.findall("\n".join(lines[span[0]:span[1]]))


def rewrite_rows(body: str, edits: Mapping[int, Mapping[int, str]]) -> str:
    """The report with some cells of some rows written again: `edits[line][column]` is the new cell (already escaped). Every other
    cell, row and line stays as it was."""
    lines = (body or "").split("\n")
    for line, cells in edits.items():
        row = split_cells(lines[line])
        for column, text in cells.items():
            while len(row) <= column:
                row.append("")
            row[column] = text
        lines[line] = with_cells(row)
    return "\n".join(lines)
