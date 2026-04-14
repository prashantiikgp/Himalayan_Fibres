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


_AVATAR_EMOJIS = ["🙂", "😊", "😎", "🤗", "🧑", "👤", "🧔", "👨", "👩", "🦊", "🐼", "🐻", "🐯", "🦁", "🐸", "🦄"]


def _avatar_for(contact_id: str) -> str:
    """Deterministic emoji avatar based on contact id — stable across reloads."""
    h = 0
    for ch in str(contact_id):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _AVATAR_EMOJIS[h % len(_AVATAR_EMOJIS)]


def _get_active_conversations(db):
    """Return list of (label, contact_id) tuples for Radio choices.

    Label embeds an emoji avatar + name + company + preview + timestamp in a
    Gradio-safe ASCII format. The Radio value is the contact_id directly.

    Plan D Phase 1.1: was 1 + 2N queries (distinct contact_ids → loop →
    Contact.filter.first() + WAChat.filter.first() per contact). Rewrote as
    a single JOIN query selecting only the 7 columns this renderer uses —
    ~100 queries/load → 1 query/load.
    """
    from services.models import WAMessage, WAChat, Contact

    # One query: all contacts that have at least one WAMessage, left-joined
    # with WAChat for preview/ts/unread. Column-tuple form — SQLAlchemy
    # fetches only these 7 columns over the wire, not full 38-col Contact
    # rows. outerjoin so contacts with a message but no chat row still
    # appear (edge case during migration / webhook races).
    rows = (
        db.query(
            Contact.id,
            Contact.first_name,
            Contact.last_name,
            Contact.company,
            WAChat.last_message_at,
            WAChat.last_message_preview,
            WAChat.unread_count,
        )
        .outerjoin(WAChat, WAChat.contact_id == Contact.id)
        .filter(Contact.id.in_(db.query(WAMessage.contact_id).distinct()))
        .all()
    )

    convs = []
    for cid, first, last, company_raw, last_msg_at, preview_raw, unread_count in rows:
        name = f"{first or ''} {last or ''}".strip() or (company_raw or "") or "Unknown"
        company = (company_raw or "").strip()
        preview = (preview_raw or "")[:28]
        ts = last_msg_at.strftime("%H:%M") if last_msg_at else ""
        unread = f" ({unread_count})" if unread_count else ""
        emoji = _avatar_for(cid)
        header = f"{emoji}  {name}" + (f" · {company}" if company else "")
        tail = f"{preview}" + (f"  {ts}" if ts else "") + unread
        label = f"{header}\n     {tail}" if tail.strip() else header
        convs.append((last_msg_at, label, str(cid)))

    convs.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [(label, cid) for _, label, cid in convs]


def _search_all_contacts(db, term: str, limit: int = 20):
    """Case-insensitive search across ALL WhatsApp-capable contacts.

    Used by the "Start New Conversation" section so the user can initiate a
    chat with a contact that has no prior WAMessage history. Filters out
    contacts without a wa_id since they can't receive WhatsApp messages.
    """
    from services.models import Contact
    if not term or len(term.strip()) < 2:
        return []
    q = f"%{term.strip()}%"
    contacts = (
        db.query(Contact)
        .filter(Contact.wa_id.isnot(None))
        .filter(
            Contact.first_name.ilike(q)
            | Contact.last_name.ilike(q)
            | Contact.company.ilike(q)
        )
        .order_by(Contact.company, Contact.first_name)
        .limit(limit)
        .all()
    )
    results = []
    for c in contacts:
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or "Unknown"
        company = (c.company or "").strip()
        emoji = _avatar_for(c.id)
        header = f"{emoji}  {name}" + (f" · {company}" if company else "")
        results.append((header, str(c.id)))
    return results


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


# Map file extensions → (Meta API media type, display emoji)
_MEDIA_KIND_BY_EXT = {
    ".jpg": ("image", "🖼"),
    ".jpeg": ("image", "🖼"),
    ".png": ("image", "🖼"),
    ".webp": ("image", "🖼"),
    ".mp4": ("video", "🎬"),
    ".3gp": ("video", "🎬"),
    ".pdf": ("document", "📄"),
    ".doc": ("document", "📄"),
    ".docx": ("document", "📄"),
    ".xls": ("document", "📄"),
    ".xlsx": ("document", "📄"),
    ".ppt": ("document", "📄"),
    ".pptx": ("document", "📄"),
    ".txt": ("document", "📄"),
    ".csv": ("document", "📄"),
    ".mp3": ("audio", "🎤"),
    ".ogg": ("audio", "🎤"),
    ".opus": ("audio", "🎤"),
    ".aac": ("audio", "🎤"),
    ".amr": ("audio", "🎤"),
    ".m4a": ("audio", "🎤"),
}


