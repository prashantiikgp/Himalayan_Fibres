"""Flow execution engine v2 — per-contact memberships, multi-channel steps.

Replaces the cohort-shaped v1 (`hf_dashboard/services/flows_engine.py`,
which is preserved for legacy `flow_runs` reads). This module is the
Phase 7.7 engine that drives `flow_memberships` and `flow_step_runs`.

PLAN_flows §3-§5 reference. Key invariants:

* Per-contact `flow_memberships` row is the unit of state. Status is
  one of {active, waiting_event, paused, completed, failed, stopped}.
* Idempotency key for every send — the **channel suffix is required**
  so multi-channel steps don't collide:
      ``flowmem_<membership_id>_step_<step_index>_<channel>``
* `membership.metadata_json` (NOT `.metadata` — SQLAlchemy reserves the
  attribute name) carries per-membership send vars (tracking_id,
  courier_name, ...).
* Trigger evaluators are wired only into the dedicated mutator
  endpoints (lifecycle, PATCH-with-tag-diff). Bulk paths must NOT call
  them — see §9.5 storm prevention.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

# These imports rely on hf_dashboard/ being on sys.path (api_v2/main.py
# inserts it before importing routers — same pattern as scheduler.py).
from services.database import get_db  # type: ignore[import-not-found]
from services.interactions import log_interaction  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Contact,
    EmailSend,
    EmailTemplate,
    Flow,
    FlowMembership,
    FlowStepRun,
    WAChat,
    WAMessage,
)

log = logging.getLogger("api_v2.flows_engine_v2")

# §5.6: hard limit on memberships fired per tick. At 3s/email this
# caps a worst-case all-email tick around 60s, matching the cadence.
TICK_LIMIT = 20

# Sender rate limits (mirrors broadcast_engine).
EMAIL_SEND_DELAY_S = 3
WA_SEND_DELAY_S = 1

# §5.7: failure budget per step before the membership flips to failed.
MAX_CONSECUTIVE_FAILURES = 3


# ─────────────────────────────────────────────────────────────────────
# Duration parsing
# ─────────────────────────────────────────────────────────────────────


def parse_duration(spec: dict | None) -> timedelta:
    """Parse `{value, unit}` per §3.3. Defaults to 0s."""
    if not spec:
        return timedelta(0)
    value = int(spec.get("value", 0))
    unit = (spec.get("unit") or "days").lower()
    if unit in {"minute", "minutes", "min"}:
        return timedelta(minutes=value)
    if unit in {"hour", "hours", "hr"}:
        return timedelta(hours=value)
    if unit in {"day", "days", "d"}:
        return timedelta(days=value)
    log.warning("parse_duration: unknown unit %r — treating as days", unit)
    return timedelta(days=value)


# ─────────────────────────────────────────────────────────────────────
# Step conditions
# ─────────────────────────────────────────────────────────────────────


def _check_conditions(contact: Contact, conditions: list[dict] | None) -> tuple[bool, str]:
    """Return (passed, reason). PLAN §3.3 condition shape."""
    if not conditions:
        return True, ""
    for cond in conditions:
        field = cond.get("field", "")
        op = cond.get("op", "exists")
        val = getattr(contact, field, None)

        if op == "exists":
            if not val or (isinstance(val, str) and not val.strip()):
                return False, f"{field} missing"
            if isinstance(val, str) and "placeholder" in val:
                # Placeholder emails (wa_*@placeholder.local) don't count
                # as a real address — same convention as broadcast_engine.
                return False, f"{field} is placeholder"
        elif op == "in":
            allowed = cond.get("values") or []
            if val not in allowed:
                return False, f"{field}={val!r} not in {allowed}"
        elif op == "not_in":
            denied = cond.get("values") or []
            if val in denied:
                return False, f"{field}={val!r} in deny list {denied}"
        elif op == "equals":
            if val != cond.get("value"):
                return False, f"{field}={val!r} != {cond.get('value')!r}"
        else:
            log.warning("unknown condition op %r — treating as fail-open", op)
    return True, ""


def _channels_for_step(step: dict) -> list[str]:
    """A step can fire on email, whatsapp, or both. Returns the channels
    actually requested by the step JSON."""
    channel = (step.get("channel") or "email").lower()
    if channel == "both":
        return ["email", "whatsapp"]
    if channel in {"email", "whatsapp"}:
        return [channel]
    log.warning("unknown step.channel %r — defaulting to email", channel)
    return ["email"]


# ─────────────────────────────────────────────────────────────────────
# Trigger idempotency (§4.5) — pre-insert SELECT
# ─────────────────────────────────────────────────────────────────────

ACTIVE_STATUSES = ("active", "waiting_event", "paused")


def _has_live_membership(db: Session, flow_id: int, contact_id: str) -> bool:
    return (
        db.query(FlowMembership)
        .filter(
            FlowMembership.flow_id == flow_id,
            FlowMembership.contact_id == contact_id,
            FlowMembership.status.in_(ACTIVE_STATUSES),
        )
        .first()
        is not None
    )


def assign_flow(
    db: Session,
    *,
    flow_id: int,
    contact_id: str,
    trigger_source: str,
    trigger_actor: str = "",
    trigger_payload: dict | None = None,
    metadata: dict | None = None,
    commit: bool = False,
) -> FlowMembership | None:
    """Insert a `flow_memberships` row for (flow, contact). Idempotent.

    The pre-insert SELECT bounds the race; the partial unique index
    `fm_contact_flow_uniq` is the structural guarantee under concurrent
    triggers (§3.4 / §4.5). On constraint violation we swallow and
    return None — that's the "already enrolled" signal.

    Step 0's `next_fire_at` is now() so the first tick claims it.
    """
    if _has_live_membership(db, flow_id, contact_id):
        log.debug("assign_flow: %s already in flow %s — skip", contact_id, flow_id)
        return None

    now = datetime.now(timezone.utc)
    # SAVEPOINT-isolated insert: if the partial unique index
    # (`fm_contact_flow_uniq`) rejects the row because a concurrent
    # trigger raced us, only the SAVEPOINT is rolled back — the
    # caller's pending lifecycle/tag write stays intact. Without this
    # the implicit `db.rollback()` would silently discard the entire
    # outer transaction, losing the lifecycle change that was the
    # whole reason this evaluator ran. Trigger evaluation must be
    # best-effort by design.
    member = FlowMembership(
        flow_id=flow_id,
        contact_id=contact_id,
        status="active",
        current_step_index=0,
        started_at=now,
        next_fire_at=now,
        trigger_source=trigger_source,
        trigger_actor=trigger_actor or "",
        trigger_payload=trigger_payload or {},
        metadata_json=metadata or {},
    )
    try:
        with db.begin_nested():
            db.add(member)
            db.flush()
    except IntegrityError:
        log.debug(
            "assign_flow: race on (flow_id=%s, contact_id=%s) — already enrolled",
            flow_id, contact_id,
        )
        return None

    # Activity-tab visibility — the drawer surfaces flow events for free.
    log_interaction(
        db,
        contact_id=contact_id,
        kind="flow_assigned",
        summary=f"Assigned to flow #{flow_id} via {trigger_source}",
        payload={"flow_id": flow_id, "membership_id": member.id, "trigger_source": trigger_source},
        actor=trigger_actor or "system",
        commit=False,
    )

    if commit:
        db.commit()
    return member


# ─────────────────────────────────────────────────────────────────────
# Trigger evaluators (§4.2, §4.3)
# ─────────────────────────────────────────────────────────────────────


def evaluate_lifecycle_trigger(
    db: Session,
    *,
    contact: Contact,
    old_lifecycle: str,
    new_lifecycle: str,
) -> int:
    """Find lifecycle-trigger flows whose `trigger_config.to` matches
    `new_lifecycle` and assign the contact to each. Inline; same
    transaction as the lifecycle write. Returns count of new memberships.
    """
    if not new_lifecycle or new_lifecycle == old_lifecycle:
        return 0

    flows = (
        db.query(Flow)
        .filter(Flow.trigger_type == "lifecycle", Flow.is_active.is_(True))
        .all()
    )
    n = 0
    for flow in flows:
        cfg = flow.trigger_config or {}
        to_match = cfg.get("to") or cfg.get("lifecycle")
        if isinstance(to_match, str):
            matches = (to_match == new_lifecycle)
        elif isinstance(to_match, list):
            matches = (new_lifecycle in to_match)
        else:
            matches = False
        if not matches:
            continue

        # §7.2 compound: optional customer_type filter — only useful for
        # lifecycle triggers but we keep the door open with a simple
        # equals/in check.
        ctype_filter = cfg.get("customer_type")
        if ctype_filter:
            actual = contact.customer_type or ""
            if isinstance(ctype_filter, str) and actual != ctype_filter:
                continue
            if isinstance(ctype_filter, list) and actual not in ctype_filter:
                continue

        member = assign_flow(
            db,
            flow_id=flow.id,
            contact_id=contact.id,
            trigger_source="lifecycle",
            trigger_payload={"old": old_lifecycle, "new": new_lifecycle},
        )
        if member is not None:
            n += 1
    return n


def evaluate_tag_trigger(
    db: Session,
    *,
    contact_id: str,
    tag_name: str,
) -> int:
    """Find tag-trigger flows whose `trigger_config.tag` matches
    `tag_name` and assign the contact. Inline; same transaction as the
    tag write. Also resumes any `waiting_event` memberships whose
    current step has a matching `trigger_event`.
    Returns count of new memberships (resumed memberships are not
    counted in the return — they update existing rows).
    """
    if not tag_name:
        return 0
    tag_name = tag_name.strip()

    n_new = 0
    # 1. New enrollments.
    flows = (
        db.query(Flow)
        .filter(Flow.trigger_type == "tag", Flow.is_active.is_(True))
        .all()
    )
    for flow in flows:
        cfg = flow.trigger_config or {}
        configured = cfg.get("tag") or ""
        if configured != tag_name:
            continue
        member = assign_flow(
            db,
            flow_id=flow.id,
            contact_id=contact_id,
            trigger_source="tag",
            trigger_payload={"tag": tag_name},
        )
        if member is not None:
            n_new += 1

    # 2. Resume memberships parked at waiting_event whose current step's
    # trigger_event matches `tag_added:<tag_name>`.
    parked = (
        db.query(FlowMembership)
        .filter(
            FlowMembership.contact_id == contact_id,
            FlowMembership.status == "waiting_event",
        )
        .all()
    )
    if parked:
        flow_ids = {m.flow_id for m in parked}
        flow_map = {
            f.id: f
            for f in db.query(Flow).filter(Flow.id.in_(flow_ids)).all()
        }
        now = datetime.now(timezone.utc)
        for m in parked:
            flow = flow_map.get(m.flow_id)
            if not flow:
                continue
            steps = flow.steps or []
            if m.current_step_index >= len(steps):
                continue
            step = steps[m.current_step_index]
            ev = step.get("trigger_event") or {}
            if ev.get("type") == "tag" and ev.get("value") == tag_name:
                m.status = "active"
                m.next_fire_at = now
                m.error = ""
                log.info("resume membership %s on tag %r", m.id, tag_name)

    return n_new


# ─────────────────────────────────────────────────────────────────────
# Idempotency key + step run audit
# ─────────────────────────────────────────────────────────────────────


def _idem_key(membership_id: int, step_index: int, channel: str) -> str:
    return f"flowmem_{membership_id}_step_{step_index}_{channel}"


def _email_send_idem_key(membership_id: int, step_index: int) -> str:
    """Fits the 64-char `email_sends.idempotency_key` column without
    truncation. Distinct from the FlowStepRun key (96 chars) because
    that column is wider and we want easy grep'ability there."""
    import hashlib

    raw = f"flowmem_{membership_id}_step_{step_index}_email"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:40]
    return f"flowmem_{digest}"


