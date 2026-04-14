"""WhatsApp Template Studio — draft, upload, submit, sync WA templates.

Three-column layout:

  Left    — tabs of drafts / submitted / approved / rejected + Sync button
  Center  — editor form (name, category, language, header, body, footer, buttons)
  Right   — live preview + image/document guidance

Submitting a draft posts to Meta's WABA message_templates endpoint. Status
is pulled back via the Sync button. Drafts and synced Meta state share the
same `WATemplate` table, disambiguated by the `is_draft` column.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import gradio as gr

from loader.config_loader import get_config_loader
from services.config import get_settings

log = logging.getLogger(__name__)


_STATUS_BADGE = {
    "DRAFT": ("✏️", "#64748b"),
    "PENDING": ("🟡", "#f59e0b"),
    "APPROVED": ("🟢", "#22c55e"),
    "REJECTED": ("🔴", "#ef4444"),
}

_CATEGORY_CHOICES = ["MARKETING", "UTILITY", "AUTHENTICATION"]
_LANGUAGE_CHOICES = ["en", "en_US", "en_GB", "hi", "hi_IN"]
_HEADER_FORMAT_CHOICES = ["NONE", "TEXT", "IMAGE", "DOCUMENT"]


def _list_templates(db, *, drafts: bool, status: str | None = None):
    """Return WATemplate rows filtered by draft/status."""
    from services.models import WATemplate

    q = db.query(WATemplate)
    if drafts:
        q = q.filter(WATemplate.is_draft.is_(True))
    else:
        q = q.filter(WATemplate.is_draft.is_(False))
        if status:
            q = q.filter(WATemplate.status == status)
    return q.order_by(WATemplate.name).all()


def _template_row_label(t) -> str:
    status = "DRAFT" if t.is_draft else (t.status or "PENDING")
    icon, _ = _STATUS_BADGE.get(status, ("⚪", "#64748b"))
    lang = t.language or "?"
    return f"{icon} {t.name} · {lang}"


def _refresh_lists():
    """Pull lists for all four tabs from the DB."""
    from services.database import get_db

    db = get_db()
    try:
        drafts = [(_template_row_label(t), t.id) for t in _list_templates(db, drafts=True)]
        pending = [
            (_template_row_label(t), t.id)
            for t in _list_templates(db, drafts=False, status="PENDING")
        ]
        approved = [
            (_template_row_label(t), t.id)
            for t in _list_templates(db, drafts=False, status="APPROVED")
        ]
        rejected = [
            (_template_row_label(t), t.id)
            for t in _list_templates(db, drafts=False, status="REJECTED")
        ]
        return (
            gr.update(choices=drafts, value=None),
            gr.update(choices=pending, value=None),
            gr.update(choices=approved, value=None),
            gr.update(choices=rejected, value=None),
        )
    finally:
        db.close()


def _blank_form_state() -> dict:
    return {
        "id": None,
        "name": "",
        "category": "MARKETING",
        "language": "en_US",
        "header_format": "NONE",
        "header_text": "",
        "header_asset_url": "",
        "body_text": "",
        "footer_text": "",
        "buttons_json": "[]",
    }


def _extract_from_components(components: list[dict]) -> dict:
    """Extract editor-form fields from the Meta-native components array.

    Synced templates store their content in `components` (the Meta API
    shape), not in the flat `body_text` / `header_*` / `footer_text` /
    `buttons` columns. When the user loads a synced row into the editor
    we reconstruct those flat fields so the form and the phone preview
    have something to display.
    """
    out = {
        "header_format": "NONE",
        "header_text": "",
        "header_asset_url": "",
        "body_text": "",
        "footer_text": "",
        "buttons": [],
    }
    for comp in components or []:
        ctype = (comp.get("type") or "").upper()
        if ctype == "HEADER":
            fmt = (comp.get("format") or "").upper()
            if fmt == "TEXT":
                out["header_format"] = "TEXT"
                out["header_text"] = comp.get("text", "")
            elif fmt in ("IMAGE", "VIDEO", "DOCUMENT"):
                out["header_format"] = fmt
                example = comp.get("example") or {}
                handles = example.get("header_handle") or []
                if handles:
                    out["header_asset_url"] = handles[0]
        elif ctype == "BODY":
            out["body_text"] = comp.get("text", "")
        elif ctype == "FOOTER":
            out["footer_text"] = comp.get("text", "")
        elif ctype == "BUTTONS":
            out["buttons"] = comp.get("buttons") or []
    return out


def _load_row_into_form(template_id: int) -> dict:
    from services.database import get_db
    from services.models import WATemplate

    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).one_or_none()
        if t is None:
            return _blank_form_state()

        # Drafts (is_draft=True) store content in the flat columns; synced
        # Meta rows store it in `components`. Prefer flat columns when set,
        # fall back to parsing components otherwise.
        extracted = _extract_from_components(t.components or [])

        body = t.body_text or extracted["body_text"]
        header_fmt = t.header_format or extracted["header_format"]
        header_text = t.header_text or extracted["header_text"]
        header_url = t.header_asset_url or extracted["header_asset_url"]
        footer = t.footer_text or extracted["footer_text"]
        buttons = t.buttons or extracted["buttons"]

        return {
            "id": t.id,
            "name": t.name or "",
            "category": t.category or "MARKETING",
            "language": t.language or "en_US",
            "header_format": header_fmt or "NONE",
            "header_text": header_text,
            "header_asset_url": header_url,
            "body_text": body,
            "footer_text": footer,
            "buttons_json": json.dumps(buttons, indent=2),
        }
    finally:
        db.close()


def _parse_buttons(buttons_json: str) -> list[dict]:
    s = (buttons_json or "").strip()
    if not s:
        return []
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"Buttons JSON invalid: {e}") from e
    if not isinstance(data, list):
        raise ValueError("Buttons JSON must be a list")
    return data


# WhatsApp dark-theme palette — matches the mobile app exactly so the preview
# feels authentic without pulling in external assets.
_WA_BG = "#0b141a"
_WA_HEADER = "#1f2c33"
_WA_IN_BUBBLE = "#1f2c33"
_WA_OUT_BUBBLE = "#005c4b"
_WA_TEXT = "#e9edef"
_WA_MUTED = "#8696a0"
_WA_LINK = "#53bdeb"
_WA_BUTTON_GREEN = "#00a884"

# Placeholder chat history shown above the live-preview template so the user
# can see how the message will feel in an actual conversation thread.
_CONTEXT_MESSAGES = [
    {"dir": "out", "text": "Hi 👋 This is Himalayan Fibres", "ts": "10:41"},
    {"dir": "in", "text": "Hey! Are you still making samples?", "ts": "10:42"},
]

_VAR_RE = re.compile(r"(\{\{[^{}]+\}\})")


def _highlight_vars(text: str) -> str:
    """Wrap {{placeholder}} tokens in a distinct amber span so they stand out."""
    def _repl(m):
        return (
            f'<span style="color:#ffd54f; background:rgba(255,213,79,.12); '
            f'padding:0 4px; border-radius:3px; font-weight:500;">{m.group(1)}</span>'
        )
    return _VAR_RE.sub(_repl, text)


def _render_bubble(direction: str, body_html: str, ts: str, *, header_html: str = "",
                   footer_text: str = "", buttons: list[dict] | None = None,
                   show_check: bool = True) -> str:
    """Render a single WhatsApp-styled chat bubble (inbound or outbound)."""
    is_out = direction == "out"
    bg = _WA_OUT_BUBBLE if is_out else _WA_IN_BUBBLE
    align = "flex-end" if is_out else "flex-start"
    # Tail shape: outbound has sharper top-right, inbound has sharper top-left.
    radius = "8px 8px 4px 8px" if is_out else "8px 8px 8px 4px"

    footer_html = (
        f'<div style="font-size:10px; color:{_WA_MUTED}; margin-top:4px;">{footer_text}</div>'
        if footer_text
        else ""
    )

    check_html = ""
    if is_out and show_check:
        check_html = (
            f'<span style="color:{_WA_LINK}; font-size:11px; margin-left:4px;">✓✓</span>'
        )

    meta_row = (
        f'<div style="display:flex; justify-content:flex-end; align-items:center; '
        f'margin-top:2px;">'
        f'<span style="font-size:10px; color:{_WA_MUTED};">{ts}</span>'
        f'{check_html}'
        f'</div>'
    )

    buttons_html = ""
    if buttons:
        rows = []
        for b in buttons:
            btype = (b.get("type") or "").upper()
            text = b.get("text", "")
            icon = "🔗" if btype == "URL" else ("📞" if btype == "PHONE_NUMBER" else "⤴")
            rows.append(
                f'<div style="border-top:1px solid rgba(255,255,255,0.08); '
                f'padding:8px 12px; text-align:center; color:{_WA_BUTTON_GREEN}; '
                f'font-size:12px; font-weight:500;">{icon} &nbsp;{text}</div>'
            )
        buttons_html = (
            f'<div style="background:{bg}; border-radius:0 0 8px 8px; '
            f'margin-top:-4px;">{"".join(rows)}</div>'
        )

    return (
        f'<div style="display:flex; justify-content:{align}; margin:4px 0;">'
        f'<div style="max-width:78%;">'
        f'<div style="background:{bg}; color:{_WA_TEXT}; padding:6px 8px 6px 8px; '
        f'border-radius:{radius}; font-size:13px; line-height:1.35; '
        f'box-shadow:0 1px 0.5px rgba(0,0,0,.15);">'
        f'{header_html}'
        f'<div style="padding:2px 4px 0 4px;">{body_html}</div>'
        f'{footer_html}'
        f'{meta_row}'
        f'</div>'
        f'{buttons_html}'
        f'</div>'
        f'</div>'
    )


def _template_body_html(header_format, header_text, header_asset_url,
                        body_text, footer_text) -> tuple[str, str]:
    """Return (header_html, body_html) for the template-under-preview bubble."""
    header_html = ""
    if header_format == "TEXT" and header_text:
        header_html = (
            f'<div style="font-weight:700; font-size:14px; color:{_WA_TEXT}; '
            f'padding:2px 4px 4px 4px;">{_highlight_vars(header_text)}</div>'
        )
    elif header_format == "IMAGE" and header_asset_url:
        header_html = (
            f'<img src="{header_asset_url}" '
            f'style="display:block; width:100%; max-height:200px; object-fit:cover; '
            f'border-radius:6px 6px 0 0; margin:-6px -8px 6px -8px;" '
            f'onerror="this.style.display=\'none\'" />'
        )
    elif header_format == "DOCUMENT" and header_asset_url:
        fname = header_asset_url.rsplit("/", 1)[-1]
        header_html = (
            f'<div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px; '
            f'margin:-2px -4px 6px -4px; display:flex; align-items:center; gap:8px;">'
            f'<div style="font-size:20px;">📄</div>'
            f'<div style="font-size:12px; color:{_WA_TEXT};">{fname}</div>'
            f'</div>'
        )

    if body_text:
        body = _highlight_vars(body_text).replace("\n", "<br>")
    else:
        body = f'<em style="color:{_WA_MUTED};">Body text appears here…</em>'

    return header_html, body


def _render_preview(name, category, language, header_format, header_text,
                    header_asset_url, body_text, footer_text, buttons_json="[]") -> str:
    """Render the full phone-style preview: header bar, context messages, template bubble."""
    contact_name = "Potential customer"
    cat = category or "MARKETING"
    lang = language or "en_US"
    tpl_name = (name or "").strip() or "<new template>"

    try:
        buttons = _parse_buttons(buttons_json)
    except ValueError:
        buttons = []

    header_html, body_html = _template_body_html(
        header_format, header_text, header_asset_url, body_text, footer_text
    )
    template_bubble = _render_bubble(
        "out", body_html, "10:43",
        header_html=header_html, footer_text=footer_text, buttons=buttons,
    )

    context_bubbles = "".join(
        _render_bubble(m["dir"], m["text"], m["ts"]) for m in _CONTEXT_MESSAGES
    )

    # WhatsApp-style "doodle" pattern using a subtle radial gradient stack.
    # Avoids external assets while giving the chat area visual texture.
    chat_bg_style = (
        f"background:{_WA_BG}; "
        "background-image:"
        "radial-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),"
        "radial-gradient(rgba(255,255,255,0.015) 1px, transparent 1px); "
        "background-size:20px 20px, 30px 30px; "
        "background-position:0 0, 10px 10px;"
    )

    return f"""
