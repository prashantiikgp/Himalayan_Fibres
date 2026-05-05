"""Pydantic schemas for /api/v2/broadcasts/* endpoints (Phase 3.0)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BroadcastListItem(BaseModel):
    """Unified row for the History tab — normalizes both `Broadcast`
    (WhatsApp) and `Campaign` (Email) into the same shape so the table
    can render either with a single column set.

    The `id` field carries a `wa-` or `em-` prefix because the two
    underlying tables have overlapping primary keys (both autoincrement
    from 1). Phase 6 (out of scope here) would migrate to a UUID column
    on each table and drop the prefix.
    """

    id: str
    channel: Literal["whatsapp", "email"]
    name: str
    template_id: str
    """For WA: template name. For Email: template slug (or empty)."""
    segment_id: str | None
    status: str
    total_recipients: int
    total_sent: int
    total_failed: int
    sent_at: datetime | None
    scheduled_at: datetime | None
    """Currently only Email Campaigns have this column populated;
    Broadcast.scheduled_at lands when Phase 3.1 ships scheduling."""
    created_at: datetime
    updated_at: datetime | None


class BroadcastListResponse(BaseModel):
    broadcasts: list[BroadcastListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Phase 3.1 Compose ───────────────────────────────────────────────────


class BroadcastFiltersIn(BaseModel):
    """User-selected filters from the Compose tab. Mirrors v1's
    BroadcastFilters dataclass field-for-field so the audit's audience
    funnel logic can be reused without a translation layer."""

    segment_id: str | None = None
    countries: list[str] = []
    tags: list[str] = []
    lifecycles: list[str] = []
    consents: list[str] = []
    max_recipients: int = 0


class AudiencePreviewRequest(BaseModel):
    channel: Literal["whatsapp", "email"]
    filters: BroadcastFiltersIn = BroadcastFiltersIn()


class AudienceBreakdownItem(BaseModel):
    label: str
    count: int


class AudiencePreviewResponse(BaseModel):
    """Funnel + breakdown — drives the B3-fix sticky header + chips."""

    total_in_segment: int
    eligible_on_channel: int
    final_recipients: int
    excluded_by_channel: int
    excluded_by_filters: int
    consent: list[AudienceBreakdownItem]
    geography: list[AudienceBreakdownItem]
    lifecycle: list[AudienceBreakdownItem]
    customer_type: list[AudienceBreakdownItem]


class CostEstimateRequest(BaseModel):
    channel: Literal["whatsapp", "email"]
    category: str = "marketing"
    """WA template category: MARKETING / UTILITY / AUTHENTICATION.
    Email ignores this — the rate is flat per send."""
    filters: BroadcastFiltersIn = BroadcastFiltersIn()


class CostBreakdownItem(BaseModel):
    country: str
    recipients: int
    rate: float
    currency: str
    symbol: str
    subtotal: float
    display: str


class CostEstimateResponse(BaseModel):
    recipients: int
    per_message_display: str
    total_display: str
    currency: str
    category: str | None = None
    breakdown: list[CostBreakdownItem]
    est_delivery_seconds: int


class SendBroadcastRequest(BaseModel):
    """POST /broadcasts/wa body — synchronous send for now (small
    batches; v1's loop is fine for <100 recipients)."""

    name: str
    channel: Literal["whatsapp"] = "whatsapp"
    template_id: str
    filters: BroadcastFiltersIn = BroadcastFiltersIn()
    subject: str = ""


class SendBroadcastResponse(BaseModel):
    broadcast_id: int
    name: str
    total_recipients: int
    total_sent: int
    total_failed: int
    status: str