def _record_step_run(
    db: Session,
    *,
    membership_id: int,
    step_index: int,
    channel: str,
    status: str,
    template_slug: str,
    message_ref: str = "",
    error: str = "",
) -> bool:
    """Insert a FlowStepRun row. Returns False if the unique key blocks
    the insert (the row already exists — caller decides next step).

    SAVEPOINT-isolated: if the unique constraint rejects the insert,
    only the nested transaction is rolled back; the caller's outer
    transaction (and any prior step's writes) stays intact. This is
    the same pattern as `assign_flow`."""
    row = FlowStepRun(
        membership_id=membership_id,
        step_index=step_index,
        channel=channel,
        status=status,
        template_slug=template_slug,
        message_ref=message_ref,
        error=error,
        idempotency_key=_idem_key(membership_id, step_index, channel),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return True
    except IntegrityError:
        log.debug(
            "step_run idempotency blocked re-insert mem=%s step=%s ch=%s",
            membership_id, step_index, channel,
        )
        return False


def _existing_step_run(
    db: Session, *, membership_id: int, step_index: int, channel: str
) -> FlowStepRun | None:
    return (
        db.query(FlowStepRun)
        .filter(
            FlowStepRun.idempotency_key == _idem_key(membership_id, step_index, channel)
        )
        .first()
    )


def _claim_or_recover_placeholder(
    db: Session, *, membership_id: int, step_index: int, channel: str, template_slug: str,
) -> tuple[str, FlowStepRun | None]:
    """Insert a 'sending' placeholder, OR recover an existing one.

    Returns ``(action, row)``:
      - ``("fresh", row)``     — no prior attempt, placeholder inserted, proceed.
      - ``("retry", row)``     — prior attempt left the row in 'sending'
        (stranded by a crash). The send should be retried; reuse row.
      - ``("done", row)``      — terminal state already (sent / failed /
        skipped); caller must NOT re-fire.

    The reaper (`reap_stranded_memberships`) re-arms the membership but
    doesn't touch step-run rows; this is the per-step recovery half.
    """
    if _record_step_run(
        db,
        membership_id=membership_id,
        step_index=step_index,
        channel=channel,
        status="sending",
        template_slug=template_slug,
    ):
        return "fresh", _existing_step_run(
            db, membership_id=membership_id, step_index=step_index, channel=channel,
        )

    existing = _existing_step_run(
        db, membership_id=membership_id, step_index=step_index, channel=channel,
    )
    if existing is None:
        # Truly weird — flush said duplicate but the SELECT can't find
        # it. Treat as fresh; the next flush will surface a clearer
        # error if there's a real problem.
        return "fresh", None

    if existing.status in ("sent", "failed", "skipped"):
        return "done", existing

    # status='sending' (or any other non-terminal value) → stranded.
    # Caller will retry the send and update the row in place.
    log.warning(
        "recovering stranded step_run mem=%s step=%s ch=%s status=%s",
        membership_id, step_index, channel, existing.status,
    )
    return "retry", existing


# ─────────────────────────────────────────────────────────────────────
# Send paths (email + WA)
# ─────────────────────────────────────────────────────────────────────


def _build_email_vars(
    contact: Contact, membership_metadata: dict, step_extra: dict | None = None
) -> dict[str, Any]:
    """Per-recipient variables for a flow email.

    Sources merged (last wins):
      1. shared branding config (banner_url, footer, social, ...)
      2. contact fields (first_name, name, email, contact_company)
      3. membership.metadata_json (tracking_id, courier_name, ...)
      4. step.vars_template once it's resolved (Phase 7.9 work)
    """
    from services.email_personalization import build_send_variables  # type: ignore

    extra: dict[str, Any] = {}
    if membership_metadata:
        extra.update(membership_metadata)
    if step_extra:
        extra.update(step_extra)
    return build_send_variables(contact, attachments={}, extra=extra)


def _send_email_step(
    db: Session,
    *,
    membership: FlowMembership,
    contact: Contact,
    step: dict,
    step_index: int,
) -> tuple[str, str]:
    """Run the email half of a step. Returns (status, error).
    `status` ∈ {"sent","failed","skipped"}. Side-effects: writes
    EmailSend + FlowStepRun + log_interaction."""
    from services.email_sender import (  # type: ignore
        EmailSender,
        render_template_by_slug,
        render_template_string,
    )

    template_slug = step.get("template_slug") or ""
    if not template_slug:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="email",
            status="skipped",
            template_slug="",
            error="no template_slug",
        )
        return "skipped", "no template_slug"

    tpl = (
        db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
    )
    if not tpl:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="email",
            status="skipped",
            template_slug=template_slug,
            error="template_missing",
        )
        return "skipped", "template_missing"

    ok, reason = _check_conditions(contact, step.get("conditions"))
    if not ok:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="email",
            status="skipped",
            template_slug=template_slug,
            error=f"conditions_failed: {reason}",
        )
        return "skipped", reason

    sender = EmailSender()
    if not sender.is_configured():
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="email",
            status="failed",
            template_slug=template_slug,
            error="gmail_not_configured",
        )
        return "failed", "gmail_not_configured"

    variables = _build_email_vars(
        contact,
        membership.metadata_json or {},
        step_extra=step.get("vars_template") or None,
    )
    subject_src = (
        step.get("subject_override") or tpl.subject_template or ""
    )
    try:
        rendered_html = render_template_by_slug(template_slug, variables)
        rendered_subject = render_template_string(subject_src, variables)
    except Exception as e:
        log.exception("flow render failed mem=%s step=%s", membership.id, step_index)
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="email",
            status="failed",
            template_slug=template_slug,
            error=f"render_error: {e}",
        )
        return "failed", f"render_error: {e}"

    # Idempotency + stranded-attempt recovery. The placeholder is the
    # safety net for the next-tick reclaim if anything below crashes.
    action, run = _claim_or_recover_placeholder(
        db,
        membership_id=membership.id,
        step_index=step_index,
        channel="email",
        template_slug=template_slug,
    )
    if action == "done" and run is not None:
        # The previous attempt reached a terminal state (sent, failed,
        # or skipped) — never re-fire. Surface the prior outcome so the
        # caller advances or accounts for the failure correctly.
        return run.status, run.error or "idempotent_skip"

    # We have to commit the placeholder before the network call so a
    # concurrent tick (or post-crash reaper) can see it.
    db.commit()

    try:
        result = sender.send_email(
            contact.email, rendered_subject, rendered_html,
            to_name=contact.first_name,
        )
    except Exception as e:
        log.exception(
            "EmailSender.send_email raised mem=%s step=%s", membership.id, step_index,
        )
        # Mark the placeholder failed so the next tick treats it as a
        # terminal failure rather than a "stranded sending" retry.
        run_now = _existing_step_run(
            db, membership_id=membership.id, step_index=step_index, channel="email",
        )
        if run_now:
            run_now.status = "failed"
            run_now.error = f"send_exception: {e}"[:1000]
            db.commit()
        return "failed", f"send_exception: {e}"

    # Update placeholder + write EmailSend row.
    run = _existing_step_run(
        db, membership_id=membership.id, step_index=step_index, channel="email",
    )
    success = bool(result.get("success"))
    if run:
        run.status = "sent" if success else "failed"
        run.message_ref = result.get("message_id", "") or ""
        run.error = "" if success else (result.get("message", "") or "")[:1000]

    db.add(EmailSend(
        contact_id=contact.id,
        contact_email=contact.email or "",
        campaign_id=None,
        subject=rendered_subject,
        status="sent" if success else "failed",
        idempotency_key=_email_send_idem_key(membership.id, step_index),
        error_message="" if success else (result.get("message", "") or "")[:1000],
        sent_at=datetime.now(timezone.utc) if success else None,
    ))

    if success:
        contact.total_emails_sent = (contact.total_emails_sent or 0) + 1
        contact.last_email_sent_at = datetime.now(timezone.utc)

    log_interaction(
        db,
        contact_id=contact.id,
        kind="flow_step_sent" if success else "email_sent",
        summary=f"Flow step {step_index} email · {template_slug}",
        payload={
            "membership_id": membership.id,
            "flow_id": membership.flow_id,
            "step_index": step_index,
            "channel": "email",
            "template_slug": template_slug,
            "ok": success,
        },
        actor="system",
        commit=False,
    )

    db.commit()
    time.sleep(EMAIL_SEND_DELAY_S)
    return ("sent" if success else "failed", "" if success else result.get("message", ""))


