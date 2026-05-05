"""Pydantic schemas for /api/v2/wa/* endpoints (Phase 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ConversationListItem(BaseModel):
    """One row in the conversation-list panel (left column of WA Inbox)."""

    model_config = ConfigDict(from_attributes=True)

    contact_id: str
    contact_name: str
    contact_company: str
    last_message_at: datetime | None
    last_message_preview: str
    unread_count: int
    window_expires_at: datetime | None
    window_open: bool
    """True if window_expires_at is in the future — drives B2 fix."""


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


_INBOUND_DIRECTIONS = {"in", "incoming", "received"}
_OUTBOUND_DIRECTIONS = {"out", "outgoing", "sent"}


class WAMessageOut(BaseModel):
    """One message bubble."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: Literal["in", "out"]
    """Normalized — DB may carry legacy values like 'incoming'/'outgoing'
    from older webhook code; the validator below maps them to in/out
    (review fix #5)."""
    status: str
    text: str
    media_type: str | None
    media_path: str | None
    media_caption: str | None
    wa_message_id: str | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, v: object) -> str:
        s = str(v or "").lower().strip()
        if s in _INBOUND_DIRECTIONS:
            return "in"
        if s in _OUTBOUND_DIRECTIONS:
            return "out"
        # Pass through unrecognized values so Pydantic's Literal check
        # still raises and surfaces unknown direction strings instead of
        # silently coercing them.
        return s


class ConversationDetail(BaseModel):
    """Full conversation with all messages — drives the chat panel."""

    contact_id: str
    contact_name: str
    contact_company: str
    contact_phone: str
    contact_wa_id: str | None
    consent_status: str
    lifecycle: str
    window_expires_at: datetime | None
    window_open: bool
    last_inbound_at: datetime | None
    """Timestamp of the most recent INBOUND message; null if customer has
    never messaged us. Drives the 'no inbound yet — use a template' UI."""
    messages: list[WAMessageOut]


class WATemplateOut(BaseModel):
    """A template visible in the Send-Template sheet."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    language: str
    category: str | None
    status: str | None
    body_text: str
    header_format: str | None
    header_asset_url: str | None
    header_text: str | None
    footer_text: str | None
    variables: list[str]
    """Names of {{ }} placeholders in body/header/footer/buttons/components.
    First-appearance order so the variables form renders inputs in the
    same sequence as the template body (B1 fix consumer)."""


class WATemplatesResponse(BaseModel):
    templates: list[WATemplateOut]
    total: int


class SendMessageRequest(BaseModel):
    """POST /wa/messages — text reply within an open 24h window."""

    contact_id: str
    text: str


class SendTemplateRequest(BaseModel):
    """POST /wa/template-sends — template send (works outside the window)."""

    contact_id: str
    template_name: str
    language: str = "en_US"
    variables: list[str] = []
    """Positional ({{1}}, {{2}}…) values. The wa sender currently only
    consumes positional in this endpoint; named-variable templates are
    a Phase 2.2 follow-up since the frontend variables form already
    knows the variable order from the templates endpoint."""
