"""`POST /api/morning` — the morning's one ask a day (docs/design/agent-fixes.md, fix 3).

The app calls it once its morning hour has come and an agent is there. The first call of the owner's day answers
`asked: true` and the app asks the agent for the report; every later call, from this window or any other, answers
`asked: false`. `owner` is read from `request.app.state.config.owner`, never from the request, like every route here."""

from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, Depends, Request

from verticals.api.deps import get_conn, verify_bearer_token
from verticals.core import morning as core_morning

router = APIRouter(dependencies=[Depends(verify_bearer_token)])


@router.post("/api/morning")
def post_morning(request: Request, date: _date) -> dict:
    """`date` is the owner's today, as the board's own `date`: the app reads it off its clock."""
    owner = request.app.state.config.owner
    with get_conn(request) as conn:
        begun = core_morning.begin(conn, owner=owner, day=date)
    return {"asked": begun.asked}
