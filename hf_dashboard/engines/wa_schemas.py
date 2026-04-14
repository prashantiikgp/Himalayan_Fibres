"""WhatsApp-specific YAML Pydantic schemas.

Keeps WA config validation separate from theme/layout/dashboard schemas so
engines under `hf_dashboard/engines/` and services under
`hf_dashboard/services/` can depend on these without pulling in the full
theme graph.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MediaFormatGuidelines(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formats: list[str]
    max_size_mb: int
    recommended: str = ""
    tips: list[str] = Field(default_factory=list)


class MediaGuidelinesDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header_image: MediaFormatGuidelines
    header_video: MediaFormatGuidelines
    header_document: MediaFormatGuidelines


class MediaGuidelinesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_guidelines: MediaGuidelinesDefinition