def _send_wa_step(
    db: Session,
    *,
    membership: FlowMembership,
    contact: Contact,
    step: dict,
    step_index: int,
) -> tuple[str, str]:
    """Run the WhatsApp half of a step. Returns (status, error)."""
    from services.wa_config import get_wa_config  # type: ignore
    from services.wa_sender import WhatsAppSender  # type: ignore

    wa_template = step.get("wa_template") or ""
    if not wa_template:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="whatsapp",
            status="skipped",
            template_slug="",
            error="no wa_template",
        )
        return "skipped", "no wa_template"

    if not contact.wa_id:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="whatsapp",
            status="skipped",
            template_slug=wa_template,
            error="no wa_id",
        )
        return "skipped", "no wa_id"

    ok, reason = _check_conditions(contact, step.get("conditions"))
    if not ok:
        _record_step_run(
            db,
            membership_id=membership.id,
            step_index=step_index,
            channel="whatsapp",
            status="skipped",
            template_slug=wa_template,
            error=f"conditions_failed: {reason}",
        )
        return "skipped", reason

    action, run = _claim_or_recover_placeholder(
        db,
        membership_id=membership.id,
        step_index=step_index,
        channel="whatsapp",
        template_slug=wa_template,
    )
    if action == "done" and run is not None:
        return run.status, run.error or "idempotent_skip"
    db.commit()

    sender = WhatsAppSender()
    cfg = get_wa_config()
    tpl_def = cfg.get_template(wa_template)
    lang = step.get("wa_template_lang") or (tpl_def.language if tpl_def else "en")

    # Render variables. Step-level `wa_variables` is a list of strings
    # with `{{first_name}}` / `{{tracking_id}}` style placeholders that
    # we resolve from contact + membership.metadata_json.
    raw_vars = step.get("wa_variables") or []
    metadata = membership.metadata_json or {}
    rendered_vars: list[tuple[str, str]] = []
    if tpl_def and tpl_def.variables:
        for i, var in enumerate(tpl_def.variables):
            raw = raw_vars[i] if i < len(raw_vars) else ""
            value = _resolve_wa_token(raw, contact, metadata) or f"[{var.name}]"
            rendered_vars.append((var.name, value))
    else:
        for raw in raw_vars:
            value = _resolve_wa_token(raw, contact, metadata)
            rendered_vars.append(("", value))

    try:
        sent_ok, msg_id, error = sender.send_template(
            contact.wa_id, wa_template, lang=lang,
            variables=rendered_vars or None,
        )
    except Exception as e:
        log.exception(
            "WhatsAppSender.send_template raised mem=%s step=%s",
            membership.id, step_index,
        )
        run_now = _existing_step_run(
            db, membership_id=membership.id, step_index=step_index, channel="whatsapp",
        )
        if run_now:
            run_now.status = "failed"
            run_now.error = f"send_exception: {e}"[:1000]
            db.commit()
        return "failed", f"send_exception: {e}"

    run = _existing_step_run(
        db, membership_id=membership.id, step_index=step_index, channel="whatsapp",
    )
    if run:
        run.status = "sent" if sent_ok else "failed"
        run.message_ref = msg_id or ""
        run.error = "" if sent_ok else (error or "")[:1000]

    if sent_ok:
        contact.last_wa_outbound_at = datetime.now(timezone.utc)
        chat = db.query(WAChat).filter(WAChat.contact_id == contact.id).first()
        if not chat:
            chat = WAChat(contact_id=contact.id)
            db.add(chat)
            db.flush()
        db.add(WAMessage(
            chat_id=chat.id,
            contact_id=contact.id,
            direction="out",
            status="sent",
            text=f"[Flow template: {wa_template}]",
            wa_message_id=msg_id,
            wa_batch_id=f"flowmem_{membership.id}",
        ))

    log_interaction(
        db,
        contact_id=contact.id,
        kind="flow_step_sent" if sent_ok else "wa_sent",
        summary=f"Flow step {step_index} WA · {wa_template}",
        payload={
            "membership_id": membership.id,
            "flow_id": membership.flow_id,
            "step_index": step_index,
            "channel": "whatsapp",
            "template_slug": wa_template,
            "ok": sent_ok,
        },
        actor="system",
        commit=False,
    )

    db.commit()
    time.sleep(WA_SEND_DELAY_S)
    return ("sent" if sent_ok else "failed", "" if sent_ok else (error or ""))


