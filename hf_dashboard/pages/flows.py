"""Flows & Automations page — view and start multi-step flows."""

from __future__ import annotations

import gradio as gr

from components.kpi_card import render_kpi_row
from components.styled_table import render_table, cell, cell_badge
from components.section_card import render_section_card
from components.badges import channel_badge
from components.empty_state import render_empty_state
from shared.theme import COLORS, FONTS


def _build_flow_details(flow):
    """Render step-by-step flow visualization as HTML."""
    channel_icon = "&#x2709;" if flow.channel == "email" else "&#x1F4AC;"
    steps_html = ""

    for i, step in enumerate(flow.steps or []):
        day = step.get("day", 0)
        template = step.get("template_slug", step.get("wa_template", ""))
        subject = step.get("subject", "")

        step_html = (
            f'<div style="background:{COLORS.CARD_BG}; border-radius:8px; padding:10px 14px; '
            f'border-left:3px solid {COLORS.PRIMARY}; margin:4px 0;">'
            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
            f'<span style="font-weight:600; color:{COLORS.TEXT};">{channel_icon} Step {i+1} (Day {day})</span>'
            f'<span style="font-size:{FONTS.XS}; color:{COLORS.TEXT_MUTED};">Template: {template}</span>'
            f'</div>'
        )
        if subject:
            step_html += f'<div style="font-size:{FONTS.SM}; color:{COLORS.TEXT_SUBTLE}; margin-top:4px;">{subject}</div>'
        step_html += '</div>'

        if i < len(flow.steps) - 1:
            step_html += f'<div style="text-align:center; color:{COLORS.TEXT_MUTED}; font-size:16px;">&#x25BC;</div>'

        steps_html += step_html

    return (
        f'<div style="margin:8px 0;">'
        f'<div style="font-size:{FONTS.MD}; font-weight:600; color:{COLORS.TEXT}; margin-bottom:4px;">{flow.name}</div>'
        f'<div style="font-size:{FONTS.SM}; color:{COLORS.TEXT_SUBTLE}; margin-bottom:8px;">'
        f'Channel: {flow.channel.title()} | {len(flow.steps)} steps</div>'
        f'{steps_html}</div>'
    )


def _build_flow_runs_table(db):
    from services.models import FlowRun, Flow
    runs = db.query(FlowRun).order_by(FlowRun.created_at.desc()).limit(10).all()
    if not runs:
        return render_empty_state("No flow runs yet. Start a flow above.")

    rows = []
    for run in runs:
        flow = db.query(Flow).filter(Flow.id == run.flow_id).first()
        flow_name = flow.name if flow else f"Flow #{run.flow_id}"
        status_colors = {"active": COLORS.SUCCESS, "paused": COLORS.WARNING, "completed": COLORS.TEXT_MUTED, "cancelled": COLORS.ERROR}
        color = status_colors.get(run.status, COLORS.TEXT_MUTED)

        rows.append([
            cell(flow_name, bold=True),
            cell_badge(run.status.upper(), color),
            cell(f"{run.current_step}/{len(flow.steps) if flow else '?'}", align="center"),
            cell(str(run.total_sent), align="center"),
            cell(run.next_step_at.strftime("%Y-%m-%d") if run.next_step_at else "--"),
        ])

    return render_table(
        [("Flow", "left"), ("Status", "center"), ("Step", "center"), ("Sent", "center"), ("Next", "left")],
        rows, title="Flow Runs",
    )


def build(ctx) -> dict:
    with gr.Row():
        with gr.Column(scale=1, elem_classes=["page-left-col"]):
            gr.HTML(f'<div style="font-size:13px; font-weight:600; color:{COLORS.TEXT}; margin-bottom:8px;">Select Flow</div>')
            flow_select = gr.Dropdown(label="Flow", choices=[], interactive=True)
            channel_filter = gr.Dropdown(label="Channel", choices=["All", "Email", "WhatsApp"], value="All")

            gr.HTML(f'<div style="font-size:13px; font-weight:600; color:{COLORS.TEXT}; margin:12px 0 8px;">Start Flow</div>')
            segment_select = gr.Dropdown(label="Segment", choices=[], interactive=True)
            start_date = gr.Textbox(label="Start Date", value=str(__import__("datetime").date.today()))
            start_btn = gr.Button("Start Flow", variant="primary", size="sm")
            start_result = gr.HTML(value="")

            gr.HTML('<div class="nav-separator"></div>')
            left_kpis = gr.HTML(value="")

        with gr.Column(scale=3):
            flow_details_html = gr.HTML(value="")
            flow_runs_html = gr.HTML(value="")

    def _on_flow_selected(flow_choice):
        if not flow_choice:
            return ""
        from services.database import get_db
        from services.models import Flow
        db = get_db()
        try:
            flow = db.query(Flow).filter(Flow.name == flow_choice).first()
            if flow:
                return _build_flow_details(flow)
            return ""
        finally:
            db.close()

    flow_select.change(fn=_on_flow_selected, inputs=[flow_select], outputs=[flow_details_html])

    def _start_flow(flow_choice, segment_choice, start_date_val):
        if not flow_choice:
            return f'<div style="color:{COLORS.ERROR};">Select a flow first</div>'

        from services.database import get_db
        from services.models import Flow, FlowRun
        db = get_db()
        try:
            flow = db.query(Flow).filter(Flow.name == flow_choice).first()
            if not flow:
                return f'<div style="color:{COLORS.ERROR};">Flow not found</div>'

            run = FlowRun(
                flow_id=flow.id,
                segment_id=segment_choice if segment_choice != "all" else None,
                status="active",
                current_step=0,
            )
            db.add(run)
            db.commit()
            return f'<div style="color:{COLORS.SUCCESS};">Flow "{flow.name}" started</div>'
        except Exception as e:
            db.rollback()
            return f'<div style="color:{COLORS.ERROR};">Error: {e}</div>'
        finally:
            db.close()

    start_btn.click(
        fn=_start_flow,
        inputs=[flow_select, segment_select, start_date],
        outputs=[start_result],
    )

    def _refresh():
        from services.database import get_db
        from services.models import Flow, FlowRun, Segment
        db = get_db()
        try:
            flows = db.query(Flow).all()
            active_runs = db.query(FlowRun).filter(FlowRun.status == "active").count()
            completed_runs = db.query(FlowRun).filter(FlowRun.status == "completed").count()

            kpis = render_kpi_row([
                (str(active_runs), "Active", "", COLORS.SUCCESS),
                (str(completed_runs), "Completed", "", COLORS.TEXT),
                (str(len(flows)), "Flows", "", COLORS.PRIMARY),
            ])

            flow_choices = [f.name for f in flows]
            segment_choices = ["all"] + [s.id for s in db.query(Segment).filter(Segment.is_active == True).all()]

            details = ""
            if flows:
                details = _build_flow_details(flows[0])

            runs_table = _build_flow_runs_table(db)

            return (
                kpis,
                gr.update(choices=flow_choices, value=flow_choices[0] if flow_choices else None),
                gr.update(choices=segment_choices, value="all"),
                details,
                runs_table,
            )
        finally:
            db.close()

    return {
        "update_fn": _refresh,
        "outputs": [left_kpis, flow_select, segment_select, flow_details_html, flow_runs_html],
    }
