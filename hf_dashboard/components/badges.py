"""Badge HTML builders — status pills, channel indicators."""

from __future__ import annotations

from shared.theme import COLORS
from components.styles import badge_pill


# -- Status badges --

STATUS_COLORS = {
    "sent": (COLORS.SUCCESS, "#fff"),
    "delivered": (COLORS.SUCCESS, "#fff"),
    "draft": (COLORS.TEXT_MUTED, "#fff"),
    "sending": (COLORS.WARNING, "#fff"),
    "scheduled": (COLORS.INFO, "#fff"),
    "failed": (COLORS.ERROR, "#fff"),
    "cancelled": (COLORS.TEXT_MUTED, "#fff"),
    "active": (COLORS.SUCCESS, "#fff"),
    "paused": (COLORS.WARNING, "#fff"),
    "completed": (COLORS.SUCCESS, "#fff"),
    "opted_in": (COLORS.SUCCESS, "#fff"),
    "opted_out": (COLORS.ERROR, "#fff"),
    "pending": (COLORS.WARNING, "#fff"),
    "approved": (COLORS.SUCCESS, "#fff"),
    "read": (COLORS.PRIMARY, "#fff"),
    "queued": (COLORS.TEXT_SUBTLE, "#fff"),
}


def status_badge(status: str) -> str:
    """Render a status badge pill."""
    bg, fg = STATUS_COLORS.get(status.lower(), (COLORS.TEXT_MUTED, "#fff"))
    return f'<span style="{badge_pill(bg, fg)}">{status}</span>'


def channel_badge(channel: str) -> str:
    """Render channel indicator (email/whatsapp)."""
    if channel.lower() in ("email", "e"):
        return f'<span style="{badge_pill(COLORS.PRIMARY, "#fff")}">EMAIL</span>'
    elif channel.lower() in ("whatsapp", "wa"):
        return f'<span style="{badge_pill(COLORS.SUCCESS, "#fff")}">WA</span>'
    return f'<span style="{badge_pill(COLORS.TEXT_MUTED, "#fff")}">{channel}</span>'