def _resolve_wa_token(token: str, contact: Contact, metadata: dict) -> str:
    """Resolve a single `{{name}}` token from contact + membership metadata.
    No regex — literal substitution only, like v1's flows engine."""
    if not token:
        return ""
    out = token
    out = out.replace("{{first_name}}", contact.first_name or "")
    out = out.replace("{{last_name}}", contact.last_name or "")
    out = out.replace("{{company_name}}", contact.company or "")
    out = out.replace("{{name}}", (f"{contact.first_name or ''} {contact.last_name or ''}").strip() or "")
    for key, value in (metadata or {}).items():
        out = out.replace(f"{{{{{key}}}}}", str(value or ""))
    return out


# ─────────────────────────────────────────────────────────────────────
# Single-membership fire (called from threadpool executor)
# ─────────────────────────────────────────────────────────────────────


def fire_membership_step(membership_id: int) -> dict:
    """Fire one membership's current step. Opens its own session.

    Called from `tick_flows` via `loop.run_in_executor` so the blocking
    sleeps inside the senders don't block the asyncio event loop.

    Either advances `current_step_index += 1` and reschedules
    `next_fire_at`, parks at `waiting_event`, completes, or fails.
    """
    db = get_db()
    try:
        member = db.query(FlowMembership).filter(FlowMembership.id == membership_id).first()
        if member is None:
            return {"ok": False, "error": "membership_gone"}
        if member.status != "active":
            log.info("fire_membership_step: mem=%s status=%s — skip", membership_id, member.status)
            return {"ok": False, "error": f"status={member.status}"}

        flow = db.query(Flow).filter(Flow.id == member.flow_id).first()
        if flow is None:
            member.status = "failed"
            member.error = "flow_gone"
            db.commit()
            return {"ok": False, "error": "flow_gone"}

        steps: list[dict] = list(flow.steps or [])
        idx = member.current_step_index
        if idx >= len(steps):
            member.status = "completed"
            member.next_fire_at = None
            member.last_step_at = datetime.now(timezone.utc)
            log_interaction(
                db,
                contact_id=member.contact_id,
                kind="flow_completed",
                summary=f"Flow #{flow.id} completed",
                payload={"membership_id": member.id, "flow_id": flow.id},
                actor="system",
                commit=False,
            )
            db.commit()
            return {"ok": True, "completed": True}

        step = steps[idx]
        contact = db.query(Contact).filter(Contact.id == member.contact_id).first()
        if contact is None:
            member.status = "failed"
            member.error = "contact_gone"
            db.commit()
            return {"ok": False, "error": "contact_gone"}

        any_failed = False
        any_sent = False
        per_channel_errors: list[str] = []
        for ch in _channels_for_step(step):
            if ch == "email":
                status, err = _send_email_step(
                    db, membership=member, contact=contact, step=step, step_index=idx,
                )
            else:
                status, err = _send_wa_step(
                    db, membership=member, contact=contact, step=step, step_index=idx,
                )
            if status == "sent":
                any_sent = True
            elif status == "failed":
                any_failed = True
                per_channel_errors.append(f"{ch}: {err}"[:200])

        # Re-load member after the sub-sends commit.
        member = db.query(FlowMembership).filter(FlowMembership.id == membership_id).first()
        if member is None:
            return {"ok": True}

        member.last_step_at = datetime.now(timezone.utc)

        # Failure budget §5.7
        if any_failed and not any_sent:
            member.consecutive_failures = (member.consecutive_failures or 0) + 1
            if member.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                member.status = "failed"
                member.error = f"{MAX_CONSECUTIVE_FAILURES} consecutive step failures"
                member.next_fire_at = None
                db.commit()
                try:
                    import sentry_sdk  # type: ignore[import-not-found]

                    sentry_sdk.capture_message(
                        f"flow membership {member.id} failed: 3 consecutive errors",
                        level="error",
                    )
                except ImportError:
                    pass
                return {"ok": False, "error": "max_failures"}
            # Re-arm for retry on the next tick. Same delay as the step's
            # delay_after_prev so we don't hammer.
            member.next_fire_at = datetime.now(timezone.utc) + timedelta(minutes=2)
            db.commit()
            return {"ok": False, "retry_at": member.next_fire_at.isoformat()}
        else:
            member.consecutive_failures = 0
            # Partial multi-channel failure (e.g. email succeeded, WA
            # template was rejected). Surface it via member.error so the
            # UI can show a yellow badge; the membership still advances
            # because at least one channel reached the recipient.
            if any_failed and per_channel_errors:
                member.error = "; ".join(per_channel_errors)[:1000]
                try:
                    import sentry_sdk  # type: ignore[import-not-found]

                    sentry_sdk.capture_message(
                        f"flow membership {member.id} partial step failure: "
                        + member.error,
                        level="warning",
                    )
                except ImportError:
                    pass
            else:
                member.error = ""

        # Advance.
        next_idx = idx + 1
        if next_idx >= len(steps):
            member.status = "completed"
            member.current_step_index = next_idx
            member.next_fire_at = None
            log_interaction(
                db,
                contact_id=member.contact_id,
                kind="flow_completed",
                summary=f"Flow #{flow.id} completed",
                payload={"membership_id": member.id, "flow_id": flow.id},
                actor="system",
                commit=False,
            )
            db.commit()
            return {"ok": True, "completed": True}

        next_step = steps[next_idx]
        member.current_step_index = next_idx
        if next_step.get("trigger_event"):
            member.status = "waiting_event"
            member.next_fire_at = None
        else:
            delay = parse_duration(next_step.get("delay_after_prev"))
            member.status = "active"
            member.next_fire_at = datetime.now(timezone.utc) + delay
        db.commit()
        return {"ok": True, "advanced_to": next_idx}
    except Exception as e:
        log.exception("fire_membership_step failed for %s", membership_id)
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────
# Tick — claim + dispatch
# ─────────────────────────────────────────────────────────────────────


