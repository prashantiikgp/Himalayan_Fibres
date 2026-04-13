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

_PAGE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "home.yml"


def _load_page_config() -> dict:
    with open(_PAGE_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


def build(ctx) -> dict:
    cfg = _load_page_config()

    status_html = gr.HTML(value="")
    kpi_row1 = gr.HTML(value="")
    kpi_row2 = gr.HTML(value="")
    lifecycle_html = gr.HTML(value="")
    activity_html = gr.HTML(value="")
    info_html = gr.HTML(value="")

    def _refresh():
        from services.database import get_db
        from services.models import Contact, Campaign, EmailSend, Flow, FlowRun, WAChat, WAMessage
        from services.contact_schema import get_lifecycle_stages

        db = get_db()
        try:
            # Check pending flow steps
            try:
                from services.flows_engine import check_pending_steps
                check_pending_steps(db)
            except Exception:
                pass

            # -- Counts --
            total_contacts = db.query(Contact).count()
            opted_in = db.query(Contact).filter(Contact.consent_status == "opted_in").count()
            pending = db.query(Contact).filter(Contact.consent_status == "pending").count()

            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            emails_today = db.query(EmailSend).filter(EmailSend.sent_at >= today_start).count()
            wa_today = db.query(WAMessage).filter(
                WAMessage.direction == "out", WAMessage.created_at >= today_start
            ).count()

            # 24h window contacts
            from datetime import timedelta
            window_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            wa_24h = db.query(Contact).filter(Contact.last_wa_inbound_at >= window_cutoff).count()

            email_campaigns = db.query(Campaign).filter(Campaign.status == "sent").count()
            # WA campaigns = distinct wa_batch_ids
            wa_campaigns = db.query(WAMessage.wa_batch_id).filter(
                WAMessage.wa_batch_id.isnot(None)
            ).distinct().count()

            total_flows = db.query(Flow).count()
            active_runs = db.query(FlowRun).filter(FlowRun.status == "active").count()

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
            stages = get_lifecycle_stages()
            lifecycle_bars = ""
            for stage in stages:
                count = db.query(Contact).filter(Contact.lifecycle == stage["id"]).count()
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
            activity_cfg = cfg.get("sections", {}).get("activity", {})
            icons = activity_cfg.get("icons", {})
            limit = activity_cfg.get("limit", 20)

            # Merge EmailSend + WAMessage
            activities = []
            for es in db.query(EmailSend).order_by(EmailSend.created_at.desc()).limit(limit).all():
                ts = es.sent_at or es.created_at
                activities.append((ts, icons.get("email_sent", "✉"), f"Email to {es.contact_email}: {es.subject[:40]}"))

            for wm in db.query(WAMessage).order_by(WAMessage.created_at.desc()).limit(limit).all():
                icon = icons.get("wa_received", "📩") if wm.direction == "in" else icons.get("wa_sent", "💬")
                activities.append((wm.created_at, icon, f"WA {'from' if wm.direction == 'in' else 'to'} {wm.contact_id}: {wm.text[:40]}"))

            activities.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

            activity_title = activity_cfg.get("title", "Recent Activity")
            if activities:
                items = ""
                for ts, icon, text in activities[:limit]:
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
        finally:
            db.close()

    return {"update_fn": _refresh, "outputs": [status_html, kpi_row1, kpi_row2, lifecycle_html, activity_html, info_html]}
