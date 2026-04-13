"""WhatsApp Inbox — 3-panel: Conversations | Chat | Tools.

Panel 1: Full-height radio list of active conversations
Panel 2: Chat with header bar + bubbles + send at bottom
Panel 3: Refresh + Template selector/preview + Send Template
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import gradio as gr
import yaml

from components.styles import chat_bubble, chat_timestamp
from components.tools_panel import render_full_tools, render_wa_template_preview, render_tools_empty

_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "wa_inbox.yml"


def _cfg():
    with open(_CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


def _get_active_conversations(db):
    """Return list of (label, contact_id) tuples for Radio choices.

    Label embeds name + company + preview + timestamp in a Gradio-safe ASCII
    format. The Radio value is the contact_id directly (no map indirection).
    """
    from services.models import WAMessage, WAChat, Contact
    contact_ids = set(r[0] for r in db.query(WAMessage.contact_id).distinct().all())
    if not contact_ids:
        return []
    convs = []
    for cid in contact_ids:
        c = db.query(Contact).filter(Contact.id == cid).first()
        if not c:
            continue
        name = f"{c.first_name} {c.last_name}".strip() or c.company or "Unknown"
        company = (c.company or "").strip()
        chat = db.query(WAChat).filter(WAChat.contact_id == cid).first()
        preview = ((chat.last_message_preview or "") if chat else "")[:28]
        ts = chat.last_message_at.strftime("%H:%M") if chat and chat.last_message_at else ""
        unread = f" ({chat.unread_count})" if chat and chat.unread_count else ""
        header = f"{name} - {company}" if company else name
        tail = f"{preview}" + (f"  {ts}" if ts else "") + unread
        label = f"{header}\n{tail}" if tail.strip() else header
        convs.append((chat.last_message_at if chat else None, label, str(cid)))
    convs.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [(label, cid) for _, label, cid in convs]


def _system_event(text):
    return f'<div style="text-align:center; padding:3px 0;"><span style="font-size:9px; color:#64748b;">○ {text}</span></div>'


def _build_chat_header(db, contact_id):
    """Top bar for Panel 2 — contact name or placeholder."""
    if not contact_id:
        return '<div style="padding:12px 16px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06); font-size:13px; color:#64748b;">Select a conversation</div>'

    from services.models import Contact
    c = db.query(Contact).filter(Contact.id == contact_id).first()
    if not c:
        return '<div style="padding:12px 16px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06); font-size:13px; color:#64748b;">Contact not found</div>'

    name = f"{c.first_name} {c.last_name}".strip() or "Unknown"

    # 24h window
    now = datetime.now(timezone.utc)
    wtext = ""
    if c.last_wa_inbound_at:
        last = c.last_wa_inbound_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = now - last
        if delta.total_seconds() < 86400:
            r = timedelta(hours=24) - delta
            wtext = f'<span style="color:#22c55e; font-size:10px;">● {int(r.total_seconds()//3600)}h left</span>'
        else:
            wtext = '<span style="color:#f59e0b; font-size:10px;">○ closed</span>'
    else:
        wtext = '<span style="color:#f59e0b; font-size:10px;">○ no inbound</span>'

    return (
        f'<div style="padding:10px 16px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06); '
        f'display:flex; justify-content:space-between; align-items:center;">'
        f'<div><div style="font-weight:700; font-size:13px; color:#e7eaf3;">{name}</div>'
        f'<div style="font-size:10px; color:#64748b;">{c.wa_id or c.phone or ""}</div></div>'
        f'{wtext}</div>'
    )


def _build_chat_messages(db, contact_id):
    """Chat bubbles only — no header."""
    if not contact_id:
        return '<div style="display:flex; align-items:center; justify-content:center; height:40vh; color:#64748b; font-size:12px;">💬 Pick a chat to start</div>'

    from services.models import Contact, WAMessage
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return ''

    cfg = _cfg().get("column_2", {})
    events = cfg.get("system_events", {})
    wcfg = cfg.get("window_warning", {})

    # System events
    sys = ""
    if contact.created_at:
        sys += f'<div style="text-align:center; padding:6px 0;"><span style="background:rgba(255,255,255,.06); padding:2px 8px; border-radius:6px; font-size:9px; color:#64748b;">{contact.created_at.strftime("%B %d, %Y")}</span></div>'
        sys += _system_event(events.get("contact_added", "Contact added by you"))
    first_out = db.query(WAMessage).filter(WAMessage.contact_id == contact.id, WAMessage.direction == "out").order_by(WAMessage.created_at.asc()).first()
    if first_out:
        sys += _system_event(events.get("conversation_opened", "Conversation opened by you"))

    msgs = db.query(WAMessage).filter(WAMessage.contact_id == contact.id).order_by(WAMessage.created_at.asc()).limit(50).all()
    bubbles = ""
    ld = ""
    for m in msgs:
        d = m.created_at.strftime("%B %d, %Y") if m.created_at else ""
        if d and d != ld:
            bubbles += f'<div style="text-align:center; padding:6px 0;"><span style="background:rgba(255,255,255,.06); padding:2px 8px; border-radius:6px; font-size:9px; color:#64748b;">{d}</span></div>'
            ld = d
        ts = m.created_at.strftime("%H:%M") if m.created_at else ""
        si = ""
        if m.direction == "out":
            icons = {"sent": "✓", "delivered": "✓✓", "read": "✓✓", "failed": "✗"}
            si = f'<span style="color:{"#6366f1" if m.status == "read" else "#64748b"}; font-size:9px;">{icons.get(m.status, "")}</span>'
        bubbles += f'<div style="{chat_bubble(m.direction)}"><div style="font-size:12px; color:#e7eaf3; line-height:1.4;">{m.text or ""}</div><div style="display:flex; justify-content:flex-end; gap:4px; margin-top:2px;"><span style="{chat_timestamp()}">{ts}</span>{si}</div></div>'

    if not msgs:
        bubbles = '<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">No messages. Use templates in the right panel →</div>'

    # Window warning
    now = datetime.now(timezone.utc)
    warn = ""
    in_window = False
    if contact.last_wa_inbound_at:
        last = contact.last_wa_inbound_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        in_window = (now - last).total_seconds() < 86400
    if not in_window:
        warn = f'<div style="background:rgba(245,158,11,.06); border-top:1px solid rgba(245,158,11,.15); padding:8px 14px;"><div style="font-size:10px; color:#f59e0b; font-weight:600;">⚠ {wcfg.get("title", "Window closed")}</div><div style="font-size:9px; color:#64748b; margin-top:2px;">{wcfg.get("detail", "Use template.")}</div></div>'

    return f'<div style="max-height:calc(100vh - 260px); overflow-y:auto; padding:8px 14px;">{sys}{bubbles}</div>{warn}'


def build(ctx):
    cfg = _cfg()

    placeholder_header = '<div style="padding:12px 16px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06); font-size:13px; color:#64748b;">Select a conversation</div>'
    placeholder_messages = '<div style="display:flex; align-items:center; justify-content:center; height:40vh; color:#64748b; font-size:12px;">Pick a chat to start</div>'

    with gr.Row():
        # ═══ PANEL 1: Conversations ═══
        with gr.Column(scale=1, min_width=260, elem_classes=["conv-list-panel"]):
            search_box = gr.Textbox(placeholder="Search...", label="", container=False)
            conversation_radio = gr.Radio(label="Active Chats", choices=[], interactive=True, elem_classes=["wa-conv-radio"])

        # ═══ PANEL 2: Chat ═══
        with gr.Column(scale=2, min_width=400, elem_classes=["chat-panel"]):
            chat_header = gr.HTML(value=placeholder_header)
            chat_messages = gr.HTML(value=placeholder_messages)
            with gr.Row():
                msg_input = gr.Textbox(placeholder="Type a message...", label="", container=False, scale=6)
                send_btn = gr.Button("Send", size="sm", variant="primary", scale=1)
            send_result = gr.HTML(value="")

        # ═══ PANEL 3: Contact details + Templates + Refresh ═══
        with gr.Column(scale=1, min_width=260, elem_classes=["tools-panel"]):
            tools_html = gr.HTML(value=render_tools_empty())
            gr.HTML('<div style="height:1px; background:rgba(255,255,255,.06); margin:10px 0;"></div>')
            tpl_dropdown = gr.Dropdown(label="Select Template", choices=[], interactive=True)
            tpl_preview = gr.HTML(value=render_wa_template_preview(""))
            send_tpl_btn = gr.Button("Send Template", variant="primary", size="sm")
            send_tpl_result = gr.HTML(value="")
            gr.HTML('<div style="height:1px; background:rgba(255,255,255,.06); margin:10px 0;"></div>')
            refresh_btn = gr.Button("🔄 Refresh", size="sm", variant="secondary")

    def _on_select(contact_id):
        if not contact_id:
            return placeholder_header, placeholder_messages, render_tools_empty(), ""
        from services.database import get_db
        db = get_db()
        try:
            return (
                _build_chat_header(db, contact_id),
                _build_chat_messages(db, contact_id),
                render_full_tools(db, contact_id, "whatsapp"),
                "",
            )
        finally:
            db.close()

    conversation_radio.change(
        fn=_on_select,
        inputs=[conversation_radio],
        outputs=[chat_header, chat_messages, tools_html, send_result],
    )

    def _search(text):
        from services.database import get_db
        db = get_db()
        try:
            convs = _get_active_conversations(db)
            if text and len(text) >= 2:
                t = text.lower()
                convs = [(l, cid) for l, cid in convs if t in l.lower()]
            return gr.update(choices=convs, value=None)
        finally:
            db.close()

    search_box.change(fn=_search, inputs=[search_box], outputs=[conversation_radio])

    tpl_dropdown.change(fn=render_wa_template_preview, inputs=[tpl_dropdown], outputs=[tpl_preview])

    def _send_text(contact_id, msg):
        if not contact_id or not msg:
            return '<div style="color:#ef4444; font-size:10px;">Select chat + type message</div>'
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            if not c or not c.wa_id:
                return '<div style="color:#ef4444; font-size:10px;">No WhatsApp ID on contact</div>'
            now = datetime.now(timezone.utc)
            if c.last_wa_inbound_at:
                last = c.last_wa_inbound_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() > 86400:
                    return '<div style="color:#f59e0b; font-size:10px;">Outside 24h window — use a template</div>'
            else:
                return '<div style="color:#f59e0b; font-size:10px;">No inbound yet — use a template</div>'
            from services.wa_sender import WhatsAppSender
            ok, _, err = WhatsAppSender().send_text(c.wa_id, msg)
            if ok:
                return '<div style="color:#22c55e; font-size:10px;">Sent ✓</div>'
            return f'<div style="color:#ef4444; font-size:10px;">{err or "Send failed"}</div>'
        finally:
            db.close()

    send_btn.click(fn=_send_text, inputs=[conversation_radio, msg_input], outputs=[send_result])

    def _send_tpl(contact_id, tpl):
        if not contact_id or not tpl:
            return '<div style="color:#ef4444; font-size:10px;">Select chat + template</div>'
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            if not c or not c.wa_id:
                return '<div style="color:#ef4444; font-size:10px;">No WhatsApp ID on contact</div>'
            from services.wa_sender import WhatsAppSender
            ok, _, err = WhatsAppSender().send_template(c.wa_id, tpl)
            if ok:
                return '<div style="color:#22c55e; font-size:10px;">Template sent ✓</div>'
            return f'<div style="color:#ef4444; font-size:10px;">{err or "Send failed"}</div>'
        finally:
            db.close()

    send_tpl_btn.click(fn=_send_tpl, inputs=[conversation_radio, tpl_dropdown], outputs=[send_tpl_result])

    def _do_refresh():
        from services.database import get_db
        from services.wa_config import get_wa_config
        db = get_db()
        try:
            convs = _get_active_conversations(db)
            tpls = get_wa_config().get_template_names()
            return (
                gr.update(choices=convs, value=None),
                placeholder_header,
                placeholder_messages,
                render_tools_empty(),
                "",
                gr.update(choices=tpls, value=None),
                render_wa_template_preview(""),
            )
        finally:
            db.close()

    refresh_btn.click(
        fn=_do_refresh,
        outputs=[conversation_radio, chat_header, chat_messages, tools_html, send_result, tpl_dropdown, tpl_preview],
    )

    return {
        "update_fn": _do_refresh,
        "outputs": [conversation_radio, chat_header, chat_messages, tools_html, send_result, tpl_dropdown, tpl_preview],
    }
