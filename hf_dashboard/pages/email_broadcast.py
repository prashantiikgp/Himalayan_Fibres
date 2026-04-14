"""Email Broadcast page — pick template, pick audience, (optionally) attach
per-recipient invoices, send.

Flow
----

1. Founder picks a template (dropdown of active rows in ``email_templates``).
2. Founder picks a segment (dropdown of active rows in ``segments``).
3. Right-side iframe previews the rendered HTML with dummy per-recipient vars.
4. Optional: founder opens the "📎 Invoice attachments" accordion, picks a
   recipient from a dropdown, drops a PDF, clicks Attach. The PDF uploads
   to Supabase Storage (bucket ``email-invoices``) and an EmailAttachment
   row is created linked to a draft Campaign.
5. Click Send Now → the draft Campaign flips to ``sending``, each recipient
   is resolved, variables are built via ``build_send_variables`` (shared
   config + contact + invoice_url from attachment if any), template is
   rendered with Jinja2, email is sent via Gmail API, EmailSend row is
   recorded, campaign totals updated.

Lazy draft campaign creation: the Campaign row is only created on first
successful attach OR on Send — not on page load — so opening the page
doesn't leak empty draft rows.
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
    """Render a single contact as a dropdown choice label+value.

    We embed the contact id into the value using a separator so the handler
    can reliably look up the Contact regardless of how Gradio renders the
    visible label.
    """
    first = (contact.first_name or "").strip()
    last = (contact.last_name or "").strip()
    name = (first + " " + last).strip() or contact.email or contact.id
    return f"{name} <{contact.email or '—'}>{_RECIPIENT_VALUE_SEP}{contact.id}"


def _parse_recipient_value(value: str) -> str | None:
    """Extract the contact id from a recipient dropdown value."""
    if not value or _RECIPIENT_VALUE_SEP not in value:
        return None
    return value.rsplit(_RECIPIENT_VALUE_SEP, 1)[-1] or None


def _resolve_segment_contacts(db, segment_id: str | None) -> list:
    """Return contacts for a segment, filtered to those with emails.

    Matches the existing email_campaigns.py flow: fall back to
    ``all opted-in / pending`` when the sentinel ``all_opted_in`` is
    passed, otherwise look up segment contacts via ``flows_engine``.
    """
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


def _build_sample_vars_for_preview(template_slug: str) -> dict:
    """Sample per-recipient vars used only for the preview iframe."""
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


def _render_preview_html(template_slug: str) -> str:
    """Render a template with sample vars for the preview panel."""
    if not template_slug:
        return (
            f'<div style="color:{COLORS.TEXT_MUTED};padding:40px;text-align:center;">'
            f"Pick a template to preview.</div>"
        )

    from services.email_personalization import build_send_variables
    from services.email_sender import render_template_by_slug
    from services.models import Contact

    # Build a dummy Contact-like object to pass to build_send_variables —
    # it only reads first_name/last_name/company/email off it. We use a
    # real Contact so callers don't need ad-hoc shims.
    stub = Contact(
        id="preview",
        email="preview@himalayanfibres.com",
        first_name="Alisha",
        last_name="Panda",
        company="",
    )
    vars_for_preview = build_send_variables(stub, {}, extra=_build_sample_vars_for_preview(template_slug))

    try:
        html = render_template_by_slug(template_slug, vars_for_preview)
    except Exception as e:
        log.exception("Preview render failed for %s", template_slug)
        return (
            f'<div style="color:#ef4444;padding:20px;">'
            f"Failed to render preview: {e}</div>"
        )

    # Wrap in an iframe-like scrollable container
    return (
        f'<div style="background:#ffffff;border:1px solid rgba(255,255,255,.08);'
        f"border-radius:10px;overflow:auto;max-height:70vh;\">{html}</div>"
    )


def _build_attachments_table_html(db, campaign_id: int | None, contact_ids: list[str]) -> str:
    """Render the 'Recipient | Email | Invoice' status table."""
    from services.models import Contact, EmailAttachment

    if not contact_ids:
        return (
            f'<div style="color:{COLORS.TEXT_MUTED};padding:12px;font-size:11px;">'
            f"Pick a segment to see recipients.</div>"
        )

    contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
    by_id = {c.id: c for c in contacts}

    attachments = {}
    if campaign_id:
        rows = (
            db.query(EmailAttachment)
            .filter(EmailAttachment.campaign_id == campaign_id)
            .all()
        )
        attachments = {r.contact_id: r for r in rows}

    tr_rows = []
    for cid in contact_ids:
        c = by_id.get(cid)
        if not c:
            continue
        name = (
            ((c.first_name or "") + " " + (c.last_name or "")).strip()
            or c.email
            or cid
        )
        att = attachments.get(cid)
        if att:
            status = (
                f'<span style="color:#22c55e;font-weight:600;">✓</span> '
                f'<span style="color:{COLORS.TEXT_SUBTLE};">{att.file_name or "invoice.pdf"}</span>'
            )
        else:
            status = f'<span style="color:{COLORS.TEXT_MUTED};">—</span>'
        tr_rows.append(
            f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
            f'<td style="padding:6px 10px;font-size:11px;color:{COLORS.TEXT};">{name}</td>'
            f'<td style="padding:6px 10px;font-size:11px;color:{COLORS.TEXT_SUBTLE};">{c.email}</td>'
            f"<td style=\"padding:6px 10px;font-size:11px;\">{status}</td></tr>"
        )

    return (
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="border-bottom:1px solid rgba(255,255,255,.06);">'
        f'<th style="padding:6px 10px;text-align:left;font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;">Recipient</th>'
        f'<th style="padding:6px 10px;text-align:left;font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;">Email</th>'
        f'<th style="padding:6px 10px;text-align:left;font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;">Invoice</th>'
        "</tr></thead><tbody>" + "".join(tr_rows) + "</tbody></table>"
    )


def _ensure_draft_campaign(db, existing_id: int | None, template_slug: str, segment_id: str | None) -> int:
    """Return the draft Campaign id, creating one if none exists yet.

    Lazy creation keeps the table clean when the founder opens the page
    and navigates away without attaching anything.
    """
    from services.models import Campaign

    if existing_id:
        row = db.query(Campaign).filter(Campaign.id == existing_id).first()
        if row is not None:
            # Keep the draft in sync with whatever the founder last picked
            row.template_slug = template_slug or row.template_slug
            row.segment_id = segment_id or row.segment_id
            db.flush()
            return row.id
        # If the id was stale (db reset etc.), fall through and create a new one

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


# ═══════════════════════════════════════════════════════════════════════
# Page builder
# ═══════════════════════════════════════════════════════════════════════

def build(ctx) -> dict:
    gr.HTML(
        f'<div style="font-size:15px;font-weight:700;color:{COLORS.TEXT};margin:0 0 4px;">Email Broadcast</div>'
        f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin-bottom:14px;">'
        f"Pick a template, pick an audience, (optionally) attach per-recipient invoices, and send.</div>"
    )

    # ── Session state (per-user in Gradio) ──
    draft_campaign_state = gr.State(None)  # campaign_id (int) or None
    recipient_ids_state = gr.State([])     # list[str] contact ids for current segment

    with gr.Row():
        # ═══════════════════ LEFT: compose controls ═══════════════════
        with gr.Column(scale=2, min_width=360):
            template_dropdown = gr.Dropdown(
                label="Template",
                choices=[],
                interactive=True,
            )
            segment_dropdown = gr.Dropdown(
                label="Audience (Segment)",
                choices=[],
                interactive=True,
            )
            subject_input = gr.Textbox(
                label="Subject",
                placeholder="Auto-fills from template — override if needed",
                interactive=True,
            )

            audience_kpi_html = gr.HTML(value="")

            # ── Attachments accordion ──
            with gr.Accordion("📎 Invoice attachments (optional)", open=False):
                gr.HTML(
                    f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin-bottom:8px;">'
                    f"Attach a PDF invoice for any recipient. The ‘Download Invoice’ button "
                    f"auto-appears in their email only. Recipients without an attachment see "
                    f"the email with no invoice button.</div>"
                )
                recipient_dropdown = gr.Dropdown(
                    label="Recipient",
                    choices=[],
                    interactive=True,
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
                attachments_table_html = gr.HTML(value="")

            # ── Send controls ──
            with gr.Row():
                send_btn = gr.Button("Send Now", variant="primary", size="sm", scale=2)
                test_btn = gr.Button("Send Test to Me", size="sm", scale=1)
            test_email_input = gr.Textbox(
                label="Test email",
                placeholder="your@email.com",
                interactive=True,
            )
            send_result_html = gr.HTML(value="")

        # ═══════════════════ RIGHT: preview ═══════════════════
        with gr.Column(scale=3, min_width=500):
            gr.HTML(
                f'<div style="font-size:12px;font-weight:600;color:{COLORS.TEXT};margin:0 0 6px;">Preview</div>'
            )
            preview_html = gr.HTML(value=_render_preview_html(""))

    # ═══════════════════════════════════════════════════════════════════
    # Event handlers
    # ═══════════════════════════════════════════════════════════════════

    def _on_template_change(template_slug: str):
        """Refresh subject + preview when the template changes."""
        from services.database import get_db
        from services.models import EmailTemplate

        if not template_slug:
            return "", _render_preview_html("")
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
        return subject, _render_preview_html(template_slug)

    template_dropdown.change(
        fn=_on_template_change,
        inputs=[template_dropdown],
        outputs=[subject_input, preview_html],
    )

    def _on_segment_change(segment_id: str, draft_id: int | None):
        """Resolve segment → contact list → recipient dropdown + KPI + table."""
        from services.database import get_db

        db = get_db()
        try:
            contacts = _resolve_segment_contacts(db, segment_id)
            choices = [_format_recipient(c) for c in contacts]
            cids = [c.id for c in contacts]
            n = len(contacts)
            kpi = (
                f'<div style="background:{COLORS.CARD_BG};border-radius:8px;padding:10px 14px;'
                f'border:1px solid rgba(255,255,255,.06);margin:8px 0;">'
                f'<span style="font-size:20px;font-weight:700;color:{COLORS.TEXT};">{n}</span>'
                f'<span style="font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;'
                f'letter-spacing:.5px;margin-left:8px;">recipients</span></div>'
            )
            table = _build_attachments_table_html(db, draft_id, cids)
        finally:
            db.close()
        return (
            gr.update(choices=choices, value=None),
            cids,
            kpi,
            table,
        )

    segment_dropdown.change(
        fn=_on_segment_change,
        inputs=[segment_dropdown, draft_campaign_state],
        outputs=[recipient_dropdown, recipient_ids_state, audience_kpi_html, attachments_table_html],
    )

    # ── Attach handler ──
    def _on_attach(
        template_slug: str,
        segment_id: str,
        recipient_value: str,
        file_bytes,
        draft_id: int | None,
        contact_ids: list[str],
    ):
        from services.database import get_db
        from services.models import EmailAttachment
        from services.supabase_storage import SupabaseStorageError, upload_file

        if not template_slug:
            return draft_id, _err("Pick a template first."), ""
        if not recipient_value:
            return draft_id, _err("Pick a recipient from the dropdown."), ""
        if not file_bytes:
            return draft_id, _err("Drop a PDF file first."), ""

        contact_id = _parse_recipient_value(recipient_value)
        if not contact_id:
            return draft_id, _err("Could not parse the selected recipient."), ""

        # file_bytes from gr.File(type="binary") is already raw bytes
        raw = file_bytes if isinstance(file_bytes, (bytes, bytearray)) else bytes(file_bytes)

        db = get_db()
        try:
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
                return draft_id, _err(f"Upload failed: {e}"), ""

            # Delete any existing attachment for this (campaign, contact, kind)
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

            table = _build_attachments_table_html(db, new_draft_id, contact_ids)
            return (
                new_draft_id,
                _ok(f"Attached invoice for {contact_id}"),
                table,
            )
        except Exception as e:
            db.rollback()
            log.exception("Attach failed")
            return draft_id, _err(f"Attach failed: {e}"), ""
        finally:
            db.close()

    attach_btn.click(
        fn=_on_attach,
        inputs=[
            template_dropdown,
            segment_dropdown,
            recipient_dropdown,
            invoice_file,
            draft_campaign_state,
            recipient_ids_state,
        ],
        outputs=[draft_campaign_state, attach_result_html, attachments_table_html],
    )

    # ── Remove handler ──
    def _on_remove(
        recipient_value: str,
        draft_id: int | None,
        contact_ids: list[str],
    ):
        from services.database import get_db
        from services.models import EmailAttachment
        from services.supabase_storage import SupabaseStorageError, delete_file

        if not draft_id:
            return _err("No draft campaign yet — nothing to remove."), ""
        contact_id = _parse_recipient_value(recipient_value)
        if not contact_id:
            return _err("Pick a recipient to remove the attachment."), ""

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
                return _ok("No attachment to remove."), _build_attachments_table_html(
                    db, draft_id, contact_ids
                )

            try:
                delete_file(att.storage_bucket, att.storage_path)
            except SupabaseStorageError:
                log.warning("Supabase delete failed for %s — removing DB row anyway", att.storage_path)

            db.delete(att)
            db.commit()
            table = _build_attachments_table_html(db, draft_id, contact_ids)
            return _ok(f"Removed attachment for {contact_id}"), table
        except Exception as e:
            db.rollback()
            log.exception("Remove failed")
            return _err(f"Remove failed: {e}"), ""
        finally:
            db.close()

    remove_btn.click(
        fn=_on_remove,
        inputs=[recipient_dropdown, draft_campaign_state, recipient_ids_state],
        outputs=[attach_result_html, attachments_table_html],
    )

    # ── Send Now handler ──
    def _on_send_now(
        template_slug: str,
        segment_id: str,
        subject: str,
        draft_id: int | None,
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
        from services.email_sender import EmailSender, render_template_by_slug, generate_idempotency_key
        from services.models import Campaign, EmailSend, EmailTemplate

        sender = EmailSender()
        if not sender.is_configured():
            return draft_id, _err(
                "Gmail API not configured. Set GMAIL_REFRESH_TOKEN / GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET in HF Space secrets."
            )

        db = get_db()
        try:
            contacts = _resolve_segment_contacts(db, segment_id)
            if not contacts:
                return draft_id, _err("No recipients resolved from that segment.")

            # Flip the draft into a real campaign (or create one if no draft)
            campaign_id = _ensure_draft_campaign(db, draft_id, template_slug, segment_id)
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            tpl = (
                db.query(EmailTemplate)
                .filter(EmailTemplate.slug == template_slug)
                .first()
            )
            if tpl is None:
                return campaign_id, _err(f"Template {template_slug!r} not found in DB.")

            campaign.name = f"Send: {tpl.name} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
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
            # Campaign is no longer a draft — clear the state so the next
            # compose cycle starts fresh
            return None, msg
        except Exception as e:
            db.rollback()
            log.exception("Send failed")
            return draft_id, _err(f"Send failed: {e}")
        finally:
            db.close()

    send_btn.click(
        fn=_on_send_now,
        inputs=[template_dropdown, segment_dropdown, subject_input, draft_campaign_state],
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
    # Initial load — populate dropdowns
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

            preview = _render_preview_html(first_slug or "")
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
    return (
        f'<div style="color:#22c55e;font-size:11px;padding:6px 0;">✓ {msg}</div>'
    )


def _err(msg: str) -> str:
    return (
        f'<div style="color:#ef4444;font-size:11px;padding:6px 0;">✗ {msg}</div>'
    )
