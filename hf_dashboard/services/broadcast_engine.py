"""Broadcast engine — unified bulk send for Email and WhatsApp channels.

Orchestrates wa_sender and email_sender to deliver one-shot broadcasts
to a segment of contacts. Tracks results in the Broadcast model.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from services.models import (
    Broadcast, Contact, Segment, EmailTemplate, EmailSend,
    WAMessage, WAChat,
)

log = logging.getLogger(__name__)

_PRICING_PATH = Path(__file__).resolve().parent.parent / "config" / "whatsapp" / "pricing.yml"


@dataclass
class BroadcastResult:
    broadcast_id: int
    sent: int
    failed: int
    total: int
    errors: list[str]


@dataclass
class BroadcastFilters:
    """All the filters a user can apply when creating a broadcast."""
    segment_id: str | None = None
    countries: list[str] = field(default_factory=list)     # empty = no country filter
    tags: list[str] = field(default_factory=list)          # empty = no tag filter
    lifecycles: list[str] = field(default_factory=list)    # empty = no lifecycle filter
    consents: list[str] = field(default_factory=list)      # empty = no consent filter
    max_recipients: int = 0                                # 0 = unlimited


def get_segment_contacts(db: Session, segment_id: str | None) -> list[Contact]:
    """Get contacts for a segment, or all opted-in contacts."""
    if not segment_id or segment_id == "all_opted_in":
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


def _contact_country(c: Contact) -> str:
    return (c.country or c.geography or "Unknown").strip() or "Unknown"


def _is_eligible_for_channel(c: Contact, channel: str) -> bool:
    if channel == "whatsapp":
        return bool(c.wa_id)
    return bool(c.email) and "placeholder" not in (c.email or "")


def apply_filters(
    contacts: list[Contact],
    channel: str,
    filters: BroadcastFilters,
) -> list[Contact]:
    """Apply channel eligibility + country/tag/limit filters.

    Returns contacts ordered by most recently updated so re-running a
    capped broadcast hits newer contacts first.
    """
    # 1. Channel eligibility
    out = [c for c in contacts if _is_eligible_for_channel(c, channel)]

    # 2. Country filter (include-only)
    if filters.countries:
        wanted = {x.strip() for x in filters.countries}
        out = [c for c in out if _contact_country(c) in wanted]

    # 3. Tag filter (any match)
    if filters.tags:
        wanted_tags = {t.strip() for t in filters.tags}
        out = [
            c for c in out
            if c.tags and any(t in wanted_tags for t in c.tags)
        ]

    # 4. Lifecycle filter
    if filters.lifecycles:
        wanted_lc = {x.strip() for x in filters.lifecycles}
        out = [c for c in out if (c.lifecycle or "new_lead") in wanted_lc]

    # 5. Consent filter
    if filters.consents:
        wanted_co = {x.strip() for x in filters.consents}
        out = [c for c in out if (c.consent_status or "pending") in wanted_co]

    # 6. Sort by most-recently-updated, then cap
    out.sort(key=lambda c: c.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    if filters.max_recipients and filters.max_recipients > 0:
        out = out[:filters.max_recipients]

    return out


def count_eligible_contacts(db: Session, channel: str, segment_id: str | None) -> int:
    """Count contacts eligible for a broadcast on the given channel (no extra filters)."""
    contacts = get_segment_contacts(db, segment_id)
    return len(apply_filters(contacts, channel, BroadcastFilters(segment_id=segment_id)))


def get_unique_countries_in_segment(db: Session, channel: str, segment_id: str | None) -> list[str]:
    """Return unique countries (sorted by frequency desc) among eligible contacts."""
    contacts = get_segment_contacts(db, segment_id)
    eligible = [c for c in contacts if _is_eligible_for_channel(c, channel)]
    counts: dict[str, int] = {}
    for c in eligible:
        key = _contact_country(c)
        counts[key] = counts.get(key, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda x: -x[1])]


def get_unique_tags_in_segment(db: Session, channel: str, segment_id: str | None) -> list[str]:
    """Return unique tags present among eligible contacts in the segment."""
    contacts = get_segment_contacts(db, segment_id)
    eligible = [c for c in contacts if _is_eligible_for_channel(c, channel)]
    counts: dict[str, int] = {}
    for c in eligible:
        for tag in (c.tags or []):
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda x: -x[1])]


def get_unique_lifecycles_in_segment(db: Session, channel: str, segment_id: str | None) -> list[str]:
    contacts = get_segment_contacts(db, segment_id)
    eligible = [c for c in contacts if _is_eligible_for_channel(c, channel)]
    counts: dict[str, int] = {}
    for c in eligible:
        key = c.lifecycle or "new_lead"
        counts[key] = counts.get(key, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda x: -x[1])]


def get_unique_consents_in_segment(db: Session, channel: str, segment_id: str | None) -> list[str]:
    contacts = get_segment_contacts(db, segment_id)
    eligible = [c for c in contacts if _is_eligible_for_channel(c, channel)]
    counts: dict[str, int] = {}
    for c in eligible:
        key = c.consent_status or "pending"
        counts[key] = counts.get(key, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda x: -x[1])]


def get_audience_breakdown(
    db: Session,
    channel: str,
    filters: BroadcastFilters,
) -> dict:
    """Rich audience stats with filter-aware reach calculation.

    Reports: total in segment → eligible on channel → after filters (= final).
    Plus breakdowns on the final filtered set.
    """
    contacts = get_segment_contacts(db, filters.segment_id)
    total = len(contacts)

    eligible = [c for c in contacts if _is_eligible_for_channel(c, channel)]
    final = apply_filters(contacts, channel, filters)

    # Breakdowns on the FINAL set (what will actually be sent)
    def bucket(items, key_fn):
        out: dict[str, int] = {}
        for item in items:
            k = key_fn(item) or "unknown"
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items(), key=lambda x: -x[1]))

    return {
        "total_in_segment": total,
        "eligible_on_channel": len(eligible),
        "final_recipients": len(final),
        "excluded_by_channel": total - len(eligible),
        "excluded_by_filters": len(eligible) - len(final),
        "consent": bucket(final, lambda c: c.consent_status),
        "geography": dict(list(bucket(final, _contact_country).items())[:8]),
        "lifecycle": bucket(final, lambda c: c.lifecycle),
        "customer_type": bucket(final, lambda c: c.customer_type),
    }


# ═══════════════════════════════════════════════════════════════════
# Cost estimation
# ═══════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_pricing() -> dict:
    try:
        with open(_PRICING_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning("Failed to load pricing.yml: %s", e)
        return {}


def _pricing_for_country(country: str) -> dict:
    pricing = _load_pricing()
    rates = pricing.get("rates", {})
    if country in rates:
        return rates[country]
    fallback = pricing.get("fallback_country", "India")
    return rates.get(fallback, {})


def _currency_symbol(code: str) -> str:
    return _load_pricing().get("currency", {}).get("symbols", {}).get(code, code)


def estimate_cost(
    db: Session,
    channel: str,
    category: str,
    filters: BroadcastFilters,
) -> dict:
    """Estimate broadcast cost based on filtered recipients + template category.

    Handles mixed-country breakdowns by grouping final recipients by country
    and applying per-country rates. Returns total in INR (normalised) plus
    per-country line items.
    """
    contacts = get_segment_contacts(db, filters.segment_id)
    final = apply_filters(contacts, channel, filters)

    if channel == "email":
        pricing = _load_pricing().get("email", {})
        rate = pricing.get("cost_per_message", 0.0)
        symbol = _currency_symbol(pricing.get("currency", "INR"))
        return {
            "recipients": len(final),
            "per_message_display": f"{symbol}{rate:.2f}",
            "total_display": f"{symbol}{rate * len(final):.2f}",
            "currency": pricing.get("currency", "INR"),
            "breakdown": [],
            "est_delivery_seconds": len(final) * 3,
        }

    cat_key = category.lower() if category else "marketing"
    # Group by country
    by_country: dict[str, int] = {}
    for c in final:
        key = _contact_country(c)
        by_country[key] = by_country.get(key, 0) + 1

    breakdown = []
    total_inr = 0.0  # We'll show INR total for the default market
    primary_symbol = _currency_symbol("INR")
    primary_rate = 0.0

    for country, count in sorted(by_country.items(), key=lambda x: -x[1]):
        rate_info = _pricing_for_country(country)
        rate = rate_info.get(cat_key, 0.0)
        currency = rate_info.get("currency", "INR")
        symbol = _currency_symbol(currency)
        subtotal = rate * count
        breakdown.append({
            "country": country,
            "recipients": count,
            "rate": rate,
            "currency": currency,
            "symbol": symbol,
            "subtotal": subtotal,
            "display": f"{count} × {symbol}{rate:.2f} = {symbol}{subtotal:.2f}",
        })
        # For total display, use India rate as baseline
        if currency == "INR":
            total_inr += subtotal
            if primary_rate == 0.0:
                primary_rate = rate

    # If no INR recipients, fall back to first breakdown row
    if total_inr == 0.0 and breakdown:
        total_display = f"{breakdown[0]['symbol']}{sum(b['subtotal'] for b in breakdown):.2f}"
        per_msg_display = f"{breakdown[0]['symbol']}{breakdown[0]['rate']:.2f}"
    else:
        total_display = f"{primary_symbol}{total_inr:.2f}"
        per_msg_display = f"{primary_symbol}{primary_rate:.2f}" if primary_rate else f"{primary_symbol}0.00"

    return {
        "recipients": len(final),
        "per_message_display": per_msg_display,
        "total_display": total_display,
        "currency": "INR",
        "category": cat_key,
        "breakdown": breakdown,
        "est_delivery_seconds": len(final) * 1,  # 1s rate limit for WA
    }


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"~{seconds // 60} min"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    return f"~{hours}h {mins}m" if mins else f"~{hours}h"


def send_broadcast(
    db: Session,
    name: str,
    channel: str,
    template_id: str,
    filters: BroadcastFilters,
    subject: str = "",
    extra_vars: dict | None = None,
) -> BroadcastResult:
    """Send a broadcast to a filtered audience on a given channel.

    Args:
        db: Database session
        name: Broadcast name for tracking
        channel: "email" or "whatsapp"
        template_id: Email template slug or WA template name
        filters: BroadcastFilters with segment + country + tag + limit
        subject: Email subject line (email channel only)
        extra_vars: Phase 7.2a — typed variable values applied to every
            recipient as the `extra` dict on `build_send_variables`.
            Email-only; ignored for WA. Auto-resolved per-recipient names
            (first_name, etc.) should not appear here.
    """
    broadcast = Broadcast(
        name=name,
        channel=channel,
        template_id=template_id,
        segment_id=filters.segment_id,
        status="sending",
    )
    db.add(broadcast)
    db.flush()

    segment_contacts = get_segment_contacts(db, filters.segment_id)
    final = apply_filters(segment_contacts, channel, filters)

    if channel == "whatsapp":
        result = _send_wa_broadcast(db, broadcast, template_id, final)
    else:
        result = _send_email_broadcast(
            db, broadcast, template_id, subject, final, extra_vars=extra_vars
        )

    broadcast.status = "sent" if result.failed == 0 else ("sent" if result.sent > 0 else "failed")
    broadcast.total_recipients = result.total
    broadcast.total_sent = result.sent
    broadcast.total_failed = result.failed
    broadcast.sent_at = datetime.now(timezone.utc)
    db.commit()

    return result


def _send_wa_broadcast(
    db: Session,
    broadcast: Broadcast,
    template_name: str,
    contacts: list[Contact],
) -> BroadcastResult:
    """Send WhatsApp template to all eligible contacts."""
    from services.wa_sender import WhatsAppSender
    from services.wa_config import get_wa_config

    sender = WhatsAppSender()
    wa_config = get_wa_config()
    tpl_def = wa_config.get_template(template_name)

    # Fallback: if the YAML doesn't know this template, look it up in the
    # DB. Studio-created templates that were never written back to YAML
    # land here. We synthesize a TemplateDefinition just for this send so
    # the variable-resolution path stays uniform.
    body_var_names: list[str] = []
    header_var_names: list[str] = []
    if tpl_def:
        body_var_names = tpl_def.variable_names
        header_var_names = tpl_def.header_variable_names
        lang = tpl_def.language
    else:
        from services.models import WATemplate as _WATemplate

        db_row = (
            db.query(_WATemplate)
            .filter(_WATemplate.name == template_name)
            .filter(_WATemplate.is_draft.is_(False))
            .first()
        )
        if db_row is not None:
            body_var_names = list(db_row.variables or [])
            header_var_names = _extract_placeholders_local(db_row.header_text or "")
            lang = db_row.language or "en"
            log.warning(
                "WA template %r not in YAML — falling back to DB row "
                "(register it in templates.yml/new_templates.yml to silence this).",
                template_name,
            )
        else:
            lang = "en_US"

    # contacts are already pre-filtered by apply_filters() at the caller
    eligible = contacts
    sent, failed = 0, 0
    errors = []

    for contact in eligible:
        rendered_body: list[tuple[str, str]] = [
            (n, _resolve_wa_variable(n, contact)) for n in body_var_names
        ]
        rendered_header: list[tuple[str, str]] = [
            (n, _resolve_wa_variable(n, contact)) for n in header_var_names
        ]

        ok, msg_id, error = sender.send_template(
            contact.wa_id, template_name, lang=lang,
            variables=rendered_body or None,
            header_variables=rendered_header or None,
        )

        if ok:
            sent += 1
            contact.last_wa_outbound_at = datetime.now(timezone.utc)
            # Track message
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
                text=f"[Template: {template_name}]",
                wa_message_id=msg_id,
                wa_batch_id=str(broadcast.id),
            ))
        else:
            failed += 1
            errors.append(f"{contact.wa_id}: {error}")
            log.warning("WA broadcast send failed for %s: %s", contact.wa_id, error)

        time.sleep(1)  # Rate limit

    db.flush()
    return BroadcastResult(
        broadcast_id=broadcast.id,
        sent=sent, failed=failed,
        total=len(eligible), errors=errors,
    )


def _send_email_broadcast(
    db: Session,
    broadcast: Broadcast,
    template_slug: str,
    subject: str,
    contacts: list[Contact],
    *,
    extra_vars: dict | None = None,
) -> BroadcastResult:
    """Send email template to all eligible contacts.

    Phase 7.2a: rewired to use ``build_send_variables`` +
    ``render_template_by_slug`` so seeded templates resolve
    ``{% extends %}`` correctly and pick up shared branding vars
    (banner_url, footer links, social) — the prior inline narrow
    ``{name, first_name, company_name, email}`` dict silently dropped
    every shared-config value.
    """
    from services.email_personalization import build_send_variables
    from services.email_sender import (
        EmailSender,
        generate_idempotency_key,
        render_template_by_slug,
        render_template_string,
    )

    tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
    if not tpl:
        return BroadcastResult(
            broadcast_id=broadcast.id,
            sent=0, failed=0, total=0,
            errors=[f"Template '{template_slug}' not found"],
        )

    sender = EmailSender()
    if not sender.is_configured():
        return BroadcastResult(
            broadcast_id=broadcast.id,
            sent=0, failed=0, total=0,
            errors=["Gmail API not configured (GMAIL_REFRESH_TOKEN unset)"],
        )

    # contacts are already pre-filtered by apply_filters() at the caller
    eligible = contacts
    sent, failed = 0, 0
    errors: list[str] = []
    subject_src = subject or tpl.subject_template or ""

    for contact in eligible:
        idem_key = generate_idempotency_key(f"broadcast_{broadcast.id}", contact.id)
        if db.query(EmailSend).filter(EmailSend.idempotency_key == idem_key).first():
            continue

        variables = build_send_variables(
            contact, attachments={}, extra=extra_vars or None,
        )
        try:
            rendered_html = render_template_by_slug(template_slug, variables)
            rendered_subject = render_template_string(subject_src, variables)
        except Exception as e:
            log.exception("Render failed for broadcast %s contact %s", broadcast.id, contact.id)
            db.add(EmailSend(
                contact_id=contact.id, contact_email=contact.email or "",
                campaign_id=None, subject=subject_src,
                status="failed",
                idempotency_key=idem_key,
                error_message=f"Render error: {e}",
            ))
            failed += 1
            errors.append(f"{contact.email}: render error: {e}")
            continue

        result = sender.send_email(
            contact.email, rendered_subject, rendered_html,
            to_name=contact.first_name,
        )

        db.add(EmailSend(
            contact_id=contact.id, contact_email=contact.email,
            campaign_id=None, subject=rendered_subject,
            status="sent" if result["success"] else "failed",
            idempotency_key=idem_key,
            error_message="" if result["success"] else result.get("message", ""),
            sent_at=datetime.now(timezone.utc) if result["success"] else None,
        ))

        if result["success"]:
            sent += 1
        else:
            failed += 1
            errors.append(f"{contact.email}: {result.get('message', 'unknown error')}")

        time.sleep(3)  # Rate limit for email

    db.flush()
    return BroadcastResult(
        broadcast_id=broadcast.id,
        sent=sent, failed=failed,
        total=len(eligible), errors=errors,
    )


def _extract_placeholders_local(text: str) -> list[str]:
    """Same shape as WAConfigManager._extract_placeholders but without the
    import cycle; used for the DB-fallback path when a template isn't in
    YAML."""
    import re

    seen: list[str] = []
    for m in re.finditer(r"\{\{\s*([\w]+)\s*\}\}", text or ""):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def _resolve_wa_variable(var_name: str, contact: Contact) -> str:
    """Map a WA template variable name to a contact field value.

    Always returns a non-empty string — Meta rejects empty parameters
    with 'Parameter name is missing or empty'. Unmapped variables fall
    back to a bracketed placeholder so a broadcast never fails silently.
    """
    full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    mapping = {
        "customer_name": full_name or contact.company or "Customer",
        "first_name": contact.first_name or full_name or "Customer",
        "name": full_name or "Customer",
        "company_name": contact.company or full_name or "your company",
        # Positional-style placeholders commonly used for name
        "1": full_name or contact.first_name or "Customer",
        "2": contact.company or "—",
    }
    value = mapping.get(var_name, "")
    if not value:
        # Unmapped transactional variables (order_id, amount, etc.) — return
        # a placeholder rather than empty string so Meta accepts the call.
        value = f"[{var_name}]"
    return value


def get_broadcast_history(db: Session, limit: int = 20) -> list[Broadcast]:
    """Get recent broadcasts ordered by creation date."""
    return db.query(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit).all()
