"""Tools panel component — shared between WA and Email inbox pages.

Renders: mini contact info, activity log, template preview.
Styles from config/theme/components.yml → tools_panel section.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from components.styles import badge, activity_item, activity_timestamp, activity_text
from services.contact_schema import get_lifecycle_color, get_lifecycle_icon

_COMP_PATH = Path(__file__).resolve().parent.parent / "config" / "theme" / "components.yml"


@lru_cache(maxsize=1)
def _tp():
    with open(_COMP_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("components", {}).get("tools_panel", {})


def _section_title(text: str) -> str:
    c = _tp()
    return (
        f'<div style="font-size:{c.get("section_title_size", "10px")}; '
        f'font-weight:{c.get("section_title_weight", "700")}; '
        f'color:{c.get("section_title_color", "#64748b")}; '
        f'text-transform:{c.get("section_title_transform", "uppercase")}; '
        f'margin-bottom:4px;">{text}</div>'
    )


def _divider() -> str:
    c = _tp()
    return f'<div style="border-top:{c.get("divider", "1px solid rgba(255,255,255,.06)")}; margin:{c.get("section_gap", "10px")} 0;"></div>'


def render_contact_mini(contact, channel: str = "whatsapp") -> str:
    """Compact contact info: name + phone/email."""
    if not contact:
        return ""

    c = _tp()
    name = f"{contact.first_name} {contact.last_name}".strip() or "Unknown"
    detail = contact.wa_id or contact.phone or "" if channel == "whatsapp" else contact.email or ""

    return (
        f'{_section_title("Contact")}'
        f'<div style="font-size:{c.get("contact_name_size", "12px")}; font-weight:600; '
        f'color:{c.get("contact_name_color", "#e7eaf3")};">{name}</div>'
        f'<div style="font-size:{c.get("contact_detail_size", "10px")}; '
        f'color:{c.get("contact_detail_color", "#64748b")};">{detail}</div>'
    )


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def render_contact_card(contact) -> str:
    """Rich contact card: avatar + name + company tag + notes + tags.

    No phone number. Used by the WhatsApp inbox tools panel.
    """
    if not contact:
        return ""

    name = f"{contact.first_name} {contact.last_name}".strip() or "Unknown"
    company = (contact.company or "").strip()
    initials = _initials(name)

    avatar = (
        f'<div style="width:44px; height:44px; border-radius:50%; '
        f'background:linear-gradient(135deg,#6366f1,#8b5cf6); display:flex; '
        f'align-items:center; justify-content:center; font-weight:700; '
        f'font-size:14px; color:#fff; flex-shrink:0;">{initials}</div>'
    )

    company_tag = (
        f'<span style="display:inline-block; margin-top:4px; padding:2px 8px; '
        f'background:rgba(99,102,241,.15); border:1px solid rgba(99,102,241,.35); '
        f'border-radius:10px; font-size:9px; color:#a5b4fc; font-weight:600;">'
        f'{company}</span>'
        if company else ''
    )

    header = (
        f'<div style="display:flex; gap:10px; align-items:center;">'
        f'{avatar}'
        f'<div style="min-width:0; flex:1;">'
        f'<div style="font-size:13px; font-weight:700; color:#e7eaf3; '
        f'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{name}</div>'
        f'{company_tag}'
        f'</div></div>'
    )

    # Tags
    tags_html = ""
    tags = getattr(contact, "tags", None) or []
    if tags:
        chips = "".join(
            f'<span style="display:inline-block; margin:2px 4px 0 0; padding:1px 6px; '
            f'background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08); '
            f'border-radius:8px; font-size:9px; color:#94a3b8;">{t}</span>'
            for t in tags[:8]
        )
        tags_html = f'<div style="margin-top:8px;">{chips}</div>'

    # Notes — full text, not a snippet
    notes_html = ""
    notes = (getattr(contact, "notes", "") or "").strip()
    if notes:
        notes_html = (
            f'<div style="margin-top:10px;">'
            f'{_section_title("Notes")}'
            f'<div style="font-size:10px; color:#94a3b8; line-height:1.5; '
            f'white-space:pre-wrap; word-wrap:break-word;">{notes}</div>'
            f'</div>'
        )

    return f'{header}{tags_html}{notes_html}'


def render_activity(db, contact_id: str, limit: int = 8) -> str:
    """Merged WA + Email activity timeline."""
    if not contact_id:
        return ""

    from services.models import WAMessage, EmailSend

    activities = []

    for wm in db.query(WAMessage).filter(WAMessage.contact_id == contact_id).order_by(WAMessage.created_at.desc()).limit(limit).all():
        ts = wm.created_at.strftime("%b %d %H:%M") if wm.created_at else ""
        d = "received" if wm.direction == "in" else "sent"
        activities.append((
            wm.created_at,
            f'<div style="{activity_item()}"><span style="{activity_timestamp()}">{ts}</span>'
            f'<span style="{activity_text()}">💬 WA {d}</span></div>'
        ))

    for es in db.query(EmailSend).filter(EmailSend.contact_id == contact_id).order_by(EmailSend.created_at.desc()).limit(limit).all():
        ts = es.sent_at.strftime("%b %d %H:%M") if es.sent_at else ""
        activities.append((
            es.sent_at or es.created_at,
            f'<div style="{activity_item()}"><span style="{activity_timestamp()}">{ts}</span>'
            f'<span style="{activity_text()}">✉ Email {es.status}</span></div>'
        ))

    activities.sort(key=lambda x: x[0] or __import__("datetime").datetime.min, reverse=True)
    items = "".join(h for _, h in activities[:limit])

    if not items:
        items = '<div style="color:#64748b; font-size:10px;">No activity yet</div>'

    return f'{_section_title("Activity")}{items}'


_WA_PREVIEW_BOX_STYLE = (
    "background:rgba(15,23,42,.55); border:1px solid rgba(255,255,255,.08); "
    "border-radius:8px; padding:12px; min-height:220px; max-height:320px; "
    "overflow-y:auto; display:flex; flex-direction:column;"
)


def _wa_preview_wrap(inner: str) -> str:
    return f'<div style="{_WA_PREVIEW_BOX_STYLE}">{inner}</div>'


def render_wa_template_preview(template_name: str) -> str:
    """Preview a WhatsApp template from YAML config.

    Always returns a fixed-height container so selecting different templates
    does not reflow Panel 3. Renders full body text (not just metadata)."""
    if not template_name:
        return _wa_preview_wrap(
            '<div style="display:flex; align-items:center; justify-content:center; '
            'flex:1; color:#64748b; font-size:10px;">Select a template to preview</div>'
        )

    from services.wa_config import get_wa_config
    tpl = get_wa_config().get_template(template_name)
    if not tpl:
        return _wa_preview_wrap(
            f'<div style="color:#ef4444; font-size:10px;">"{template_name}" not found</div>'
        )

    # Variables
    vars_html = ""
    if tpl.variables:
        chips = "".join(
            f'<span style="display:inline-block; margin:2px 4px 0 0; padding:1px 6px; '
            f'background:rgba(99,102,241,.12); border:1px solid rgba(99,102,241,.3); '
            f'border-radius:6px; font-size:9px; color:#a5b4fc;">{{{{{v.name}}}}}</span>'
            for v in tpl.variables
        )
        vars_html = (
            f'<div style="margin-top:8px;">'
            f'<div style="font-size:9px; color:#64748b; text-transform:uppercase; '
            f'font-weight:700; margin-bottom:3px;">Variables</div>{chips}</div>'
        )

    # Body text — full rendering
    body = getattr(tpl, "body", None) or getattr(tpl, "body_text", None) or ""
    body_html = ""
    if body:
        body_html = (
            f'<div style="margin-top:8px; padding:8px 10px; '
            f'background:rgba(34,197,94,.05); border-left:2px solid rgba(34,197,94,.4); '
            f'border-radius:4px; font-size:11px; color:#e7eaf3; line-height:1.5; '
            f'white-space:pre-wrap; word-wrap:break-word;">{body}</div>'
        )

    header = (
        f'<div style="display:flex; justify-content:space-between; align-items:start; gap:8px;">'
        f'<div style="font-size:12px; font-weight:700; color:#e7eaf3; flex:1;">{tpl.display_name}</div>'
        f'<span style="{badge("#6366f1")}">{tpl.category}</span>'
        f'</div>'
    )

    desc_html = (
        f'<div style="font-size:10px; color:#94a3b8; margin-top:4px; line-height:1.4;">{tpl.description}</div>'
        if tpl.description else ''
    )
    use_case_html = (
        f'<div style="font-size:9px; color:#64748b; margin-top:4px; font-style:italic;">Use case: {tpl.use_case}</div>'
        if getattr(tpl, "use_case", None) else ''
    )

    return _wa_preview_wrap(f'{header}{desc_html}{use_case_html}{body_html}{vars_html}')


def render_email_template_preview(template_slug: str) -> str:
    """Preview an email template — name + subject + truncated text."""
    if not template_slug:
        return '<div style="color:#64748b; font-size:10px;">Select a template</div>'

    from services.database import get_db
    from services.models import EmailTemplate
    import re

    db = get_db()
    try:
        tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
        if not tpl:
            return f'<div style="color:#64748b; font-size:10px;">"{template_slug}" not found</div>'

        # Extract plain text preview from HTML
        plain = re.sub("<[^<]+?>", "", tpl.html_content or "")
        plain = re.sub(r"\s+", " ", plain).strip()[:200]

        c = _tp()
        cat_color = "#6366f1" if tpl.category == "campaign" else "#14b8a6"

        return (
            f'<div style="background:{c.get("preview_bg")}; border:{c.get("preview_border")}; '
            f'border-radius:{c.get("preview_radius")}; padding:{c.get("preview_padding")};">'
            f'<div style="font-size:11px; font-weight:600; color:#e7eaf3;">{tpl.name}</div>'
            f'<div style="font-size:10px; color:#94a3b8; margin-top:2px;">Subject: {tpl.subject_template}</div>'
            f'<div style="font-size:9px; color:#64748b; margin-top:4px; line-height:1.4;">{plain}...</div>'
            f'<div style="margin-top:4px;"><span style="{badge(cat_color)}">{tpl.category}</span></div>'
            f'</div>'
        )
    finally:
        db.close()


def render_tools_empty(message: str = "Select a conversation to see tools") -> str:
    """Empty state for Panel 3."""
    return f'<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">{message}</div>'


def render_full_tools(db, contact_id: str, channel: str = "whatsapp") -> str:
    """Render the complete tools panel.

    WhatsApp: rich contact card (name + company tag, no phone) + notes + tags
    + activity timeline. Templates section header is not included here — the
    template dropdown/preview lives as separate Gradio components below.
    """
    if not contact_id:
        return render_tools_empty()

    from services.models import Contact
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return render_tools_empty("Contact not found")

    if channel == "whatsapp":
        card = render_contact_card(contact)
    else:
        card = render_contact_mini(contact, channel)

    div = _divider()
    act = render_activity(db, contact_id)

    return f'<div style="padding:10px;">{card}{div}{act}</div>'
