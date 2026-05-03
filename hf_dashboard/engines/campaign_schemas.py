"""Pydantic schemas for the campaign/ folder.

Loaded by scripts/validate_campaigns.py and (eventually) by the
dashboard campaign builder UI. Strict (`extra='forbid'`) so typos
in YAML keys fail at load time instead of silently dropping.

Schemas:
    BrandVoiceFile      campaign/brand_voice.yml
    WhatsAppTemplate    campaign/whatsapp_campaign/shared/**/*.yml
    CampaignFile        campaign/whatsapp_campaign/<segment>/campaigns.yml
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Brand voice -----------------------------------------------------------

class VoiceTone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formality: int = Field(ge=1, le=5, description="1=casual, 5=formal")
    warmth: int = Field(ge=1, le=5)
    technical_density: int = Field(ge=1, le=5)
    enthusiasm: int = Field(ge=1, le=5)


class VoiceExamples(BaseModel):
    model_config = ConfigDict(extra="forbid")

    good: str
    bad: Optional[str] = None


class BrandVoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    pillars: list[str] = Field(default_factory=list)
    tone: VoiceTone
    do: list[str] = Field(default_factory=list)
    dont: list[str] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    examples: Optional[VoiceExamples] = None
    sign_off: str = ""
    emoji_policy: str = ""


class BrandVoiceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_voice: str
    voices: dict[str, BrandVoice]

    def get(self, key: str | None = None) -> BrandVoice:
        return self.voices[key or self.default_voice]


# -- WhatsApp template -----------------------------------------------------

# Internal taxonomy (not sent to Meta)
TemplateTier = Literal["company", "category", "product", "utility"]
ProductCategory = Literal["nettle", "hemp", "wool", "collections"]

# Meta WhatsApp Cloud API enums
MetaCategory = Literal["MARKETING", "UTILITY", "AUTHENTICATION"]
HeaderFormat = Literal["TEXT", "IMAGE", "VIDEO", "DOCUMENT"]
ButtonType = Literal["QUICK_REPLY", "URL", "PHONE_NUMBER", "CATALOG"]


class TemplateButton(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ButtonType
    text: str
    url: Optional[str] = None
    phone_number: Optional[str] = None


class TemplateHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: HeaderFormat
    text: Optional[str] = None
    image: Optional[str] = None         # primary public URL (used in header)
    image_caption: Optional[str] = None  # internal note, not sent to Meta
    alternates: list[str] = Field(default_factory=list)  # alt URLs to swap in


class WhatsAppTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tier: TemplateTier
    voice: str                           # validated against BrandVoiceFile.voices
    meta_category: MetaCategory
    language: str = "en"

    product_category: Optional[ProductCategory] = None
    product_sku: Optional[str] = None

    header: Optional[TemplateHeader] = None
    body: str
    body_example: list[str] = Field(default_factory=list)
    footer: Optional[str] = None
    buttons: list[TemplateButton] = Field(default_factory=list)

    notes: str = ""


# -- Campaign --------------------------------------------------------------

Segment = Literal[
    "existing_clients",
    "churned_clients",
    "potential_domestic",
    "international_email",
]
Channel = Literal["whatsapp", "email"]


class CampaignStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str           # WhatsAppTemplate.name
    delay_hours: int = 0    # delay before sending this step
    only_if_no_reply: bool = True


class Campaign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    segment: Segment
    channel: Channel
    description: str = ""
    steps: list[CampaignStep] = Field(default_factory=list)
    audience_filter: dict = Field(default_factory=dict)
    is_active: bool = True


class CampaignFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaigns: list[Campaign]
