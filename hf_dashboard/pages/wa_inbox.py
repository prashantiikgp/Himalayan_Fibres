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
from components.tools_panel import (
    render_activity_compact,
    render_full_tools,
    render_tools_empty,
    render_wa_template_filled,
    render_wa_template_preview,
)

# Pre-allocated variable input slots in Panel 3. Real templates max out
# at 4 vars (order_confirmation, order_tracking); 5 gives one slot of
# headroom. Gradio components must exist at page-build time, so we
# create N slots up front and toggle visibility per template.
MAX_VARS = 5

_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "wa_inbox.yml"


def _cfg():
    with open(_CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


_AVATAR_EMOJIS = ["🙂", "😊", "😎", "🤗", "🧑", "👤", "🧔", "👨", "👩", "🦊", "🐼", "🐻", "🐯", "🦁", "🐸", "🦄"]


def get_wa_config_safe_categories() -> list[str]:
    """Return the sorted unique template categories. Wrapped so the
    page module degrades gracefully if the YAML config is missing."""
    try:
        from services.wa_config import get_wa_config
        return get_wa_config().get_template_categories()
    except Exception:
        return []


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

    refresh_hint_text = col1_cfg.get(
        "refresh_caption", "Click Refresh after sending a message to see updates."
    )

    with gr.Row():
        # ═══ PANEL 1: Conversations (Active + Start New) ═══
        # Width: 20% of content area (scale=1 of 1+2+2=5 total)
        with gr.Column(scale=1, min_width=240, elem_classes=["conv-list-panel"]):
            gr.HTML(
                f'<div class="conv-section-title" style="margin:0 0 6px 0;">'
                f'{col1_cfg.get("title", "Active Chats")}</div>'
            )
            search_box = gr.Textbox(
                placeholder=col1_cfg.get("search_placeholder", "Search active… (press Enter)"),
                label="", container=False,
            )
            with gr.Column(elem_classes=["wa-active-scroll"]):
                conversation_radio = gr.Radio(
                    label="", choices=[], interactive=True,
                    elem_classes=["wa-conv-radio"],
                )
            gr.HTML('<div class="conv-section-divider"></div>')
            gr.HTML(
                f'<div class="conv-section-title">{new_conv_cfg.get("title", "Start New Conversation")}</div>'
            )
            new_conv_search = gr.Textbox(
                placeholder=new_conv_cfg.get("search_placeholder", "Search contact… (press Enter)"),
                label="", container=False,
            )
            with gr.Column(elem_classes=["wa-new-scroll"]):
                new_conv_radio = gr.Radio(
                    label="", choices=[], interactive=True,
                    elem_classes=["wa-new-conv-radio"],
                )
            gr.HTML(
                f'<div class="conv-section-hint">{new_conv_cfg.get("empty_hint", "")}</div>'
            )

        # ═══ PANEL 2: Chat ═══
        # Width: 40% of content area (scale=2 of 5 total)
        with gr.Column(scale=2, min_width=380, elem_classes=["chat-panel"]):
            chat_header = gr.HTML(value=placeholder_header, elem_classes=["chat-header-slot"])
            chat_messages = gr.HTML(value=placeholder_messages, elem_classes=["chat-messages-slot"])

            # Send row: textbox + attach chip (visible when file picked)
            # + clear-attach button + 📎 attach button + Send button.
            # The real gr.File lives inside the attachment modal below.
            with gr.Row(elem_classes=["chat-send-row"]):
                msg_input = gr.Textbox(
                    placeholder="Type a message or caption…",
                    label="", container=False, scale=8,
                    elem_classes=["chat-send-input"],
                )
                attach_chip = gr.HTML(value="", elem_classes=["chat-attach-chip-slot"])
                clear_attach_btn = gr.Button(
                    "✕", size="sm", variant="secondary",
                    scale=0, min_width=24, visible=False,
                    elem_classes=["chat-attach-clear"],
                )
                attach_btn = gr.Button(
                    "📎", size="sm", variant="secondary",
                    scale=0, min_width=36,
                    elem_classes=["chat-attach-btn"],
                )
                send_btn = gr.Button(
                    "Send", size="sm", variant="primary",
                    scale=1, elem_classes=["chat-send-btn"],
                )
            send_result = gr.HTML(value="", elem_classes=["chat-send-result"])

            # Attachment modal — hidden by default. Clicking 📎 reveals it.
            with gr.Column(visible=False, elem_classes=["hf-modal", "wa-attach-modal"]) as attach_modal:
                gr.HTML(
                    '<div style="font-size:14px; font-weight:700; color:#e7eaf3;">Attach a file</div>'
                    '<div style="font-size:11px; color:#94a3b8; margin-top:4px;">'
                    'Image, document, video, or audio. Max one file per message.</div>'
                )
                media_input = gr.File(
                    label="Drop file or click to upload",
                    file_types=[
                        ".jpg", ".jpeg", ".png", ".webp",
                        ".mp4", ".3gp",
                        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
                        ".mp3", ".ogg", ".opus", ".aac", ".amr", ".m4a",
                    ],
                    type="filepath",
                    elem_classes=["chat-media-input"],
                )
                with gr.Row(elem_classes=["wa-attach-actions"]):
                    attach_cancel_btn = gr.Button("Cancel", size="sm", variant="secondary")
                    attach_done_btn = gr.Button("Done", size="sm", variant="primary")

        # ═══ PANEL 3: Refresh + Past Activity + Category + Template + Variables + Preview ═══
        # Width: 40% of content area (scale=2 of 5 total). Refresh button
        # moved here from Panel 1 — it's prominent at the top with a hint
        # right below it. A single _do_refresh handler reloads everything.
        with gr.Column(scale=2, min_width=320, elem_classes=["tools-panel"]):
            refresh_btn = gr.Button(
                "🔄  Refresh",
                size="sm", variant="secondary",
                elem_classes=["tp-refresh-btn"],
            )
            gr.HTML(
                f'<div class="tp-refresh-hint">{refresh_hint_text}</div>'
            )
            tp_activity_box = gr.HTML(
                value='<div style="color:#64748b; font-size:11px; padding:6px;">No activity</div>',
                elem_classes=["tp-activity-box"],
            )
            # Category + Template share one row so they fit without
            # horizontal scrolling and free up ~70px of vertical space
            # for the variable inputs and preview below.
            with gr.Row(elem_classes=["tp-filter-row"]):
                tp_category = gr.Dropdown(
                    label="Category",
                    choices=["All"] + get_wa_config_safe_categories(),
                    value="All", interactive=True,
                    scale=1, min_width=0,
                    elem_classes=["tp-category", "wa-filter-sm"],
                )
                tp_template = gr.Dropdown(
                    label="Template",
                    choices=[], interactive=True,
                    scale=1, min_width=0,
                    elem_classes=["tp-template", "wa-filter-sm"],
                )
            with gr.Column(elem_classes=["tp-vars-box"]) as tp_vars_box:
                # Pre-allocate slots as visible=True so they exist in the DOM
                # from the start. Gradio omits visible=False components from
                # initial render, leaving no element for later visibility
                # updates to attach to. We rely on _do_refresh (which the nav
                # engine fires on every WhatsApp tab click — see
                # navigation_engine.py:148) to immediately drive them all to
                # visible=False, and on _on_template_change to selectively
                # re-show the ones the active template needs.
                var_slots: list[gr.Textbox] = []
                for i in range(MAX_VARS):
                    slot = gr.Textbox(
                        label=f"var_{i}",
                        placeholder="",
                        visible=True,
                        value="",
                        interactive=True,
                        container=True,
                        elem_classes=["wa-var-slot"],
                    )
                    var_slots.append(slot)
            tp_preview_box = gr.HTML(
                value=render_wa_template_filled("", {}),
                elem_classes=["tp-preview-box"],
            )
            tp_send_btn = gr.Button(
                "Send Template", variant="primary", size="sm",
                elem_classes=["tp-send-btn"],
            )
            tp_send_result = gr.HTML(value="", elem_classes=["tp-send-result"])

            # Legacy handles for downstream wiring that referenced the old
            # names. We keep them as no-op aliases so the rest of build()
            # need not change.
            tools_html = tp_activity_box
            tpl_dropdown = tp_template
            tpl_preview = tp_preview_box
            send_tpl_btn = tp_send_btn
            send_tpl_result = tp_send_result

    # JS snippet that scrolls the chat panel to the bottom after send —
    # Gradio 6 sanitizes <script> inside gr.HTML so we can't inline it;
    # instead chain it as a .then() follow-up on send_btn / send_tpl_btn.
    _SCROLL_CHAT_JS = (
        "() => { const el = document.querySelector('.chat-messages-slot'); "
        "if (el) el.scrollTop = el.scrollHeight; return []; }"
    )

    def _load_chat_view(contact_id: str):
        """Build the full chat view for a contact. Returns the tuple of
        outputs needed by both radio .change handlers below.

        Panel 3 now renders compact past-activity instead of the full
        tools card — the contact name already shows in Panel 2's chat
        header so the duplicate card was just noise.
        """
        empty_activity = '<div style="color:#64748b; font-size:10px;">No activity</div>'
        if not contact_id:
            return (placeholder_header, placeholder_messages, empty_activity, "")
        from services.database import get_db
        db = get_db()
        try:
            return (
                _build_chat_header(db, contact_id),
                _build_chat_messages(db, contact_id),
                render_activity_compact(db, contact_id),
                "",
            )
        finally:
            db.close()

    def _select_from_active(cid):
        """Active Chats radio picked. Clear the New radio, set shared state,
        and render the chat view."""
        if not cid:
            empty_activity = '<div style="color:#64748b; font-size:10px;">No activity</div>'
            return ("", placeholder_header, placeholder_messages, empty_activity, "", gr.update(value=None))
        header, messages, tools, _ = _load_chat_view(cid)
        return (cid, header, messages, tools, "", gr.update(value=None))

    def _select_from_new(cid):
        """Start New radio picked. Clear the Active radio, set shared state,
        and render the chat view."""
        if not cid:
            empty_activity = '<div style="color:#64748b; font-size:10px;">No activity</div>'
            return ("", placeholder_header, placeholder_messages, empty_activity, "", gr.update(value=None))
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

    # Plan D Phase 1.4: search fires on Enter key (.submit), not per
    # keystroke (.change), so we don't burn a DB query per character.
    search_box.submit(fn=_search, inputs=[search_box], outputs=[conversation_radio])

    def _search_new(text):
        from services.database import get_db
        db = get_db()
        try:
            results = _search_all_contacts(db, text or "")
            return gr.update(choices=results, value=None)
        finally:
            db.close()

    # Plan D Phase 1.4: submit on Enter instead of firing per keystroke.
    new_conv_search.submit(fn=_search_new, inputs=[new_conv_search], outputs=[new_conv_radio])

    # ─── Attachment popover ───
    def _open_attach():
        return gr.update(visible=True)

    def _close_attach():
        return gr.update(visible=False)

    def _on_media_change(path):
        if not path:
            return ("", gr.update(visible=False))
        name = path.rsplit("/", 1)[-1]
        chip = (
            f'<div class="chat-attach-chip" title="{name}">📎 {name}</div>'
        )
        return (chip, gr.update(visible=True))

    def _clear_attach():
        return (gr.update(value=None), "", gr.update(visible=False))

    attach_btn.click(fn=_open_attach, outputs=[attach_modal])
    attach_cancel_btn.click(fn=_close_attach, outputs=[attach_modal])
    attach_done_btn.click(fn=_close_attach, outputs=[attach_modal])
    media_input.change(
        fn=_on_media_change,
        inputs=[media_input],
        outputs=[attach_chip, clear_attach_btn],
    )
    clear_attach_btn.click(
        fn=_clear_attach,
        outputs=[media_input, attach_chip, clear_attach_btn],
    )

    # ─── Template flow: category → template → variables → preview ───
    def _on_category_change(category: str):
        from services.wa_config import get_wa_config
        names = get_wa_config().get_templates_by_category(category or "All")
        return gr.update(choices=names, value=None)

    tp_category.change(
        fn=_on_category_change,
        inputs=[tp_category],
        outputs=[tp_template],
        show_progress="hidden",
    )

    def _on_template_change(template_name: str):
        """Reconfigure variable slots and reset preview when a template
        is picked. Each output is a single Textbox update with visible
        + label + value + placeholder set together so Gradio doesn't
        no-op a 'visible-only' update on a Textbox that hadn't received
        any other prop change."""
        from services.wa_config import get_wa_config
        n = MAX_VARS

        if not template_name:
            slot_updates = [
                gr.update(visible=False, value="", label=f"var_{i}", placeholder="")
                for i in range(n)
            ]
            return (*slot_updates, render_wa_template_filled("", {}))

        tpl = get_wa_config().get_template(template_name)
        if not tpl:
            slot_updates = [
                gr.update(visible=False, value="", label=f"var_{i}", placeholder="")
                for i in range(n)
            ]
            return (*slot_updates, '<div style="color:#ef4444; font-size:10px;">Template not found</div>')

        slot_updates = []
        for i in range(n):
            if i < len(tpl.variables):
                v = tpl.variables[i]
                slot_updates.append(gr.update(
                    visible=True,
                    value="",
                    label=v.name,
                    placeholder=v.example or v.description or "",
                ))
            else:
                slot_updates.append(gr.update(
                    visible=False, value="", label=f"var_{i}", placeholder="",
                ))
        return (*slot_updates, render_wa_template_filled(template_name, {}))

    tp_template.change(
        fn=_on_template_change,
        inputs=[tp_template],
        outputs=[*var_slots, tp_preview_box],
        show_progress="hidden",
    )

    def _preview_update(template_name, *slot_values):
        from services.wa_config import get_wa_config
        tpl = get_wa_config().get_template(template_name) if template_name else None
        values: dict[str, str] = {}
        if tpl:
            for i, v in enumerate(tpl.variables):
                if i < len(slot_values):
                    values[v.name] = slot_values[i] or ""
        return render_wa_template_filled(template_name, values)

    # ONE merged listener for all slot.change events. When the user picks
    # a different template, _on_template_change updates 5 slot values at
    # once — which would otherwise queue 5 separate _preview_update jobs
    # and stack the "processing" spinner on every input field. gr.on +
    # trigger_mode="always_last" collapses the burst into a single call,
    # and show_progress="hidden" suppresses the per-input spinner since
    # the substitution is just a string replace.
    gr.on(
        triggers=[s.change for s in var_slots],
        fn=_preview_update,
        inputs=[tp_template, *var_slots],
        outputs=[tp_preview_box],
        trigger_mode="always_last",
        show_progress="hidden",
    )

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

    def _send_tpl_filled(contact_id, template_name, *slot_values):
        """Send a filled template, persist the substituted body, and
        reset the variable slots + preview. Templates bypass the 24h
        customer-service window."""
        n_slots = MAX_VARS
        no_change_slots = [gr.update() for _ in range(n_slots)]

        def _err(msg):
            return (
                f'<div style="color:#ef4444; font-size:10px;">{msg}</div>',
                gr.update(),
                *no_change_slots,
                gr.update(),
            )

        if not contact_id or not template_name:
            return _err("Select chat + template")

        from services.wa_config import get_wa_config
        tpl = get_wa_config().get_template(template_name)
        if not tpl:
            return _err("Template not found")

        # Build the named-variable list strictly from the template's
        # declared variables (slot indices > len(tpl.variables) are
        # ignored even if the user typed something there).
        variables: list[tuple[str, str]] = []
        for i, v in enumerate(tpl.variables):
            if i < len(slot_values):
                variables.append((v.name, (slot_values[i] or "").strip()))

        # Required-field validation
        required_names = {v.name for v in tpl.variables if v.required}
        missing = [name for name, val in variables if not val and name in required_names]
        if missing:
            return (
                f'<div style="color:#f59e0b; font-size:10px;">Missing: {", ".join(missing)}</div>',
                gr.update(),
                *no_change_slots,
                gr.update(),
            )

        from services.database import get_db
        from services.models import Contact, WAChat, WAMessage
        from services.wa_sender import WhatsAppSender
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            if not c or not c.wa_id:
                return _err("No WhatsApp ID on contact")

            ok, msg_id, err = WhatsAppSender().send_template(
                c.wa_id, template_name,
                lang=tpl.language or "en_US",
                variables=variables,
            )
            if not ok:
                return _err(err or "Send failed")

            # Substitute into the body so the chat log shows what Meta
            # actually delivered, not "[Template: xyz]".
            filled_body = tpl.body_text or ""
            for name, val in variables:
                filled_body = filled_body.replace("{{" + name + "}}", val)

            now = datetime.now(timezone.utc)
            chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
            if not chat:
                chat = WAChat(contact_id=c.id)
                db.add(chat)
                db.flush()
            chat.last_message_at = now
            chat.last_message_preview = filled_body[:100]
            db.add(WAMessage(
                chat_id=chat.id,
                contact_id=c.id,
                direction="out",
                status="sent",
                text=filled_body,
                wa_message_id=msg_id,
            ))
            c.last_wa_outbound_at = now
            db.commit()

            cleared_slots = [gr.update(value="") for _ in range(n_slots)]
            return (
                '<div style="color:#22c55e; font-size:10px;">Template sent ✓</div>',
                _build_chat_messages(db, contact_id),
                *cleared_slots,
                render_wa_template_filled(template_name, {}),
            )
        finally:
            db.close()

    tp_send_btn.click(
        fn=_send_tpl_filled,
        inputs=[selected_cid_state, tp_template, *var_slots],
        outputs=[tp_send_result, chat_messages, *var_slots, tp_preview_box],
    ).then(
        fn=None, inputs=None, outputs=None, js=_SCROLL_CHAT_JS,
    )

    def _do_refresh():
        from services.database import get_db
        from services.wa_config import get_wa_config
        db = get_db()
        try:
            convs = _get_active_conversations(db)
            cfg_wa = get_wa_config()
            empty_activity = '<div style="color:#64748b; font-size:10px;">No activity</div>'
            slot_resets = [
                gr.update(visible=False, value="", label=f"var_{i}", placeholder="")
                for i in range(MAX_VARS)
            ]
            return (
                gr.update(choices=convs, value=None),       # conversation_radio
                gr.update(choices=[], value=None),          # new_conv_radio
                gr.update(value=""),                        # new_conv_search
                "",                                          # selected_cid_state
                placeholder_header,                          # chat_header
                placeholder_messages,                        # chat_messages
                empty_activity,                              # tp_activity_box
                "",                                          # send_result
                gr.update(value="All"),                      # tp_category
                gr.update(choices=cfg_wa.get_template_names(), value=None),  # tp_template
                *slot_resets,                                # var_slots × MAX_VARS
                render_wa_template_filled("", {}),           # tp_preview_box
                "",                                          # tp_send_result
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
        tp_activity_box,
        send_result,
        tp_category,
        tp_template,
        *var_slots,
        tp_preview_box,
        tp_send_result,
    ]

    refresh_btn.click(fn=_do_refresh, outputs=_refresh_outputs)

    return {
        "update_fn": _do_refresh,
        "outputs": _refresh_outputs,
    }