def _claim_due_memberships(db: Session, now: datetime) -> list[int]:
    """Atomically claim up to TICK_LIMIT due memberships. Returns ids.

    Park each by NULL'ing `next_fire_at` so a concurrent tick won't
    re-claim while we work — §5.3 claim trick. Single-replica HF Space
    means concurrent ticks shouldn't happen; the SKIP LOCKED is just
    belt-and-braces."""
    is_sqlite = db.bind.dialect.name == "sqlite" if db.bind else False
    try:
        q = db.query(FlowMembership).filter(
            FlowMembership.status == "active",
            FlowMembership.next_fire_at.isnot(None),
            FlowMembership.next_fire_at <= now,
        )
        if not is_sqlite:
            q = q.with_for_update(skip_locked=True)
        rows = q.order_by(FlowMembership.next_fire_at.asc()).limit(TICK_LIMIT).all()
    except OperationalError:
        # SQLite without WAL — fall back to a plain SELECT.
        rows = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.status == "active",
                FlowMembership.next_fire_at.isnot(None),
                FlowMembership.next_fire_at <= now,
            )
            .order_by(FlowMembership.next_fire_at.asc())
            .limit(TICK_LIMIT)
            .all()
        )

    ids: list[int] = []
    for r in rows:
        ids.append(r.id)
        r.next_fire_at = None  # park
    db.commit()
    return ids


