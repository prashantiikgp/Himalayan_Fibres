"""Email page — simplified. Pick contacts, pick template, send."""

from __future__ import annotations

from datetime import datetime, timezone
import time

import gradio as gr

from shared.theme import COLORS


def build(ctx) -> dict:
    # -- Step 1: Who to send to --
    gr.HTML(f'<div style="font-size:14px; font-weight:700; color:{COLORS.TEXT}; margin-bottom:4px;">Send Email</div>')
    gr.HTML(f'<div style="font-size:11px; color:{COLORS.TEXT_MUTED}; margin-bottom:12px;">Pick a template, choose your audience, and send.</div>')

    with gr.Row():
        template_dropdown = gr.Dropdown(label="1. Pick Template", choices=[], interactive=True, scale=1)
        segment_dropdown = gr.Dropdown(label="2. Send To", choices=[], interactive=True, scale=1)

    subject_input = gr.Textbox(label="3. Subject Line", placeholder="e.g. Premium Himalayan Fibers for {{company_name}}")

    # -- Preview --
    preview_html = gr.HTML(value="")

    # -- Send controls --
    with gr.Row():
        send_btn = gr.Button("Send Emails", variant="primary", size="sm", scale=1)
        send_test_btn = gr.Button("Send Test to Me", size="sm", scale=1)
        test_email_input = gr.Textbox(label="", placeholder="your@email.com", container=False, scale=1)

    result_html = gr.HTML(value="")

    # -- Past campaigns --
    gr.HTML(f'<div style="font-size:13px; font-weight:700; color:{COLORS.TEXT}; margin-top:20px;">Past Sends</div>')
    history_html = gr.HTML(value="")

    # -- Template preview on change --
    def _on_template_change(template_slug):
        if not template_slug:
            return ""
        from services.database import get_db
        from services.models import EmailTemplate
        db = get_db()
        try:
            tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
            if not tpl:
                return ""
            return (
                f'<div style="background:{COLORS.CARD_BG}; border-radius:8px; padding:12px; margin:8px 0;">'
                f'<div style="font-size:11px; color:{COLORS.TEXT_MUTED}; margin-bottom:4px;">Preview: {tpl.name}</div>'
                f'<div style="background:#fff; border-radius:6px; padding:12px; max-height:300px; overflow-y:auto;">'
                f'{tpl.html_content[:2000]}</div></div>'
            )
        finally:
            db.close()

    template_dropdown.change(fn=_on_template_change, inputs=[template_dropdown], outputs=[preview_html])

    # -- Send test email --
    def _send_test(template_slug, subject, test_email):
        if not test_email or not template_slug:
            return f'<div style="color:#ef4444; font-size:11px;">Select a template and enter your email</div>'

        from services.database import get_db
        from services.models import EmailTemplate
        from services.email_sender import EmailSender

        db = get_db()
        try:
            tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
            if not tpl:
                return f'<div style="color:#ef4444; font-size:11px;">Template not found</div>'

            sender = EmailSender()
            if not sender.smtp_password:
                return f'<div style="color:#ef4444; font-size:11px;">SMTP_PASSWORD not set. Add it in HF Space Settings → Secrets.</div>'

            result = sender.send_email(test_email, subject or tpl.subject_template, tpl.html_content)
            if result["success"]:
                return f'<div style="color:#22c55e; font-size:11px;">Test email sent to {test_email}</div>'
            return f'<div style="color:#ef4444; font-size:11px;">{result["message"]}</div>'
        finally:
            db.close()

    send_test_btn.click(fn=_send_test, inputs=[template_dropdown, subject_input, test_email_input], outputs=[result_html])

    # -- Send campaign --
    def _send_campaign(template_slug, segment_id, subject):
        if not template_slug or not subject:
            return f'<div style="color:#ef4444; font-size:11px;">Select a template and enter a subject line</div>'

        from services.database import get_db
        from services.models import EmailTemplate, Contact, EmailSend, Campaign
        from services.email_sender import EmailSender, generate_idempotency_key

        db = get_db()
        try:
            tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
            if not tpl:
                return f'<div style="color:#ef4444; font-size:11px;">Template not found</div>'

            sender = EmailSender()
            if not sender.smtp_password:
                return f'<div style="color:#ef4444; font-size:11px;">SMTP_PASSWORD not set. Add it in HF Space Settings → Secrets.</div>'

            # Get contacts
            if segment_id and segment_id != "all_opted_in":
                from services.flows_engine import _get_segment_contacts
                contacts = _get_segment_contacts(db, segment_id)
            else:
                contacts = db.query(Contact).filter(Contact.consent_status.in_(["opted_in", "pending"])).all()

            valid = [c for c in contacts if c.email and "placeholder" not in c.email]

            if not valid:
                return f'<div style="color:#ef4444; font-size:11px;">No contacts to send to. Opt in some contacts first.</div>'

            # Create campaign record
            campaign = Campaign(name=f"Send: {tpl.name}", subject=subject,
                               template_slug=template_slug, segment_id=segment_id, status="sending")
            db.add(campaign)
            db.flush()

            sent, failed = 0, 0
            for contact in valid:
                idem_key = generate_idempotency_key(f"campaign_{campaign.id}", contact.id)
                if db.query(EmailSend).filter(EmailSend.idempotency_key == idem_key).first():
                    continue

                variables = {
                    "name": f"{contact.first_name} {contact.last_name}".strip() or "there",
                    "first_name": contact.first_name or "there",
                    "company_name": contact.company or "your company",
                    "email": contact.email,
                }
                rendered_subject = sender.render_template(subject, variables)
                rendered_html = sender.render_template(tpl.html_content, variables)

                result = sender.send_email(contact.email, rendered_subject, rendered_html, to_name=contact.first_name)

                db.add(EmailSend(
                    contact_id=contact.id, contact_email=contact.email,
                    campaign_id=campaign.id, subject=rendered_subject,
                    status="sent" if result["success"] else "failed",
                    idempotency_key=idem_key,
                    error_message="" if result["success"] else result.get("message", ""),
                    sent_at=datetime.now(timezone.utc) if result["success"] else None,
                ))

                if result["success"]:
                    sent += 1
                else:
                    failed += 1

                time.sleep(3)

            campaign.status = "sent"
            campaign.total_recipients = len(valid)
            campaign.total_sent = sent
            campaign.total_failed = failed
            campaign.sent_at = datetime.now(timezone.utc)
            db.commit()

            color = "#22c55e" if failed == 0 else "#f59e0b"
            return (
                f'<div style="background:{COLORS.CARD_BG}; border-radius:8px; padding:12px; '
                f'border-left:4px solid {color};">'
                f'<div style="font-weight:600; color:{color};">Done!</div>'
                f'<div style="color:{COLORS.TEXT_SUBTLE}; font-size:11px;">Sent: {sent} | Failed: {failed} | Total: {len(valid)}</div>'
                f'</div>'
            )
        except Exception as e:
            db.rollback()
            return f'<div style="color:#ef4444; font-size:11px;">Error: {e}</div>'
        finally:
            db.close()

    send_btn.click(fn=_send_campaign, inputs=[template_dropdown, segment_dropdown, subject_input], outputs=[result_html])

    # -- Build past campaigns history --
    def _build_history(db):
        from services.models import Campaign
        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).limit(10).all()
        if not campaigns:
            return f'<div style="color:{COLORS.TEXT_MUTED}; font-size:11px; padding:8px;">No emails sent yet.</div>'

        rows = ""
        for c in campaigns:
            color = {"sent": "#22c55e", "sending": "#f59e0b", "draft": "#64748b", "failed": "#ef4444"}.get(c.status, "#64748b")
            date = c.sent_at.strftime("%Y-%m-%d %H:%M") if c.sent_at else "—"
            rows += f"""<tr style="border-bottom:1px solid rgba(255,255,255,.04);">
                <td style="padding:6px 10px; font-size:11px; color:{COLORS.TEXT};">{c.name}</td>
                <td style="padding:6px 10px; font-size:11px; color:{color};">{c.status}</td>
                <td style="padding:6px 10px; font-size:11px; color:{COLORS.TEXT_SUBTLE};">{c.total_sent or 0} sent</td>
                <td style="padding:6px 10px; font-size:11px; color:{COLORS.TEXT_MUTED};">{date}</td>
            </tr>"""

        return f"""<table style="width:100%; border-collapse:collapse; margin-top:4px;">
            <thead><tr style="border-bottom:1px solid rgba(255,255,255,.06);">
                <th style="padding:6px 10px; text-align:left; font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase;">Name</th>
                <th style="padding:6px 10px; text-align:left; font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase;">Status</th>
                <th style="padding:6px 10px; text-align:left; font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase;">Sent</th>
                <th style="padding:6px 10px; text-align:left; font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase;">Date</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>"""

    # -- Refresh --
    def _refresh():
        from services.database import get_db
        from services.models import EmailTemplate, Segment, Contact
        db = get_db()
        try:
            templates = db.query(EmailTemplate).filter(EmailTemplate.is_active == True).all()
            tpl_choices = [t.slug for t in templates]

            segments = db.query(Segment).filter(Segment.is_active == True).all()
            seg_choices = ["all_opted_in"] + [s.id for s in segments]

            history = _build_history(db)

            return (
                gr.update(choices=tpl_choices, value=tpl_choices[0] if tpl_choices else None),
                gr.update(choices=seg_choices, value="all_opted_in"),
                history,
            )
        finally:
            db.close()

    return {"update_fn": _refresh, "outputs": [template_dropdown, segment_dropdown, history_html]}
