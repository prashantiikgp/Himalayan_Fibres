"""Chat bubble HTML builder — WhatsApp conversation rendering."""

from __future__ import annotations

from shared.theme import COLORS, FONTS
from components.styles import chat_bubble_inbound, chat_bubble_outbound


def render_message_bubble(
    text: str,
    direction: str,
    sender_name: str = "",
    timestamp: str = "",
    media_type: str | None = None,
    status: str = "",
) -> str:
    """Render a single chat message bubble.

    Args:
        direction: "in" for inbound, "out" for outbound.
    """
    is_inbound = direction == "in"
    style = chat_bubble_inbound() if is_inbound else chat_bubble_outbound()
    sender_label = sender_name or ("Contact" if is_inbound else "You")

    media_html = ""
    if media_type:
        media_html = f'<div style="font-size:{FONTS.XS}; color:{COLORS.TEXT_MUTED};">[{media_type}]</div>'

    status_html = ""
    if status and not is_inbound:
        status_icons = {"sent": "&#x2713;", "delivered": "&#x2713;&#x2713;", "read": "&#x2713;&#x2713;", "failed": "&#x274C;"}
        status_color = COLORS.PRIMARY if status == "read" else COLORS.TEXT_MUTED
        icon = status_icons.get(status, "")
        status_html = f'<span style="font-size:{FONTS.XS}; color:{status_color};">{icon}</span>'

    time_html = ""
    if timestamp:
        time_html = f'<span style="font-size:{FONTS.XS}; color:{COLORS.TEXT_MUTED};">{timestamp}</span>'

    return (
        f'<div style="{style}">'
        f'<div style="font-weight:700; font-size:{FONTS.SM}; margin-bottom:2px;">{sender_label}</div>'
        f'{media_html}'
        f'<div>{text}</div>'
        f'<div style="display:flex; justify-content:space-between; margin-top:4px;">'
        f'{time_html}{status_html}</div>'
        f'</div>'
    )


def render_chat_list_item(
    name: str,
    last_message: str,
    timestamp: str = "",
    unread: int = 0,
    is_selected: bool = False,
) -> str:
    """Render a chat list entry for the sidebar."""
    bg = COLORS.PRIMARY_TINT_STRONG if is_selected else "transparent"
    border = f"border-left:3px solid {COLORS.PRIMARY};" if is_selected else "border-left:3px solid transparent;"

    unread_badge = ""
    if unread > 0:
        unread_badge = (
            f'<span style="background:{COLORS.SUCCESS}; color:#fff; border-radius:50%; '
            f'padding:2px 6px; font-size:{FONTS.XS}; font-weight:700;">{unread}</span>'
        )

    return (
        f'<div style="padding:8px 10px; {border} background:{bg}; cursor:pointer; '
        f'border-radius:4px; margin:2px 0;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
        f'<span style="font-weight:600; font-size:{FONTS.MD}; color:{COLORS.TEXT};">{name}</span>'
        f'{unread_badge}'
        f'</div>'
        f'<div style="font-size:{FONTS.XS}; color:{COLORS.TEXT_MUTED}; '
        f'white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px;">{last_message}</div>'
        f'<div style="font-size:{FONTS.XXS}; color:{COLORS.TEXT_MUTED};">{timestamp}</div>'
        f'</div>'
    )