<div style="width:100%; max-width:540px; margin:0 auto; background:#000;
            border-radius:28px; padding:10px 6px;
            box-shadow:0 25px 60px rgba(0,0,0,0.6);">
  <div style="background:{_WA_BG}; border-radius:20px; overflow:hidden;
              border:1px solid rgba(255,255,255,0.06);">

    <!-- Chat header bar -->
    <div style="background:{_WA_HEADER}; padding:10px 14px; display:flex;
                align-items:center; gap:10px; border-bottom:1px solid rgba(0,0,0,0.3);">
      <div style="color:{_WA_TEXT}; font-size:18px;">←</div>
      <div style="width:36px; height:36px; border-radius:50%; background:#6b7280;
                  display:flex; align-items:center; justify-content:center;
                  font-size:16px;">🙂</div>
      <div style="flex:1;">
        <div style="color:{_WA_TEXT}; font-size:14px; font-weight:600;">{contact_name}</div>
        <div style="color:{_WA_MUTED}; font-size:11px;">online</div>
      </div>
      <div style="color:{_WA_TEXT}; font-size:16px;">📹</div>
      <div style="color:{_WA_TEXT}; font-size:16px;">📞</div>
      <div style="color:{_WA_TEXT}; font-size:16px;">⋮</div>
    </div>

    <!-- Conversation area -->
    <div style="{chat_bg_style} padding:14px 12px 16px 12px; min-height:520px;
                max-height:calc(100vh - 280px); overflow-y:auto;">
      <!-- Day separator -->
      <div style="text-align:center; margin:8px 0 12px 0;">
        <span style="background:{_WA_HEADER}; color:{_WA_MUTED}; font-size:10px;
                     padding:3px 10px; border-radius:8px;">TODAY</span>
      </div>
      {context_bubbles}
      {template_bubble}
    </div>

    <!-- Input bar (decorative — not interactive) -->
    <div style="background:{_WA_HEADER}; padding:8px 12px; display:flex;
                align-items:center; gap:8px; border-top:1px solid rgba(0,0,0,0.3);">
      <div style="color:{_WA_MUTED}; font-size:18px;">😊</div>
      <div style="flex:1; background:{_WA_BG}; border-radius:20px; padding:8px 14px;
                  color:{_WA_MUTED}; font-size:12px;">Message</div>
      <div style="color:{_WA_MUTED}; font-size:18px;">🎤</div>
    </div>
  </div>

  <!-- Meta info strip below the phone -->
  <div style="text-align:center; margin-top:10px; font-size:10px; color:#64748b;">
    {cat} · {lang} · <span style="color:#94a3b8;">{tpl_name}</span>
  </div>
