"""Shared email branding config — loaded once from config/email/shared.yml.

Every email template is rendered with these variables available in its
Jinja2 context, so changes to the banner URL / company address / social links
propagate to all templates on reseed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "email" / "shared.yml"


class SharedEmailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    banner_url: str
    banner_alt: str

    company_name: str
    address: str
    company_email: str
    company_phone: str

    whatsapp_url: str
    whatsapp_icon_url: str
    instagram_url: str
    instagram_icon_url: str
    facebook_url: str
    facebook_icon_url: str

    privacy_url: str
    terms_url: str
    refund_url: str
    unsubscribe_mailto: str

    copyright_line: str

    color_text: str
    color_body: str
    color_accent: str
    color_button_bg: str
    color_button_text: str
    color_link: str
    color_footer_bg: str
    color_card_bg: str
    color_card_border: str
    font_stack: str

    # Curated media library — full public Supabase URLs for the
    # `wa-template-images` bucket. Templates reference via `{{ media.<key> }}`
    # so adding a new image is one YAML edit, not a template-wide search/replace.
    media: dict[str, str] = Field(default_factory=dict)

    # Canonical price-list PDF — signed Supabase URL (1-year expiry).
    # Refresh with `python scripts/upload_price_list.py <local-pdf-path>`.
    # Surfaced to templates as `{{ price_list_url }}` via build_send_variables
    # whenever the per-recipient EmailAttachment lookup misses.
    price_list_pdf_url: str = ""

    # Canonical product-catalogue PDF (signed Supabase URL, 1-year).
    # Surfaced to templates as `{{ catalog_link }}` via build_send_variables
    # so every catalog CTA renders with a working link by default.
    catalog_pdf_url: str = ""

    # Public sample-request / contact page — default for the
    # `{{ sample_request_link }}` / `{{ sample_form_link }}` CTAs.
    sample_request_url: str = ""

    # ── Layout (Wave 6) — single source of truth for shell dimensions
    # and the optional "card" treatment. Surfaced into every render via
    # build_send_variables → base.html / partials.
    email_width: int = 720
    content_max_width: int = 680
    card_variant: bool = False
    card_radius: int = 10
    card_shadow: str = "0 0 18px rgba(0,0,0,0.12)"
    card_margin: int = 16
    card_heading_font: str = "'Amiri', Georgia, serif"


class _SharedEmailConfigDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared: SharedEmailConfig


@lru_cache(maxsize=1)
def load_shared_config() -> dict:
    """Read config/email/shared.yml once, validate, return as dict.

    Returned as a plain dict (not the Pydantic model) because Jinja2
    template rendering uses ``**shared_config`` kwargs.
    """
    with _CFG_PATH.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    doc = _SharedEmailConfigDocument(**raw)
    return doc.shared.model_dump()


def reload_shared_config() -> dict:
    """Clear the cache and reload — use after editing shared.yml at runtime."""
    load_shared_config.cache_clear()
    return load_shared_config()
