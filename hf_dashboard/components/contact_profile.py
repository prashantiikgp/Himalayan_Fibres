"""Shared contact profile panel — used by both WA and Email inbox pages.

Renders: avatar, name, company, channels, contact fields, lifecycle, tags, activity log.
"""

from __future__ import annotations

from components.styles import (
    badge, channel_badge_email, channel_badge_wa,
    activity_item, activity_timestamp, activity_text,
)
from services.contact_schema import get_lifecycle_color, get_lifecycle_icon


def _avatar(name: str, size: int = 40) -> str:
    colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#ec4899", "#14b8a6", "#8b5cf6"]
    bg = colors[hash(name) % len(colors)]
    initials = "".join(w[0].upper() for w in (name or "?").split()[:2])
    return (
        f'<div style="width:{size}px; height:{size}px; border-radius:50%; background:{bg}; '
        f'display:flex; align-items:center; justify-content:center; '
        f'font-size:{size // 3}px; font-weight:700; color:#fff; flex-shrink:0;">{initials}</div>'
    )


def render_profile(db, contact_id: str) -> str:
    """Render full contact profile panel HTML."""
    if not contact_id:
        return ""

    from services.models import Contact, WAMessage, EmailSend

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return ""

    name = f"{contact.first_name} {contact.last_name}".strip() or "Unknown"

    # Channels
    channels = ""
    if contact.wa_id:
        channels += f'<span style="{channel_badge_wa()}">WhatsApp</span> '
    if contact.email and "placeholder" not in contact.email:
        channels += f'<span style="{channel_badge_email()}">Email</span>'

    # Tags
    tags = ""
    if contact.tags and isinstance(contact.tags, list):
        for t in contact.tags[:5]:
            tags += (
                f'<span style="background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1); '
                f'padding:1px 5px; border-radius:3px; font-size:9px; color:#94a3b8; margin:1px;">{t}</span> '
            )

    # Lifecycle
    lc_id = contact.lifecycle or "new_lead"
    lc_color = get_lifecycle_color(lc_id)
    lc_icon = get_lifecycle_icon(lc_id)
    lc_label = lc_id.replace("_", " ").title()

    # Activity log — merge WA + Email, sorted by date
    activities = []

    for wm in db.query(WAMessage).filter(WAMessage.contact_id == contact.id).order_by(WAMessage.created_at.desc()).limit(10).all():
        ts = wm.created_at.strftime("%b %d") if wm.created_at else ""
        direction = "received" if wm.direction == "in" else "sent"
        activities.append((
            wm.created_at,
            f'<div style="{activity_item()}">'
            f'<span style="{activity_timestamp()}">{ts}</span>'
            f'<span style="{activity_text()}">💬 WA message {direction}</span></div>'
        ))

    for es in db.query(EmailSend).filter(EmailSend.contact_id == contact.id).order_by(EmailSend.created_at.desc()).limit(10).all():
        ts = es.sent_at.strftime("%b %d") if es.sent_at else ""
        activities.append((
            es.sent_at or es.created_at,
            f'<div style="{activity_item()}">'
            f'<span style="{activity_timestamp()}">{ts}</span>'
            f'<span style="{activity_text()}">✉ Email {es.status}</span></div>'
        ))

    activities.sort(key=lambda x: x[0] or __import__("datetime").datetime.min, reverse=True)
    activity_html = "".join(html for _, html in activities[:10])
    if not activity_html:
        activity_html = '<div style="color:#64748b; font-size:10px; padding:4px;">No activity yet</div>'

    return f"""
    <div style="padding:12px;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:14px;">
            {_avatar(name)}
            <div>
                <div style="font-weight:700; font-size:13px; color:#e7eaf3;">{name}</div>
                <div style="font-size:10px; color:#64748b;">{contact.company or ''}</div>
            </div>
        </div>

        <div style="font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px;">Channels</div>
        <div style="margin-bottom:10px;">{channels or '—'}</div>

        <div style="font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px;">Details</div>
        <div style="font-size:11px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,.03);">
                <span style="color:#64748b;">Phone</span><span style="color:#e7eaf3;">{contact.phone or '—'}</span></div>
            <div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,.03);">
                <span style="color:#64748b;">Email</span><span style="color:#e7eaf3; font-size:10px;">{contact.email if contact.email and 'placeholder' not in contact.email else '—'}</span></div>
            <div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,.03);">
                <span style="color:#64748b;">Country</span><span style="color:#e7eaf3;">{contact.country or '—'}</span></div>
            <div style="display:flex; justify-content:space-between; padding:3px 0;">
                <span style="color:#64748b;">Lifecycle</span><span style="{badge(lc_color)}">{lc_icon} {lc_label}</span></div>
        </div>

        <div style="font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px;">Tags</div>
        <div style="margin-bottom:10px;">{tags or '<span style="color:#64748b; font-size:10px;">No tags</span>'}</div>

        <div style="font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px;">Activity</div>
        {activity_html}
    </div>
    """