</div>
"""


def _render_guidelines_html() -> str:
    """Render a compact header-asset guidelines card for the left sidebar.

    Shows one row per media type with formats + max size; tips are rendered
    as a small details/summary so the column doesn't get overwhelmed.
    """
    loader = get_config_loader()
    g = loader.load_wa_media_guidelines().media_guidelines

    def _row(icon: str, label: str, spec) -> str:
        tips = "".join(f'<li style="margin-bottom:3px;">{t}</li>' for t in spec.tips)
        return f"""
<details style="margin-bottom:6px;">
  <summary style="cursor:pointer; font-size:11px; color:#e7eaf3; padding:4px 0;
                  list-style:none;">
    <span style="font-size:13px;">{icon}</span>
    <strong style="color:#c7d2fe;">{label}</strong>
    <span style="color:#8696a0; font-size:10px;">
      · {"/".join(spec.formats)} · {spec.max_size_mb} MB
    </span>
  </summary>
  <div style="font-size:10px; color:#8696a0; padding:2px 0 4px 20px;">
    {spec.recommended}
    <ul style="margin:4px 0 0 0; padding-left:14px;">{tips}</ul>
  </div>
</details>
"""

    return f"""
<div style="background:rgba(15,23,42,.50); border:1px solid rgba(255,255,255,.06);
            border-radius:8px; padding:10px; margin-top:6px;">
  <div style="font-weight:700; color:#e7eaf3; font-size:11px; margin-bottom:6px;
              text-transform:uppercase; letter-spacing:0.5px;">Header guidelines</div>
  {_row("🖼", "Image", g.header_image)}
  {_row("🎬", "Video", g.header_video)}
  {_row("📄", "Document", g.header_document)}
