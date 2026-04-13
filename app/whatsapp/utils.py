"""WhatsApp utility functions."""

from __future__ import annotations

import re
from datetime import datetime, timezone

PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


def normalize_phone(raw: str) -> str:
    """Return a sanitized E.164-ish phone string.

    Raises ValueError on invalid input.
    """
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"[^0-9+]+", "", cleaned)
    if cleaned.startswith("+"):
        cleaned = "+" + re.sub(r"[^0-9]", "", cleaned[1:])
    else:
        cleaned = re.sub(r"[^0-9]", "", cleaned)
    if not cleaned:
        raise ValueError("Phone number is required")
    digits_only = re.sub(r"\D", "", cleaned)
    if len(digits_only) < 7 or len(digits_only) > 15:
        raise ValueError("Phone number must contain 7-15 digits")
    if not PHONE_RE.match(cleaned if cleaned.startswith("+") else digits_only):
        raise ValueError("Phone number format is invalid")
    return cleaned if cleaned.startswith("+") else digits_only


def contact_within_24h(last_inbound_at: datetime | None) -> bool:
    """Check if the contact's last inbound message is within 24 hours.

    WhatsApp allows free-form text only within 24h of the last inbound message.
    Outside this window, only approved templates can be sent.
    """
    if last_inbound_at is None:
        return False
    now = datetime.now(timezone.utc)
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    delta = now - last_inbound_at
    return delta.total_seconds() < 86400  # 24 hours