def _media_info_for_filename(filename: str) -> tuple[str, str]:
    """Return (meta_media_type, emoji) for a filename, defaulting to document."""
    from pathlib import Path as _P
    ext = _P(filename).suffix.lower()
    return _MEDIA_KIND_BY_EXT.get(ext, ("document", "📄"))


def _render_message_body(m) -> str:
    """HTML for one message bubble's body — handles text + media consistently."""
    text = (m.text or m.media_caption or "").strip()
    if m.media_type:
        kind = (m.media_type or "").lower()
        icon = {"image": "🖼", "video": "🎬", "document": "📄", "audio": "🎤"}.get(kind, "📎")
        fname = ""
        if m.media_path:
            fname = m.media_path.rsplit("/", 1)[-1]
        header = (
            f'<div style="display:flex; align-items:center; gap:6px; '
            f'background:rgba(99,102,241,.08); padding:6px 8px; border-radius:6px; '
            f'margin-bottom:4px; font-size:11px; color:#c7d2fe;">'
            f'<span style="font-size:14px;">{icon}</span>'
            f'<span>{kind.title()}{" · " + fname if fname else ""}</span>'
            f'</div>'
        )
        body = f'<div style="font-size:12px; color:#e7eaf3; line-height:1.4;">{text}</div>' if text else ""
        return header + body
    return f'<div style="font-size:12px; color:#e7eaf3; line-height:1.4;">{text}</div>'


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
    new_cfg = cfg.get("new_conversation_warning", {})

    # System events
    sys = ""
    if contact.created_at:
        sys += f'<div style="text-align:center; padding:6px 0;"><span style="background:rgba(255,255,255,.06); padding:2px 8px; border-radius:6px; font-size:9px; color:#64748b;">{contact.created_at.strftime("%B %d, %Y")}</span></div>'
        sys += _system_event(events.get("contact_added", "Contact added by you"))
    first_out = db.query(WAMessage).filter(WAMessage.contact_id == contact.id, WAMessage.direction == "out").order_by(WAMessage.created_at.asc()).first()
    if first_out:
        sys += _system_event(events.get("conversation_opened", "Conversation opened by you"))

    msgs = db.query(WAMessage).filter(WAMessage.contact_id == contact.id).order_by(WAMessage.created_at.asc()).limit(50).all()

    # Charge banner for contacts with zero message history — they're being
    # selected from "Start New Conversation" and we need to warn about the
    # billable window opening on first template send.
    new_conv_banner = ""
    if not msgs:
        new_title = new_cfg.get("title", "No conversation yet")
        new_detail = new_cfg.get(
            "detail",
            "Sending a template will open a 24-hour service window and incur a WhatsApp conversation fee.",
        )
        new_conv_banner = (
            '<div style="background:rgba(245,158,11,.08); border:1px solid rgba(245,158,11,.22);'
            ' border-radius:8px; padding:10px 12px; margin:10px 14px;">'
            f'<div style="font-size:11px; color:#f59e0b; font-weight:700;">⚠ {new_title}</div>'
            f'<div style="font-size:10px; color:#94a3b8; margin-top:4px; line-height:1.4;">{new_detail}</div>'
            '</div>'
        )
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
        body_html = _render_message_body(m)
        bubbles += (
            f'<div style="{chat_bubble(m.direction)}">{body_html}'
            f'<div style="display:flex; justify-content:flex-end; gap:4px; margin-top:2px;">'
            f'<span style="{chat_timestamp()}">{ts}</span>{si}</div></div>'
        )

    if not msgs:
        bubbles = new_conv_banner or (
            '<div style="text-align:center; padding:30px; color:#64748b; font-size:11px;">'
            'No messages. Use templates in the right panel →</div>'
        )

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
    col1_cfg = cfg.get("column_1", {})
    new_conv_cfg = col1_cfg.get("new_conversation", {})

    placeholder_header = '<div style="padding:12px 16px; background:rgba(15,23,42,.60); border-bottom:1px solid rgba(255,255,255,.06); font-size:13px; color:#64748b;">Select a conversation</div>'
    placeholder_messages = '<div style="display:flex; align-items:center; justify-content:center; height:40vh; color:#64748b; font-size:12px;">Pick a chat to start</div>'

    # Shared currently-selected contact_id, updated from either the Active
    # Chats radio or the Start New Conversation radio. Send handlers read
    # from this State so they work no matter which list the user picked from.
    selected_cid_state = gr.State("")

    with gr.Row():
        # ═══ PANEL 1: Conversations (Active + Start New) ═══
        with gr.Column(scale=1, min_width=260, elem_classes=["conv-list-panel"]):
            gr.HTML(
                f'<div class="conv-section-title">{col1_cfg.get("title", "Active Chats")}</div>'
            )
            search_box = gr.Textbox(
                placeholder=col1_cfg.get("search_placeholder", "Search active..."),
                label="", container=False,
            )
            conversation_radio = gr.Radio(
                label="", choices=[], interactive=True,
                elem_classes=["wa-conv-radio"],
            )
            gr.HTML('<div class="conv-section-divider"></div>')
            gr.HTML(
                f'<div class="conv-section-title">{new_conv_cfg.get("title", "Start New Conversation")}</div>'
            )
            new_conv_search = gr.Textbox(
                placeholder=new_conv_cfg.get("search_placeholder", "Search contact..."),
                label="", container=False,
            )
            new_conv_radio = gr.Radio(
                label="", choices=[], interactive=True,
                elem_classes=["wa-new-conv-radio"],
            )
            gr.HTML(
                f'<div class="conv-section-hint">{new_conv_cfg.get("empty_hint", "")}</div>'
            )

        # ═══ PANEL 2: Chat ═══
        with gr.Column(scale=2, min_width=400, elem_classes=["chat-panel"]):
            chat_header = gr.HTML(value=placeholder_header, elem_classes=["chat-header-slot"])
            chat_messages = gr.HTML(value=placeholder_messages, elem_classes=["chat-messages-slot"])
            # File upload for media attachments. When a file is attached the
            # text input below doubles as a caption. Supported: images
            # (jpg/png), documents (pdf/doc/xls/ppt/txt/csv), video (mp4),
            # audio (mp3/ogg/m4a). See _MEDIA_KIND_BY_EXT.
            media_input = gr.File(
                label="📎 Attach image / document / video / audio",
                file_types=[
                    ".jpg", ".jpeg", ".png", ".webp",
                    ".mp4", ".3gp",
                    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
                    ".mp3", ".ogg", ".opus", ".aac", ".amr", ".m4a",
                ],
                type="filepath",
                elem_classes=["chat-media-input"],
            )
            with gr.Row(elem_classes=["chat-send-row"]):
                msg_input = gr.Textbox(placeholder="Type a message or caption…", label="", container=False, scale=8, elem_classes=["chat-send-input"])
                send_btn = gr.Button("Send", size="sm", variant="primary", scale=1, elem_classes=["chat-send-btn"])
            send_result = gr.HTML(value="", elem_classes=["chat-send-result"])

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

    # JS snippet that scrolls the chat panel to the bottom after send —
    # Gradio 6 sanitizes <script> inside gr.HTML so we can't inline it;
    # instead chain it as a .then() follow-up on send_btn / send_tpl_btn.
    _SCROLL_CHAT_JS = (
        "() => { const el = document.querySelector('.chat-messages-slot'); "
        "if (el) el.scrollTop = el.scrollHeight; return []; }"
    )

    def _load_chat_view(contact_id: str):
        """Build the full chat view for a contact. Returns the tuple of
        outputs needed by both radio .change handlers below."""
        if not contact_id:
            return (placeholder_header, placeholder_messages, render_tools_empty(), "")
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

    def _select_from_active(cid):
        """Active Chats radio picked. Clear the New radio, set shared state,
        and render the chat view."""
        if not cid:
            return ("", placeholder_header, placeholder_messages, render_tools_empty(), "", gr.update(value=None))
        header, messages, tools, _ = _load_chat_view(cid)
        return (cid, header, messages, tools, "", gr.update(value=None))

    def _select_from_new(cid):
        """Start New radio picked. Clear the Active radio, set shared state,
        and render the chat view."""
        if not cid:
            return ("", placeholder_header, placeholder_messages, render_tools_empty(), "", gr.update(value=None))
        header, messages, tools, _ = _load_chat_view(cid)
        return (cid, header, messages, tools, "", gr.update(value=None))

    conversation_radio.change(
        fn=_select_from_active,
        inputs=[conversation_radio],
        outputs=[selected_cid_state, chat_header, chat_messages, tools_html, send_result, new_conv_radio],
    )
    new_conv_radio.change(
        fn=_select_from_new,
        inputs=[new_conv_radio],
        outputs=[selected_cid_state, chat_header, chat_messages, tools_html, send_result, conversation_radio],
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

    def _search_new(text):
        from services.database import get_db
        db = get_db()
        try:
            results = _search_all_contacts(db, text or "")
            return gr.update(choices=results, value=None)
        finally:
            db.close()

    new_conv_search.change(fn=_search_new, inputs=[new_conv_search], outputs=[new_conv_radio])

    tpl_dropdown.change(fn=render_wa_template_preview, inputs=[tpl_dropdown], outputs=[tpl_preview])

    def _send_message(contact_id, msg, media_path):
        """Unified send handler: text-only OR media (with optional caption).

        If a file is attached, uploads it to Meta via WhatsAppSender.upload_media
        and sends as the right media_type. If no file, sends plain text. Both
        paths respect the 24h customer-service window.
        """
        if not contact_id:
            return (
                '<div style="color:#ef4444; font-size:10px;">Select a chat first</div>',
                gr.update(), gr.update(), gr.update(),
            )
        has_media = bool(media_path)
        has_text = bool((msg or "").strip())
        if not has_media and not has_text:
            return (
                '<div style="color:#ef4444; font-size:10px;">Type a message or attach a file</div>',
                gr.update(), gr.update(), gr.update(),
            )

        from services.database import get_db
        from services.models import Contact, WAChat, WAMessage
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            if not c or not c.wa_id:
                return (
                    '<div style="color:#ef4444; font-size:10px;">No WhatsApp ID on contact</div>',
                    gr.update(), gr.update(), gr.update(),
                )

            # 24h customer-service window applies to text AND media. Only
            # templates bypass it (see _send_tpl below).
            now = datetime.now(timezone.utc)
            if c.last_wa_inbound_at:
                last = c.last_wa_inbound_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() > 86400:
                    return (
                        '<div style="color:#f59e0b; font-size:10px;">Outside 24h window — use a template</div>',
                        gr.update(), gr.update(), gr.update(),
                    )
            else:
                return (
                    '<div style="color:#f59e0b; font-size:10px;">No inbound yet — use a template</div>',
                    gr.update(), gr.update(), gr.update(),
                )

            from services.wa_sender import WhatsAppSender
            sender = WhatsAppSender()

            if has_media:
                original_name = media_path.rsplit("/", 1)[-1]
                media_kind, _ = _media_info_for_filename(original_name)
                ok_u, wa_media_id, err_u = sender.upload_media(media_path)
                if not ok_u:
                    return (
                        f'<div style="color:#ef4444; font-size:10px;">Upload failed: {err_u or "?"}</div>',
                        gr.update(), gr.update(), gr.update(),
                    )
                caption = msg if has_text else None
                ok, msg_id, err = sender.send_media(
                    c.wa_id, wa_media_id, media_type=media_kind, caption=caption,
                )
                if not ok:
                    return (
                        f'<div style="color:#ef4444; font-size:10px;">{err or "Send failed"}</div>',
                        gr.update(), gr.update(), gr.update(),
                    )
                chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
                if not chat:
                    chat = WAChat(contact_id=c.id)
                    db.add(chat)
                    db.flush()
                preview = f"[{media_kind}] {original_name}"
                if has_text:
                    preview = f"[{media_kind}] {msg[:60]}"
                chat.last_message_at = now
                chat.last_message_preview = preview[:100]
                db.add(WAMessage(
                    chat_id=chat.id,
                    contact_id=c.id,
                    direction="out",
                    status="sent",
                    text=msg if has_text else "",
                    wa_message_id=msg_id,
                    media_type=media_kind,
                    media_id=wa_media_id,
                    media_path=original_name,
                    media_caption=msg if has_text else None,
                ))
                c.last_wa_outbound_at = now
                db.commit()
                ok_msg = f'<div style="color:#22c55e; font-size:10px;">Sent {media_kind} ✓</div>'
            else:
                ok, msg_id, err = sender.send_text(c.wa_id, msg)
                if not ok:
                    return (
                        f'<div style="color:#ef4444; font-size:10px;">{err or "Send failed"}</div>',
                        gr.update(), gr.update(), gr.update(),
                    )
                chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
                if not chat:
                    chat = WAChat(contact_id=c.id)
                    db.add(chat)
                    db.flush()
                chat.last_message_at = now
                chat.last_message_preview = (msg or "")[:100]
                db.add(WAMessage(
                    chat_id=chat.id,
                    contact_id=c.id,
                    direction="out",
                    status="sent",
                    text=msg,
                    wa_message_id=msg_id,
                ))
                c.last_wa_outbound_at = now
                db.commit()
                ok_msg = '<div style="color:#22c55e; font-size:10px;">Sent ✓</div>'

            return (
                ok_msg,
                _build_chat_messages(db, contact_id),
                gr.update(value=""),
                gr.update(value=None),
            )
        finally:
            db.close()

    send_btn.click(
        fn=_send_message,
        inputs=[selected_cid_state, msg_input, media_input],
        outputs=[send_result, chat_messages, msg_input, media_input],
    ).then(
        fn=None, inputs=None, outputs=None, js=_SCROLL_CHAT_JS,
    )

    def _send_tpl(contact_id, tpl):
        """Send an approved template and persist the outbound WAMessage so
        it appears in the chat view. Templates bypass the 24h window check.
        """
        if not contact_id or not tpl:
            return (
                '<div style="color:#ef4444; font-size:10px;">Select chat + template</div>',
                gr.update(),
            )
        from services.database import get_db
        from services.models import Contact, WAChat, WAMessage
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            if not c or not c.wa_id:
                return (
                    '<div style="color:#ef4444; font-size:10px;">No WhatsApp ID on contact</div>',
                    gr.update(),
                )

            from services.wa_sender import WhatsAppSender
            ok, msg_id, err = WhatsAppSender().send_template(c.wa_id, tpl)
            if not ok:
                return (
                    f'<div style="color:#ef4444; font-size:10px;">{err or "Send failed"}</div>',
                    gr.update(),
                )

            now = datetime.now(timezone.utc)
            chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
            if not chat:
                chat = WAChat(contact_id=c.id)
                db.add(chat)
                db.flush()
            chat.last_message_at = now
            chat.last_message_preview = f"[Template: {tpl}]"[:100]
            db.add(WAMessage(
                chat_id=chat.id,
                contact_id=c.id,
                direction="out",
                status="sent",
                text=f"[Template: {tpl}]",
                wa_message_id=msg_id,
            ))
            c.last_wa_outbound_at = now
            db.commit()

            return (
                '<div style="color:#22c55e; font-size:10px;">Template sent ✓</div>',
                _build_chat_messages(db, contact_id),
            )
        finally:
            db.close()

    send_tpl_btn.click(
        fn=_send_tpl,
        inputs=[selected_cid_state, tpl_dropdown],
        outputs=[send_tpl_result, chat_messages],
    ).then(
        fn=None, inputs=None, outputs=None, js=_SCROLL_CHAT_JS,
    )

    def _do_refresh():
        from services.database import get_db
        from services.wa_config import get_wa_config
        db = get_db()
        try:
            convs = _get_active_conversations(db)
            tpls = get_wa_config().get_template_names()
            return (
                gr.update(choices=convs, value=None),
                gr.update(choices=[], value=None),
                gr.update(value=""),
                "",
                placeholder_header,
                placeholder_messages,
                render_tools_empty(),
                "",
                gr.update(choices=tpls, value=None),
                render_wa_template_preview(""),
            )
        finally:
            db.close()

    _refresh_outputs = [
        conversation_radio,
        new_conv_radio,
        new_conv_search,
        selected_cid_state,
        chat_header,
        chat_messages,
        tools_html,
        send_result,
        tpl_dropdown,
        tpl_preview,
    ]

    refresh_btn.click(fn=_do_refresh, outputs=_refresh_outputs)

    return {
        "update_fn": _do_refresh,
        "outputs": _refresh_outputs,
    }
