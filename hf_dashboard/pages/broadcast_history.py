"""Broadcast History page — past broadcasts with status and channel filters.

Mirrors the reference mockup: status sidebar (All / Draft / Scheduled /
In Progress / Completed / Failed) + main table with broadcast rows.
"""

from __future__ import annotations

import gradio as gr

from shared.theme import COLORS


STATUS_FILTERS = [
    ("all", "All", "#94a3b8"),
    ("draft", "Draft", "#64748b"),
    ("sending", "In Progress", "#f59e0b"),
    ("sent", "Completed", "#22c55e"),
    ("failed", "Failed", "#ef4444"),
]

CHANNEL_FILTERS = [
    ("all", "All Channels"),
    ("whatsapp", "WhatsApp"),
    ("email", "Email"),
]


def build(ctx) -> dict:
    gr.HTML(
        f'<div style="font-size:15px; font-weight:700; color:{COLORS.TEXT}; margin-bottom:2px;">'
        f'Broadcast History</div>'
        f'<div style="font-size:11px; color:{COLORS.TEXT_MUTED}; margin-bottom:10px;">'
        f'All broadcasts you have created — drafts, in progress, completed, and failed.</div>'
    )

    with gr.Row(equal_height=False):
        # ── Status sidebar ───────────────────────────────────
        with gr.Column(scale=1, min_width=180):
            gr.HTML(
                f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:12px 14px; '
                f'border:1px solid rgba(255,255,255,.06);">'
                f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase; '
                f'letter-spacing:.5px; margin-bottom:8px;">Status</div></div>'
            )
            status_radio = gr.Radio(
                choices=[label for _, label, _ in STATUS_FILTERS],
                value="All",
                label="",
                container=False,
                interactive=True,
            )

            gr.HTML(
                f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:12px 14px; '
                f'margin-top:10px; border:1px solid rgba(255,255,255,.06);">'
                f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase; '
                f'letter-spacing:.5px; margin-bottom:8px;">Channel</div></div>'
            )
            channel_radio = gr.Radio(
                choices=[label for _, label in CHANNEL_FILTERS],
                value="All Channels",
                label="",
                container=False,
                interactive=True,
            )

        # ── Main table + summary ─────────────────────────────
        with gr.Column(scale=4, min_width=640):
            summary_html = gr.HTML(value="")
            history_table_html = gr.HTML(value="")

    # ── Handlers ─────────────────────────────────────────────

    def _filter(status_label, channel_label):
        status_id = next((s for s, l, _ in STATUS_FILTERS if l == status_label), "all")
        channel_id = next((c for c, l in CHANNEL_FILTERS if l == channel_label), "all")
        return _render(status_id, channel_id)

    status_radio.change(
        fn=_filter,
        inputs=[status_radio, channel_radio],
        outputs=[history_table_html],
    )

    channel_radio.change(
        fn=_filter,
        inputs=[status_radio, channel_radio],
        outputs=[history_table_html],
    )

    def _refresh():
        return _render_summary(), _render("all", "all")

    return {
        "update_fn": _refresh,
        "outputs": [summary_html, history_table_html],
    }


def _render_summary() -> str:
    """Top summary strip with status counts."""
    from services.database import get_db
    from services.models import Broadcast

    db = get_db()
    try:
        all_b = db.query(Broadcast).all()
        counts = {"all": len(all_b), "draft": 0, "sending": 0, "sent": 0, "failed": 0}
        for b in all_b:
            counts[b.status] = counts.get(b.status, 0) + 1
        total_sent = sum(b.total_sent or 0 for b in all_b)
        total_failed = sum(b.total_failed or 0 for b in all_b)
    finally:
        db.close()

    cells = [
        _summary_cell("Total Broadcasts", counts["all"], COLORS.TEXT),
        _summary_cell("Completed", counts["sent"], "#22c55e"),
        _summary_cell("In Progress", counts["sending"], "#f59e0b"),
        _summary_cell("Failed", counts["failed"], "#ef4444"),
        _summary_cell("Messages Sent", total_sent, COLORS.TEXT),
    ]

    return (
        f'<div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; margin-bottom:12px;">'
        f'{"".join(cells)}</div>'
    )


def _summary_cell(label: str, value: int, color: str) -> str:
    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:12px 14px; '
        f'border:1px solid rgba(255,255,255,.06);">'
        f'<div style="font-size:20px; font-weight:700; color:{color}; line-height:1;">{value:,}</div>'
        f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase; '
        f'letter-spacing:.3px; margin-top:4px;">{label}</div>'
        f'</div>'
    )


def _render(status: str, channel: str) -> str:
    """Render the filtered broadcast table."""
    from services.database import get_db
    from services.models import Broadcast, Segment

    db = get_db()
    try:
        q = db.query(Broadcast)
        if status != "all":
            q = q.filter(Broadcast.status == status)
        if channel != "all":
            q = q.filter(Broadcast.channel == channel)

        broadcasts = q.order_by(Broadcast.created_at.desc()).limit(200).all()

        if not broadcasts:
            return _empty_state(status, channel)

        # Resolve segment names
        seg_ids = {b.segment_id for b in broadcasts if b.segment_id}
        segs = {s.id: s.name for s in db.query(Segment).filter(Segment.id.in_(seg_ids)).all()}
        segs["all_opted_in"] = "All Opted-in"

        rows = ""
        for b in broadcasts:
            rows += _render_row(b, segs)

        return (
            f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; '
            f'border:1px solid rgba(255,255,255,.06); overflow:hidden;">'
            f'<table style="width:100%; border-collapse:collapse;">'
            f'<thead><tr style="background:rgba(255,255,255,.02); '
            f'border-bottom:1px solid rgba(255,255,255,.06);">'
            f'{_th("Status")}{_th("Name")}{_th("Channel")}{_th("Template")}'
            f'{_th("Segment")}{_th("Sent")}{_th("Failed")}{_th("Date")}'
            f'</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
        )
    finally:
        db.close()


def _render_row(b, segs: dict) -> str:
    status_colors = {
        "sent": "#22c55e", "sending": "#f59e0b",
        "draft": "#64748b", "failed": "#ef4444",
    }
    color = status_colors.get(b.status, "#64748b")
    status_label = {
        "sent": "Completed", "sending": "In Progress",
        "draft": "Draft", "failed": "Failed",
    }.get(b.status, b.status)

    status_badge = (
        '<span style="display:inline-flex; align-items:center; gap:4px; '
        'background:rgba(255,255,255,.04); padding:3px 8px; border-radius:10px; '
        f'font-size:10px; color:{color}; font-weight:600;">'
        f'<span style="width:6px; height:6px; background:{color}; border-radius:50%;"></span>'
        f'{status_label}</span>'
    )

    ch_icon = "\U0001F4F1" if b.channel == "whatsapp" else "\u2709\uFE0F"
    ch_label = "WhatsApp" if b.channel == "whatsapp" else "Email"
    seg_name = segs.get(b.segment_id, b.segment_id or "—")
    date = b.sent_at.strftime("%Y-%m-%d %H:%M") if b.sent_at else (
        b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else "—"
    )

    name_cell = f'<span style="color:{COLORS.TEXT}; font-weight:500;">{b.name}</span>'
    channel_cell = f"{ch_icon} {ch_label}"
    template_cell = (
        f'<code style="background:rgba(255,255,255,.04); padding:2px 6px; '
        f'border-radius:3px; font-size:10px;">{b.template_id or "—"}</code>'
    )
    sent_cell = f'<span style="color:#22c55e;">{b.total_sent or 0}</span>'
    failed_color = "#ef4444" if (b.total_failed or 0) > 0 else COLORS.TEXT_MUTED
    failed_cell = f'<span style="color:{failed_color};">{b.total_failed or 0}</span>'
    date_cell = f'<span style="color:{COLORS.TEXT_MUTED};">{date}</span>'

    return (
        '<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
        f'{_td(status_badge)}{_td(name_cell)}{_td(channel_cell)}{_td(template_cell)}'
        f'{_td(seg_name)}{_td(sent_cell)}{_td(failed_cell)}{_td(date_cell)}'
        '</tr>'
    )


def _th(label: str) -> str:
    return (
        f'<th style="text-align:left; padding:10px 14px; font-size:10px; '
        f'color:{COLORS.TEXT_MUTED}; text-transform:uppercase; letter-spacing:.5px; '
        f'font-weight:600;">{label}</th>'
    )


def _td(content: str) -> str:
    return f'<td style="padding:10px 14px; font-size:11px; color:{COLORS.TEXT_SUBTLE};">{content}</td>'


def _empty_state(status: str, channel: str) -> str:
    filter_label = ""
    if status != "all" or channel != "all":
        parts = []
        if status != "all":
            parts.append(status)
        if channel != "all":
            parts.append(channel)
        filter_label = f' matching filter ({", ".join(parts)})'

    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:60px 20px; '
        f'text-align:center; border:1px dashed rgba(255,255,255,.08);">'
        f'<div style="font-size:36px; margin-bottom:8px;">\U0001F4ED</div>'
        f'<div style="font-size:13px; color:{COLORS.TEXT}; font-weight:600; margin-bottom:4px;">'
        f'No broadcasts{filter_label}</div>'
        f'<div style="font-size:11px; color:{COLORS.TEXT_MUTED};">'
        f'Create a broadcast from the Broadcasts page to see it here.</div>'
        f'</div>'
    )
