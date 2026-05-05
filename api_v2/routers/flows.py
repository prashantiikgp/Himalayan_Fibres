"""/api/v2/flows — read endpoints (Phase 5.0).

Read-only list of automation flows + recent runs per flow. Write paths
(start a flow on a segment, pause/cancel a run) land in Phase 5.1.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api_v2.deps import require_auth
from api_v2.schemas.flows import (
    FlowOut,
    FlowRunOut,
    FlowRunsResponse,
    FlowsResponse,
)

from services.database import get_db  # type: ignore[import-not-found]
from services.models import Flow, FlowRun  # type: ignore[import-not-found]


router = APIRouter(tags=["flows"], dependencies=[Depends(require_auth)])


def _flow_to_out(f: Flow) -> FlowOut:
    return FlowOut(
        id=f.id,
        name=f.name,
        description=f.description or "",
        channel=f.channel if f.channel in {"email", "whatsapp"} else "email",
        is_active=bool(f.is_active),
        step_count=len(f.steps or []),
        created_at=f.created_at,
    )


@router.get("/flows", response_model=FlowsResponse)
def list_flows(
    active_only: Annotated[bool, Query()] = False,
    channel: Annotated[str | None, Query()] = None,
) -> FlowsResponse:
    """All flows. `active_only=true` filters to is_active rows.
    `channel` filters by 'email' or 'whatsapp'.
    """
    if channel and channel not in {"email", "whatsapp"}:
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'whatsapp'")

    db = get_db()
    try:
        q = db.query(Flow)
        if active_only:
            q = q.filter(Flow.is_active.is_(True))
        if channel:
            q = q.filter(Flow.channel == channel)
        rows = q.order_by(Flow.created_at.desc()).all()
        return FlowsResponse(flows=[_flow_to_out(f) for f in rows], total=len(rows))
    finally:
        db.close()


@router.get("/flows/{flow_id}/runs", response_model=FlowRunsResponse)
def list_flow_runs(
    flow_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FlowRunsResponse:
    """Recent runs of a flow. 404 if the flow doesn't exist."""
    db = get_db()
    try:
        if db.query(Flow).filter(Flow.id == flow_id).first() is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        rows = (
            db.query(FlowRun)
            .filter(FlowRun.flow_id == flow_id)
            .order_by(FlowRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return FlowRunsResponse(
            runs=[FlowRunOut.model_validate(r) for r in rows],
            total=len(rows),
        )
    finally:
        db.close()
