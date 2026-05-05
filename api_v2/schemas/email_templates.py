"""Pydantic schemas for /api/v2/email/templates (Phase 6.4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmailTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    subject_template: str
    html_content: str
    email_type: str
    required_variables: list[str]
    category: str
    is_active: bool
    created_at: datetime


class EmailTemplatesResponse(BaseModel):
    templates: list[EmailTemplateOut]
    total: int


class EmailTemplateUpsert(BaseModel):
    """POST body for create + save. `slug` is required on create
    (unique), ignored on save."""

    name: str | None = None
    slug: str | None = None
    subject_template: str = ""
    html_content: str = ""
    email_type: str = "campaign"
    required_variables: list[str] = []
    category: str = ""
    is_active: bool = True
