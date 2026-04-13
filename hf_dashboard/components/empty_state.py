"""Empty state placeholder."""

from __future__ import annotations

from shared.theme import COLORS, FONTS


def render_empty_state(message: str = "No data", icon: str = "&#x1F4ED;") -> str:
    """Render an empty state message."""
    return (
        f'<div style="text-align:center; padding:40px; color:{COLORS.TEXT_MUTED};">'
        f'<div style="font-size:32px; margin-bottom:8px;">{icon}</div>'
        f'<div style="font-size:{FONTS.MD};">{message}</div>'
        f'</div>'
    )
