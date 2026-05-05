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

from fastapi import APIRouter, Depends, HTTPException, Query

from api_v2.deps import require_auth
from api_v2.schemas.broadcasts import BroadcastListItem, BroadcastListResponse

from services.database import get_db  # type: ignore[import-not-found]
from services.models import Broadcast, Campaign  # type: ignore[import-not-found]


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
