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
