"""Writing a source document (docs/design/sources.md): what the agent's tool does to the document, in two steps so the
check can be run between them without a lock held.

`prepare` reads the document (if there is one) and works out what it would become: the new title and body, the check in
it and whether that check may run now. It writes nothing. The caller runs the check if it may, then `save` writes the
document through `core/docs.py`, a new revision like any other save. A part the caller leaves out stays exactly as the
owner last left it: only the sections named are replaced.

The title is the document's own; the file name comes from it once, at the start (`sources/calendar.md`), and does not move
when the title does. A new source whose name is taken is refused, naming the one that has it: a retried call must not
leave a second `calendar-2.md` behind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from verticals.core import docs as core_docs
from verticals.core import source_checks as sc
from verticals.core import sources as core
from verticals.core.errors import ValidationError
from verticals.core.field_rules import validate_owner

_NEEDED_TO_START = ("title", "gives", "how", "since", "check")


@dataclass(frozen=True)
class Draft:
    """What the document would become. `id` is None for a source that does not exist yet."""

    id: str | None
    path: str
    title: str | None
    body: str
    revision: int | None
    check: sc.Check | None
    approved_hash: str | None
    changed: bool

    @property
    def created(self) -> bool:
        return self.id is None

    @property
    def runnable(self) -> bool:
        """The check may run now: it is one the agent can write, and a command or a file has the owner's approval."""
        check = self.check
        return check is not None and check.kind in sc.KINDS and (not check.gated or self.approved_hash == check.hash)


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string", field=name)
    if len(value) > 20000:
        raise ValidationError(f"{name} must be at most 20000 characters", field=name)
    return value.strip()


def _new_path(conn: psycopg.Connection, owner: str, title: str) -> str:
    path = f"{sc.PREFIX}{sc.slug(title)}.md"
    twin = conn.execute("SELECT id FROM docs WHERE owner = %(owner)s AND path = %(path)s", {"owner": owner, "path": path}).fetchone()
    if twin is not None:
        raise ValidationError(f"there is already a source at {path!r} [{twin[0]}]: pass its id to change it, or choose another title",
                              field="title")
    return path


def prepare(
    conn: psycopg.Connection,
    *,
    owner: str,
    ref: str | None = None,
    title: object = None,
    gives: object = None,
    how: object = None,
    since: object = None,
    fixes: Sequence[str] | None = None,
    check: object = None,
) -> Draft:
    """Work out the document from the parts given. With `ref` (an id or a path) it is an update of that source; without,
    a new one, which needs a title, what it gives, how to read it, since when and its check."""
    owner = validate_owner(owner)
    given = {"title": title, "gives": gives, "how": how, "since": since, "check": check}
    new_check = sc.Check.from_dict(check) if check is not None else None

    if ref is None:
        missing = [name for name in _NEEDED_TO_START if given[name] is None]
        if missing:
            raise ValidationError(f"a new source needs {', '.join(missing)}", field=missing[0])
        name = _text("title", title)
        body = sc.build_body(gives=_text("gives", gives), how=_text("how", how), since=_text("since", since),
                             check=new_check, fixes=list(fixes or ()))
        return Draft(id=None, path=_new_path(conn, owner, name), title=name, body=body, revision=None, check=new_check,
                     approved_hash=None, changed=True)

    source = core.find(conn, owner=owner, ref=ref)
    body = source.body
    if gives is not None:
        body = sc.set_section(body, "gives", _text("gives", gives))
    if how is not None:
        body = sc.set_section(body, "how", _text("how", how))
    if since is not None:
        body = sc.set_section(body, "since", _text("since", since))
    if fixes is not None:
        body = sc.set_section(body, "fixes", sc.fixes_text(list(fixes)))
    if new_check is not None:
        body = sc.set_section(body, "check", sc.render_block(new_check))
    name = _text("title", title) if title is not None else source.title
    now_check = new_check
    if now_check is None:
        try:
            now_check = sc.parse_check(body, app=True)
        except ValidationError:
            now_check = None
    approved = source.row.approved_hash if source.row else None
    return Draft(id=source.id, path=source.path, title=name, body=body, revision=source.revision, check=now_check,
                 approved_hash=approved, changed=(body != source.body or name != source.title))


def save(conn: psycopg.Connection, *, owner: str, draft: Draft, now: datetime) -> core.Source:
    """Write the document, and wake the source so the open app sees it. A draft that changed nothing writes nothing."""
    owner = validate_owner(owner)
    if draft.created:
        doc_id = core_docs.create(conn, owner=owner, path=draft.path, title=draft.title, body=draft.body).doc.id
    else:
        doc_id = draft.id
        if draft.changed:
            core_docs.save(conn, owner=owner, id=doc_id, expected_revision=draft.revision, title=draft.title, body=draft.body)
    if draft.changed:
        core.wake(conn, owner=owner, doc_id=doc_id, now=now)
    return core.find(conn, owner=owner, ref=doc_id)
