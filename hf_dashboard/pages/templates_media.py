"""Templates & Media page — preview email/WA templates and manage product images."""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from components.kpi_card import render_kpi_row
from components.styled_table import render_table, cell, cell_badge
from components.section_card import render_section_card
from components.empty_state import render_empty_state
from shared.theme import COLORS, FONTS

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _get_email_templates(db):
    from services.models import EmailTemplate
    return db.query(EmailTemplate).filter(EmailTemplate.is_active == True).all()


def _build_template_list(templates):
    if not templates:
        return render_empty_state("No email templates found")

    rows = []
    for t in templates:
        category_color = COLORS.PRIMARY if t.category == "campaign" else COLORS.INFO
        rows.append([
            cell(t.name, bold=True),
            cell(t.slug, mono=True),
            cell_badge(t.category.upper(), category_color),
            cell(t.subject_template[:40] if t.subject_template else "--"),
        ])

    return render_table(
        [("Name", "left"), ("Slug", "left"), ("Type", "center"), ("Subject", "left")],
        rows, title="Email Templates",
    )


def _build_wa_template_list():
    """Build WA template list from YAML config."""
    try:
        import yaml
        config_path = Path(__file__).resolve().parent.parent / "config" / "whatsapp" / "templates.yml"
        if not config_path.exists():
            return render_empty_state("WhatsApp templates config not found")

        with open(config_path) as f:
            data = yaml.safe_load(f)

        templates = data.get("templates", {})
        if not templates:
            return render_empty_state("No WhatsApp templates defined")

        rows = []
        for name, tpl in templates.items():
            display = tpl.get("display_name", name)
            category = tpl.get("category", "")
            use_case = tpl.get("use_case", "")
            num_vars = len(tpl.get("variables", []))
            cat_color = COLORS.PRIMARY if category == "MARKETING" else COLORS.INFO

            rows.append([
                cell(display, bold=True),
                cell(name, mono=True),
                cell_badge(category, cat_color),
                cell(use_case),
                cell(str(num_vars), align="center"),
            ])

        return render_table(
            [("Name", "left"), ("Template ID", "left"), ("Category", "center"),
             ("Use Case", "left"), ("Vars", "center")],
            rows, title="WhatsApp Templates (Meta-Approved)",
        )
    except Exception as e:
        return render_section_card(f'<div style="color:{COLORS.ERROR};">Error loading WA templates: {e}</div>')


def build(ctx) -> dict:
    with gr.Row():
        with gr.Column(scale=1, elem_classes=["page-left-col"]):
            gr.HTML(f'<div style="font-size:13px; font-weight:600; color:{COLORS.TEXT}; margin-bottom:8px;">View</div>')
            channel_toggle = gr.Radio(label="Channel", choices=["Email", "WhatsApp", "Media"], value="Email")
            template_select = gr.Dropdown(label="Template", choices=[], interactive=True)

            gr.HTML('<div class="nav-separator"></div>')

            gr.HTML(f'<div style="font-size:13px; font-weight:600; color:{COLORS.TEXT}; margin:8px 0;">Upload</div>')
            upload_file = gr.File(label="Upload HTML Template", file_types=[".html"])
            upload_result = gr.HTML(value="")

            gr.HTML('<div class="nav-separator"></div>')

            gr.HTML(f'<div style="font-size:13px; font-weight:600; color:{COLORS.TEXT}; margin:8px 0;">Test Send</div>')
            test_email = gr.Textbox(label="Email", placeholder="test@example.com")
            test_send_btn = gr.Button("Send Preview", size="sm")
            test_result = gr.HTML(value="")

            gr.HTML('<div class="nav-separator"></div>')
            left_kpis = gr.HTML(value="")

        with gr.Column(scale=3):
            template_list_html = gr.HTML(value="")
            preview_html = gr.HTML(value="")

    def _on_template_selected(template_choice, channel):
        if not template_choice:
            return ""
        if channel == "Email":
            from services.database import get_db
            from services.models import EmailTemplate
            db = get_db()
            try:
                tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_choice).first()
                if tpl and tpl.html_content:
                    return (
                        f'<div style="font-size:{FONTS.MD}; font-weight:600; color:{COLORS.TEXT}; margin-bottom:8px;">'
                        f'Preview: {tpl.name}</div>'
                        f'<div style="background:#fff; border-radius:8px; padding:16px; max-height:500px; overflow-y:auto;">'
                        f'{tpl.html_content}</div>'
                    )
                return render_empty_state("No HTML content for this template")
            finally:
                db.close()
        return ""

    template_select.change(
        fn=_on_template_selected,
        inputs=[template_select, channel_toggle],
        outputs=[preview_html],
    )

    def _on_channel_change(channel):
        from services.database import get_db
        db = get_db()
        try:
            if channel == "Email":
                templates = _get_email_templates(db)
                choices = [t.slug for t in templates]
                list_html = _build_template_list(templates)
                return (
                    gr.update(choices=choices, value=choices[0] if choices else None),
                    list_html, "",
                )
            elif channel == "WhatsApp":
                list_html = _build_wa_template_list()
                return (
                    gr.update(choices=[], value=None),
                    list_html, "",
                )
            else:  # Media
                return (
                    gr.update(choices=[], value=None),
                    render_empty_state("Product media gallery — upload images to send via WhatsApp", icon="&#x1F4F7;"),
                    "",
                )
        finally:
            db.close()

    channel_toggle.change(
        fn=_on_channel_change,
        inputs=[channel_toggle],
        outputs=[template_select, template_list_html, preview_html],
    )

    def _test_send(email, template_slug):
        if not email or not template_slug:
            return f'<div style="color:{COLORS.ERROR};">Email and template required</div>'

        from services.database import get_db
        from services.models import EmailTemplate
        from services.email_sender import EmailSender

        db = get_db()
        try:
            tpl = db.query(EmailTemplate).filter(EmailTemplate.slug == template_slug).first()
            if not tpl:
                return f'<div style="color:{COLORS.ERROR};">Template not found</div>'

            sender = EmailSender()
            result = sender.send_email(email, tpl.subject_template, tpl.html_content)
            if result["success"]:
                return f'<div style="color:{COLORS.SUCCESS};">Test email sent to {email}</div>'
            return f'<div style="color:{COLORS.ERROR};">{result["message"]}</div>'
        finally:
            db.close()

    test_send_btn.click(
        fn=_test_send,
        inputs=[test_email, template_select],
        outputs=[test_result],
    )

    def _refresh():
        from services.database import get_db
        db = get_db()
        try:
            templates = _get_email_templates(db)
            email_count = len(templates)

            import yaml
            wa_count = 0
            config_path = Path(__file__).resolve().parent.parent / "config" / "whatsapp" / "templates.yml"
            if config_path.exists():
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                wa_count = len(data.get("templates", {}))

            kpis = render_kpi_row([
                (str(email_count), "Email", "", COLORS.PRIMARY),
                (str(wa_count), "WhatsApp", "", COLORS.SUCCESS),
            ])

            choices = [t.slug for t in templates]
            list_html = _build_template_list(templates)

            return (
                kpis,
                gr.update(choices=choices, value=choices[0] if choices else None),
                list_html, "",
            )
        finally:
            db.close()

    return {
        "update_fn": _refresh,
        "outputs": [left_kpis, template_select, template_list_html, preview_html],
    }
