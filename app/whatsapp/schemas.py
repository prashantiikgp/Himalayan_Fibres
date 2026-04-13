"""WhatsApp Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ===========================================
# REQUEST SCHEMAS
# ===========================================


class WASendTextRequest(BaseModel):
    """Send a text message to a contact."""

    contact_id: int
    text: str = Field(..., min_length=1, max_length=4096)


class WASendTemplateRequest(BaseModel):
    """Send a template message to a contact."""

    contact_id: int
    template_name: str
    language: str = "en_US"
    variables: list[str] = []


class WAReplyRequest(BaseModel):
    """Reply to an existing chat."""

    text: str = Field(..., min_length=1, max_length=4096)


# ===========================================
# RESPONSE SCHEMAS
# ===========================================


class WASendResult(BaseModel):
    """Result of sending a WhatsApp message."""

    ok: bool
    wa_message_id: str | None = None
    db_message_id: int | None = None
    error: str | None = None


class WAMessageResponse(BaseModel):
    """Single WhatsApp message in a conversation."""

    id: int
    direction: str
    text: str
    status: str
    wa_message_id: str | None = None
    media_type: str | None = None
    media_path: str | None = None
    media_caption: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WAChatResponse(BaseModel):
    """WhatsApp conversation summary."""

    id: int
    contact_id: int
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_company: str | None = None
    contact_wa_id: str | None = None
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    unread_count: int = 0
    window_open: bool = False  # True if within 24h messaging window
    is_archived: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class WAChatListResponse(BaseModel):
    """Paginated list of WhatsApp conversations."""

    chats: list[WAChatResponse]
    total: int


class WATemplateResponse(BaseModel):
    """WhatsApp message template."""

    id: int
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    quality_score: str | None = None
    components: list[dict[str, Any]] = []
    last_synced_at: datetime | None = None

    model_config = {"from_attributes": True}


class WATemplateSyncResult(BaseModel):
    """Result of syncing templates from Meta."""

    synced: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = []
