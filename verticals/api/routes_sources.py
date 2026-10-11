"""The `/api/sources*` routes (docs/design/sources.md): every source with its colour for the Inbox, and the owner's
Approve for a command or a file.

Approve lives here and nowhere else. No MCP tool calls `core.sources.approve`, so the agent can write a check and never run
a command of its own: the button sits beside the exact text it approves, and the hash it sends is the hash the owner was
shown, so a check edited in between is refused (409) instead of approved unseen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from verticals.api.deps import get_conn, verify_bearer_token
from verticals.core import sources as core_sources
from verticals.sources.scheduler import utcnow

router = APIRouter(dependencies=[Depends(verify_bearer_token)])


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_hash: str = Field(min_length=64, max_length=64)


@router.get("/api/sources")
def list_sources(request: Request, response: Response) -> dict:
    """Every document under `sources/` with its state, what needs a look first: red, waiting, then the rest. Each carries
    the start of its text, as the Documents desk does, so a tile draws its page without a second read."""
    owner = request.app.state.config.owner
    with get_conn(request) as conn:
        views = core_sources.views(conn, owner=owner, now=utcnow())
        response.headers["X-Query-Count"] = str(conn.query_count)
    return {"sources": [view.as_dict() for view in views]}


@router.post("/api/sources/{id}/approve")
def approve_source(request: Request, response: Response, id: str, payload: ApproveRequest) -> dict:
    """The owner pressed Approve on the check they were shown. The timer is nudged, so the first answer arrives within
    seconds instead of at the next look."""
    owner = request.app.state.config.owner
    with get_conn(request) as conn:
        view = core_sources.approve(conn, owner=owner, doc_id=id, check_hash=payload.check_hash, now=utcnow())
        response.headers["X-Query-Count"] = str(conn.query_count)
    timer = getattr(request.app.state, "sources", None)
    if timer is not None:
        timer.poke()
    return view.as_dict()
