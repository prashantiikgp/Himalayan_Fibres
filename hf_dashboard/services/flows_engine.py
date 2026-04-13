"""Flow execution engine — runs multi-step email/WA automation flows.

Handles:
- Starting flows (create FlowRun, send step 1)
- Executing individual flow steps (email or WA template)
- Checking and executing pending steps (called periodically)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from services.models import Flow, FlowRun, Contact, Segment, EmailSend, WAMessage, WAChat
from services.email_sender import EmailSender, generate_idempotency_key

log = logging.getLogger(__name__)


def start_flow(db: Session, flow_id: int, segment_id: str | None, start_date: str | None = None) -> FlowRun:
    """Start a flow for a segment. Creates FlowRun and executes step 0 if start_date is today."""
    flow = db.query(Flow).filter(Flow.id == flow_id).first()
    if not flow:
        raise ValueError(f"Flow {flow_id} not found")

    # Count contacts in segment
    contacts = _get_segment_contacts(db, segment_id)
    total = len(contacts)

    # Calculate next step time
    steps = flow.steps or []
    next_step_at = None
    if len(steps) > 1:
        day_offset = steps[1].get("day", 1)
        next_step_at = datetime.now(timezone.utc) + timedelta(days=day_offset)

    run = FlowRun(
        flow_id=flow.id,
        segment_id=segment_id,
        status="active",
        current_step=0,
        total_contacts=total,
        next_step_at=next_step_at,
    )
    db.add(run)
    db.flush()

    # Execute step 0 immediately
    if steps:
        execute_flow_step(db, run, flow, 0, contacts)

    db.commit()
    log.info("Started flow '%s' with %d contacts", flow.name, total)
    return run


def execute_flow_step(db: Session, run: FlowRun, flow: Flow, step_index: int, contacts: list[Contact] | None = None):
    """Execute a specific step of a flow run."""
    steps = flow.steps or []
    if step_index >= len(steps):
        run.status = "completed"
        db.flush()
        return

    step = steps[step_index]

    if contacts is None:
        contacts = _get_segment_contacts(db, run.segment_id)

    sent = 0
    failed = 0

    if flow.channel == "email":
        sent, failed = _send_email_step(db, run, step, contacts)
    elif flow.channel == "whatsapp":
        sent, failed = _send_wa_step(db, run, step, contacts)

    run.current_step = step_index + 1
    run.total_sent = (run.total_sent or 0) + sent
    run.total_failed = (run.total_failed or 0) + failed

    # Set next step time or mark completed
    if step_index + 1 < len(steps):
        next_day = steps[step_index + 1].get("day", 0)
        current_day = step.get("day", 0)
        day_diff = max(next_day - current_day, 1)
        run.next_step_at = datetime.now(timezone.utc) + timedelta(days=day_diff)
    else:
        run.status = "completed"
        run.next_step_at = None

    db.flush()
    log.info("Flow step %d/%d: sent=%d, failed=%d", step_index + 1, len(steps), sent, failed)


def _send_email_step(db: Session, run: FlowRun, step: dict, contacts: list[Contact]) -> tuple[int, int]:
    """Send an email flow step to all contacts."""
    template_slug = step.get("template_slug", "")
    subject = step.get("subject", "")
    sent, failed = 0, 0

    sender = EmailSender()

    # Load template
    from services.models import EmailTemplate
    tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
    if not tpl:
        log.error("Template '%s' not found for flow step", template_slug)
        return 0, len(contacts)

    for contact in contacts:
        if not contact.email or "placeholder" in contact.email:
            continue
        if contact.consent_status != "opted_in" and contact.consent_status != "pending":
            continue

        # Idempotency
        idem_key = generate_idempotency_key(f"flow_{run.id}", contact.id, str(run.current_step))
        existing = db.query(EmailSend).filter(EmailSend.idempotency_key == idem_key).first()
        if existing:
            continue

        # Render
        variables = {
            "name": f"{contact.first_name} {contact.last_name}".strip() or "there",
            "first_name": contact.first_name or "there",
            "company_name": contact.company or "your company",
            "email": contact.email,
        }
        rendered_subject = sender.render_template(subject, variables)
        rendered_html = sender.render_template(tpl.html_content, variables)

        result = sender.send_email(contact.email, rendered_subject, rendered_html, to_name=contact.first_name)

        email_send = EmailSend(
            contact_id=contact.id,
            contact_email=contact.email,
            campaign_id=None,
            subject=rendered_subject,
            status="sent" if result["success"] else "failed",
            idempotency_key=idem_key,
            error_message=result.get("message", "") if not result["success"] else "",
            sent_at=datetime.now(timezone.utc) if result["success"] else None,
        )
        db.add(email_send)

        if result["success"]:
            sent += 1
            contact.total_emails_sent = (contact.total_emails_sent or 0) + 1
            contact.last_email_sent_at = datetime.now(timezone.utc)
        else:
            failed += 1

        time.sleep(3)  # Rate limit

    db.flush()
    return sent, failed


def _send_wa_step(db: Session, run: FlowRun, step: dict, contacts: list[Contact]) -> tuple[int, int]:
    """Send a WhatsApp template flow step to all contacts."""
    from services.wa_sender import WhatsAppSender
    from services.wa_config import get_wa_config

    wa_template = step.get("wa_template", "")
    variables = step.get("variables", [])
    sent, failed = 0, 0

    sender = WhatsAppSender()
    tpl_def = get_wa_config().get_template(wa_template)
    lang = tpl_def.language if tpl_def else "en_US"

    for contact in contacts:
        wa_id = contact.wa_id
        if not wa_id:
            continue

        # Render flow-step variables with contact data, paired with the
        # template's variable names so the sender can use named-param format.
        rendered_vars: list[tuple[str, str]] = []
        if tpl_def and tpl_def.variables:
            for i, var in enumerate(tpl_def.variables):
                raw = variables[i] if i < len(variables) else ""
                rendered = raw.replace("{{first_name}}", contact.first_name or "")
                rendered = rendered.replace("{{company_name}}", contact.company or "")
                if not rendered:
                    rendered = f"[{var.name}]"
                rendered_vars.append((var.name, rendered))

        ok, msg_id, error = sender.send_template(wa_id, wa_template, lang=lang, variables=rendered_vars or None)

        if ok:
            sent += 1
            contact.last_wa_outbound_at = datetime.now(timezone.utc)
        else:
            failed += 1
            log.warning("WA flow send failed for %s: %s", wa_id, error)

        time.sleep(1)  # Rate limit

    db.flush()
    return sent, failed


def check_pending_steps(db: Session) -> int:
    """Check and execute any pending flow steps. Returns count of steps executed."""
    now = datetime.now(timezone.utc)
    pending_runs = db.query(FlowRun).filter(
        FlowRun.status == "active",
        FlowRun.next_step_at <= now,
        FlowRun.next_step_at.isnot(None),
    ).all()

    executed = 0
    for run in pending_runs:
        flow = db.query(Flow).filter(Flow.id == run.flow_id).first()
        if not flow:
            run.status = "cancelled"
            continue

        execute_flow_step(db, run, flow, run.current_step)
        executed += 1

    if executed:
        db.commit()
        log.info("Executed %d pending flow steps", executed)

    return executed


def _get_segment_contacts(db: Session, segment_id: str | None) -> list[Contact]:
    """Get contacts for a segment, or all opted-in contacts."""
    if not segment_id or segment_id == "all":
        return db.query(Contact).filter(
            Contact.consent_status.in_(["opted_in", "pending"])
        ).all()

    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    if not segment or not segment.rules:
        return []

    rules = segment.rules
    q = db.query(Contact)

    if "customer_type" in rules:
        q = q.filter(Contact.customer_type.in_(rules["customer_type"]))
    if "customer_subtype" in rules:
        q = q.filter(Contact.customer_subtype.in_(rules["customer_subtype"]))
    if "geography" in rules:
        q = q.filter(Contact.geography.in_(rules["geography"]))

    return q.all()
