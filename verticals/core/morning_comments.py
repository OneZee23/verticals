"""The owner's comments in a report land on their tasks, word for word, and are read back (docs/design/morning-quality.md).

The last cell of a report's row is the owner's: they write what they think of the task beside it. The next morning, before the
agent is asked for a new report, the server takes every such cell of the report before it and saves it as a comment on the row's
task. The words come from the cell and go to the comment as they are, by code, so no summary stands in for them; the thread is
read again from the database and the report's cell is cleared only when what was read back is what the cell held. A cell
that did not land stays as it is, with the reason, and the next morning tries it again; the same words are never saved twice.

The agent's own path to the same end is the morning-report skill's comment procedure (a report is also commented on after the
morning, and "Check again" hands those over); this is the part of it a script can do exactly.

IR-02: takes an open connection, never commits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import psycopg

from verticals.core import comments as core_comments
from verticals.core import docs as core_docs
from verticals.core import morning_report as report
from verticals.core.errors import NotFound, RevisionMismatch, ValidationError
from verticals.core.field_rules import validate_owner

# What the receipt in the "Next action" cell says once the comment is on the task.
RECEIPT = "Your comment is on the task."


@dataclass(frozen=True)
class Landed:
    """One comment saved on its task: the words as the cell held them, as read back from the thread."""

    goal_id: str
    title: str
    text: str
    thread_id: str
    reused: bool = False

    def as_dict(self) -> dict[str, object]:
        return {"goal_id": self.goal_id, "title": self.title, "text": self.text, "thread_id": self.thread_id}


@dataclass(frozen=True)
class Landing:
    landed: tuple[Landed, ...]
    failed: tuple[str, ...]  # one line each: which row and why its cell stayed
    cleared: bool  # the landed cells were cleared in the document


def _token(doc_id: str, goal_id: str, text: str) -> str:
    return f"report-comment:{doc_id}:{goal_id}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}"


def _existing(conn: psycopg.Connection, *, owner: str, goal_id: str, text: str) -> str | None:
    """The thread already holding exactly these words as its first message, if there is one: a retry, or the owner's own
    comment of the same words, is not saved a second time."""
    for thread in core_comments.list_for_goal(conn, owner=owner, goal_id=goal_id):
        if thread.messages and thread.messages[0].body == text:
            return thread.id
    return None


def _read_back(conn: psycopg.Connection, *, owner: str, goal_id: str, thread_id: str) -> str | None:
    for thread in core_comments.list_for_goal(conn, owner=owner, goal_id=goal_id):
        if thread.id == thread_id and thread.messages:
            return thread.messages[0].body
    return None


def land(conn: psycopg.Connection, *, owner: str, doc_id: str) -> Landing:
    """Save every comment in the report's rows on its task, read each back, and clear the cells that landed. Returns what
    landed (the words as read back) and what did not. Never raises for one bad row: that row stays and says why."""
    owner = validate_owner(owner)
    doc = core_docs.get(conn, owner=owner, id=doc_id)
    pending = [row for row in report.task_rows(doc.body) if row.comment]
    landed: list[Landed] = []
    failed: list[str] = []
    done_lines: dict[int, report.TaskRow] = {}
    for row in pending:
        what = f"{row.title or 'a row'}"
        if row.goal is None:
            failed.append(f"{what}: the row links no task, so its comment has nowhere to go")
            continue
        try:
            with conn.transaction():
                thread_id = _existing(conn, owner=owner, goal_id=row.goal, text=row.comment)
                reused = thread_id is not None
                if thread_id is None:
                    made = core_comments.create_thread(
                        conn, owner=owner, goal_id=row.goal, body=row.comment, author="agent",
                        client_token=_token(doc.id, row.goal, row.comment),
                    )
                    thread_id = made.thread.id
                    if not made.replayed:
                        core_comments.add_message(
                            conn, owner=owner, thread_id=thread_id, author="agent",
                            body=f"From your comment in {doc.title or doc.path}.",
                        )
                stored = _read_back(conn, owner=owner, goal_id=row.goal, thread_id=thread_id)
                if stored != row.comment:
                    raise ValidationError("the comment read back is not the comment written", field="body")
        except NotFound:
            failed.append(f"{what}: the task is gone")
            continue
        except (ValidationError, psycopg.Error) as exc:
            failed.append(f"{what}: {getattr(exc, 'message', exc)}")
            continue
        landed.append(Landed(goal_id=row.goal, title=row.title, text=stored, thread_id=thread_id, reused=reused))
        done_lines[row.line] = row
    cleared = _clear(conn, owner=owner, doc=doc, rows=done_lines) if done_lines else False
    return Landing(landed=tuple(landed), failed=tuple(failed), cleared=cleared)


def _edits(rows: dict[int, report.TaskRow]) -> dict[int, dict[int, str]]:
    edits: dict[int, dict[int, str]] = {}
    for line, row in rows.items():
        cells = {row.comment_col: ""}
        if row.next_col is not None and row.next_col < len(row.cells):
            said = row.cells[row.next_col]
            cells[row.next_col] = said if RECEIPT in said else f"{said} {RECEIPT}".strip()
        edits[line] = cells
    return edits


def _clear(conn: psycopg.Connection, *, owner: str, doc, rows: dict[int, report.TaskRow]) -> bool:
    """Write the document once with the landed cells empty and a receipt beside them. If the document moved on meanwhile (the
    owner is editing it), read it again and find the same rows by their words; give up quietly the second time: the comments are
    saved, and the next landing finds them there."""
    for attempt in range(2):
        body = report.rewrite_rows(doc.body, _edits(rows))
        try:
            with conn.transaction():
                core_docs.save(conn, owner=owner, id=doc.id, expected_revision=doc.revision, body=body)
            return True
        except ValidationError:
            return False  # a document the app will not take (too long): the comments are saved and the cells stay
        except RevisionMismatch:
            if attempt:
                return False
            doc = core_docs.get(conn, owner=owner, id=doc.id)
            wanted = {(row.goal, row.comment) for row in rows.values()}
            rows = {row.line: row for row in report.task_rows(doc.body) if (row.goal, row.comment) in wanted}
            if not rows:
                return False
    return False
