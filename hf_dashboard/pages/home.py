"""Home page — dashboard with KPIs, lifecycle bars, activity feed.

Layout and labels driven by config/pages/home.yml.
Styles driven by config/theme/components.yml.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
import yaml

from components.kpi_card import render_kpi_row
from components.styles import (
    section_card, progress_bar_bg, progress_bar_fill,
    progress_label, progress_count, activity_item,
    activity_timestamp, activity_text,
)
from services.ttl_cache import ttl_cache

_PAGE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "home.yml"


def _load_page_config() -> dict:
    with open(_PAGE_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


# ══════════════════════════════════════════════════════════════════════
# Plan D Phase 2b — cached metric loaders.
#
# Three nullary helpers that each wrap a batched DB query in a TTL
# cache. Bucket names are declared in config/cache/ttl.yml and validated
# by engines/cache_schemas.py, so tuning any TTL is a YAML edit.
#
# These replace a loose pile of ~10 count queries + 2 activity queries
# + a lifecycle loop that all fired every time _refresh ran.
# ══════════════════════════════════════════════════════════════════════


@ttl_cache("home_counts_seconds")
def _home_counters_cached() -> dict:
    """Batch every Home KPI count into one DB round or a few small ones.

    Contact-derived counts (total / opted_in / pending / wa_24h) are
    combined into a single aggregated query using `func.count` +
    `case(...)` so the DB does the filtering and we only pull one row.
    Time-windowed counts (emails_today / wa_today) stay separate but
    all share the 60 s cache bucket.
    """
    from datetime import timedelta

    from sqlalchemy import case, func

    from services.database import get_db
    from services.models import (
        Contact, Campaign, EmailSend, WAMessage, Flow, FlowRun,
    )

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_cutoff = now - timedelta(hours=24)

    db = get_db()
    try:
        contact_row = db.query(
            func.count().label("total"),
            func.sum(
                case((Contact.consent_status == "opted_in", 1), else_=0)
            ).label("opted_in"),
            func.sum(
                case((Contact.consent_status == "pending", 1), else_=0)
            ).label("pending"),
            func.sum(
                case((Contact.last_wa_inbound_at >= window_cutoff, 1), else_=0)
            ).label("wa_24h"),
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
def _lifecycle_counts_cached() -> dict[str, int]:
    """Single `group_by(lifecycle)` query instead of N count queries."""
    from sqlalchemy import func
    from services.database import get_db
    from services.models import Contact

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
def _activity_feed_cached(limit: int = 20) -> list[tuple]:
    """Combined recent-activity feed: EmailSend + WAMessage.

    Returns a list of (timestamp, kind_string, text) tuples sorted
    newest-first. `kind_string` is the semantic label (e.g. "email_sent",
    "wa_sent", "wa_received") — the caller maps it to a display icon
    from the page YAML, so this cached value stays independent of UI
    copy changes.

    Uses `with_entities` so only the 4-5 columns the renderer reads
    come over the wire, not full ORM rows.
    """
    from services.database import get_db
    from services.models import EmailSend, WAMessage

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


def build(ctx) -> dict:
    cfg = _load_page_config()

    status_html = gr.HTML(value="")
    kpi_row1 = gr.HTML(value="")
    kpi_row2 = gr.HTML(value="")
    lifecycle_html = gr.HTML(value="")
    activity_html = gr.HTML(value="")
    info_html = gr.HTML(value="")

    def _refresh():
        from services.contact_schema import get_lifecycle_stages

        # Plan D Phase 2b: every count/activity query now hits a cached
        # nullary helper. First call in the TTL window goes to the DB;
        # subsequent calls (e.g. page re-render, nav-back, background
        # refresh) reuse the cached result. TTLs live in
        # config/cache/ttl.yml and are tunable without code edits.
        try:
            # Flow-step check is a background side-effect, not a count —
            # keep it non-cached so queued flows advance on each refresh.
            from services.database import get_db
            from services.flows_engine import check_pending_steps
            _db = get_db()
            try:
                check_pending_steps(_db)
            finally:
                _db.close()
        except Exception:
            pass

        counts = _home_counters_cached()
        total_contacts = counts["total"]
        opted_in = counts["opted_in"]
        pending = counts["pending"]
        wa_24h = counts["wa_24h"]
        emails_today = counts["emails_today"]
        wa_today = counts["wa_today"]
        email_campaigns = counts["email_campaigns"]
        wa_campaigns = counts["wa_campaigns"]
        total_flows = counts["total_flows"]
        active_runs = counts["active_runs"]

        try:
            # -- Connection status --
            status_cfg = cfg.get("status_bar", {})
            smtp_ok = bool(os.getenv("GMAIL_REFRESH_TOKEN", ""))
            wa_ok = bool(os.getenv("WA_TOKEN", ""))
            setup_url = status_cfg.get("setup_url", "")

            status = f"""
            <div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:12px;">
                <div style="display:flex; align-items:center; gap:6px; padding:6px 14px;
                     background:#1e293b; border-radius:8px; font-size:12px;">
                    <span style="color:{'#22c55e' if smtp_ok else '#ef4444'};">{'●' if smtp_ok else '○'}</span>
                    <span style="color:#e7eaf3;">Email (Gmail API)</span>
                    <span style="color:#64748b;">{'configured' if smtp_ok else 'not set'}</span>
                </div>
                <div style="display:flex; align-items:center; gap:6px; padding:6px 14px;
                     background:#1e293b; border-radius:8px; font-size:12px;">
                    <span style="color:{'#22c55e' if wa_ok else '#ef4444'};">{'●' if wa_ok else '○'}</span>
                    <span style="color:#e7eaf3;">WhatsApp API</span>
                    <span style="color:#64748b;">{'configured' if wa_ok else 'not set'}</span>
                </div>
            </div>
            """
            if not smtp_ok or not wa_ok:
                status += (
                    f'<div style="background:rgba(245,158,11,.08); border:1px solid rgba(245,158,11,.2); '
                    f'border-radius:8px; padding:8px 14px; margin-bottom:12px; font-size:11px; color:#94a3b8;">'
                    f'<strong style="color:#f59e0b;">Setup needed:</strong> '
                    f'<a href="{setup_url}" target="_blank" style="color:#818cf8;">Add secrets in HF Space Settings</a></div>'
                )

            # -- KPI Row 1 --
            row1 = render_kpi_row([
                (f"{emails_today}/500", "Emails Today", "", "#e7eaf3"),
                (f"{wa_today}/1000", "WA Today", "", "#e7eaf3"),
                (str(total_contacts), "Contacts", "", "#6366f1"),
                (str(wa_24h), "24h Window", "", "#22c55e" if wa_24h > 0 else "#64748b"),
            ])

            # -- KPI Row 2 --
            row2 = render_kpi_row([
                (str(opted_in), "Opted In", "", "#22c55e"),
                (str(pending), "Pending", "", "#f59e0b"),
                (str(email_campaigns), "Email Campaigns", "", "#6366f1"),
                (str(wa_campaigns), "WA Campaigns", "", "#22c55e"),
            ])

            # -- Lifecycle Breakdown --
            # Plan D Phase 2b: single cached group_by query instead of
            # N separate COUNTs in a Python loop.
            lifecycle_map = _lifecycle_counts_cached()
            stages = get_lifecycle_stages()
            lifecycle_bars = ""
            for stage in stages:
                count = lifecycle_map.get(stage["id"], 0)
                pct = (count / total_contacts * 100) if total_contacts > 0 else 0
                lifecycle_bars += (
                    f'<div style="display:flex; align-items:center; gap:10px; padding:4px 0;">'
                    f'<span style="{progress_label()}; min-width:80px;">{stage["icon"]} {stage["label"]}</span>'
                    f'<div style="{progress_bar_bg()}">'
                    f'<div style="{progress_bar_fill(stage["color"], pct)}"></div>'
                    f'</div>'
                    f'<span style="{progress_count()}">{count}</span>'
                    f'<span style="font-size:10px; color:#64748b;">({pct:.0f}%)</span>'
                    f'</div>'
                )

            section_title = cfg.get("sections", {}).get("lifecycle", {}).get("title", "Lifecycle")
            lifecycle = (
                f'<div style="{section_card()}; margin:12px 0;">'
                f'<div style="font-size:12px; font-weight:700; color:#e7eaf3; margin-bottom:8px;">{section_title}</div>'
                f'{lifecycle_bars}</div>'
            )

            # -- Recent Activity --
            # Plan D Phase 2b: cached combined feed. The cached value
            # stores semantic kind strings ("email_sent", "wa_sent",
            # "wa_received"); icons come from config so we can change
            # emoji without busting the cache.
            activity_cfg = cfg.get("sections", {}).get("activity", {})
            icons = activity_cfg.get("icons", {})
            limit = activity_cfg.get("limit", 20)
            raw_activities = _activity_feed_cached(limit)

            activity_title = activity_cfg.get("title", "Recent Activity")
            if raw_activities:
                items = ""
                for ts, kind, text in raw_activities:
                    icon = icons.get(kind, "•")
                    time_str = ts.strftime("%H:%M") if ts else "--"
                    items += (
                        f'<div style="{activity_item()}">'
                        f'<span style="{activity_timestamp()}">{time_str}</span>'
                        f'<span>{icon}</span>'
                        f'<span style="{activity_text()}">{text}</span>'
                        f'</div>'
                    )
                activity = f'<div style="{section_card()}; margin:8px 0;"><div style="font-size:12px; font-weight:700; color:#e7eaf3; margin-bottom:8px;">{activity_title}</div>{items}</div>'
            else:
                activity = f'<div style="{section_card()}; margin:8px 0; text-align:center; padding:20px; color:#64748b;">No activity yet</div>'

            # -- Getting Started + System --
            gs_cfg = cfg.get("sections", {}).get("getting_started", {})
            sys_cfg = cfg.get("sections", {}).get("system", {})
            steps = gs_cfg.get("steps", [])
            steps_html = "<br>".join(f"{i+1}. {s}" for i, s in enumerate(steps))

            info = f"""
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:8px;">
                <div style="{section_card()}">
                    <div style="font-size:11px; color:#64748b; text-transform:uppercase; margin-bottom:6px;">{gs_cfg.get("title", "Getting Started")}</div>
                    <div style="font-size:12px; color:#e7eaf3; line-height:1.8;">{steps_html}</div>
                </div>
                <div style="{section_card()}">
                    <div style="font-size:11px; color:#64748b; text-transform:uppercase; margin-bottom:6px;">{sys_cfg.get("title", "System")}</div>
                    <div style="font-size:12px; color:#e7eaf3; line-height:1.8;">
                        Campaigns: <strong>{email_campaigns} email, {wa_campaigns} WA</strong><br>
                        Flows: <strong>{total_flows} defined, {active_runs} active</strong><br>
                        Templates: <strong>7 email, 13 WA</strong><br>
                        Daily limits: <strong>500 email, 1000 WA</strong>
                    </div>
                </div>
            </div>
            """

            return (status, row1, row2, lifecycle, activity, info)
        except Exception:
            # Previously wrapped in try/finally with db.close(); the
            # refresh no longer holds a long-lived session (cached
            # helpers manage their own), so we just swallow render
            # exceptions and return placeholders. Any unhandled error
            # in the helpers surfaces as "No activity yet".
            import logging
            logging.getLogger(__name__).exception("home refresh failed")
            empty = "<div style='color:#64748b; padding:20px;'>Error loading Home data</div>"
            return (empty, empty, empty, empty, empty, empty)

    return {"update_fn": _refresh, "outputs": [status_html, kpi_row1, kpi_row2, lifecycle_html, activity_html, info_html]}
