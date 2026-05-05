"""Pydantic schemas for /api/v2/email/templates (Phase 6.4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from api_v2.schemas.email_send import EmailVariableSpec


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
    variable_spec: list[EmailVariableSpec] | None = None
    """Phase 7.1: rich per-variable spec from `.meta.yml`. Falls back to
    a synthesized list (text inputs) for DB-only templates without a
    YAML companion. None means we couldn't determine a spec."""


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
