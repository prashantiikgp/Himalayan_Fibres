"""/api/v2/flows — read endpoints + Phase 7.7 membership endpoints.

Phase 5.0 read endpoints kept (`GET /flows`, `GET /flows/{id}/runs`)
for backward compatibility. Phase 7.7 adds per-contact membership
endpoints that drive the new flow detail page + contact drawer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func

from api_v2.deps import require_auth
from api_v2.schemas.flows import (
    FlowDetailOut,
    FlowMembershipCreate,
    FlowMembershipDetail,
    FlowMembershipDetailsResponse,
    FlowMembershipOut,
    FlowMembershipsResponse,
    FlowOut,
    FlowRunOut,
    FlowRunsResponse,
    FlowStepRunOut,
    FlowStepRunsResponse,
    FlowsResponse,
)

from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Contact,
    Flow,
    FlowMembership,
    FlowRun,
    FlowStepRun,
)


router = APIRouter(tags=["flows"], dependencies=[Depends(require_auth)])


# A second router under a different prefix — POST /flow-memberships/{id}/stop
# isn't a sub-resource of /flows, so it gets its own mount in api_v2/main.py.
membership_router = APIRouter(tags=["flow_memberships"], dependencies=[Depends(require_auth)])


def _flow_to_out(f: Flow, active_count: int = 0) -> FlowOut:
    channel = f.channel if f.channel in {"email", "whatsapp", "multi"} else "email"
    return FlowOut(
        id=f.id,
        name=f.name,
        slug=f.slug,
        description=f.description or "",
        channel=channel,
        is_active=bool(f.is_active),
        step_count=len(f.steps or []),
        trigger_type=f.trigger_type or "manual",
        trigger_config=dict(f.trigger_config or {}),
        active_count=active_count,
        created_at=f.created_at,
    )


def _membership_to_out(
    m: FlowMembership,
    *,
    flow: Flow | None = None,
    contact: Contact | None = None,
) -> FlowMembershipOut:
    name = ""
    email = None
    if contact is not None:
        name = (f"{contact.first_name or ''} {contact.last_name or ''}").strip()
        if contact.email and "placeholder" not in contact.email:
            email = contact.email
    return FlowMembershipOut(
        id=m.id,
        flow_id=m.flow_id,
        flow_name=flow.name if flow else "",
        flow_slug=flow.slug if flow else None,
        contact_id=m.contact_id,
        contact_name=name,
        contact_email=email,
        status=m.status,
        current_step_index=m.current_step_index,
        total_steps=len(flow.steps or []) if flow else 0,
        started_at=m.started_at,
        last_step_at=m.last_step_at,
        next_fire_at=m.next_fire_at,
        trigger_source=m.trigger_source,
        trigger_actor=m.trigger_actor or "",
        error=m.error or "",
    )


@router.get("/flows", response_model=FlowsResponse)
def list_flows(
    active_only: Annotated[bool, Query()] = False,
    channel: Annotated[str | None, Query()] = None,
) -> FlowsResponse:
    """All flows. `active_only=true` filters to is_active rows.
    `channel` filters by 'email' / 'whatsapp' / 'multi'.

    Phase 7.7: response now includes `active_count` per flow — computed
    from a single GROUP BY query so the list endpoint stays O(flows)."""
    if channel and channel not in {"email", "whatsapp", "multi"}:
        raise HTTPException(status_code=400, detail="channel must be 'email', 'whatsapp', or 'multi'")

    db = get_db()
    try:
        q = db.query(Flow)
        if active_only:
            q = q.filter(Flow.is_active.is_(True))
        if channel:
            q = q.filter(Flow.channel == channel)
        rows = q.order_by(Flow.created_at.desc()).all()

        # One GROUP BY query for active counts across all listed flows.
        flow_ids = [r.id for r in rows]
        active_counts: dict[int, int] = {}
        if flow_ids:
            counts = (
                db.query(FlowMembership.flow_id, func.count(FlowMembership.id))
                .filter(
                    FlowMembership.flow_id.in_(flow_ids),
                    FlowMembership.status.in_(("active", "waiting_event", "paused")),
                )
                .group_by(FlowMembership.flow_id)
                .all()
            )
            active_counts = {fid: int(cnt) for fid, cnt in counts}

        return FlowsResponse(
            flows=[_flow_to_out(f, active_counts.get(f.id, 0)) for f in rows],
            total=len(rows),
        )
    finally:
        db.close()


@router.get("/flows/{flow_id}/runs", response_model=FlowRunsResponse)
def list_flow_runs(
    flow_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FlowRunsResponse:
    """Legacy v1 cohort runs of a flow. Deprecated — Phase 7.7 UI uses
    `/flows/{id}/memberships` instead. 404 if the flow doesn't exist."""
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


