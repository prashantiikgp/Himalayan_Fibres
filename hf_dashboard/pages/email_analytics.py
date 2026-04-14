"""Email Analytics page — campaign performance + per-recipient status.

Layout
------

  [ KPI strip — sent / opened / clicked / scheduled / failed (30d) ]

  ┌─ Left ──────────────────┐  ┌─ Right ─────────────────────────┐
  │ Tab: Sent / Scheduled / │  │ Selected campaign detail         │
  │      Drafts             │  │   metric tiles                   │
  │                         │  │   recipient table                │
  │ Campaign picker         │  │   (name / email / status / sent_at) │
  └─────────────────────────┘  └─────────────────────────────────┘

All data reads directly from ``campaigns`` and ``email_sends`` — no
intermediate aggregation table. The 30-day KPI metrics are simple SQL
counts over ``email_sends.sent_at``.

Drafts are filtered OUT of the 30d metrics (nothing sent) but kept as a
dedicated tab so the founder can see in-progress compose sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import gradio as gr
from sqlalchemy import and_, func

from shared.theme import COLORS

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# KPI computations
# ═══════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _thirty_days_ago() -> datetime:
    return _utcnow() - timedelta(days=30)


def _kpi_counts(db) -> dict:
    """Pull the 5 top-line metrics in one pass each."""
    from services.models import Campaign, EmailSend

    cutoff = _thirty_days_ago()

    sent_30d = (
        db.query(func.count(EmailSend.id))
        .filter(EmailSend.status == "sent", EmailSend.sent_at >= cutoff)
        .scalar()
    ) or 0
    failed_30d = (
        db.query(func.count(EmailSend.id))
        .filter(EmailSend.status == "failed", EmailSend.created_at >= cutoff)
        .scalar()
    ) or 0

    # opened / clicked columns are optional on EmailSend (older schema
    # may not have them populated). Guard with hasattr.
    opened_30d = clicked_30d = 0
    if hasattr(EmailSend, "opened_at"):
        opened_30d = (
            db.query(func.count(EmailSend.id))
            .filter(EmailSend.opened_at != None, EmailSend.sent_at >= cutoff)  # noqa: E711
            .scalar()
        ) or 0
    if hasattr(EmailSend, "clicked_at"):
        clicked_30d = (
            db.query(func.count(EmailSend.id))
            .filter(EmailSend.clicked_at != None, EmailSend.sent_at >= cutoff)  # noqa: E711
            .scalar()
        ) or 0

    scheduled = (
        db.query(func.count(Campaign.id))
        .filter(Campaign.status == "scheduled")
        .scalar()
    ) or 0

    return {
        "sent_30d": int(sent_30d),
        "opened_30d": int(opened_30d),
        "clicked_30d": int(clicked_30d),
        "scheduled": int(scheduled),
        "failed_30d": int(failed_30d),
    }


def _kpi_strip_html(kpis: dict) -> str:
    """Render the 5-card KPI row."""
    tiles = [
        ("SENT (30D)", f"{kpis['sent_30d']:,}", "#e7eaf3"),
        ("OPENED (30D)", f"{kpis['opened_30d']:,}", "#14b8a6"),
        ("CLICKED (30D)", f"{kpis['clicked_30d']:,}", "#0ea5e9"),
        ("SCHEDULED", f"{kpis['scheduled']:,}", "#f59e0b"),
        ("FAILED (30D)", f"{kpis['failed_30d']:,}", "#ef4444"),
    ]
    cards = "".join(
        f'<div style="background:{COLORS.CARD_BG};border-radius:10px;padding:14px 16px;'
        f'border:1px solid rgba(255,255,255,.06);flex:1;min-width:140px;">'
        f'<div style="font-size:22px;font-weight:700;color:{color};line-height:1;">{value}</div>'
        f'<div style="font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;'
        f'letter-spacing:.5px;margin-top:6px;">{label}</div></div>'
        for label, value, color in tiles
    )
    return (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">{cards}</div>'
    )


# ═══════════════════════════════════════════════════════════════════════
# Tab → status filter
# ═══════════════════════════════════════════════════════════════════════

_TABS = [
    ("Sent", ["sent", "sending", "sent_partial"], "No campaigns sent yet."),
    ("Scheduled", ["scheduled"], "No scheduled campaigns."),
    ("Drafts", ["draft"], "No drafts in progress."),
]


def _list_campaigns(db, tab_label: str) -> list:
    """Return campaigns matching the current tab's status filter."""
    from services.models import Campaign

    statuses = next((s for (lbl, s, _) in _TABS if lbl == tab_label), ["sent"])
    return (
        db.query(Campaign)
        .filter(Campaign.status.in_(statuses))
        .order_by(Campaign.created_at.desc())
        .limit(200)
        .all()
    )


def _campaign_choice_label(c) -> str:
    """Dropdown label: 'Name · sent_date · N sent'."""
    when = c.sent_at or c.scheduled_at or c.created_at
    when_str = when.strftime("%b %d") if when else "—"
    return f"{c.name} · {when_str} · {c.total_sent or 0} sent"


