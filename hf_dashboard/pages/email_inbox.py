"""Email Inbox — 3-panel: Radio contacts | Email thread | Tools panel.

Panel 1: Radio list of emailed contacts (clickable). Search queries all contacts.
Panel 2: Email thread view — sent emails per contact
Panel 3: Mini contact + Activity + Email template selector/preview + Subject + Send
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
import yaml

from components.styles import section_card, badge
from components.tools_panel import render_full_tools, render_email_template_preview, render_tools_empty
from services.contact_schema import get_lifecycle_choices, get_lifecycle_id_by_label

_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "email_inbox.yml"


def _cfg():
    with open(_CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


def _get_emailed_contacts(db):
    from services.models import EmailSend, Contact
    from sqlalchemy import func
    sub = db.query(EmailSend.contact_id, func.max(EmailSend.created_at).label("last")).group_by(EmailSend.contact_id).subquery()
    results = db.query(Contact, sub.c.last).join(sub, Contact.id == sub.c.contact_id).order_by(sub.c.last.desc()).all()

    convs = []
    for c, last_sent in results[:30]:
        name = f"{c.first_name} {c.last_name}".strip() or c.company or "Unknown"
        last_email = db.query(EmailSend).filter(EmailSend.contact_id == c.id).order_by(EmailSend.created_at.desc()).first()
        subj = (last_email.subject or "")[:20] if last_email else "..."
        ts = last_sent.strftime("%b %d") if last_sent else ""
        convs.append((f"{name} — ✉ {subj} {ts}", c.id))
    return convs


def _build_email_thread(db, contact_id):
    if not contact_id:
        cfg = _cfg()
        return f'<div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:50vh; color:#64748b;"><div style="font-size:28px; margin-bottom:8px;">✉</div><div style="font-size:13px;">{cfg.get("column_2", {}).get("empty_message", "Select a contact")}</div></div>'

    from services.models import Contact, EmailSend
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return '<div style="color:#ef4444;">Not found</div>'

    name = f"{contact.first_name} {contact.last_name}".strip() or "Unknown"
    header = (
        f'<div style="padding:10px 14px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06);">'
        f'<div style="font-weight:700; font-size:13px; color:#e7eaf3;">{name}</div>'
        f'<div style="font-size:10px; color:#64748b;">{contact.email or "—"}</div></div>'
    )

    emails = db.query(EmailSend).filter(EmailSend.contact_id == contact.id).order_by(EmailSend.created_at.desc()).limit(20).all()
    if not emails:
        return header + '<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">No emails sent. Use the template selector in the right panel.</div>'

    items = ""
    for es in emails:
        sc = "#22c55e" if es.status == "sent" else "#ef4444"
        ts = es.sent_at.strftime("%b %d, %H:%M") if es.sent_at else "—"
        items += (
            f'<div style="{section_card()}; margin:6px 0;">'
            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
            f'<div><div style="font-size:12px; font-weight:600; color:#e7eaf3;">{es.subject or "No subject"}</div>'
            f'<div style="font-size:10px; color:#64748b; margin-top:2px;">To: {es.contact_email} · {ts}</div></div>'
            f'<span style="{badge(sc)}">{es.status}</span></div></div>'
        )

    return f'<div style="border:1px solid rgba(255,255,255,.06); border-radius:8px; overflow:hidden;">{header}<div style="max-height:calc(100vh - 300px); overflow-y:auto; padding:8px 14px;">{items}</div></div>'


def build(ctx):
    cfg = _cfg()

    with gr.Row():
        gr.HTML(f'<div style="font-size:15px; font-weight:700; color:#e7eaf3;">{cfg.get("title", "Email Inbox")}</div>')
        contact_search = gr.Textbox(placeholder=cfg.get("column_1", {}).get("search_placeholder", "Search..."), label="", container=False, scale=2)
        refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=120)

    with gr.Row():
        # ═══ PANEL 1: Contact list ═══
        with gr.Column(scale=1, min_width=260, elem_classes=["conv-list-panel"]):
            contact_radio = gr.Radio(label=cfg.get("column_1", {}).get("title", "Sent Emails"), choices=[], interactive=True)

        # ═══ PANEL 2: Email thread ═══
        with gr.Column(scale=2, min_width=400, elem_classes=["chat-panel"]):
            thread_html = gr.HTML(value="")

        # ═══ PANEL 3: Tools ═══
        with gr.Column(scale=1, min_width=250, elem_classes=["tools-panel"]):
            tools_html = gr.HTML(value=render_tools_empty(cfg.get("column_3", {}).get("empty_message", "")))
            tpl_dropdown = gr.Dropdown(label="Select Template", choices=[], interactive=True)
            tpl_preview = gr.HTML(value="")
            subject_input = gr.Textbox(label="Subject", placeholder="Email subject...", container=False)
            send_btn = gr.Button("Send Email", variant="primary", size="sm")
            send_result = gr.HTML(value="")
            gr.HTML('<div style="height:1px; background:rgba(255,255,255,.06); margin:8px 0;"></div>')
            edit_lifecycle = gr.Dropdown(label="Lifecycle", choices=get_lifecycle_choices(include_all=False), interactive=True)
            edit_tags = gr.Textbox(label="Tags", placeholder="comma separated", container=False)
            edit_result = gr.HTML(value="")

    contact_map = gr.State({})

    # Search ALL contacts (not just emailed)
    def _search(text):
        if not text or len(text) < 2:
            from services.database import get_db
            db = get_db()
            try:
                convs = _get_emailed_contacts(db)
                return gr.update(choices=[l for l, _ in convs], value=None), {l: c for l, c in convs}
            finally:
                db.close()

        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            term = f"%{text}%"
            contacts = db.query(Contact).filter(
                Contact.email.isnot(None), ~Contact.email.like("%placeholder%"),
                (Contact.first_name.like(term)) | (Contact.last_name.like(term)) | (Contact.company.like(term))
            ).limit(20).all()
            choices = [f"{c.first_name} {c.last_name} — {c.email} ({c.id})" for c in contacts]
            return gr.update(choices=choices, value=None), {l: l.split("(")[-1].rstrip(")") for l in choices}
        finally:
            db.close()

    contact_search.change(fn=_search, inputs=[contact_search], outputs=[contact_radio, contact_map])

    # Select contact
    def _on_select(choice, cmap):
        if not choice or not cmap:
            return "", render_tools_empty(), ""
        cid = cmap.get(choice, "")
        if not cid:
            return "", render_tools_empty(), ""
        from services.database import get_db
        db = get_db()
        try:
            return _build_email_thread(db, cid), render_full_tools(db, cid, "email"), ""
        finally:
            db.close()

    contact_radio.change(fn=_on_select, inputs=[contact_radio, contact_map], outputs=[thread_html, tools_html, send_result])

    # Template preview
    tpl_dropdown.change(fn=render_email_template_preview, inputs=[tpl_dropdown], outputs=[tpl_preview])

    # Send email
    def _send(choice, tpl_slug, subject, cmap):
        if not choice:
            return '<div style="color:#ef4444; font-size:10px;">Select a contact</div>'
        if not tpl_slug:
            return '<div style="color:#ef4444; font-size:10px;">Select a template</div>'
        if not subject:
            return '<div style="color:#ef4444; font-size:10px;">Enter a subject</div>'

        cid = cmap.get(choice, "")
        from services.database import get_db
        from services.models import Contact, EmailTemplate, EmailSend
        from services.email_sender import EmailSender, generate_idempotency_key
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == cid).first()
            if not c or not c.email or "placeholder" in c.email:
                return '<div style="color:#ef4444; font-size:10px;">No valid email</div>'

            tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == tpl_slug).first()
            if not tpl:
                return '<div style="color:#ef4444; font-size:10px;">Template not found</div>'

            sender = EmailSender()
            if not sender.is_configured():
                return '<div style="color:#ef4444; font-size:10px;">Gmail API not configured</div>'

            variables = {
                "name": f"{c.first_name} {c.last_name}".strip() or "there",
                "first_name": c.first_name or "there",
                "company_name": c.company or "your company",
                "email": c.email,
            }
            rs = sender.render_template(subject, variables)
            rh = sender.render_template(tpl.html_content, variables)

            ik = generate_idempotency_key("inbox_email", c.id)
            if db.query(EmailSend).filter(EmailSend.idempotency_key == ik).first():
                return '<div style="color:#f59e0b; font-size:10px;">Already sent today</div>'

            result = sender.send_email(c.email, rs, rh, to_name=c.first_name)
            db.add(EmailSend(
                contact_id=c.id, contact_email=c.email, subject=rs,
                status="sent" if result["success"] else "failed",
                idempotency_key=ik,
                error_message="" if result["success"] else result.get("message", ""),
                sent_at=datetime.now(timezone.utc) if result["success"] else None,
            ))
            db.commit()
            return f'<div style="color:#22c55e; font-size:10px;">Email sent to {c.email}</div>' if result["success"] else f'<div style="color:#ef4444; font-size:10px;">{result["message"]}</div>'
        finally:
            db.close()

    send_btn.click(fn=_send, inputs=[contact_radio, tpl_dropdown, subject_input, contact_map], outputs=[send_result])

    # Edit lifecycle
    def _save_lc(choice, lc, cmap):
        if not choice or not lc:
            return ""
        cid = cmap.get(choice, "")
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == cid).first()
            if c:
                c.lifecycle = get_lifecycle_id_by_label(lc) or "new_lead"
                db.commit()
                return f'<div style="color:#22c55e; font-size:10px;">→ {lc}</div>'
            return ""
        finally:
            db.close()

    edit_lifecycle.change(fn=_save_lc, inputs=[contact_radio, edit_lifecycle, contact_map], outputs=[edit_result])

    # Edit tags
    def _save_tags(choice, tags, cmap):
        if not choice:
            return ""
        cid = cmap.get(choice, "")
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == cid).first()
            if c:
                c.tags = [t.strip() for t in (tags or "").split(",") if t.strip()]
                db.commit()
                return f'<div style="color:#22c55e; font-size:10px;">Saved</div>'
            return ""
        finally:
            db.close()

    edit_tags.change(fn=_save_tags, inputs=[contact_radio, edit_tags, contact_map], outputs=[edit_result])

    # Refresh
    def _do_refresh():
        from services.database import get_db
        from services.models import EmailTemplate
        db = get_db()
        try:
            convs = _get_emailed_contacts(db)
            tpls = [t.slug for t in db.query(EmailTemplate).filter(EmailTemplate.is_active == True).all()]
            return (
                gr.update(choices=[l for l, _ in convs], value=None),
                {l: c for l, c in convs},
                _build_email_thread(db, None), render_tools_empty(), "",
                gr.update(choices=tpls, value=None), "",
            )
        finally:
            db.close()

    refresh_btn.click(fn=_do_refresh, outputs=[contact_radio, contact_map, thread_html, tools_html, send_result, tpl_dropdown, tpl_preview])

    def _refresh():
        return _do_refresh()

    return {"update_fn": _refresh, "outputs": [contact_radio, contact_map, thread_html, tools_html, send_result, tpl_dropdown, tpl_preview]}