@router.get("/flows/{flow_id}", response_model=FlowDetailOut)
def get_flow(flow_id: int) -> FlowDetailOut:
    """Single-flow detail — drives the /flows/:id page header + KPIs.
    Returns the full steps array plus per-status counts of memberships."""
    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if flow is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        # Per-status counts in one GROUP BY.
        rows = (
            db.query(FlowMembership.status, func.count(FlowMembership.id))
            .filter(FlowMembership.flow_id == flow_id)
            .group_by(FlowMembership.status)
            .all()
        )
        counts: dict[str, int] = {st: int(cnt) for st, cnt in rows}
        # Fold {active, waiting_event, paused} into the response's
        # `active_count` field for consistency with the list endpoint.
        active_count = (
            counts.get("active", 0)
            + counts.get("waiting_event", 0)
            + counts.get("paused", 0)
        )

        base = _flow_to_out(flow, active_count)
        return FlowDetailOut(
            **base.model_dump(),
            steps=list(flow.steps or []),
            counts=counts,
        )
    finally:
        db.close()


@router.get("/flows/{flow_id}/memberships", response_model=FlowMembershipsResponse)
def list_flow_memberships(
    flow_id: int,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> FlowMembershipsResponse:
    """Per-contact memberships for a flow — drives the flow detail page's
    Members tab. `status` filter is one of {active, waiting_event,
    paused, completed, failed, stopped} or omitted for all."""
    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if flow is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        q = db.query(FlowMembership).filter(FlowMembership.flow_id == flow_id)
        if status_filter:
            q = q.filter(FlowMembership.status == status_filter)
        rows = q.order_by(FlowMembership.started_at.desc()).limit(limit).all()

        contact_ids = [r.contact_id for r in rows]
        contact_map: dict[str, Contact] = {}
        if contact_ids:
            for c in db.query(Contact).filter(Contact.id.in_(contact_ids)).all():
                contact_map[c.id] = c

        return FlowMembershipsResponse(
            memberships=[
                _membership_to_out(m, flow=flow, contact=contact_map.get(m.contact_id))
                for m in rows
            ],
            total=len(rows),
        )
    finally:
        db.close()


@router.get("/flows/{flow_id}/step-runs", response_model=FlowStepRunsResponse)
def list_flow_step_runs(
    flow_id: int,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> FlowStepRunsResponse:
    """Flat audit log: every `flow_step_runs` row for memberships of
    this flow, latest-first. Powers the flow detail page's Step Runs
    tab. `status` ∈ {sent, failed, skipped} or omitted."""
    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if flow is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        member_ids = [
            mid for (mid,) in db.query(FlowMembership.id)
            .filter(FlowMembership.flow_id == flow_id).all()
        ]
        if not member_ids:
            return FlowStepRunsResponse(step_runs=[], total=0)

        q = db.query(FlowStepRun).filter(FlowStepRun.membership_id.in_(member_ids))
        if status_filter:
            q = q.filter(FlowStepRun.status == status_filter)
        rows = q.order_by(FlowStepRun.fired_at.desc()).limit(limit).all()
        return FlowStepRunsResponse(
            step_runs=[FlowStepRunOut.model_validate(r) for r in rows],
            total=len(rows),
        )
    finally:
        db.close()


@router.post(
    "/flows/{flow_id}/memberships",
    response_model=FlowMembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def create_flow_membership(
    flow_id: int,
    body: FlowMembershipCreate,
) -> FlowMembershipOut:
    """Manual enrollment — drawer's "Add to flow" button.

    Inserts a membership; idempotent under the partial unique index
    (`fm_contact_flow_uniq`). Returns 409 if the contact already has a
    live membership in this flow.
    """
    from api_v2.services.flows_engine_v2 import assign_flow

    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if flow is None:
            raise HTTPException(status_code=404, detail="Flow not found")
        if not flow.is_active:
            raise HTTPException(status_code=400, detail="Flow is inactive")

        contact = db.query(Contact).filter(Contact.id == body.contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        member = assign_flow(
            db,
            flow_id=flow.id,
            contact_id=contact.id,
            trigger_source="manual",
            trigger_actor=body.actor or "user",
            commit=True,
        )
        if member is None:
            raise HTTPException(
                status_code=409,
                detail="Contact already has a live membership in this flow",
            )
        return _membership_to_out(member, flow=flow, contact=contact)
    finally:
        db.close()


def _set_membership_status(
    membership_id: int,
    *,
    target_status: str,
    allowed_from: tuple[str, ...],
    interaction_kind: str,
    interaction_summary_template: str,
    re_arm: bool = False,
) -> FlowMembershipOut:
    """Shared transition logic for stop / pause / resume.

    `allowed_from` lists the statuses we'll transition out of; any other
    status returns 409 (idempotent stops/pauses on terminal rows return
    the row unchanged with 200 — see stop_membership for the special
    case). `re_arm=True` sets next_fire_at=now (for resume).
    """
    from datetime import datetime, timezone

    from services.interactions import log_interaction  # type: ignore[import-not-found]

    db = get_db()
    try:
        m = db.query(FlowMembership).filter(FlowMembership.id == membership_id).first()
        if m is None:
            raise HTTPException(status_code=404, detail="Membership not found")
        if m.status not in allowed_from:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition from status '{m.status}' to '{target_status}'",
            )

        now = datetime.now(timezone.utc)
        m.status = target_status
        m.last_step_at = now
        if re_arm:
            m.next_fire_at = now
            m.error = ""  # clear stale error on resume
        else:
            m.next_fire_at = None
        log_interaction(
            db,
            contact_id=m.contact_id,
            kind=interaction_kind,
            summary=interaction_summary_template.format(flow_id=m.flow_id),
            payload={"membership_id": m.id, "flow_id": m.flow_id},
            actor="user",
            commit=False,
        )
        db.commit()

        flow = db.query(Flow).filter(Flow.id == m.flow_id).first()
        contact = db.query(Contact).filter(Contact.id == m.contact_id).first()
        return _membership_to_out(m, flow=flow, contact=contact)
    finally:
        db.close()


@membership_router.post(
    "/flow-memberships/{membership_id}/stop",
    response_model=FlowMembershipOut,
)
def stop_membership(membership_id: int) -> FlowMembershipOut:
    """Operator-driven stop. Sets status='stopped', clears next_fire_at,
    writes a `flow_stopped` interaction. Idempotent — already-stopped
    rows return their current state without erroring."""
    from datetime import datetime, timezone

    from services.interactions import log_interaction  # type: ignore[import-not-found]

    db = get_db()
    try:
        m = db.query(FlowMembership).filter(FlowMembership.id == membership_id).first()
        if m is None:
            raise HTTPException(status_code=404, detail="Membership not found")

        if m.status not in {"stopped", "completed", "failed"}:
            m.status = "stopped"
            m.next_fire_at = None
            m.last_step_at = datetime.now(timezone.utc)
            log_interaction(
                db,
                contact_id=m.contact_id,
                kind="flow_stopped",
                summary=f"Stopped flow #{m.flow_id}",
                payload={"membership_id": m.id, "flow_id": m.flow_id},
                actor="user",
                commit=False,
            )
            db.commit()

        flow = db.query(Flow).filter(Flow.id == m.flow_id).first()
        contact = db.query(Contact).filter(Contact.id == m.contact_id).first()
        return _membership_to_out(m, flow=flow, contact=contact)
    finally:
        db.close()


@membership_router.post(
    "/flow-memberships/{membership_id}/pause",
    response_model=FlowMembershipOut,
)
def pause_membership(membership_id: int) -> FlowMembershipOut:
    """Operator pause. From {active, waiting_event} → paused. The next
    `tick_flows()` claim filter excludes 'paused' so no further sends
    fire until Resume. Idempotent on already-paused rows: returns
    409 'Cannot transition' so the UI knows nothing changed."""
    return _set_membership_status(
        membership_id,
        target_status="paused",
        allowed_from=("active", "waiting_event"),
        interaction_kind="flow_paused",
        interaction_summary_template="Paused flow #{flow_id}",
    )


@membership_router.post(
    "/flow-memberships/{membership_id}/resume",
    response_model=FlowMembershipOut,
)
def resume_membership(membership_id: int) -> FlowMembershipOut:
    """Operator resume. From paused → active with next_fire_at=now so
    the next tick claims and fires the membership's current step.
    409 if the membership isn't paused (e.g., already active or
    terminal)."""
    return _set_membership_status(
        membership_id,
        target_status="active",
        allowed_from=("paused",),
        interaction_kind="flow_resumed",
        interaction_summary_template="Resumed flow #{flow_id}",
        re_arm=True,
    )


def _membership_to_detail(
    m: FlowMembership,
    *,
    flow: Flow | None = None,
    contact: Contact | None = None,
) -> FlowMembershipDetail:
    """Like `_membership_to_out`, but enriches with `flow_trigger_type`
    and the resolved current step JSON. The drawer uses these to decide
    whether to render the Mark Sample Shipped button (membership in
    sample_dispatch + status='waiting_event' + current_step has
    trigger_event tag=samples_shipped)."""
    base = _membership_to_out(m, flow=flow, contact=contact)
    steps = list(flow.steps or []) if flow else []
    current = (
        steps[m.current_step_index]
        if 0 <= m.current_step_index < len(steps)
        else None
    )
    return FlowMembershipDetail(
        **base.model_dump(),
        flow_trigger_type=(flow.trigger_type if flow else "manual") or "manual",
        current_step=current,
    )


@membership_router.get(
    "/contacts/{contact_id}/flow-memberships",
    response_model=FlowMembershipDetailsResponse,
)
def list_contact_flow_memberships(
    contact_id: str,
    include_past: Annotated[bool, Query()] = True,
) -> FlowMembershipDetailsResponse:
    """Drawer Flows-tab data — all memberships for a contact, enriched
    with the flow's trigger context and the resolved current step JSON.
    `include_past=false` filters out completed/failed/stopped."""
    db = get_db()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        q = db.query(FlowMembership).filter(FlowMembership.contact_id == contact_id)
        if not include_past:
            q = q.filter(
                FlowMembership.status.in_(("active", "waiting_event", "paused"))
            )
        rows = q.order_by(FlowMembership.started_at.desc()).all()

        flow_ids = {r.flow_id for r in rows}
        flow_map: dict[int, Flow] = {}
        if flow_ids:
            for f in db.query(Flow).filter(Flow.id.in_(flow_ids)).all():
                flow_map[f.id] = f

        return FlowMembershipDetailsResponse(
            memberships=[
                _membership_to_detail(
                    m, flow=flow_map.get(m.flow_id), contact=contact,
                )
                for m in rows
            ],
            total=len(rows),
        )
    finally:
        db.close()
