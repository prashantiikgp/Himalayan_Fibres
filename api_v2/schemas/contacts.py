"""Pydantic models for /api/v2/contacts endpoints (Phase 1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContactRow(BaseModel):
    """Compact row used by the list endpoint. Mirrors v1's
    Plan D Phase 1.3 column-narrowing — only the 14 fields the
    table actually needs."""

    id: str
    first_name: str
    last_name: str
    company: str
    email: str
    phone: str
    wa_id: str | None
    lifecycle: str
    customer_type: str
    consent_status: str
    country: str
    tags: list[str] = Field(default_factory=list)
    segments: list[str] = Field(
        default_factory=list,
        description="Segment IDs this contact matches (rule-evaluated, not stored).",
    )
    channels: list[Literal["email", "whatsapp"]] = Field(default_factory=list)


class ContactListResponse(BaseModel):
    contacts: list[ContactRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class SegmentSummary(BaseModel):
    id: str
    name: str
    color: str | None = None
    description: str | None = None
    member_count: int


class SegmentsResponse(BaseModel):
    segments: list[SegmentSummary]


class TagsResponse(BaseModel):
    tags: list[str]


class CountriesResponse(BaseModel):
    countries: list[str]


class ContactNoteOut(BaseModel):
    id: int
    body: str
    author: str | None
    created_at: str = Field(description="ISO 8601 UTC timestamp")


class ContactInteractionOut(BaseModel):
    id: int
    kind: str
    summary: str
    actor: str | None
    created_at: str = Field(description="ISO 8601 UTC timestamp")


class ContactDetail(ContactRow):
    """Full contact detail — used by GET /contacts/{id}.

    Adds threaded notes + activity timeline + matched-segments to ContactRow.
    """

    customer_subtype: str = ""
    geography: str = ""
    legacy_notes: str = Field(default="", description="v1's single-string notes column")
    threaded_notes: list[ContactNoteOut] = Field(default_factory=list)
    activity: list[ContactInteractionOut] = Field(default_factory=list)
    matched_segments: list[SegmentSummary] = Field(default_factory=list)


class ContactCreate(BaseModel):
    """Body for POST /api/v2/contacts. Required: first_name + phone."""

    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = ""
    phone: str = Field(min_length=1, description="Digits only or starting with +")
    email: str = ""
    company: str = ""
    country: str = "India"
    customer_type: str = "other"
    lifecycle: str = "new_lead"
    tags: list[str] = Field(default_factory=list)


class ContactUpdate(BaseModel):
    """Body for PATCH /api/v2/contacts/{id}. All fields optional."""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    country: str | None = None
    lifecycle: str | None = None
    consent_status: str | None = None
    tags: list[str] | None = None
    notes: str | None = Field(default=None, description="legacy notes column")


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
