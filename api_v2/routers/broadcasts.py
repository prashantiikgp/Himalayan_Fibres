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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api_v2.deps import require_auth
from api_v2.schemas.broadcasts import (
    AudienceBreakdownItem,
    AudiencePreviewRequest,
    AudiencePreviewResponse,
    BroadcastListItem,
    BroadcastListResponse,
    CostBreakdownItem,
    CostEstimateRequest,
    CostEstimateResponse,
    SendBroadcastRequest,
    SendBroadcastResponse,
)

from services.database import get_db  # type: ignore[import-not-found]
from services.models import Broadcast, Campaign  # type: ignore[import-not-found]
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
        # Broadcast doesn't have scheduled_at yet (Phase 3.1 migration).
        scheduled_at=None,
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
