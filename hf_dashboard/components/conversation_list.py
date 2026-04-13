"""Shared conversation list — used by both WA and Email inbox pages.

Renders scrollable list of contacts with last message preview.
"""

from __future__ import annotations


def _avatar(name: str, size: int = 32) -> str:
    colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#ec4899", "#14b8a6", "#8b5cf6"]
    bg = colors[hash(name) % len(colors)]
    initials = "".join(w[0].upper() for w in (name or "?").split()[:2])
    return (
        f'<div style="width:{size}px; height:{size}px; border-radius:50%; background:{bg}; '
        f'display:flex; align-items:center; justify-content:center; '
        f'font-size:{size // 3}px; font-weight:700; color:#fff; flex-shrink:0;">{initials}</div>'
    )


def render_wa_conversations(db, search: str = "") -> str:
    """Render WhatsApp conversation list — only contacts with active WA messages."""
    from services.models import WAChat, WAMessage, Contact

    # Get contacts with WA messages
    contact_ids = set()
    for wm in db.query(WAMessage.contact_id).distinct().all():
        contact_ids.add(wm[0])

    if not contact_ids:
        return '<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">No active WhatsApp conversations</div>'

    contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()

    # Get last message + unread count per contact
    items = []
    for c in contacts:
        name = f"{c.first_name} {c.last_name}".strip() or c.company or "Unknown"
        if search and search.lower() not in name.lower():
            continue

        chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
        last_msg = chat.last_message_preview if chat else ""
        unread = chat.unread_count if chat and chat.unread_count else 0
        ts = chat.last_message_at.strftime("%H:%M") if chat and chat.last_message_at else ""

        unread_html = ""
        if unread > 0:
            unread_html = f'<span style="background:#22c55e; color:#fff; border-radius:50%; padding:1px 5px; font-size:9px; font-weight:700;">{unread}</span>'

        items.append((
            chat.last_message_at if chat else None,
            f'<div style="display:flex; align-items:center; gap:10px; padding:8px 10px; '
            f'border-bottom:1px solid rgba(255,255,255,.03); cursor:default;">'
            f'{_avatar(name)}'
            f'<div style="flex:1; min-width:0;">'
            f'<div style="display:flex; justify-content:space-between;">'
            f'<span style="font-weight:600; font-size:11px; color:#e7eaf3;">{name}</span>'
            f'<span style="font-size:9px; color:#64748b;">{ts}</span>'
            f'</div>'
            f'<div style="display:flex; justify-content:space-between; margin-top:1px;">'
            f'<span style="font-size:9px; color:#64748b; white-space:nowrap; overflow:hidden; '
            f'text-overflow:ellipsis; max-width:140px;">{last_msg or "No messages"}</span>'
            f'{unread_html}'
            f'</div></div></div>'
        ))

    # Sort by most recent
    items.sort(key=lambda x: x[0] or __import__("datetime").datetime.min, reverse=True)
    html = "".join(h for _, h in items[:30])
    return f'<div style="max-height:calc(100vh - 280px); overflow-y:auto;">{html}</div>'


def render_email_conversations(db, search: str = "") -> str:
    """Render Email conversation list — only contacts who have been emailed."""
    from services.models import EmailSend, Contact
    from sqlalchemy import func

    # Get contacts with emails, with last email info
    subq = db.query(
        EmailSend.contact_id,
        func.max(EmailSend.created_at).label("last_sent"),
        func.count(EmailSend.id).label("email_count"),
    ).group_by(EmailSend.contact_id).subquery()

    results = db.query(Contact, subq.c.last_sent, subq.c.email_count).join(
        subq, Contact.id == subq.c.contact_id
    ).order_by(subq.c.last_sent.desc()).all()

    if not results:
        return '<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">No emails sent yet</div>'

    items = []
    for contact, last_sent, count in results[:30]:
        name = f"{contact.first_name} {contact.last_name}".strip() or contact.company or "Unknown"
        if search and search.lower() not in name.lower():
            continue

        # Get last email subject
        last_email = db.query(EmailSend).filter(
            EmailSend.contact_id == contact.id
        ).order_by(EmailSend.created_at.desc()).first()
        subject = last_email.subject[:30] if last_email and last_email.subject else "No subject"
        ts = last_sent.strftime("%b %d") if last_sent else ""
        status_color = "#22c55e" if last_email and last_email.status == "sent" else "#ef4444"

        items.append(
            f'<div style="display:flex; align-items:center; gap:10px; padding:8px 10px; '
            f'border-bottom:1px solid rgba(255,255,255,.03); cursor:default;">'
            f'{_avatar(name)}'
            f'<div style="flex:1; min-width:0;">'
            f'<div style="display:flex; justify-content:space-between;">'
            f'<span style="font-weight:600; font-size:11px; color:#e7eaf3;">{name}</span>'
            f'<span style="font-size:9px; color:#64748b;">{ts}</span>'
            f'</div>'
            f'<div style="display:flex; justify-content:space-between; margin-top:1px;">'
            f'<span style="font-size:9px; color:#64748b; white-space:nowrap; overflow:hidden; '
            f'text-overflow:ellipsis; max-width:140px;">✉ {subject}</span>'
            f'<span style="font-size:8px; color:{status_color};">{count} emails</span>'
            f'</div></div></div>'
        )

    html = "".join(items)
    return f'<div style="max-height:calc(100vh - 280px); overflow-y:auto;">{html}</div>'
