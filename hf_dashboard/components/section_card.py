"""Section card wrapper — consistent card containers."""

from __future__ import annotations

from components.styles import section_card


def render_section_card(content: str, accent_color: str = "", compact: bool = False) -> str:
    """Wrap content in a styled section card."""
    return f'<div style="{section_card(accent_color=accent_color, compact=compact)}; margin:8px 0;">{content}</div>'
