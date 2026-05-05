"""Home page cached metric loaders — gradio-free.

Phase 2.3 extraction: these helpers were originally defined in
hf_dashboard/pages/home.py, which top-level imports gradio. api_v2's
dashboard router needs the same data but should not pull gradio into
its import chain (Plan D + STANDARDS rule). Moving them here means
api_v2 imports `services.home_metrics` and never touches gradio.

`hf_dashboard/pages/home.py` re-exports these names for backwards
compatibility, so v1 keeps working without any handler changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func

from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Contact,
    Campaign,
    EmailSend,
    Flow,
    FlowRun,
    WAMessage,
)
from services.ttl_cache import ttl_cache  # type: ignore[import-not-found]


@ttl_cache("home_counts_seconds")
def home_counters_cached() -> dict:
    """Batch every Home KPI count into one DB round or a few small ones.

    Contact-derived counts (total / opted_in / pending / wa_24h) are
    combined into a single aggregated query using `func.count` +
    `case(...)` so the DB does the filtering and we only pull one row.
    Time-windowed counts (emails_today / wa_today) stay separate but
    all share the 60s cache bucket configured in cache/ttl.yml.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_cutoff = now - timedelta(hours=24)

    db = get_db()
    try:
        contact_row = db.query(
            func.count().label("total"),
            func.sum(case((Contact.consent_status == "opted_in", 1), else_=0)).label("opted_in"),
            func.sum(case((Contact.consent_status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((Contact.last_wa_inbound_at >= window_cutoff, 1), else_=0)).label("wa_24h"),
            func.sum(case((Contact.wa_id.isnot(None), 1), else_=0)).label("wa_ready"),
        ).one()

        emails_today = db.query(func.count()).select_from(EmailSend).filter(
            EmailSend.sent_at >= today_start
        ).scalar() or 0
        wa_today = db.query(func.count()).select_from(WAMessage).filter(
            WAMessage.direction == "out", WAMessage.created_at >= today_start
        ).scalar() or 0
        email_campaigns = db.query(func.count()).select_from(Campaign).filter(
            Campaign.status == "sent"
        ).scalar() or 0
        wa_campaigns = db.query(
            func.count(func.distinct(WAMessage.wa_batch_id))
        ).filter(WAMessage.wa_batch_id.isnot(None)).scalar() or 0
        total_flows = db.query(func.count()).select_from(Flow).scalar() or 0
        active_runs = db.query(func.count()).select_from(FlowRun).filter(
            FlowRun.status == "active"
        ).scalar() or 0

        return {
            "total": int(contact_row.total or 0),
            "opted_in": int(contact_row.opted_in or 0),
            "pending": int(contact_row.pending or 0),
            "wa_24h": int(contact_row.wa_24h or 0),
            "wa_ready": int(contact_row.wa_ready or 0),
            "emails_today": int(emails_today),
            "wa_today": int(wa_today),
            "email_campaigns": int(email_campaigns),
            "wa_campaigns": int(wa_campaigns),
            "total_flows": int(total_flows),
            "active_runs": int(active_runs),
        }
    finally:
        db.close()


@ttl_cache("lifecycle_counts_seconds")
def lifecycle_counts_cached() -> dict[str, int]:
    """Single `group_by(lifecycle)` query instead of N count queries."""
    db = get_db()
    try:
        rows = (
            db.query(Contact.lifecycle, func.count())
            .group_by(Contact.lifecycle)
            .all()
        )
        return {(lc or ""): int(n or 0) for lc, n in rows}
    finally:
        db.close()


@ttl_cache("home_activity_seconds")
def activity_feed_cached(limit: int = 20) -> list[tuple]:
    """Combined recent-activity feed: EmailSend + WAMessage.

    Returns a list of (timestamp, kind_string, text) tuples sorted
    newest-first. `kind_string` is the semantic label (e.g. "email_sent",
    "wa_sent", "wa_received") — the caller maps it to a display icon
    from the page YAML, so this cached value stays independent of UI
    copy changes.

    Uses `with_entities` semantics via `db.query(...col...)` so only the
    4-5 columns the renderer reads come over the wire, not full ORM rows.
    """
    db = get_db()
    try:
        activities: list[tuple] = []
        emails = (
            db.query(
                EmailSend.sent_at,
                EmailSend.created_at,
                EmailSend.contact_email,
                EmailSend.subject,
            )
            .order_by(EmailSend.created_at.desc())
            .limit(limit)
            .all()
        )
        for es in emails:
            ts = es.sent_at or es.created_at
            activities.append((
                ts, "email_sent",
                f"Email to {es.contact_email}: {(es.subject or '')[:40]}",
            ))

        wa_rows = (
            db.query(
                WAMessage.created_at,
                WAMessage.direction,
                WAMessage.contact_id,
                WAMessage.text,
            )
            .order_by(WAMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        for wm in wa_rows:
            kind = "wa_received" if wm.direction == "in" else "wa_sent"
            direction_word = "from" if wm.direction == "in" else "to"
            activities.append((
                wm.created_at, kind,
                f"WA {direction_word} {wm.contact_id}: {(wm.text or '')[:40]}",
            ))

        activities.sort(
            key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return activities[:limit]
    finally:
        db.close()
