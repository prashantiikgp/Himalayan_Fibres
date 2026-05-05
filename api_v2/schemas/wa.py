"""Pydantic schemas for /api/v2/wa/* endpoints (Phase 2).

Mirrors the WAChat / WAMessage / WATemplate ORM models in
hf_dashboard/services/models.py, narrowed to the columns the v2 frontend
actually renders. Plan D Phase 1.3 column-narrowing applied throughout
so the wire payload stays small.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class WAMessageOut(BaseModel):
    """One message bubble."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: Literal["in", "out"]
    status: str
    text: str
    media_type: str | None
    media_path: str | None
    media_caption: str | None
    wa_message_id: str | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime


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
    """Names of {{ }} placeholders in body/header/buttons — drives the
    variables form (B1 fix: render exactly N inputs, no padding)."""


class WATemplatesResponse(BaseModel):
    templates: list[WATemplateOut]
    total: int
