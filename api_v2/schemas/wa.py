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
    """A template visible in the Send-Template sheet AND the Template
    Studio list (Phase 4.0 expanded the shape)."""

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

    # Phase 4.0 additions — needed by Template Studio list + editor.
    is_draft: bool = False
    tier: str = "company"
    """Computed tier: company/category/product/utility. Inferred from
    name + category server-side. Mirrors v1's _infer_tier."""
    rejection_reason: str = ""
    submitted_at: datetime | None = None
    quality_score: str | None = None
    buttons: list[dict] = []
    """Raw Meta-format buttons array; empty list when none. Editor uses
    this to populate the buttons FieldArray; sender ignores it (the
    Meta API derives behavior from the approved template by name)."""


class WATemplatesResponse(BaseModel):
    templates: list[WATemplateOut]
    total: int


class TemplateRegistryEntry(BaseModel):
    """One row from config/whatsapp/templates.yml — joined client-side
    with `WATemplateOut` rows so the picker can show Intent badges and
    rich descriptions without a second round-trip.

    `intent_label` is derived server-side from `use_case` via a fixed
    map (onboarding→Intro, transactional→Order, product_showcase→Sample,
    catalog→Catalog, retention→Follow-up, testing→Test, default→Other)
    so the frontend never needs to know the raw values.
    """

    name: str
    display_name: str
    description: str = ""
    use_case: str = ""
    intent_label: str = "Other"
    category: str = ""
    notes: str = ""


class TemplateRegistryOut(BaseModel):
    entries: list[TemplateRegistryEntry]


class SendMessageRequest(BaseModel):
    """POST /wa/messages — text reply within an open 24h window."""

    contact_id: str
    text: str


class TemplateUpsert(BaseModel):
    """Body for POST /wa/templates and POST /wa/templates/{id}/save.

    Includes only the fields the Studio editor exposes. `name` is
    required on create; on save it's optional and ignored if provided
    (templates can't be renamed after creation — Meta uses the name as
    the identifier).
    """

    name: str | None = None
    language: str = "en_US"
    category: str = "MARKETING"
    body_text: str = ""
    header_format: str | None = None
    """TEXT / IMAGE / DOCUMENT / VIDEO. None = no header."""
    header_text: str | None = None
    header_asset_url: str | None = None
    footer_text: str | None = None
    buttons: list[dict] = []


class SendTemplateRequest(BaseModel):
    """POST /wa/template-sends — template send (works outside the window)."""

    contact_id: str
    template_name: str
    language: str = "en_US"
    variables: list[str] = []
    """Positional body params ({{1}}, {{2}}…). For named-param templates
    the frontend supplies values in declaration order from the templates
    endpoint."""
    header_variables: list[str] = []
    """Positional header params for templates that declare a TEXT header
    with placeholders. Empty for body-only templates. Meta rejects sends
    that omit header params with code 132000."""
