"""/api/v2/broadcasts — unified broadcasts list (Phase 3.0).

Reads both `broadcasts` (WhatsApp) and `campaigns` (Email) tables and
returns a single normalized list. This is the **B6 fix at the data
layer** — v1's `pages/broadcast_history.py` only reads from `broadcasts`,
which is structurally why the Email channel filter on that page always
returned zero rows even when emails were being sent.

Phase 3.1+ will add Compose endpoints (audience-preview, cost-estimate,
WA send, Email queue) and the scheduler. Phase 3.0 ships the read-side
that the History tab needs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from api_v2.deps import require_auth
from api_v2.schemas.broadcasts import (
    AudienceBreakdownItem,
    AudiencePreviewRequest,
    AudiencePreviewResponse,
    BroadcastDetail,
    BroadcastListItem,
    BroadcastListResponse,
    CostBreakdownItem,
    CostEstimateRequest,
    CostEstimateResponse,
    QueueEmailBroadcastResponse,
    RecipientItem,
    RecipientsResponse,
    SchedulePatch,
    SendBroadcastRequest,
    SendBroadcastResponse,
    SendEmailBroadcastRequest,
)
from api_v2.services.job_store import get_job_store

from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Broadcast,
    Campaign,
    Contact,
    EmailSend,
    WAMessage,
)
from services.broadcast_engine import (  # type: ignore[import-not-found]
    BroadcastFilters,
    estimate_cost,
    get_audience_breakdown,
    send_broadcast,
)


router = APIRouter(tags=["broadcasts"], dependencies=[Depends(require_auth)])


def _wa_to_item(b: Broadcast) -> BroadcastListItem:
    return BroadcastListItem(
        id=f"wa-{b.id}",
        channel="whatsapp",
        name=b.name,
        template_id=b.template_id or "",
        segment_id=b.segment_id,
        status=b.status or "draft",
        total_recipients=b.total_recipients or 0,
        total_sent=b.total_sent or 0,
        total_failed=b.total_failed or 0,
        sent_at=b.sent_at,
        # Phase 3.1b.2 — populated once the migration has run.
        # Old DBs without the column return None thanks to nullable.
        scheduled_at=getattr(b, "scheduled_at", None),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def _email_to_item(c: Campaign) -> BroadcastListItem:
    return BroadcastListItem(
        id=f"em-{c.id}",
        channel="email",
        name=c.name,
        template_id=c.template_slug or "",
        segment_id=c.segment_id,
        status=c.status or "draft",
        total_recipients=c.total_recipients or 0,
        total_sent=c.total_sent or 0,
        total_failed=c.total_failed or 0,
        sent_at=c.sent_at,
        scheduled_at=c.scheduled_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("/broadcasts", response_model=BroadcastListResponse)
def list_broadcasts(
    channel: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BroadcastListResponse:
    """Unified broadcasts list reading both `broadcasts` (WA) and
    `campaigns` (Email). Filters apply at the DB layer per table; the
    two result sets are merged in Python and sorted by created_at desc
    before pagination.

    `channel` accepts `whatsapp` | `email`. Omitted = both.
    """
    if channel and channel not in {"whatsapp", "email"}:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'email'")

    db = get_db()
    try:
        items: list[BroadcastListItem] = []

        if channel != "email":
            wa_q = db.query(Broadcast)
            if status_filter:
                wa_q = wa_q.filter(Broadcast.status == status_filter)
            if search:
                wa_q = wa_q.filter(Broadcast.name.ilike(f"%{search}%"))
            for row in wa_q.all():
                items.append(_wa_to_item(row))

        if channel != "whatsapp":
            em_q = db.query(Campaign)
            if status_filter:
                em_q = em_q.filter(Campaign.status == status_filter)
            if search:
                em_q = em_q.filter(Campaign.name.ilike(f"%{search}%"))
            for row in em_q.all():
                items.append(_email_to_item(row))

        # Newest first; rows missing created_at sink to the bottom.
        items.sort(
            key=lambda i: i.created_at or i.updated_at or i.sent_at,
            reverse=True,
        )

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        effective_page = min(page, max(0, total_pages - 1)) if total else 0
        start = effective_page * page_size
        page_items = items[start : start + page_size]

        return BroadcastListResponse(
            broadcasts=page_items,
            total=total,
            page=effective_page,
            page_size=page_size,
            total_pages=total_pages,
        )
    finally:
        db.close()


# ─── Phase 3.1 Compose endpoints ─────────────────────────────────────────


def _to_filters(req_filters) -> BroadcastFilters:  # type: ignore[no-untyped-def]
    """Convert the API's BroadcastFiltersIn to v1's dataclass."""
    return BroadcastFilters(
        segment_id=req_filters.segment_id,
        countries=list(req_filters.countries or []),
        tags=list(req_filters.tags or []),
        lifecycles=list(req_filters.lifecycles or []),
        consents=list(req_filters.consents or []),
        max_recipients=int(req_filters.max_recipients or 0),
    )


def _bucket_to_items(d: dict[str, int]) -> list[AudienceBreakdownItem]:
    return [AudienceBreakdownItem(label=k or "unknown", count=int(v)) for k, v in d.items()]


@router.post("/broadcasts/audience-preview", response_model=AudiencePreviewResponse)
def audience_preview(req: AudiencePreviewRequest) -> AudiencePreviewResponse:
    """Return funnel counts + breakdowns for the current filter selection.

    Drives the B3-fix sticky header on the Compose tab. Reuses v1's
    `get_audience_breakdown` so segment-rule eval stays in one place.
    """
    db = get_db()
    try:
        raw = get_audience_breakdown(db, req.channel, _to_filters(req.filters))
        return AudiencePreviewResponse(
            total_in_segment=int(raw["total_in_segment"]),
            eligible_on_channel=int(raw["eligible_on_channel"]),
            final_recipients=int(raw["final_recipients"]),
            excluded_by_channel=int(raw["excluded_by_channel"]),
            excluded_by_filters=int(raw["excluded_by_filters"]),
            consent=_bucket_to_items(raw.get("consent", {})),
            geography=_bucket_to_items(raw.get("geography", {})),
            lifecycle=_bucket_to_items(raw.get("lifecycle", {})),
            customer_type=_bucket_to_items(raw.get("customer_type", {})),
        )
    finally:
        db.close()


@router.post("/broadcasts/cost-estimate", response_model=CostEstimateResponse)
def cost_estimate(req: CostEstimateRequest) -> CostEstimateResponse:
    """Cost preview cards. Reuses v1's `estimate_cost` for parity."""
    db = get_db()
    try:
        raw = estimate_cost(db, req.channel, req.category, _to_filters(req.filters))
        breakdown = [
            CostBreakdownItem(**b) for b in raw.get("breakdown", [])
        ]
        return CostEstimateResponse(
            recipients=int(raw["recipients"]),
            per_message_display=str(raw["per_message_display"]),
            total_display=str(raw["total_display"]),
            currency=str(raw.get("currency", "INR")),
            category=raw.get("category"),
            breakdown=breakdown,
            est_delivery_seconds=int(raw.get("est_delivery_seconds", 0)),
        )
    finally:
        db.close()


@router.post(
    "/broadcasts/wa",
    response_model=SendBroadcastResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_wa_broadcast(req: SendBroadcastRequest) -> SendBroadcastResponse:
    """Send a WhatsApp broadcast synchronously.

    For Phase 3.1 we keep this synchronous — small batches finish in
    seconds. Email broadcasts will queue via BackgroundTasks (Phase
    3.1b) because their 3s/recipient rate limit means a 100-row
    broadcast would block this handler for 5+ min.

    Returns the persisted Broadcast row plus aggregated send counts.
    The B10 fix lives client-side: SendConfirmDialog gates this call
    behind a recipient + cost summary that the user must confirm.
    """
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not req.template_id.strip():
        raise HTTPException(status_code=400, detail="template_id is required")

    db = get_db()
    try:
        result = send_broadcast(
            db=db,
            name=req.name.strip(),
            channel="whatsapp",
            template_id=req.template_id.strip(),
            filters=_to_filters(req.filters),
            subject=req.subject or "",
        )
        # v1's BroadcastResult has sent/failed/total + a list of errors;
        # post-send we re-read the persisted row for the canonical status.
        b = db.query(Broadcast).filter(Broadcast.id == result.broadcast_id).first()
        return SendBroadcastResponse(
            broadcast_id=int(result.broadcast_id),
            name=req.name.strip(),
            total_recipients=int(result.total),
            total_sent=int(result.sent),
            total_failed=int(result.failed),
            status=(b.status if b else "unknown") or "unknown",
        )
    finally:
        db.close()


# ─── Phase 3.1b.1 — Email queue + jobs ───────────────────────────────────


_log = logging.getLogger("api_v2.broadcasts.email")


def _run_email_broadcast(
    job_id: str,
    name: str,
    template_id: str,
    subject: str,
    filters_dict: dict,
    extra_vars: dict | None = None,
) -> None:
    """BackgroundTasks worker. Wraps v1's send_broadcast in a fresh
    DB session + JobStore status updates. Per-recipient progress
    requires forking v1's loop; for now we report queued -> running
    -> done with the final counts (B13 fix scope).

    Phase 7.2a: ``extra_vars`` carries the typed Compose variable values
    through to ``build_send_variables`` so seeded templates render with
    the user's chosen subject/CTA/whatever AND the shared branding.
    """
    store = get_job_store()
    store.update(job_id, status="running", message="Sending…", progress=5)

    db = get_db()
    try:
        filters = BroadcastFilters(
            segment_id=filters_dict.get("segment_id"),
            countries=list(filters_dict.get("countries") or []),
            tags=list(filters_dict.get("tags") or []),
            lifecycles=list(filters_dict.get("lifecycles") or []),
            consents=list(filters_dict.get("consents") or []),
            max_recipients=int(filters_dict.get("max_recipients") or 0),
        )
        result = send_broadcast(
            db=db,
            name=name,
            channel="email",
            template_id=template_id,
            filters=filters,
            subject=subject,
            extra_vars=dict(extra_vars or {}),
        )
        store.update(
            job_id,
            status="done",
            progress=100,
            message=f"Sent {result.sent}, failed {result.failed}",
            result={
                "broadcast_id": result.broadcast_id,
                "total_recipients": result.total,
                "total_sent": result.sent,
                "total_failed": result.failed,
                "errors": list(result.errors or [])[:50],
            },
        )
    except Exception as e:
        _log.exception("email broadcast job %s failed", job_id)
        store.update(
            job_id,
            status="failed",
            message=str(e)[:500],
            result={"errors": [str(e)]},
        )
    finally:
        db.close()


@router.post(
    "/broadcasts/email",
    response_model=QueueEmailBroadcastResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_email_broadcast(
    req: SendEmailBroadcastRequest,
    background_tasks: BackgroundTasks,
) -> QueueEmailBroadcastResponse:
    """Queue an email broadcast and return a job_id for polling.

    **B13 fix.** v1's email Send Now ran a 3s/recipient sleep loop on
    the Gradio request-handler thread, freezing the UI for 5+ min on a
    100-row send. This endpoint dispatches via FastAPI BackgroundTasks
    and returns immediately with a job_id; the frontend polls
    `/api/v2/jobs/{job_id}/status` to render progress.
    """
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not req.template_id.strip():
        raise HTTPException(status_code=400, detail="template_id is required")

    # Compute the recipient count up front so the UI gets a denominator
    # for the progress bar before the background task touches the DB.
    db = get_db()
    try:
        preview = get_audience_breakdown(db, "email", _to_filters(req.filters))
        recipients = int(preview["final_recipients"])
    finally:
        db.close()

    # **Phase 3.1b.2** — if scheduled_at is in the future, create a
    # Campaign in status='scheduled' instead of dispatching now. The
    # scheduler loop fires it at the chosen time. We return a synthetic
    # JobStore entry pointing at the scheduled row so the UI shape is
    # unchanged for the caller.
    if req.scheduled_at is not None:
        sched = req.scheduled_at
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        if sched <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="scheduled_at must be in the future; use Send Now to fire immediately",
            )
        # Review fix #3: pass the tz-aware datetime through to
        # SQLAlchemy. Postgres TIMESTAMPTZ stores it correctly; SQLite
        # silently strips tzinfo on insert but converts back from naive
        # UTC consistently because every read site assumes UTC.
        db = get_db()
        try:
            c = Campaign(
                name=req.name.strip(),
                template_slug=req.template_id.strip(),
                segment_id=req.filters.segment_id,
                subject=req.subject or "",
                # Phase 7.2b: persist typed variables so the scheduler
                # fires with the same merge values the user typed.
                variables=dict(req.variables or {}),
                status="scheduled",
                scheduled_at=sched,
                total_recipients=recipients,
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            scheduled_id = c.id
        finally:
            db.close()
        store = get_job_store()
        job_id = store.create(
            job_type="email_broadcast_scheduled",
            message=f"Scheduled for {sched.isoformat()} ({recipients} recipient(s))",
        )
        store.update(
            job_id,
            status="done",
            progress=100,
            result={
                "scheduled": True,
                "campaign_id": scheduled_id,
                "scheduled_at": sched.isoformat(),
                "estimated_recipients": recipients,
            },
        )
        return QueueEmailBroadcastResponse(
            job_id=job_id,
            estimated_recipients=recipients,
        )

    store = get_job_store()
    job_id = store.create(
        job_type="email_broadcast",
        message=f"Queued {recipients} recipient(s)",
    )
    background_tasks.add_task(
        _run_email_broadcast,
        job_id,
        req.name.strip(),
        req.template_id.strip(),
        req.subject or "",
        req.filters.model_dump(),
        dict(req.variables or {}),
    )
    return QueueEmailBroadcastResponse(
        job_id=job_id,
        estimated_recipients=recipients,
    )


# ─── Phase 3.1b.3 — Detail + recipient pagination (B16 fix) ──────────────


def _parse_broadcast_id(prefixed: str) -> tuple[str, int]:
    """Split a prefixed broadcast id (e.g. `wa-12`) into (channel, db_id).
    Raises 400 on malformed input."""
    if "-" not in prefixed:
        raise HTTPException(status_code=400, detail="id must be 'wa-N' or 'em-N'")
    prefix, _, raw_id = prefixed.partition("-")
    if prefix == "wa":
        channel = "whatsapp"
    elif prefix == "em":
        channel = "email"
    else:
        raise HTTPException(status_code=400, detail="id prefix must be 'wa-' or 'em-'")
    if not raw_id.isdigit():
        raise HTTPException(status_code=400, detail="id suffix must be numeric")
    return channel, int(raw_id)


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastDetail)
def get_broadcast(broadcast_id: str) -> BroadcastDetail:
    """Detail for a unified broadcast row. `broadcast_id` is prefixed
    (`wa-N` or `em-N`) to disambiguate the two underlying tables."""
    channel, db_id = _parse_broadcast_id(broadcast_id)

    db = get_db()
    try:
        if channel == "whatsapp":
            b = db.query(Broadcast).filter(Broadcast.id == db_id).first()
            if b is None:
                raise HTTPException(status_code=404, detail="Broadcast not found")
            return BroadcastDetail(
                id=f"wa-{b.id}",
                channel="whatsapp",
                name=b.name,
                template_id=b.template_id or "",
                segment_id=b.segment_id,
                status=b.status or "draft",
                total_recipients=b.total_recipients or 0,
                total_sent=b.total_sent or 0,
                total_failed=b.total_failed or 0,
                sent_at=b.sent_at,
                scheduled_at=getattr(b, "scheduled_at", None),
                created_at=b.created_at,
                subject="",
            )
        else:
            c = db.query(Campaign).filter(Campaign.id == db_id).first()
            if c is None:
                raise HTTPException(status_code=404, detail="Broadcast not found")
            return BroadcastDetail(
                id=f"em-{c.id}",
                channel="email",
                name=c.name,
                template_id=c.template_slug or "",
                segment_id=c.segment_id,
                status=c.status or "draft",
                total_recipients=c.total_recipients or 0,
                total_sent=c.total_sent or 0,
                total_failed=c.total_failed or 0,
                sent_at=c.sent_at,
                scheduled_at=c.scheduled_at,
                created_at=c.created_at,
                subject=c.subject or "",
            )
    finally:
        db.close()


@router.get("/broadcasts/{broadcast_id}/recipients", response_model=RecipientsResponse)
def list_recipients(
    broadcast_id: str,
    cursor: Annotated[int | None, Query(ge=0)] = None,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> RecipientsResponse:
    """Per-broadcast recipient list, cursor-paginated by row id ASC.

    **B16 fix.** v1's per-broadcast detail capped recipient rows at
    100 silently — large campaigns lost visibility past row 100. This
    endpoint paginates by primary key with no implicit cap; clients
    fetch as many pages as they need.
    """
    channel, db_id = _parse_broadcast_id(broadcast_id)

    db = get_db()
    try:
        if channel == "whatsapp":
            base = db.query(WAMessage).filter(WAMessage.wa_batch_id == str(db_id))
            if status_filter:
                base = base.filter(WAMessage.status == status_filter)
            total = base.count()
            q = base
            if cursor is not None:
                q = q.filter(WAMessage.id > cursor)
            rows = q.order_by(WAMessage.id.asc()).limit(page_size).all()
            # Contact lookup for display address (wa_id or phone).
            cids = list({r.contact_id for r in rows})
            contacts: dict[str, Contact] = {
                c.id: c
                for c in db.query(Contact).filter(Contact.id.in_(cids)).all()
            }
            items = [
                RecipientItem(
                    id=r.id,
                    contact_id=r.contact_id,
                    address=(contacts.get(r.contact_id).wa_id if contacts.get(r.contact_id) else "")
                    or (contacts.get(r.contact_id).phone if contacts.get(r.contact_id) else "")
                    or "",
                    status=r.status or "",
                    error_message=r.error_detail or "",
                    sent_at=r.created_at if (r.status or "") == "sent" else None,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        else:
            base = db.query(EmailSend).filter(EmailSend.campaign_id == db_id)
            if status_filter:
                base = base.filter(EmailSend.status == status_filter)
            total = base.count()
            q = base
            if cursor is not None:
                q = q.filter(EmailSend.id > cursor)
            rows = q.order_by(EmailSend.id.asc()).limit(page_size).all()
            items = [
                RecipientItem(
                    id=r.id,
                    contact_id=r.contact_id,
                    address=r.contact_email or "",
                    status=r.status or "",
                    error_message=r.error_message or "",
                    sent_at=r.sent_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]

        next_cursor = items[-1].id if len(items) == page_size else None
        return RecipientsResponse(
            recipients=items, total=total, next_cursor=next_cursor,
        )
    finally:
        db.close()


# ─── Phase 3.1b.2 — Schedule / cancel ────────────────────────────────────


@router.patch("/broadcasts/{broadcast_id}", response_model=BroadcastDetail)
def patch_broadcast(broadcast_id: str, req: SchedulePatch) -> BroadcastDetail:
    """Schedule a broadcast for future delivery, or cancel a scheduled
    one.

    - `scheduled_at` in the future → status='scheduled' + scheduled_at set
    - `scheduled_at=null` → status flips back to 'draft' + scheduled_at
      cleared
    - `scheduled_at` in the past → 400 (use Send Now instead)

    The scheduler loop in api_v2/services/scheduler.py picks up due
    rows once per minute and fires them via the same paths as Send Now.
    Currently sent / failed broadcasts cannot be re-scheduled.
    """
    channel, db_id = _parse_broadcast_id(broadcast_id)

    db = get_db()
    try:
        if channel == "whatsapp":
            row = db.query(Broadcast).filter(Broadcast.id == db_id).first()
        else:
            row = db.query(Campaign).filter(Campaign.id == db_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Broadcast not found")

        if (row.status or "").lower() in {"sent", "completed", "sending", "failed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reschedule a {row.status!r} broadcast",
            )

        if req.scheduled_at is None:
            row.scheduled_at = None
            row.status = "draft"
        else:
            now = datetime.now(timezone.utc)
            sched = req.scheduled_at
            if sched.tzinfo is None:
                sched = sched.replace(tzinfo=timezone.utc)
            if sched <= now:
                raise HTTPException(
                    status_code=400,
                    detail="scheduled_at must be in the future; use Send Now to fire immediately",
                )
            # Review fix #3: keep tz-aware. Postgres TIMESTAMPTZ stores
            # it correctly; SQLite normalizes by stripping tzinfo and
            # all readers assume UTC.
            row.scheduled_at = sched
            row.status = "scheduled"

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        # Re-emit as the unified detail.
        if channel == "whatsapp":
            return BroadcastDetail(
                id=f"wa-{row.id}",
                channel="whatsapp",
                name=row.name,
                template_id=row.template_id or "",
                segment_id=row.segment_id,
                status=row.status or "draft",
                total_recipients=row.total_recipients or 0,
                total_sent=row.total_sent or 0,
                total_failed=row.total_failed or 0,
                sent_at=row.sent_at,
                scheduled_at=getattr(row, "scheduled_at", None),
                created_at=row.created_at,
                subject="",
            )
        return BroadcastDetail(
            id=f"em-{row.id}",
            channel="email",
            name=row.name,
            template_id=row.template_slug or "",
            segment_id=row.segment_id,
            status=row.status or "draft",
            total_recipients=row.total_recipients or 0,
            total_sent=row.total_sent or 0,
            total_failed=row.total_failed or 0,
            sent_at=row.sent_at,
            scheduled_at=row.scheduled_at,
            created_at=row.created_at,
            subject=row.subject or "",
        )
    finally:
        db.close()