def tick_flows() -> dict:
    """Single scheduler pass for flows. Returns counts. Synchronous —
    callable from `tick_once()` (which itself runs synchronously inside
    the asyncio scheduler loop)."""
    db = get_db()
    try:
        now = datetime.now(timezone.utc)
        ids = _claim_due_memberships(db, now)
    finally:
        db.close()

    fired = 0
    for mid in ids:
        try:
            fire_membership_step(mid)
            fired += 1
        except Exception:
            log.exception("flow tick: membership %s crashed", mid)
    return {"claimed": len(ids), "fired": fired}


async def tick_flows_async() -> dict:
    """Async wrapper that runs `tick_flows` on the asyncio threadpool so
    the embedded `time.sleep(3)` inside email sends doesn't block other
    coroutines (broadcast scheduler ticks share the same loop)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, tick_flows)


# ─────────────────────────────────────────────────────────────────────
# Stranded-membership reaper (PLAN_flows §5.5 layer 3)
# ─────────────────────────────────────────────────────────────────────


def reap_stranded_memberships() -> dict:
    """Re-arm any membership whose claim was interrupted by a process
    restart. Called once from the FastAPI lifespan startup hook.

    A "stranded" membership is one that's `status='active'` AND
    `next_fire_at IS NULL`. The tick parks rows by NULL-ing
    `next_fire_at` to prevent re-claim while the send is in flight; if
    the worker dies before `fire_membership_step` reaches a terminal
    state, the row is invisible to the next tick.

    The `flow_step_runs.idempotency_key` UNIQUE constraint guarantees
    re-arming is safe — a duplicate placeholder insert is blocked, and
    the per-step recovery in `_claim_or_recover_placeholder` decides
    whether to retry the actual send or treat the prior attempt as
    terminal.
    """
    db = get_db()
    try:
        rows = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.status == "active",
                FlowMembership.next_fire_at.is_(None),
            )
            .all()
        )
        if not rows:
            return {"reaped": 0}
        now = datetime.now(timezone.utc)
        for r in rows:
            r.next_fire_at = now
            existing = (r.error or "").strip()
            note = "reaped after restart"
            r.error = (existing + ("; " if existing else "") + note)[:1000]
        db.commit()
        log.info("reap_stranded_memberships: re-armed %d membership(s)", len(rows))
        return {"reaped": len(rows)}
    except Exception:
        log.exception("reap_stranded_memberships failed")
        try:
            db.rollback()
        except Exception:
            pass
        return {"reaped": 0, "error": "exception"}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────
# "Mark sample shipped" — drawer action helper (§7.1)
# ─────────────────────────────────────────────────────────────────────


def mark_sample_shipped(
    db: Session,
    *,
    contact: Contact,
    tracking_id: str,
    courier_name: str,
    actor: str = "user",
) -> dict:
    """Add tag `samples_shipped` to a contact and write tracking_id /
    courier_name into any waiting Sample Dispatch membership's
    `metadata_json`. One transaction.

    The tag write fires the tag-trigger evaluator, which resumes the
    membership (status='active', next_fire_at=now) — the next scheduler
    tick then fires step 1's email + WA with the tracking variables
    that we just wrote.

    Returns a summary of what changed (used by the API layer to build
    the response).
    """
    tags = list(contact.tags or [])
    tag_added = False
    if "samples_shipped" not in tags:
        tags.append("samples_shipped")
        contact.tags = tags
        tag_added = True

    log_interaction(
        db,
        contact_id=contact.id,
        kind="tag_added",
        summary="samples_shipped",
        payload={"tag": "samples_shipped", "tracking_id": tracking_id, "courier_name": courier_name},
        actor=actor,
        commit=False,
    )

    # Update metadata on any waiting/active sample_dispatch memberships
    # for this contact.
    sample_flow = db.query(Flow).filter(Flow.slug == "sample_dispatch").first()
    updated_memberships: list[int] = []
    if sample_flow:
        members = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.contact_id == contact.id,
                FlowMembership.flow_id == sample_flow.id,
                FlowMembership.status.in_(("active", "waiting_event")),
            )
            .all()
        )
        for m in members:
            data = dict(m.metadata_json or {})
            data["tracking_id"] = tracking_id
            data["courier_name"] = courier_name
            data["fibre_sent"] = data.get("fibre_sent") or _guess_fibre_from_tags(contact)
            m.metadata_json = data
            updated_memberships.append(m.id)

    n_resumed = evaluate_tag_trigger(db, contact_id=contact.id, tag_name="samples_shipped")

    return {
        "tag_added": tag_added,
        "memberships_updated": updated_memberships,
        "new_memberships_from_trigger": n_resumed,
    }


def _guess_fibre_from_tags(contact: Contact) -> str:
    """Sample fibre hint from existing tags. Soft default — empty string
    if nothing matches; the templates fall back to 'the samples'."""
    fibres = ("nettle", "hemp", "wool", "silk", "yak")
    for t in contact.tags or []:
        if t in fibres:
            return f"{t} yarn"
    return ""


__all__ = [
    "ACTIVE_STATUSES",
    "TICK_LIMIT",
    "assign_flow",
    "evaluate_lifecycle_trigger",
    "evaluate_tag_trigger",
    "fire_membership_step",
    "mark_sample_shipped",
    "parse_duration",
    "reap_stranded_memberships",
    "tick_flows",
    "tick_flows_async",
]
