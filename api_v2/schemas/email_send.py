"""Pydantic schemas for /api/v2/email/render-preview + /api/v2/email/test-sends (Phase 7.1).

`EmailVariableSpec` is also re-exported by `EmailTemplateOut.variable_spec` so the
SPA can render typed variable inputs without a second round-trip.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VariableType = Literal["text", "textarea", "url", "date"]


class EmailVariableSpec(BaseModel):
    """Rich per-variable spec lifted from the template's `.meta.yml`.

    Mirrors `services.template_seed.TemplateVariableSpec` but lives in the
    API schema layer so the frontend type-checks against it directly.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str = ""
    type: VariableType = "text"
    placeholder: str = ""
    example: str = ""
    required: bool = False


class RenderPreviewRequest(BaseModel):
    template_id: int
    variables: dict[str, str] = Field(default_factory=dict)
    contact_id: str | None = None
    """When provided, server-resolves auto-prefill vars (first_name, etc.)
    from the contact and merges them under `variables`."""
    html_content_override: str | None = None
    """Studio Advanced mode: render this HTML instead of the saved body."""
    subject_template_override: str | None = None
    """Render this subject string instead of `template.subject_template`."""


class RenderPreviewResponse(BaseModel):
    html: str
    subject: str


class TestSendRequest(BaseModel):
    template_id: int
    contact_id: str
    variables: dict[str, str] = Field(default_factory=dict)
    subject_override: str | None = None


class TestSendResponse(BaseModel):
    success: bool
    message: str
    email_send_id: int | None = None
