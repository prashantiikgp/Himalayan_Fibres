"""Email Broadcast page — compose and send templated emails.

Two send modes:

- **Broadcast** — pick a template + segment, optionally attach per-recipient
  invoices, send to everyone in the segment.
- **Individual** — search an existing contact by name/company OR inject an
  arbitrary email directly, optionally attach one invoice, send to just
  that one person.

Preview supports a Desktop / Mobile toggle that renders the template inside
a real ``<iframe srcdoc>`` so the templates' own ``<meta viewport>`` +
``max-width:640px`` tables take effect and the founder sees an accurate
phone preview before sending.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

import gradio as gr

from shared.theme import COLORS

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

_RECIPIENT_VALUE_SEP = "||"


def _format_recipient(contact) -> str:
    first = (contact.first_name or "").strip()
    last = (contact.last_name or "").strip()
    name = (first + " " + last).strip() or contact.email or contact.id
    company = (contact.company or "").strip()
    label = f"{name} <{contact.email or '—'}>"
    if company:
        label = f"{name} · {company} <{contact.email or '—'}>"
    return f"{label}{_RECIPIENT_VALUE_SEP}{contact.id}"


def _parse_recipient_value(value: str) -> str | None:
    if not value or _RECIPIENT_VALUE_SEP not in value:
        return None
    return value.rsplit(_RECIPIENT_VALUE_SEP, 1)[-1] or None


def _resolve_segment_contacts(db, segment_id: str | None) -> list:
    from services.models import Contact

    if not segment_id or segment_id == "all_opted_in":
        contacts = (
            db.query(Contact)
            .filter(Contact.consent_status.in_(["opted_in", "pending"]))
            .all()
        )
    else:
        try:
            from services.flows_engine import _get_segment_contacts

            contacts = _get_segment_contacts(db, segment_id)
        except Exception:
            log.exception("Failed to resolve segment %s — falling back to opted-in", segment_id)
            contacts = (
                db.query(Contact)
                .filter(Contact.consent_status.in_(["opted_in", "pending"]))
                .all()
            )

    return [c for c in contacts if c.email and "placeholder" not in (c.email or "")]


def _search_contacts(db, query: str, limit: int = 20) -> list:
    """Search opted-in/pending contacts by name / company / email."""
    from sqlalchemy import or_

    from services.models import Contact

    q = (query or "").strip()
    base = db.query(Contact).filter(
        Contact.consent_status.in_(["opted_in", "pending"]),
        Contact.email.isnot(None),
    )
    if q:
        like = f"%{q}%"
        base = base.filter(
            or_(
                Contact.first_name.ilike(like),
                Contact.last_name.ilike(like),
                Contact.company.ilike(like),
                Contact.email.ilike(like),
            )
        )
    return base.order_by(Contact.first_name).limit(limit).all()


def _upsert_contact_by_email(db, email: str):
    """Look up a Contact by email, or create a lightweight adhoc one."""
    from services.models import Contact

    email = (email or "").strip()
    if not email:
        return None
    existing = db.query(Contact).filter(Contact.email == email).first()
    if existing:
        return existing
    contact = Contact(
        id=f"adhoc_{uuid.uuid4().hex[:16]}",
        email=email,
        first_name="",
        last_name="",
        consent_status="pending",
        consent_source="email_broadcast_individual",
        lifecycle="new_lead",
    )
    db.add(contact)
    db.flush()
    return contact


def _build_sample_vars_for_preview(template_slug: str) -> dict:
    base = {
        "first_name": "Alisha",
        "last_name": "Panda",
        "name": "Alisha Panda",
        "email": "preview@himalayanfibres.com",
        "contact_company": "",
        "invoice_url": "",
    }

    if template_slug == "order_confirmation":
        base.update(
            order_number="10014",
            order_date="30-Aug-2025",
            items_html='<p style="margin:4px 0;">Himalayan Woollen Yarn × 500 g</p>',
            ship_to_html="Mrs. Alisha Panda<br>Brahmapur, Odisha 760004",
            subtotal="Rs 750",
            shipping="Rs 200",
            total="Rs 950",
            payment_method="UPI",
            invoice_url="https://example.com/preview-invoice.pdf",
        )
    elif template_slug == "order_shipped":
        base.update(
            courier_name="BlueDart",
            tracking_id="BD123456789",
            dispatch_date="02-Sep-2025",
            delivery_date="05-Sep-2025",
            tracking_url="https://www.bluedart.com/track/BD123456789",
            invoice_url="https://example.com/preview-invoice.pdf",
        )
    elif template_slug == "operational_update":
        base.update(
            update_title="A quick update from Himalayan Fibres",
            update_body_html=(
                "<p>We wanted to let you know about a small change coming next week.</p>"
                "<p>Thanks for being with us.</p>"
            ),
        )
    return base


def _render_preview_html(template_slug: str, device: str = "desktop") -> str:
    """Render the template inside a real iframe so the viewport meta + table
    ``max-width:640px`` rules in the email templates actually kick in.

    ``device='mobile'`` wraps the iframe in a 412px phone-frame div at 390px
    inner width, which is what unlocks an accurate mobile preview — the
    templates already ship with ``<meta viewport>`` in base.html.
    """
    if not template_slug:
        return (
            f'<div style="color:{COLORS.TEXT_MUTED};padding:40px;text-align:center;'
            f'background:{COLORS.CARD_BG};border-radius:10px;">'
            f"Pick a template to preview.</div>"
        )

    from services.email_personalization import build_send_variables
    from services.email_sender import render_template_by_slug
    from services.models import Contact

    stub = Contact(
        id="preview",
        email="preview@himalayanfibres.com",
        first_name="Alisha",
        last_name="Panda",
        company="",
    )
    vars_for_preview = build_send_variables(
        stub, {}, extra=_build_sample_vars_for_preview(template_slug)
    )

    try:
        html = render_template_by_slug(template_slug, vars_for_preview)
    except Exception as e:
        log.exception("Preview render failed for %s", template_slug)
        return (
            f'<div style="color:#ef4444;padding:20px;">'
            f"Failed to render preview: {e}</div>"
        )

    srcdoc = html.replace("&", "&amp;").replace('"', "&quot;")

    if device == "mobile":
        return (
            '<div style="display:flex;justify-content:center;padding:16px 0;">'
            '<div style="width:412px;border:10px solid #111;border-radius:36px;'
            'box-shadow:0 12px 32px rgba(0,0,0,.45);overflow:hidden;background:#000;">'
            f'<iframe srcdoc="{srcdoc}" '
            'style="width:390px;height:740px;border:0;background:#fff;display:block;">'
            '</iframe></div></div>'
        )

    return (
        '<div style="background:#fff;border:1px solid rgba(255,255,255,.08);'
        'border-radius:10px;overflow:hidden;">'
        f'<iframe srcdoc="{srcdoc}" '
        'style="width:100%;height:78vh;border:0;display:block;background:#fff;">'
        '</iframe></div>'
    )


def _ensure_draft_campaign(db, existing_id: int | None, template_slug: str, segment_id: str | None) -> int:
    from services.models import Campaign

    if existing_id:
        row = db.query(Campaign).filter(Campaign.id == existing_id).first()
        if row is not None:
            row.template_slug = template_slug or row.template_slug
            row.segment_id = segment_id or row.segment_id
            db.flush()
            return row.id

    row = Campaign(
        name=f"Draft — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        subject="",
        template_slug=template_slug or "",
        segment_id=segment_id or None,
        status="draft",
    )
    db.add(row)
    db.flush()
    return row.id


def _count_kpi_html(n: int, label: str = "recipients") -> str:
    return (
        f'<div style="background:{COLORS.CARD_BG};border-radius:8px;padding:10px 14px;'
        f'border:1px solid rgba(255,255,255,.06);margin:8px 0;">'
        f'<span style="font-size:20px;font-weight:700;color:{COLORS.TEXT};">{n}</span>'
        f'<span style="font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;'
        f'letter-spacing:.5px;margin-left:8px;">{label}</span></div>'
    )


# ═══════════════════════════════════════════════════════════════════════
# Page builder
# ═══════════════════════════════════════════════════════════════════════

def build(ctx) -> dict:
    # Session state
    draft_campaign_state = gr.State(None)         # draft Campaign.id
    send_mode_state = gr.State("broadcast")       # "broadcast" | "individual"
    preview_device_state = gr.State("desktop")    # "desktop" | "mobile"
    individual_contact_state = gr.State(None)     # Contact.id or None

    with gr.Row(equal_height=False):
        # ═══════════════════ LEFT: compose controls ═══════════════════
        with gr.Column(scale=1, min_width=340):
            gr.HTML(
                f'<div style="background:{COLORS.CARD_BG};border:1px solid rgba(255,255,255,.06);'
                f'border-radius:10px;padding:10px 14px;margin-bottom:10px;">'
                f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;'
                f'letter-spacing:.5px;">Send to</div></div>'
            )
            mode_radio = gr.Radio(
                choices=["Broadcast", "Individual"],
                value="Broadcast",
                show_label=False,
                container=False,
            )

            template_dropdown = gr.Dropdown(
                label="Template",
                choices=[],
                interactive=True,
                allow_custom_value=True,
            )

            # ── Broadcast sub-group ─────────────────────────────────────
            with gr.Group(visible=True) as broadcast_group:
                segment_dropdown = gr.Dropdown(
                    label="Audience (Segment)",
                    choices=[],
                    interactive=True,
                    allow_custom_value=True,
                )
                audience_kpi_html = gr.HTML(value="")

            # ── Individual sub-group ────────────────────────────────────
            with gr.Group(visible=False) as individual_group:
                gr.HTML(
                    f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin:6px 0 4px;">'
                    f"Search by name or company, or type any email below.</div>"
                )
                individual_search = gr.Textbox(
                    label="Search",
                    placeholder="e.g. Sushank, Lakhanpal, Amazon",
                    interactive=True,
                )
                individual_contact_dropdown = gr.Dropdown(
                    label="Contact",
                    choices=[],
                    interactive=True,
                    allow_custom_value=True,
                )
                gr.HTML(
                    f'<div style="font-size:10px;color:{COLORS.TEXT_MUTED};text-align:center;'
                    f'margin:6px 0;">— or —</div>'
                )
                individual_email_input = gr.Textbox(
                    label="Direct email",
                    placeholder="name@example.com",
                    interactive=True,
                )

            subject_input = gr.Textbox(
                label="Subject",
                placeholder="Auto-fills from template — override if needed",
                interactive=True,
            )

            # ── Invoice attachment accordion ────────────────────────────
            with gr.Accordion("📎 Invoice attachment (optional)", open=False):
                # Broadcast: per-recipient picker
                with gr.Group(visible=True) as attach_broadcast_group:
                    gr.HTML(
                        f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin-bottom:8px;">'
                        f"Attach a PDF invoice for <b>one specific recipient</b> in this segment. "
                        f"The ‘Download Invoice’ button appears only in their email. "
                        f"Repeat for each recipient who needs one.</div>"
                    )
                    recipient_dropdown = gr.Dropdown(
                        label="Recipient (in segment)",
                        choices=[],
                        interactive=True,
                        allow_custom_value=True,
                    )

                # Individual: no picker, binds to the selected individual
                with gr.Group(visible=False) as attach_individual_group:
                    gr.HTML(
                        f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin-bottom:8px;">'
                        f"Attach a PDF invoice to this email. It will be linked "
                        f"to the contact you selected (or the direct email above).</div>"
                    )

                invoice_file = gr.File(
                    label="Invoice PDF",
                    file_types=[".pdf"],
                    type="binary",
                )
                with gr.Row():
                    attach_btn = gr.Button("Attach", variant="primary", size="sm", scale=1)
                    remove_btn = gr.Button("Remove", size="sm", scale=1)
                attach_result_html = gr.HTML(value="")

            # ── Send controls ───────────────────────────────────────────
            with gr.Row():
                send_btn = gr.Button("Send Now", variant="primary", size="sm", scale=2)
                test_btn = gr.Button("Send Test to Me", size="sm", scale=1)
            test_email_input = gr.Textbox(
                label="Test email",
                placeholder="your@email.com",
                interactive=True,
            )
            send_result_html = gr.HTML(value="")

        # ═══════════════════ RIGHT: preview (dominant) ═══════════════════
        with gr.Column(scale=3, min_width=560):
            with gr.Row():
                gr.HTML(
                    f'<div style="font-size:12px;font-weight:600;color:{COLORS.TEXT};'
                    f'padding:6px 0;">Preview</div>'
                )
                device_radio = gr.Radio(
                    choices=["Desktop", "Mobile"],
                    value="Desktop",
                    show_label=False,
                    container=False,
                )
            preview_html = gr.HTML(value=_render_preview_html("", "desktop"))

    # ═══════════════════════════════════════════════════════════════════
    # Event handlers
    # ═══════════════════════════════════════════════════════════════════

    def _on_mode_change(mode_label: str):
        mode = "individual" if mode_label == "Individual" else "broadcast"
        show_broadcast = mode == "broadcast"
        return (
            mode,
            gr.update(visible=show_broadcast),   # broadcast_group
            gr.update(visible=not show_broadcast),  # individual_group
            gr.update(visible=show_broadcast),   # attach_broadcast_group
            gr.update(visible=not show_broadcast),  # attach_individual_group
        )

    mode_radio.change(
        fn=_on_mode_change,
        inputs=[mode_radio],
        outputs=[
            send_mode_state,
            broadcast_group,
            individual_group,
            attach_broadcast_group,
            attach_individual_group,
        ],
    )

    def _on_device_change(device_label: str, template_slug: str):
        device = "mobile" if device_label == "Mobile" else "desktop"
        return device, _render_preview_html(template_slug, device)

    device_radio.change(
        fn=_on_device_change,
        inputs=[device_radio, template_dropdown],
        outputs=[preview_device_state, preview_html],
    )

    def _on_template_change(template_slug: str, device: str):
        from services.database import get_db
        from services.models import EmailTemplate

        if not template_slug:
            return "", _render_preview_html("", device)
        try:
            db = get_db()
            try:
                tpl = (
                    db.query(EmailTemplate)
                    .filter(EmailTemplate.slug == template_slug)
                    .first()
                )
                subject = tpl.subject_template if tpl else ""
            finally:
                db.close()
            return subject, _render_preview_html(template_slug, device)
        except Exception as e:
            log.exception("_on_template_change failed for slug=%s", template_slug)
            err_html = (
                f'<div style="color:#ef4444;padding:20px;font-family:monospace;'
                f'font-size:11px;white-space:pre-wrap;">'
                f"{type(e).__name__}: {e}</div>"
            )
            return "", err_html

    template_dropdown.change(
        fn=_on_template_change,
        inputs=[template_dropdown, preview_device_state],
        outputs=[subject_input, preview_html],
    )

    def _on_segment_change(segment_id: str):
        from services.database import get_db

        db = get_db()
        try:
            contacts = _resolve_segment_contacts(db, segment_id)
            choices = [_format_recipient(c) for c in contacts]
            n = len(contacts)
            kpi = _count_kpi_html(n, "recipients")
        finally:
            db.close()
        return gr.update(choices=choices, value=None), kpi

    segment_dropdown.change(
        fn=_on_segment_change,
        inputs=[segment_dropdown],
        outputs=[recipient_dropdown, audience_kpi_html],
    )

    def _on_individual_search(query: str):
        from services.database import get_db

        db = get_db()
        try:
            contacts = _search_contacts(db, query, limit=25)
            choices = [_format_recipient(c) for c in contacts]
        finally:
            db.close()
        return gr.update(choices=choices, value=None)

    individual_search.change(
        fn=_on_individual_search,
        inputs=[individual_search],
        outputs=[individual_contact_dropdown],
    )

    def _on_individual_contact_pick(contact_value: str):
        return _parse_recipient_value(contact_value)

    individual_contact_dropdown.change(
        fn=_on_individual_contact_pick,
        inputs=[individual_contact_dropdown],
        outputs=[individual_contact_state],
    )

    # ── Attach handler (mode-aware) ──
    def _on_attach(
        mode: str,
        template_slug: str,
        segment_id: str,
        recipient_value: str,
        individual_contact_id: str | None,
        individual_email: str,
        file_bytes,
        draft_id: int | None,
    ):
        from services.database import get_db
        from services.models import EmailAttachment
        from services.supabase_storage import SupabaseStorageError, upload_file

        if not template_slug:
            return draft_id, _err("Pick a template first.")
        if not file_bytes:
            return draft_id, _err("Drop a PDF file first.")

        db = get_db()
        try:
            # Resolve the contact_id the attachment will bind to
            if mode == "individual":
                email = (individual_email or "").strip()
                if email:
                    contact = _upsert_contact_by_email(db, email)
                    contact_id = contact.id if contact else None
                elif individual_contact_id:
                    contact_id = individual_contact_id
                else:
                    return draft_id, _err("Pick a contact or type a direct email first.")
            else:
                contact_id = _parse_recipient_value(recipient_value)
                if not contact_id:
                    return draft_id, _err("Pick a recipient from the dropdown.")

            raw = file_bytes if isinstance(file_bytes, (bytes, bytearray)) else bytes(file_bytes)

            new_draft_id = _ensure_draft_campaign(db, draft_id, template_slug, segment_id)
            storage_path = (
                f"campaign_{new_draft_id}/contact_{contact_id}/"
                f"{uuid.uuid4().hex[:12]}_invoice.pdf"
            )
            try:
                signed_url = upload_file(
                    bucket="email-invoices",
                    path=storage_path,
                    file_bytes=raw,
                    content_type="application/pdf",
                )
            except SupabaseStorageError as e:
                db.rollback()
                return draft_id, _err(f"Upload failed: {e}")

            db.query(EmailAttachment).filter(
                EmailAttachment.campaign_id == new_draft_id,
                EmailAttachment.contact_id == contact_id,
                EmailAttachment.kind == "invoice",
            ).delete()

            att = EmailAttachment(
                campaign_id=new_draft_id,
                contact_id=contact_id,
                kind="invoice",
                file_name="invoice.pdf",
                storage_bucket="email-invoices",
                storage_path=storage_path,
                signed_url=signed_url,
                content_type="application/pdf",
                size_bytes=len(raw),
            )
            db.add(att)
            db.commit()

            return new_draft_id, _ok(f"Attached invoice for {contact_id}")
        except Exception as e:
            db.rollback()
            log.exception("Attach failed")
            return draft_id, _err(f"Attach failed: {e}")
        finally:
            db.close()

    attach_btn.click(
        fn=_on_attach,
        inputs=[
            send_mode_state,
            template_dropdown,
            segment_dropdown,
            recipient_dropdown,
            individual_contact_state,
            individual_email_input,
            invoice_file,
            draft_campaign_state,
        ],
        outputs=[draft_campaign_state, attach_result_html],
    )

    # ── Remove handler ──
    def _on_remove(
        mode: str,
        recipient_value: str,
        individual_contact_id: str | None,
        individual_email: str,
        draft_id: int | None,
    ):
        from services.database import get_db
        from services.models import Contact, EmailAttachment
        from services.supabase_storage import SupabaseStorageError, delete_file

        if not draft_id:
            return _err("No draft campaign yet — nothing to remove.")

        if mode == "individual":
            email = (individual_email or "").strip()
            if email:
                db_ = get_db()
                try:
                    c = db_.query(Contact).filter(Contact.email == email).first()
                    contact_id = c.id if c else None
                finally:
                    db_.close()
            else:
                contact_id = individual_contact_id
        else:
            contact_id = _parse_recipient_value(recipient_value)

        if not contact_id:
            return _err("Pick a recipient to remove the attachment.")

        db = get_db()
        try:
            att = (
                db.query(EmailAttachment)
                .filter(
                    EmailAttachment.campaign_id == draft_id,
                    EmailAttachment.contact_id == contact_id,
                    EmailAttachment.kind == "invoice",
                )
                .first()
            )
            if not att:
                return _ok("No attachment to remove.")

            try:
                delete_file(att.storage_bucket, att.storage_path)
            except SupabaseStorageError:
                log.warning(
                    "Supabase delete failed for %s — removing DB row anyway",
                    att.storage_path,
                )

            db.delete(att)
            db.commit()
            return _ok(f"Removed attachment for {contact_id}")
        except Exception as e:
            db.rollback()
            log.exception("Remove failed")
            return _err(f"Remove failed: {e}")
        finally:
            db.close()

    remove_btn.click(
        fn=_on_remove,
        inputs=[
            send_mode_state,
            recipient_dropdown,
            individual_contact_state,
            individual_email_input,
            draft_campaign_state,
        ],
        outputs=[attach_result_html],
    )

    # ── Send Now handler (mode-aware) ──
    def _on_send_now(
        mode: str,
        template_slug: str,
        segment_id: str,
        subject: str,
        draft_id: int | None,
        individual_contact_id: str | None,
        individual_email: str,
    ):
        if not template_slug:
            return draft_id, _err("Pick a template first.")
        if not subject:
            return draft_id, _err("Subject is empty.")

        from services.database import get_db
        from services.email_personalization import (
            build_send_variables,
            load_campaign_attachments,
        )
        from services.email_sender import (
            EmailSender,
            generate_idempotency_key,
            render_template_by_slug,
        )
        from services.models import Campaign, Contact, EmailSend, EmailTemplate

        sender = EmailSender()
        if not sender.is_configured():
            return draft_id, _err(
                "Gmail API not configured. Set GMAIL_REFRESH_TOKEN / GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET."
            )

        db = get_db()
        try:
            # Resolve contact list based on mode
            if mode == "individual":
                email = (individual_email or "").strip()
                if email:
                    contact = _upsert_contact_by_email(db, email)
                    contacts = [contact] if contact else []
                elif individual_contact_id:
                    contacts = (
                        db.query(Contact)
                        .filter(Contact.id == individual_contact_id)
                        .all()
                    )
                else:
                    return draft_id, _err("Pick a contact or type a direct email.")
                effective_segment_id = None
            else:
                contacts = _resolve_segment_contacts(db, segment_id)
                effective_segment_id = segment_id

            if not contacts:
                return draft_id, _err("No recipients resolved.")

            campaign_id = _ensure_draft_campaign(
                db, draft_id, template_slug, effective_segment_id
            )
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            tpl = (
                db.query(EmailTemplate)
                .filter(EmailTemplate.slug == template_slug)
                .first()
            )
            if tpl is None:
                return campaign_id, _err(f"Template {template_slug!r} not found in DB.")

            mode_tag = "Individual" if mode == "individual" else "Broadcast"
            campaign.name = (
                f"{mode_tag}: {tpl.name} · "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
            campaign.subject = subject
            campaign.status = "sending"
            campaign.total_recipients = len(contacts)
            db.flush()

            attachments = load_campaign_attachments(db, campaign_id)

            sent = failed = 0
            for contact in contacts:
                idem_key = generate_idempotency_key(f"campaign_{campaign_id}", contact.id)
                if db.query(EmailSend).filter(EmailSend.idempotency_key == idem_key).first():
                    continue

                variables = build_send_variables(contact, attachments)
                try:
                    rendered_html = render_template_by_slug(template_slug, variables)
                    rendered_subject = sender.render_template(subject, variables)
                except Exception as e:
                    log.exception("Render failed for %s", contact.id)
                    db.add(
                        EmailSend(
                            contact_id=contact.id,
                            contact_email=contact.email or "",
                            campaign_id=campaign_id,
                            subject=subject,
                            status="failed",
                            idempotency_key=idem_key,
                            error_message=f"Render error: {e}",
                        )
                    )
                    failed += 1
                    continue

                result = sender.send_email(
                    to_email=contact.email,
                    subject=rendered_subject,
                    html_content=rendered_html,
                    to_name=(contact.first_name or None),
                )

                db.add(
                    EmailSend(
                        contact_id=contact.id,
                        contact_email=contact.email or "",
                        campaign_id=campaign_id,
                        subject=rendered_subject,
                        status="sent" if result["success"] else "failed",
                        idempotency_key=idem_key,
                        error_message="" if result["success"] else result.get("message", ""),
                        sent_at=datetime.now(timezone.utc) if result["success"] else None,
                    )
                )
                if result["success"]:
                    sent += 1
                else:
                    failed += 1

                if len(contacts) > 1:
                    time.sleep(3)  # light rate-limit for Gmail API

            campaign.total_sent = sent
            campaign.total_failed = failed
            campaign.sent_at = datetime.now(timezone.utc)
            campaign.status = "sent" if failed == 0 else "sent_partial"
            db.commit()

            color = "#22c55e" if failed == 0 else "#f59e0b"
            msg = (
                f'<div style="background:{COLORS.CARD_BG};border-radius:8px;padding:12px;'
                f'border-left:4px solid {color};">'
                f'<div style="font-weight:600;color:{color};">Send complete</div>'
                f'<div style="color:{COLORS.TEXT_SUBTLE};font-size:11px;">'
                f"Sent: {sent}  |  Failed: {failed}  |  Total: {len(contacts)}</div></div>"
            )
            return None, msg
        except Exception as e:
            db.rollback()
            log.exception("Send failed")
            return draft_id, _err(f"Send failed: {e}")
        finally:
            db.close()

    send_btn.click(
        fn=_on_send_now,
        inputs=[
            send_mode_state,
            template_dropdown,
            segment_dropdown,
            subject_input,
            draft_campaign_state,
            individual_contact_state,
            individual_email_input,
        ],
        outputs=[draft_campaign_state, send_result_html],
    )

    # ── Test-send handler ──
    def _on_test_send(template_slug: str, subject: str, test_email: str):
        if not template_slug or not test_email or not subject:
            return _err("Pick a template, enter a subject, and enter a test email.")

        from services.email_personalization import build_send_variables
        from services.email_sender import EmailSender, render_template_by_slug
        from services.models import Contact

        sender = EmailSender()
        if not sender.is_configured():
            return _err("Gmail API not configured.")

        stub = Contact(
            id="test_send",
            email=test_email,
            first_name="Test",
            last_name="User",
        )
        try:
            variables = build_send_variables(
                stub,
                {},
                extra=_build_sample_vars_for_preview(template_slug),
            )
            rendered_html = render_template_by_slug(template_slug, variables)
            rendered_subject = sender.render_template(subject, variables)
        except Exception as e:
            return _err(f"Render failed: {e}")

        result = sender.send_email(
            to_email=test_email,
            subject=rendered_subject,
            html_content=rendered_html,
            to_name="Test",
        )
        if result["success"]:
            return _ok(f"Test email sent to {test_email}")
        return _err(result.get("message", "Send failed"))

    test_btn.click(
        fn=_on_test_send,
        inputs=[template_dropdown, subject_input, test_email_input],
        outputs=[send_result_html],
    )

    # ═══════════════════════════════════════════════════════════════════
    # Initial load
    # ═══════════════════════════════════════════════════════════════════

    def _refresh():
        from services.database import get_db
        from services.models import EmailTemplate, Segment

        db = get_db()
        try:
            templates = (
                db.query(EmailTemplate)
                .filter(EmailTemplate.is_active == True)  # noqa: E712
                .order_by(EmailTemplate.name)
                .all()
            )
            tpl_choices = [t.slug for t in templates]
            first_slug = tpl_choices[0] if tpl_choices else None
            first_subject = ""
            if first_slug:
                first_tpl = next((t for t in templates if t.slug == first_slug), None)
                first_subject = first_tpl.subject_template if first_tpl else ""

            segments = (
                db.query(Segment)
                .filter(Segment.is_active == True)  # noqa: E712
                .order_by(Segment.name)
                .all()
            )
            seg_choices = ["all_opted_in"] + [s.id for s in segments]

            preview = _render_preview_html(first_slug or "", "desktop")
        finally:
            db.close()

        return (
            gr.update(choices=tpl_choices, value=first_slug),
            gr.update(choices=seg_choices, value="all_opted_in"),
            first_subject,
            preview,
            "",  # attach_result_html
            "",  # send_result_html
        )

    return {
        "update_fn": _refresh,
        "outputs": [
            template_dropdown,
            segment_dropdown,
            subject_input,
            preview_html,
            attach_result_html,
            send_result_html,
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
# Small UI helpers
# ═══════════════════════════════════════════════════════════════════════

def _ok(msg: str) -> str:
    return f'<div style="color:#22c55e;font-size:11px;padding:6px 0;">✓ {msg}</div>'


def _err(msg: str) -> str:
    return f'<div style="color:#ef4444;font-size:11px;padding:6px 0;">✗ {msg}</div>'
