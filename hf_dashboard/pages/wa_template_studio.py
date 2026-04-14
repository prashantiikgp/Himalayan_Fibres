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


def _load_row_into_form(template_id: int) -> dict:
    from services.database import get_db
    from services.models import WATemplate

    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).one_or_none()
        if t is None:
            return _blank_form_state()
        return {
            "id": t.id,
            "name": t.name or "",
            "category": t.category or "MARKETING",
            "language": t.language or "en_US",
            "header_format": (t.header_format or "NONE"),
            "header_text": t.header_text or "",
            "header_asset_url": t.header_asset_url or "",
            "body_text": t.body_text or "",
            "footer_text": t.footer_text or "",
            "buttons_json": json.dumps(t.buttons or [], indent=2),
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


def _render_preview(name, category, language, header_format, header_text, header_asset_url, body_text, footer_text) -> str:
    """Render a compact WhatsApp-styled preview of the template."""
    name = (name or "").strip() or "<new template>"
    header_html = ""
    if header_format == "TEXT" and header_text:
        header_html = f'<div style="font-weight:600; color:#e7eaf3; margin-bottom:6px;">{header_text}</div>'
    elif header_format == "IMAGE" and header_asset_url:
        header_html = (
            f'<img src="{header_asset_url}" style="width:100%; max-height:160px; '
            f'object-fit:cover; border-radius:6px; margin-bottom:6px;" />'
        )
    elif header_format == "DOCUMENT" and header_asset_url:
        header_html = (
            f'<div style="background:rgba(99,102,241,.10); padding:8px; border-radius:6px; '
            f'margin-bottom:6px; font-size:11px; color:#c7d2fe;">📄 {header_asset_url.rsplit("/", 1)[-1]}</div>'
        )

    body_html = (body_text or "").replace("\n", "<br>")
    body_or_placeholder = body_html or '<em style="color:#64748b;">Body text appears here…</em>'
    footer_html = (
        f'<div style="font-size:10px; color:#64748b; margin-top:6px;">{footer_text}</div>'
        if footer_text
        else ""
    )

    cat = category or "MARKETING"
    lang = language or "en_US"
    return (
        f'<div style="background:#0b1220; border:1px solid rgba(255,255,255,.08); '
        f'border-radius:10px; padding:12px; font-size:12px; color:#e7eaf3; max-width:320px;">'
        f'<div style="font-size:10px; color:#64748b; margin-bottom:8px;">'
        f'{cat} · {lang} · {name}</div>'
        f'{header_html}'
        f'<div>{body_or_placeholder}</div>'
        f'{footer_html}'
        f'</div>'
    )


def _render_guidelines_html() -> str:
    """Render media guidelines from validated config."""
    loader = get_config_loader()
    g = loader.load_wa_media_guidelines().media_guidelines

    def _section(title: str, spec) -> str:
        tips = "".join(f'<li>{t}</li>' for t in spec.tips)
        return (
            f'<div style="margin-bottom:10px;">'
            f'<div style="font-weight:600; color:#c7d2fe; font-size:11px;">{title}</div>'
            f'<div style="font-size:10px; color:#94a3b8;">Formats: {", ".join(spec.formats)} · Max {spec.max_size_mb} MB</div>'
            f'<div style="font-size:10px; color:#94a3b8;">{spec.recommended}</div>'
            f'<ul style="font-size:10px; color:#64748b; margin:4px 0 0 14px; padding:0;">{tips}</ul>'
            f'</div>'
        )

    return (
        '<div style="background:rgba(15,23,42,.60); border:1px solid rgba(255,255,255,.06); '
        'border-radius:8px; padding:10px;">'
        '<div style="font-weight:700; color:#e7eaf3; font-size:11px; margin-bottom:8px;">'
        'Header asset guidelines</div>'
        + _section("Image", g.header_image)
        + _section("Video", g.header_video)
        + _section("Document", g.header_document)
        + '</div>'
    )


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
        # ═══ LEFT: list panel ═══
        with gr.Column(scale=1, min_width=260):
            gr.HTML('<div style="font-weight:700; color:#e7eaf3; font-size:12px; margin-bottom:6px;">Templates</div>')
            new_btn = gr.Button("+ New Draft", size="sm", variant="primary")
            with gr.Tabs():
                with gr.Tab("Drafts"):
                    drafts_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Pending"):
                    pending_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Approved"):
                    approved_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Tab("Rejected"):
                    rejected_radio = gr.Radio(label="", choices=[], interactive=True)
            sync_btn = gr.Button("🔄 Sync from Meta", size="sm", variant="secondary")
            sync_result = gr.HTML(value="")

        # ═══ CENTER: editor form ═══
        with gr.Column(scale=3, min_width=480):
            gr.HTML(_warning_banner())
            template_id_state = gr.State(value=None)

            with gr.Row():
                name_input = gr.Textbox(label="Name", placeholder="welcome_v1", scale=2)
                category_input = gr.Dropdown(label="Category", choices=_CATEGORY_CHOICES, value="MARKETING", scale=1)
                language_input = gr.Dropdown(label="Language", choices=_LANGUAGE_CHOICES, value="en_US", scale=1)

            header_format_input = gr.Dropdown(
                label="Header format", choices=_HEADER_FORMAT_CHOICES, value="NONE"
            )
            header_text_input = gr.Textbox(label="Header text (TEXT only)", visible=False)
            header_asset_url_input = gr.Textbox(
                label="Header asset URL (auto-filled after upload)",
                visible=False,
                interactive=True,
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
                lines=5,
                placeholder="Hello {{1}}, welcome to Himalayan Fibres.",
            )
            footer_input = gr.Textbox(label="Footer (optional)", max_lines=1)
            buttons_input = gr.Textbox(
                label="Buttons (JSON list)",
                lines=4,
                value="[]",
                placeholder='[{"type": "URL", "text": "Visit site", "url": "https://himalayanfibre.com"}]',
            )

            with gr.Row():
                save_btn = gr.Button("💾 Save Draft", variant="secondary")
                submit_btn = gr.Button("🚀 Submit to Meta", variant="primary", interactive=is_https)
            action_result = gr.HTML(value="")

        # ═══ RIGHT: preview + guidelines ═══
        with gr.Column(scale=1, min_width=320):
            gr.HTML('<div style="font-weight:700; color:#e7eaf3; font-size:12px; margin-bottom:6px;">Live preview</div>')
            preview_html = gr.HTML(value=_render_preview("", "MARKETING", "en_US", "NONE", "", "", "", ""))
            gr.HTML(_render_guidelines_html())

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
        radio.change(fn=_select_row, inputs=[radio], outputs=form_outputs)

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
