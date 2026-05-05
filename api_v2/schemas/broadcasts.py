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
