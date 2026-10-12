"""The morning's two routes the app itself calls (docs/design/agent-fixes.md, fixes 3 and 2; docs/design/morning-quality.md).

`POST /api/morning` — the morning's one ask a day. The app calls it once its morning hour has come and an agent is there. The
first call of the owner's day answers `asked: true` with `task_id`, the one open "Morning report" task, made or moved to that
day, and `landed`, the comments the owner left in the last report, now saved on their tasks word for word; the app asks the agent
for the report. Every later call, from this window or any other, answers `asked: false` and changes nothing.

`POST /api/morning/check` — the second agent's verdict. The desktop gateway runs the second agent, which only reads; the gateway
hands what it answered to this route, which writes it into the report (`core/morning_checks.py`) and says which checks failed.
Neither route is a tool: the agent has no hand in either.

`owner` is read from `request.app.state.config.owner`, never from the request, like every route here."""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from verticals.api.deps import get_conn, verify_bearer_token
from verticals.core import morning as core_morning
from verticals.core import morning_checks
from verticals.core.morning_report import Outcome
from verticals.sources.scheduler import utcnow

router = APIRouter(dependencies=[Depends(verify_bearer_token)])


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)
    # "pending" and "unchecked" put the report in a state without a verdict; "checked" writes one from `checks`.
    state: Literal["pending", "unchecked", "checked"] = "checked"
    reason: str = Field(default="", max_length=400)
    checks: dict[str, Any] | None = None
    # The outcomes of the check before the fixing turn, as this route answered them: what failed then and passes now is "fixed".
    first: dict[str, Any] | None = None


@router.post("/api/morning")
def post_morning(request: Request, date: _date) -> dict:
    """`date` is the owner's today, as the board's own `date`: the app reads it off its clock."""
    owner = request.app.state.config.owner
    with get_conn(request) as conn:
        begun = core_morning.begin(conn, owner=owner, day=date)
    answer: dict = {"asked": begun.asked, "task_id": begun.task_id}
    if begun.asked:
        answer["landed"] = [item.as_dict() for item in begun.landed]
    return answer


@router.post("/api/morning/check")
def post_check(request: Request, payload: CheckRequest) -> dict:
    owner = request.app.state.config.owner
    first = {key: Outcome(str(item.get("result")), str(item.get("note") or ""))
             for key, item in (payload.first or {}).items() if isinstance(item, dict)}
    with get_conn(request) as conn:
        if payload.state == "checked":
            applied = morning_checks.apply(conn, owner=owner, path=payload.path, asked=payload.checks, first=first, now=utcnow())
        else:
            applied = morning_checks.mark(conn, owner=owner, path=payload.path, state=payload.state, reason=payload.reason)
    return applied.as_dict()