def _tab_empty_message(tab_label: str) -> str:
    msg = next((m for (lbl, _, m) in _TABS if lbl == tab_label), "")
    return (
        f'<div style="padding:24px;text-align:center;color:{COLORS.TEXT_MUTED};font-size:11px;">{msg}</div>'
    )


# ═══════════════════════════════════════════════════════════════════════
# Campaign detail renderers
# ═══════════════════════════════════════════════════════════════════════

def _render_metric_tiles(campaign) -> str:
    tiles = [
        ("SENT", campaign.total_sent or 0, "#e7eaf3"),
        ("DELIVERED", getattr(campaign, "total_delivered", 0) or 0, "#06b6d4"),
        ("OPENED", getattr(campaign, "total_opened", 0) or 0, "#14b8a6"),
        ("CLICKED", getattr(campaign, "total_clicked", 0) or 0, "#0ea5e9"),
        ("FAILED", campaign.total_failed or 0, "#ef4444"),
    ]
    cards = "".join(
        f'<div style="background:{COLORS.CARD_BG};border-radius:10px;padding:12px 16px;'
        f'border:1px solid rgba(255,255,255,.06);flex:1;min-width:110px;">'
        f'<div style="font-size:22px;font-weight:700;color:{color};line-height:1;">{value:,}</div>'
        f'<div style="font-size:10px;color:{COLORS.TEXT_MUTED};text-transform:uppercase;'
        f'letter-spacing:.5px;margin-top:6px;">{label}</div></div>'
        for label, value, color in tiles
    )
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;">{cards}</div>'


def _format_ts(dt) -> str:
    if not dt:
        return f'<span style="color:{COLORS.TEXT_MUTED};">—</span>'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%b %d, %H:%M")


def _format_status_badge(status: str) -> str:
    color = {
        "sent": "#22c55e",
        "queued": "#94a3b8",
        "failed": "#ef4444",
        "delivered": "#06b6d4",
    }.get(status, "#94a3b8")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:600;color:{color};">'
        f'<span style="width:6px;height:6px;background:{color};border-radius:50%;"></span>{status or "—"}</span>'
    )


def _render_recipient_table(db, campaign_id: int) -> str:
    from services.models import Contact, EmailSend

    sends = (
        db.query(EmailSend, Contact)
        .outerjoin(Contact, Contact.id == EmailSend.contact_id)
        .filter(EmailSend.campaign_id == campaign_id)
        .order_by(EmailSend.created_at.desc())
        .limit(100)
        .all()
    )

    if not sends:
        return (
            f'<div style="padding:30px;text-align:center;color:{COLORS.TEXT_MUTED};font-size:11px;">'
            f"No recipients yet.</div>"
        )

    th_cells = "".join(
        f'<th style="text-align:left;padding:8px 12px;font-size:10px;color:{COLORS.TEXT_MUTED};'
        f'text-transform:uppercase;letter-spacing:.5px;font-weight:600;'
        f'border-bottom:1px solid rgba(255,255,255,.06);">{label}</th>'
        for label in ["Name", "Email", "Status", "Sent at", "Error"]
    )

    rows = []
    for send, contact in sends:
        name = ""
        if contact:
            name = ((contact.first_name or "") + " " + (contact.last_name or "")).strip()
        name = name or (contact.company if contact and contact.company else "—") or "—"
        email = (contact.email if contact and contact.email else send.contact_email) or "—"
        err = send.error_message or ""
        err_cell = (
            f'<span style="color:#ef4444;">{err[:80]}</span>' if err else ""
        )

        rows.append(
            f'<tr><td style="padding:8px 12px;font-size:11px;color:{COLORS.TEXT};'
            f'border-bottom:1px solid rgba(255,255,255,.04);">{name}</td>'
            f'<td style="padding:8px 12px;font-size:11px;color:{COLORS.TEXT_SUBTLE};'
            f'border-bottom:1px solid rgba(255,255,255,.04);">{email}</td>'
            f'<td style="padding:8px 12px;font-size:11px;'
            f'border-bottom:1px solid rgba(255,255,255,.04);">{_format_status_badge(send.status)}</td>'
            f'<td style="padding:8px 12px;font-size:11px;color:{COLORS.TEXT_SUBTLE};'
            f'border-bottom:1px solid rgba(255,255,255,.04);">{_format_ts(send.sent_at)}</td>'
            f'<td style="padding:8px 12px;font-size:11px;'
            f'border-bottom:1px solid rgba(255,255,255,.04);">{err_cell}</td></tr>'
        )

    return (
        f'<div style="background:{COLORS.CARD_BG};border-radius:10px;'
        f'border:1px solid rgba(255,255,255,.06);overflow:auto;max-height:50vh;">'
        '<table style="width:100%;border-collapse:collapse;">'
        f"<thead><tr>{th_cells}</tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _render_campaign_detail(db, campaign_id: int | None) -> str:
    if not campaign_id:
        return (
            f'<div style="padding:50px 20px;text-align:center;color:{COLORS.TEXT_MUTED};">'
            f'<div style="font-size:28px;margin-bottom:8px;">📊</div>'
            f'<div style="font-size:12px;">Select a campaign to see its analytics.</div></div>'
        )

    from services.models import Campaign

    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if c is None:
        return f'<div style="color:#ef4444;font-size:12px;padding:12px;">Campaign {campaign_id} not found</div>'

    when = c.sent_at or c.scheduled_at or c.created_at
    when_str = when.strftime("%b %d, %Y · %H:%M") if when else "—"
    header = (
        f'<div style="margin-bottom:12px;">'
        f'<div style="font-size:16px;font-weight:700;color:{COLORS.TEXT};">{c.name}</div>'
        f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};margin-top:2px;">'
        f"{c.status} · template "
        f'<code style="background:rgba(255,255,255,.05);padding:1px 5px;border-radius:3px;">{c.template_slug or "—"}</code>'
        f' · {when_str}</div>'
        f'<div style="font-size:11px;color:{COLORS.TEXT_SUBTLE};margin-top:4px;">Subject: {c.subject or "—"}</div>'
        f"</div>"
    )
    return header + _render_metric_tiles(c) + _render_recipient_table(db, campaign_id)