</div>
"""


def _warning_banner() -> str:
    settings = get_settings()
    if settings.public_base_url.lower().startswith("https://"):
        return ""
    return (
        '<div style="background:rgba(239,68,68,.08); border:1px solid rgba(239,68,68,.25); '
        'padding:10px 12px; border-radius:6px; font-size:11px; color:#fca5a5;">'
        '⚠ <b>PUBLIC_BASE_URL is not HTTPS.</b> Meta will refuse to pull header assets '
        'from an http:// URL. Submit is disabled until you set PUBLIC_BASE_URL to an '
        'HTTPS endpoint (HF Space URL in prod, ngrok tunnel in local dev).'
        '</div>'
    )


def _save_draft(
    template_id, name, category, language, header_format, header_text,
    header_asset_url, body_text, footer_text, buttons_json,
):
    from services.database import get_db
    from services.models import WATemplate

    if not (name or "").strip():
        return "❌ Name is required", template_id

    try:
        buttons = _parse_buttons(buttons_json)
    except ValueError as e:
        return f"❌ {e}", template_id

    db = get_db()
    try:
        if template_id:
            t = db.query(WATemplate).filter(WATemplate.id == template_id).one_or_none()
            if t is None:
                return "❌ Template not found", None
        else:
            t = WATemplate(name=name.strip(), language=language, is_draft=True)
            db.add(t)

        t.name = name.strip()
        t.category = category
        t.language = language
        t.header_format = None if header_format == "NONE" else header_format
        t.header_text = header_text.strip() or None
        t.header_asset_url = (header_asset_url or "").strip() or None
        t.body_text = body_text or ""
        t.footer_text = (footer_text or "").strip() or None
        t.buttons = buttons
        t.is_draft = True

        db.commit()
        db.refresh(t)
        return f"✅ Draft saved (id {t.id})", t.id
    except Exception as e:
        db.rollback()
        log.exception("Save draft failed")
        return f"❌ {e}", template_id
    finally:
        db.close()


def _submit_to_meta(
    template_id, name, category, language, header_format, header_text,
    header_asset_url, body_text, footer_text, buttons_json,
):
    """Save as draft, build components, POST to Meta, flip is_draft=False."""
    from services.database import get_db
    from services.models import WATemplate
    from services.wa_sender import WhatsAppSender
    from services.wa_template_builder import build_components

    if not get_settings().public_base_url.lower().startswith("https://"):
        return "❌ PUBLIC_BASE_URL must be HTTPS for Meta to fetch header assets", template_id

    # Ensure the latest form state is persisted first
    msg, template_id = _save_draft(
        template_id, name, category, language, header_format, header_text,
        header_asset_url, body_text, footer_text, buttons_json,
    )
    if msg.startswith("❌"):
        return msg, template_id

    spec: dict = {"body": {"text": body_text}}
    if header_format == "TEXT" and header_text:
        spec["header"] = {"type": "TEXT", "text": header_text}
    elif header_format in ("IMAGE", "DOCUMENT") and header_asset_url:
        spec["header"] = {"type": header_format, "url": header_asset_url}
    if footer_text:
        spec["footer"] = {"text": footer_text}
    try:
        buttons = _parse_buttons(buttons_json)
    except ValueError as e:
        return f"❌ {e}", template_id
    if buttons:
        spec["buttons"] = buttons

    components = build_components(spec)

    sender = WhatsAppSender()
    ok, data, err = sender.create_template(
        name=name.strip(), category=category, language=language, components=components,
    )
    if not ok:
        return f"❌ Meta rejected: {err}", template_id

    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).one_or_none()
        if t is not None:
            t.is_draft = False
            t.status = (data or {}).get("status", "PENDING")
            t.meta_template_id = str((data or {}).get("id") or "") or None
            t.submitted_at = datetime.now(timezone.utc)
            db.commit()
        return f"✅ Submitted to Meta — status {t.status}", t.id
    finally:
        db.close()


def _sync_from_meta():
    from services.database import get_db
    from services.wa_sender import WhatsAppSender

    db = get_db()
    try:
        result = WhatsAppSender().sync_templates_from_meta(db)
        if not result.get("ok"):
            return f"❌ Sync failed: {result.get('error')}"
        return (
            f"✅ Synced {result['synced']} (created {result['created']}, "
            f"updated {result['updated']})"
        )
    finally:
        db.close()


def _upload_header(file_obj):
    """Gradio upload handler → ProductMedia row → public URL."""
    if not file_obj:
        return "", ""
    from services.database import get_db
    from services.media_store import save_upload

    src_path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", None)
    if not src_path:
        return "", "❌ Could not read upload"

    original = src_path.rsplit("/", 1)[-1]
    db = get_db()
    try:
        row = save_upload(db, src_path=src_path, original_filename=original)
        return row.public_url, f"✅ Uploaded → {row.public_url}"
    except Exception as e:
        log.exception("Header upload failed")
        return "", f"❌ {e}"
    finally:
        db.close()


def build(ctx):
    is_https = get_settings().public_base_url.lower().startswith("https://")

    with gr.Row():
        # ═══ LEFT (20%) — templates list + header guidelines ═══
        with gr.Column(scale=2, min_width=220, elem_classes=["ts-list-panel"]):
            gr.HTML('<div class="ts-panel-title">Templates</div>')
            new_btn = gr.Button("+ New Draft", size="sm", variant="primary")
            sync_btn = gr.Button("🔄 Sync from Meta", size="sm", variant="secondary")
            sync_result = gr.HTML(value="")
            with gr.Tabs():
                with gr.Tab("Drafts"):
                    drafts_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Pending"):
                    pending_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Approved"):
                    approved_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Rejected"):
                    rejected_radio = gr.Radio(label="", choices=[], interactive=True)
            gr.HTML(_render_guidelines_html())

        # ═══ CENTER (30%) — compact editor form ═══
        with gr.Column(scale=3, min_width=280, elem_classes=["ts-editor-panel"]):
            gr.HTML('<div class="ts-panel-title">Editor</div>')
            gr.HTML(_warning_banner())
            template_id_state = gr.State(value=None)

            name_input = gr.Textbox(label="Name", placeholder="welcome_v1")
            with gr.Row():
                category_input = gr.Dropdown(
                    label="Category", choices=_CATEGORY_CHOICES, value="MARKETING"
                )
                language_input = gr.Dropdown(
                    label="Language", choices=_LANGUAGE_CHOICES, value="en_US"
                )

            header_format_input = gr.Dropdown(
                label="Header format", choices=_HEADER_FORMAT_CHOICES, value="NONE"
            )
            header_text_input = gr.Textbox(
                label="Header text (TEXT only)", visible=False, max_lines=1,
            )
            header_asset_url_input = gr.Textbox(
                label="Header asset URL", visible=False, interactive=True, max_lines=1,
            )
            header_upload = gr.File(
                label="Upload header asset",
                file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                visible=False,
                type="filepath",
            )
            upload_result = gr.HTML(value="")

            body_input = gr.Textbox(
                label="Body text",
                lines=4,
                placeholder="Hello {{1}}, welcome to Himalayan Fibres.",
            )
            footer_input = gr.Textbox(label="Footer (optional)", max_lines=1)
            buttons_input = gr.Textbox(
                label="Buttons (JSON list)",
                lines=3,
                value="[]",
                placeholder='[{"type": "URL", "text": "Visit site", "url": "https://..."}]',
            )

            with gr.Row():
                save_btn = gr.Button("💾 Save", variant="secondary")
                submit_btn = gr.Button("🚀 Submit", variant="primary", interactive=is_https)
            action_result = gr.HTML(value="")

        # ═══ RIGHT (50%) — WhatsApp phone-mockup preview ═══
        with gr.Column(scale=5, min_width=380, elem_classes=["ts-preview-panel"]):
            gr.HTML('<div class="ts-panel-title">Live preview — how it looks in chat</div>')
            preview_html = gr.HTML(
                value=_render_preview("", "MARKETING", "en_US", "NONE", "", "", "", "", "[]")
            )

    # -- Header format toggles which inputs are visible --
    def _on_header_format(fmt):
        return (
            gr.update(visible=(fmt == "TEXT")),
            gr.update(visible=(fmt in ("IMAGE", "DOCUMENT"))),
            gr.update(visible=(fmt in ("IMAGE", "DOCUMENT"))),
        )

    header_format_input.change(
        fn=_on_header_format,
        inputs=[header_format_input],
        outputs=[header_text_input, header_asset_url_input, header_upload],
    )

    # -- Live preview on any field change --
    preview_inputs = [
        name_input, category_input, language_input, header_format_input,
        header_text_input, header_asset_url_input, body_input, footer_input,
        buttons_input,
    ]
    for inp in preview_inputs:
        inp.change(fn=_render_preview, inputs=preview_inputs, outputs=[preview_html])

    # -- Upload handler --
    header_upload.change(
        fn=_upload_header,
        inputs=[header_upload],
        outputs=[header_asset_url_input, upload_result],
    )

    # -- New draft: reset form --
    def _new_draft():
        s = _blank_form_state()
        return (
            None, s["name"], s["category"], s["language"], s["header_format"],
            s["header_text"], s["header_asset_url"], s["body_text"], s["footer_text"],
            s["buttons_json"], "",
        )

    new_btn.click(
        fn=_new_draft,
        outputs=[
            template_id_state, name_input, category_input, language_input,
            header_format_input, header_text_input, header_asset_url_input,
            body_input, footer_input, buttons_input, action_result,
        ],
    ).then(
        fn=_render_preview, inputs=preview_inputs, outputs=[preview_html],
    )

    # -- Row selection: load form --
    def _select_row(template_id):
        if not template_id:
            return (
                None, "", "MARKETING", "en_US", "NONE", "", "", "", "", "[]",
            )
        s = _load_row_into_form(template_id)
        return (
            s["id"], s["name"], s["category"], s["language"], s["header_format"],
            s["header_text"], s["header_asset_url"], s["body_text"], s["footer_text"],
            s["buttons_json"],
        )

    form_outputs = [
        template_id_state, name_input, category_input, language_input,
        header_format_input, header_text_input, header_asset_url_input,
        body_input, footer_input, buttons_input,
    ]
    for radio in (drafts_radio, pending_radio, approved_radio, rejected_radio):
        radio.change(fn=_select_row, inputs=[radio], outputs=form_outputs).then(
            fn=_render_preview, inputs=preview_inputs, outputs=[preview_html],
        )

    # -- Save draft --
    save_btn.click(
        fn=_save_draft,
        inputs=[
            template_id_state, name_input, category_input, language_input,
            header_format_input, header_text_input, header_asset_url_input,
            body_input, footer_input, buttons_input,
        ],
        outputs=[action_result, template_id_state],
    )

    # -- Submit to Meta --
    submit_btn.click(
        fn=_submit_to_meta,
        inputs=[
            template_id_state, name_input, category_input, language_input,
            header_format_input, header_text_input, header_asset_url_input,
            body_input, footer_input, buttons_input,
        ],
        outputs=[action_result, template_id_state],
    ).then(
        fn=_refresh_lists,
        outputs=[drafts_radio, pending_radio, approved_radio, rejected_radio],
    )

    # -- Sync --
    sync_btn.click(fn=_sync_from_meta, outputs=[sync_result]).then(
        fn=_refresh_lists,
        outputs=[drafts_radio, pending_radio, approved_radio, rejected_radio],
    )

    # -- Save-draft list refresh --
    save_btn.click(
        fn=_refresh_lists,
        outputs=[drafts_radio, pending_radio, approved_radio, rejected_radio],
    )

    # -- Refresh wiring for sidebar nav --
    return {
        "update_fn": _refresh_lists,
        "outputs": [drafts_radio, pending_radio, approved_radio, rejected_radio],
    }
