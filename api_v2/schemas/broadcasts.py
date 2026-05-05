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
    batches; v1's loop is fine for <100 recipients).

    `scheduled_at` (Phase 3.1b.2): if set in the future, the row is
    created in `status='scheduled'` instead of being sent immediately.
    The scheduler loop fires it at that time."""

    name: str
    channel: Literal["whatsapp"] = "whatsapp"
    template_id: str
    filters: BroadcastFiltersIn = BroadcastFiltersIn()
    subject: str = ""
    scheduled_at: datetime | None = None


class SendBroadcastResponse(BaseModel):
    broadcast_id: int
    name: str
    total_recipients: int
    total_sent: int
    total_failed: int
    status: str


class SendEmailBroadcastRequest(BaseModel):
    """POST /broadcasts/email — queues via BackgroundTasks.

    `scheduled_at` (Phase 3.1b.2): if set in the future, the request
    creates a Campaign in `status='scheduled'` and returns a synthetic
    job_id pointing at the scheduled row instead of an immediate
    BackgroundTask."""

    name: str
    template_id: str
    """Email template SLUG (e.g. b2b_introduction). Must exist + active."""
    subject: str = ""
    """Override the template's subject_template. Empty = use default."""
    filters: BroadcastFiltersIn = BroadcastFiltersIn()
    variables: dict[str, str] = {}
    """Phase 7.2a — typed variable values applied to every recipient as
    the `extra` dict on `build_send_variables`. Auto-resolved per-
    recipient names (first_name, etc.) are filled by the server from
    the contact and should not be passed here."""
    scheduled_at: datetime | None = None


class QueueEmailBroadcastResponse(BaseModel):
    """Returned synchronously when an email broadcast is queued."""

    job_id: str
    estimated_recipients: int
    """Upfront count so the UI can render a progress bar denominator
    before the background task starts."""


# ─── Phase 3.1b.3 — Detail + recipient pagination (B16 fix) ──────────────


class BroadcastDetail(BaseModel):
    """Detail payload for the Performance tab — composes the list-item
    fields plus a few stats not shown in the table."""

    id: str
    channel: Literal["whatsapp", "email"]
    name: str
    template_id: str
    segment_id: str | None
    status: str
    total_recipients: int
    total_sent: int
    total_failed: int
    sent_at: datetime | None
    scheduled_at: datetime | None
    created_at: datetime
    subject: str = ""
    """Email-only; empty for WA."""


class RecipientItem(BaseModel):
    """One row in the per-broadcast recipient table."""

    id: int
    contact_id: str
    address: str
    """Email address for email; phone/wa_id for WhatsApp."""
    status: str
    error_message: str = ""
    sent_at: datetime | None
    created_at: datetime


class SchedulePatch(BaseModel):
    """PATCH /broadcasts/{id} body — schedule or cancel.

    `scheduled_at=None` cancels a previously scheduled broadcast (status
    flips back to draft). Otherwise the broadcast is marked
    `status=scheduled` and the scheduler loop fires it at that time.
    """

    scheduled_at: datetime | None = None


class RecipientsResponse(BaseModel):
    recipients: list[RecipientItem]
    total: int
    next_cursor: int | None
    """Pass back as `?cursor=` to fetch the next page. Null when the
    end is reached. Cursor is the opaque `last id` so pagination is
    stable under inserts (B16 fix — v1's table silently capped at 100;
    this paginates without losing rows)."""