# ═══════════════════════════════════════════════════════════════════════
# Page builder
# ═══════════════════════════════════════════════════════════════════════

def build(ctx) -> dict:
    with gr.Row():
        gr.HTML(
            f'<div style="font-size:15px;font-weight:700;color:{COLORS.TEXT};">Email Analytics</div>'
            f'<div style="font-size:11px;color:{COLORS.TEXT_MUTED};">Campaign performance — opens, clicks, scheduled queue.</div>'
        )
        refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=120)

    kpi_html = gr.HTML(value="")

    with gr.Row():
        # ── LEFT: tab + campaign list ──────────────────────────
        with gr.Column(scale=1, min_width=300):
            tab_radio = gr.Radio(
                choices=[lbl for (lbl, _, _) in _TABS],
                value=_TABS[0][0],
                label="",
                container=False,
                interactive=True,
            )
            campaign_radio = gr.Radio(
                choices=[],
                label="Campaigns",
                container=True,
                interactive=True,
            )
            empty_html = gr.HTML(value="")

        # ── RIGHT: selected campaign detail ────────────────────
        with gr.Column(scale=3, min_width=600):
            detail_html = gr.HTML(value="")

    campaign_label_to_id = gr.State({})  # label → campaign_id

    # ═══════════════════════════════════════════════════════════
    # Handlers
    # ═══════════════════════════════════════════════════════════

    def _on_tab_or_refresh(tab_label: str):
        from services.database import get_db

        db = get_db()
        try:
            campaigns = _list_campaigns(db, tab_label)
            choices = [_campaign_choice_label(c) for c in campaigns]
            label_map = {_campaign_choice_label(c): c.id for c in campaigns}
            empty = "" if choices else _tab_empty_message(tab_label)
            return (
                gr.update(choices=choices, value=None),
                label_map,
                empty,
                _render_campaign_detail(db, None),
            )
        finally:
            db.close()

    tab_radio.change(
        fn=_on_tab_or_refresh,
        inputs=[tab_radio],
        outputs=[campaign_radio, campaign_label_to_id, empty_html, detail_html],
    )

    def _on_campaign_pick(label: str, label_map: dict):
        from services.database import get_db

        if not label:
            db = get_db()
            try:
                return _render_campaign_detail(db, None)
            finally:
                db.close()

        cid = (label_map or {}).get(label)
        db = get_db()
        try:
            return _render_campaign_detail(db, cid)
        finally:
            db.close()

    campaign_radio.change(
        fn=_on_campaign_pick,
        inputs=[campaign_radio, campaign_label_to_id],
        outputs=[detail_html],
    )

    def _refresh():
        from services.database import get_db

        db = get_db()
        try:
            kpi = _kpi_strip_html(_kpi_counts(db))
            campaigns = _list_campaigns(db, _TABS[0][0])
            choices = [_campaign_choice_label(c) for c in campaigns]
            label_map = {_campaign_choice_label(c): c.id for c in campaigns}
            empty = "" if choices else _tab_empty_message(_TABS[0][0])
            detail = _render_campaign_detail(db, None)
        finally:
            db.close()
        return (
            kpi,
            gr.update(value=_TABS[0][0]),
            gr.update(choices=choices, value=None),
            label_map,
            empty,
            detail,
        )

    refresh_btn.click(
        fn=_refresh,
        outputs=[kpi_html, tab_radio, campaign_radio, campaign_label_to_id, empty_html, detail_html],
    )

    return {
        "update_fn": _refresh,
        "outputs": [kpi_html, tab_radio, campaign_radio, campaign_label_to_id, empty_html, detail_html],
    }
