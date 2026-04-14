"""Shared email branding config — loaded once from config/email/shared.yml.

Every email template is rendered with these variables available in its
Jinja2 context, so changes to the banner URL / company address / social links
propagate to all templates on reseed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

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
