"""WhatsApp Broadcasts page — WhatsApp-only creation flow.

LEFT COLUMN (compact dark cards)
  🎯 Audience · segment, country, tags, lifecycle, consent, max recipients, KPIs
  ✏️ Message · category filter + template picker

RIGHT COLUMN
  4 cost KPI cards
  Large scrollable preview (template view ↔ rendered view)
  Test + Send buttons
"""

from __future__ import annotations

import html as html_lib
import re

import gradio as gr

from shared.theme import COLORS


DEFAULT_COUNTRIES = ["India"]
DEFAULT_CONSENTS = ["opted_in", "pending"]
CHANNEL = "whatsapp"  # this page is WhatsApp-only


# ═══════════════════════════════════════════════════════════════════
# Main builder
# ═══════════════════════════════════════════════════════════════════

def build(ctx) -> dict:
    with gr.Row(equal_height=False):
        # ═══════════════════════════════════════════════════════════
        # LEFT COLUMN — Audience + Message
        # ═══════════════════════════════════════════════════════════
        with gr.Column(scale=2, min_width=380):

            # ── Audience (compact dark card) ──
            gr.HTML(_section_header("🎯 Audience", "Who will receive this broadcast"))

            segment_dropdown = gr.Dropdown(
                label="Segment",
                choices=[],
                interactive=True,
            )

            country_dropdown = gr.Dropdown(
                label="Countries (include only)",
                choices=DEFAULT_COUNTRIES,
                value=DEFAULT_COUNTRIES,
                multiselect=True,
                interactive=True,
                info="WhatsApp is only supported for India in your current setup.",
            )

            with gr.Row():
                lifecycle_dropdown = gr.Dropdown(
                    label="Lifecycle",
                    choices=[],
                    value=[],
                    multiselect=True,
                    interactive=True,
                )
                consent_dropdown = gr.Dropdown(
                    label="Consent",
                    choices=["opted_in", "pending", "opted_out"],
                    value=DEFAULT_CONSENTS,
                    multiselect=True,
                    interactive=True,
                )

            tag_dropdown = gr.Dropdown(
                label="Tags (optional)",
                choices=[],
                value=[],
                multiselect=True,
                interactive=True,
                info="Empty = all tags. Pick tags to narrow further.",
            )

            limit_slider = gr.Slider(
                label="Max recipients  ·  0 = send to all",
                minimum=0,
                maximum=1000,
                value=0,
                step=10,
                interactive=True,
            )

            audience_kpis_html = gr.HTML(value="")

            # ── Message ──
            gr.HTML(_section_header("✏️ Message", "Only MARKETING templates are broadcastable — transactional templates live in automation flows"))

            template_dropdown = gr.Dropdown(
                label="Template",
                choices=[],
                interactive=True,
            )

        # ═══════════════════════════════════════════════════════════
        # RIGHT COLUMN — Cost KPIs + Preview
        # ═══════════════════════════════════════════════════════════
        with gr.Column(scale=3, min_width=540):

            cost_kpis_html = gr.HTML(value=_empty_cost_kpis())

            gr.HTML('<div style="height:10px;"></div>')

            with gr.Row():
                gr.HTML(_section_header("👁️ Preview", "", inline=True))
                preview_mode = gr.Radio(
                    choices=["Template view", "Rendered view"],
                    value="Template view",
                    label="",
                    container=False,
                    interactive=True,
                )

            preview_html = gr.HTML(value=_empty_preview())

            with gr.Row():
                test_btn = gr.Button("Test (1 message)", size="sm", scale=1)
                send_btn = gr.Button("Send Broadcast", variant="primary", size="sm", scale=2)

            result_html = gr.HTML(value="")

    # ═══════════════════════════════════════════════════════════
    # Event handlers
    # ═══════════════════════════════════════════════════════════

    def _on_segment_change(segment_choice):
        """Segment switch: refresh country/tag/lifecycle options."""
        from services.database import get_db
        from services.broadcast_engine import (
            get_unique_countries_in_segment, get_unique_tags_in_segment,
            get_unique_lifecycles_in_segment, get_unique_consents_in_segment,
        )

        seg_id = _seg_id(segment_choice)
        db = get_db()
        try:
            all_countries = get_unique_countries_in_segment(db, CHANNEL, seg_id)
            all_tags = get_unique_tags_in_segment(db, CHANNEL, seg_id)
            all_lifecycles = get_unique_lifecycles_in_segment(db, CHANNEL, seg_id)
            all_consents = get_unique_consents_in_segment(db, CHANNEL, seg_id)
        finally:
            db.close()

        country_default = [c for c in DEFAULT_COUNTRIES if c in all_countries] or all_countries[:1]
        consent_default = [c for c in DEFAULT_CONSENTS if c in all_consents]

        return (
            gr.update(choices=all_countries or DEFAULT_COUNTRIES, value=country_default),
            gr.update(choices=all_tags, value=[]),
            gr.update(choices=all_lifecycles, value=[]),
            gr.update(choices=all_consents or ["opted_in", "pending", "opted_out"], value=consent_default),
        )

    segment_dropdown.change(
        fn=_on_segment_change,
        inputs=[segment_dropdown],
        outputs=[country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown],
    )

    def _refresh_audience_and_cost(segment_choice, countries, tags, lifecycles, consents, limit, template_choice):
        kpis = _render_audience_kpis(segment_choice, countries, tags, lifecycles, consents, limit)
        cost = _render_cost_kpis(segment_choice, countries, tags, lifecycles, consents, limit, template_choice)
        return kpis, cost

    filter_inputs = [
        segment_dropdown, country_dropdown, tag_dropdown,
        lifecycle_dropdown, consent_dropdown, limit_slider, template_dropdown,
    ]
    audience_outputs = [audience_kpis_html, cost_kpis_html]

    for comp in [segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown, limit_slider]:
        comp.change(fn=_refresh_audience_and_cost, inputs=filter_inputs, outputs=audience_outputs)

    def _on_template_change(segment_choice, countries, tags, lifecycles, consents, limit, template_choice, mode):
        preview = _render_preview(template_choice, segment_choice, countries, tags, lifecycles, consents, limit, mode)
        cost = _render_cost_kpis(segment_choice, countries, tags, lifecycles, consents, limit, template_choice)
        return preview, cost

    template_dropdown.change(
        fn=_on_template_change,
        inputs=[segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown, limit_slider, template_dropdown, preview_mode],
        outputs=[preview_html, cost_kpis_html],
    )

    preview_mode.change(
        fn=lambda seg, co, ta, lc, cs, lim, tpl, mode: _render_preview(tpl, seg, co, ta, lc, cs, lim, mode),
        inputs=[segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown, limit_slider, template_dropdown, preview_mode],
        outputs=[preview_html],
    )

    # ── Send ──
    def _send(segment_choice, countries, tags, lifecycles, consents, limit, template_choice):
        if not template_choice or not segment_choice:
            return f'<div style="color:#ef4444; font-size:11px;">Select a segment and template first.</div>'

        from services.database import get_db
        from services.broadcast_engine import send_broadcast, BroadcastFilters

        template_id = _template_id(template_choice)
        label = _template_label(template_choice)
        name = f"WhatsApp: {label}"

        filters = BroadcastFilters(
            segment_id=_seg_id(segment_choice),
            countries=list(countries or []),
            tags=list(tags or []),
            lifecycles=list(lifecycles or []),
            consents=list(consents or []),
            max_recipients=int(limit or 0),
        )

        db = get_db()
        try:
            result = send_broadcast(db, name, CHANNEL, template_id, filters)
            color = "#22c55e" if result.failed == 0 else "#f59e0b"
            error_detail = ""
            if result.errors:
                err_preview = "; ".join(result.errors[:2])
                if len(result.errors) > 2:
                    err_preview += f" (+{len(result.errors) - 2} more)"
                error_detail = (
                    f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; margin-top:4px; '
                    f'max-width:100%; overflow:hidden; text-overflow:ellipsis;">{err_preview}</div>'
                )
            return (
                f'<div style="background:{COLORS.CARD_BG}; border-radius:8px; padding:12px; '
                f'border-left:4px solid {color}; margin-top:8px;">'
                f'<div style="font-weight:600; color:{color};">Broadcast Sent!</div>'
                f'<div style="color:{COLORS.TEXT_SUBTLE}; font-size:11px;">'
                f'Sent: {result.sent} | Failed: {result.failed} | Total: {result.total}</div>'
                f'{error_detail}</div>'
            )
        except Exception as e:
            return f'<div style="color:#ef4444; font-size:11px;">Error: {e}</div>'
        finally:
            db.close()

    send_btn.click(
        fn=_send,
        inputs=[segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown, limit_slider, template_dropdown],
        outputs=[result_html],
    )

    # ── Test (single contact) ──
    def _test(segment_choice, countries, tags, lifecycles, consents, limit, template_choice):
        if not template_choice:
            return f'<div style="color:#ef4444; font-size:11px;">Select a template first.</div>'

        from services.database import get_db
        from services.broadcast_engine import BroadcastFilters, apply_filters, get_segment_contacts, _resolve_wa_variable
        from services.wa_sender import WhatsAppSender
        from services.wa_config import get_wa_config

        template_id = _template_id(template_choice)
        filters = BroadcastFilters(
            segment_id=_seg_id(segment_choice),
            countries=list(countries or []),
            tags=list(tags or []),
            lifecycles=list(lifecycles or []),
            consents=list(consents or []),
            max_recipients=1,
        )

        db = get_db()
        try:
            segment_contacts = get_segment_contacts(db, filters.segment_id)
            final = apply_filters(segment_contacts, CHANNEL, filters)
            if not final:
                return f'<div style="color:#ef4444; font-size:11px;">No contacts match the current filters.</div>'

            contact = final[0]
            tpl_def = get_wa_config().get_template(template_id)
            lang = tpl_def.language if tpl_def else "en_US"
            rendered_vars: list[tuple[str, str]] = []
            if tpl_def:
                for var in tpl_def.variables:
                    rendered_vars.append((var.name, _resolve_wa_variable(var.name, contact)))

            ok, msg_id, error = WhatsAppSender().send_template(
                contact.wa_id, template_id, lang=lang, variables=rendered_vars or None,
            )
            if ok:
                return f'<div style="color:#22c55e; font-size:11px;">Test sent to {contact.first_name} ({contact.wa_id})</div>'
            return f'<div style="color:#ef4444; font-size:11px; word-break:break-all;">Failed: {error}</div>'
        except Exception as e:
            return f'<div style="color:#ef4444; font-size:11px;">Error: {e}</div>'
        finally:
            db.close()

    test_btn.click(
        fn=_test,
        inputs=[segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown, consent_dropdown, limit_slider, template_dropdown],
        outputs=[result_html],
    )

    # ── Refresh on page load ──
    def _refresh():
        from services.database import get_db
        from services.models import Segment
        from services.broadcast_engine import (
            get_unique_countries_in_segment, get_unique_tags_in_segment,
            get_unique_lifecycles_in_segment, get_unique_consents_in_segment,
        )

        db = get_db()
        try:
            segments = db.query(Segment).filter(Segment.is_active == True).all()
            seg_choices = ["all_opted_in"] + [f"{s.id} — {s.name}" for s in segments]

            all_countries = get_unique_countries_in_segment(db, CHANNEL, "all_opted_in")
            all_tags = get_unique_tags_in_segment(db, CHANNEL, "all_opted_in")
            all_lifecycles = get_unique_lifecycles_in_segment(db, CHANNEL, "all_opted_in")
            all_consents = get_unique_consents_in_segment(db, CHANNEL, "all_opted_in")

            templates = _wa_template_choices()
            default_tpl = templates[0] if templates else None

            country_default = [c for c in DEFAULT_COUNTRIES if c in all_countries] or all_countries[:1]
            consent_default = [c for c in DEFAULT_CONSENTS if c in all_consents]

            kpis = _render_audience_kpis("all_opted_in", country_default, [], [], consent_default, 0)
            cost = _render_cost_kpis("all_opted_in", country_default, [], [], consent_default, 0, default_tpl)
            preview = _render_preview(default_tpl, "all_opted_in", country_default, [], [], consent_default, 0, "Template view")

            return (
                gr.update(choices=seg_choices, value="all_opted_in"),
                gr.update(choices=all_countries or DEFAULT_COUNTRIES, value=country_default),
                gr.update(choices=all_tags, value=[]),
                gr.update(choices=all_lifecycles, value=[]),
                gr.update(choices=all_consents or ["opted_in", "pending", "opted_out"], value=consent_default),
                gr.update(choices=templates, value=default_tpl),
                kpis,
                cost,
                preview,
            )
        finally:
            db.close()

    return {
        "update_fn": _refresh,
        "outputs": [
            segment_dropdown, country_dropdown, tag_dropdown, lifecycle_dropdown,
            consent_dropdown, template_dropdown,
            audience_kpis_html, cost_kpis_html, preview_html,
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# Section header (compact, dark)
# ═══════════════════════════════════════════════════════════════════

def _section_header(title: str, subtitle: str = "", inline: bool = False) -> str:
    if inline:
        return (
            f'<div style="display:flex; align-items:center; gap:10px; padding-top:4px;">'
            f'<span style="font-size:11px; font-weight:700; color:{COLORS.TEXT}; '
            f'text-transform:uppercase; letter-spacing:.5px;">{title}</span>'
            f'</div>'
        )
    sub_html = (
        f'<span style="font-size:10px; color:{COLORS.TEXT_MUTED}; font-weight:400; '
        f'text-transform:none; letter-spacing:0; margin-left:8px;">· {subtitle}</span>'
        if subtitle else ""
    )
    return (
        f'<div style="padding:10px 2px 4px; margin-top:6px;">'
        f'<span style="font-size:11px; font-weight:700; color:{COLORS.TEXT}; '
        f'text-transform:uppercase; letter-spacing:.5px;">{title}</span>'
        f'{sub_html}'
        f'</div>'
    )


# ═══════════════════════════════════════════════════════════════════
# Template choice helpers
# ═══════════════════════════════════════════════════════════════════

def _wa_template_choices() -> list[str]:
    """Return broadcast-eligible templates (MARKETING only).

    Transactional / utility templates need live per-order data
    (order_id, amount, tracking_id, etc.) that doesn't live on a
    Contact record, so they can't be meaningfully broadcast.
    """
    from services.wa_config import get_wa_config
    wa_cfg = get_wa_config()
    out = []
    for t in wa_cfg.list_templates():
        if t["category"].upper() != "MARKETING":
            continue
        out.append(f'{t["name"]} — {t["display_name"]}')
    return out


def _template_id(choice: str) -> str:
    if not choice:
        return ""
    return choice.split(" — ")[0]


def _template_label(choice: str) -> str:
    if not choice or " — " not in choice:
        return choice or ""
    middle = choice.split(" — ")[1]
    return middle.split(" [")[0] if " [" in middle else middle


def _seg_id(choice: str) -> str | None:
    if not choice:
        return None
    return choice.split(" — ")[0] if " — " in choice else choice


# ═══════════════════════════════════════════════════════════════════
# Audience KPI rendering (dark cards, larger numbers)
# ═══════════════════════════════════════════════════════════════════

def _render_audience_kpis(segment_choice, countries, tags, lifecycles, consents, limit) -> str:
    if not segment_choice:
        return ""

    from services.database import get_db
    from services.broadcast_engine import BroadcastFilters, get_audience_breakdown

    filters = BroadcastFilters(
        segment_id=_seg_id(segment_choice),
        countries=list(countries or []),
        tags=list(tags or []),
        lifecycles=list(lifecycles or []),
        consents=list(consents or []),
        max_recipients=int(limit or 0),
    )

    db = get_db()
    try:
        data = get_audience_breakdown(db, CHANNEL, filters)
    finally:
        db.close()

    reach_pct = int(round(100 * data["final_recipients"] / data["total_in_segment"])) if data["total_in_segment"] else 0
    bar_width = max(2, reach_pct)

    funnel = (
        f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;">'
        f'{_funnel_cell("Segment", data["total_in_segment"], COLORS.TEXT)}'
        f'{_funnel_cell("WhatsApp eligible", data["eligible_on_channel"], "#60a5fa")}'
        f'{_funnel_cell("Final", data["final_recipients"], "#22c55e")}'
        f'</div>'
    )

    progress = (
        f'<div style="margin-top:10px;">'
        f'<div style="display:flex; justify-content:space-between; font-size:10px; '
        f'color:{COLORS.TEXT_MUTED}; margin-bottom:4px;">'
        f'<span>Reach</span><span>{reach_pct}% of segment</span></div>'
        f'<div style="height:6px; background:rgba(255,255,255,.06); border-radius:3px; overflow:hidden;">'
        f'<div style="width:{bar_width}%; height:100%; '
        f'background:linear-gradient(90deg,#60a5fa,#22c55e);"></div>'
        f'</div></div>'
    )

    breakdowns = ""
    if data["final_recipients"] > 0:
        breakdowns = (
            f'<div style="margin-top:12px; background:{COLORS.CARD_BG}; border-radius:8px; '
            f'padding:10px 12px; border:1px solid rgba(255,255,255,.06);">'
            f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">'
            f'{_breakdown_block("By Geography", data["geography"])}'
            f'{_breakdown_block("By Lifecycle", data["lifecycle"])}'
            f'</div>'
            f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:10px;">'
            f'{_breakdown_block("By Consent", data["consent"])}'
            f'{_breakdown_block("By Customer Type", data["customer_type"])}'
            f'</div></div>'
        )

    return funnel + progress + breakdowns


def _funnel_cell(label: str, value: int, color: str) -> str:
    """Larger funnel cell — the three audience counters."""
    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:8px; padding:12px 10px; '
        f'text-align:center; border:1px solid rgba(255,255,255,.06);">'
        f'<div style="font-size:22px; font-weight:700; color:{color}; line-height:1;">{value:,}</div>'
        f'<div style="font-size:9px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase; '
        f'letter-spacing:.3px; margin-top:4px;">{label}</div>'
        f'</div>'
    )


def _breakdown_block(title: str, data: dict) -> str:
    if not data:
        return (
            f'<div><div style="font-size:9px; color:{COLORS.TEXT_MUTED}; '
            f'text-transform:uppercase; margin-bottom:4px;">{title}</div>'
            f'<div style="font-size:11px; color:{COLORS.TEXT_MUTED};">—</div></div>'
        )

    total = sum(data.values()) or 1
    rows = ""
    for key, count in list(data.items())[:5]:
        pct = int(round(100 * count / total))
        rows += (
            f'<div style="display:flex; justify-content:space-between; align-items:center; '
            f'font-size:11px; color:{COLORS.TEXT_SUBTLE}; padding:3px 0;">'
            f'<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:110px;">{key}</span>'
            f'<span style="color:{COLORS.TEXT}; font-weight:600;">{count} '
            f'<span style="color:{COLORS.TEXT_MUTED}; font-weight:400;">({pct}%)</span></span>'
            f'</div>'
        )

    return (
        f'<div><div style="font-size:9px; color:{COLORS.TEXT_MUTED}; '
        f'text-transform:uppercase; letter-spacing:.3px; margin-bottom:4px;">{title}</div>{rows}</div>'
    )


# ═══════════════════════════════════════════════════════════════════
# Cost KPIs
# ═══════════════════════════════════════════════════════════════════

def _render_cost_kpis(segment_choice, countries, tags, lifecycles, consents, limit, template_choice) -> str:
    if not segment_choice:
        return _empty_cost_kpis()

    from services.database import get_db
    from services.broadcast_engine import BroadcastFilters, estimate_cost, format_duration
    from services.wa_config import get_wa_config

    filters = BroadcastFilters(
        segment_id=_seg_id(segment_choice),
        countries=list(countries or []),
        tags=list(tags or []),
        lifecycles=list(lifecycles or []),
        consents=list(consents or []),
        max_recipients=int(limit or 0),
    )

    category = "MARKETING"
    if template_choice:
        tpl = get_wa_config().get_template(_template_id(template_choice))
        if tpl:
            category = tpl.category

    db = get_db()
    try:
        cost = estimate_cost(db, CHANNEL, category, filters)
    finally:
        db.close()

    delivery = format_duration(cost["est_delivery_seconds"])
    category_label = category.title()
    recipients_display = f"{cost['recipients']:,}"
    per_msg_label = f"Per Message ({category_label})"

    c1 = _cost_card("Recipients", recipients_display, "\U0001F465", COLORS.TEXT)
    c2 = _cost_card(per_msg_label, cost["per_message_display"], "\U0001F4B0", "#60a5fa")
    c3 = _cost_card("Total Cost", cost["total_display"], "\U0001F4B8", "#22c55e")
    c4 = _cost_card("Delivery", delivery, "\u23F1\uFE0F", "#f59e0b")

    return (
        '<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px;">'
        f'{c1}{c2}{c3}{c4}</div>'
    )


def _empty_cost_kpis() -> str:
    c1 = _cost_card("Recipients", "—", "\U0001F465", COLORS.TEXT_MUTED)
    c2 = _cost_card("Per Message", "—", "\U0001F4B0", COLORS.TEXT_MUTED)
    c3 = _cost_card("Total Cost", "—", "\U0001F4B8", COLORS.TEXT_MUTED)
    c4 = _cost_card("Delivery", "—", "\u23F1\uFE0F", COLORS.TEXT_MUTED)
    return (
        '<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px;">'
        f'{c1}{c2}{c3}{c4}</div>'
    )


def _cost_card(label: str, value: str, icon: str, color: str) -> str:
    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:12px 14px; '
        f'border:1px solid rgba(255,255,255,.06);">'
        f'<div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">'
        f'<span style="font-size:12px;">{icon}</span>'
        f'<span style="font-size:9px; color:{COLORS.TEXT_MUTED}; text-transform:uppercase; '
        f'letter-spacing:.4px;">{label}</span></div>'
        f'<div style="font-size:20px; font-weight:700; color:{color}; line-height:1.1;">{value}</div>'
        f'</div>'
    )


# ═══════════════════════════════════════════════════════════════════
# Preview rendering
# ═══════════════════════════════════════════════════════════════════

def _empty_preview() -> str:
    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:80px 20px; '
        f'text-align:center; color:{COLORS.TEXT_MUTED}; min-height:720px; '
        f'border:1px dashed rgba(255,255,255,.08); display:flex; flex-direction:column; '
        f'align-items:center; justify-content:center;">'
        f'<div style="font-size:42px; margin-bottom:10px;">\U0001F4E9</div>'
        f'<div style="font-size:13px;">Select a template to preview the message</div>'
        f'</div>'
    )


def _render_preview(template_choice, segment_choice, countries, tags, lifecycles, consents, limit, mode) -> str:
    if not template_choice:
        return _empty_preview()
    return _preview_wa(_template_id(template_choice), segment_choice, countries, tags, lifecycles, consents, limit, mode)


def _first_contact(segment_choice, countries, tags, lifecycles, consents, limit):
    from services.database import get_db
    from services.broadcast_engine import BroadcastFilters, apply_filters, get_segment_contacts

    filters = BroadcastFilters(
        segment_id=_seg_id(segment_choice),
        countries=list(countries or []),
        tags=list(tags or []),
        lifecycles=list(lifecycles or []),
        consents=list(consents or []),
        max_recipients=1,
    )
    db = get_db()
    try:
        segment_contacts = get_segment_contacts(db, filters.segment_id)
        final = apply_filters(segment_contacts, CHANNEL, filters)
        return final[0] if final else None
    finally:
        db.close()


def _highlight_placeholders(text: str) -> str:
    escaped = html_lib.escape(text)

    def repl(m):
        var = m.group(1)
        return (
            f'<span style="background:#fde68a; color:#78350f; padding:1px 5px; '
            f'border-radius:3px; font-weight:600;">{{{{{var}}}}}</span>'
        )

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, escaped)


def _render_with_contact(text: str, render_vars: dict) -> str:
    def repl(m):
        var = m.group(1).strip()
        value = render_vars.get(var, "")
        safe = html_lib.escape(str(value))
        return (
            f'<span style="background:#dcfce7; color:#14532d; padding:1px 5px; '
            f'border-radius:3px; font-weight:600;">{safe}</span>'
        )

    escaped = html_lib.escape(text)
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, escaped)


def _render_header_media(tpl) -> str:
    """Render the WA template header — real image if URL set, else CSS placeholder."""
    if not tpl.has_header_image:
        return ""
    if tpl.header_image_url:
        return (
            f'<div style="margin:-12px -14px 8px; border-radius:6px 6px 0 0; overflow:hidden;">'
            f'<img src="{html_lib.escape(tpl.header_image_url)}" '
            f'style="width:100%; max-height:220px; object-fit:cover; display:block;" '
            f'onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'block\';" />'
            f'<div style="display:none; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); '
            f'padding:28px 16px; text-align:center; color:white;">'
            f'<div style="font-size:32px;">\U0001F3D4\uFE0F</div>'
            f'<div style="font-size:10px; opacity:.85;">Header image unavailable</div></div>'
            f'</div>'
        )
    return (
        '<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); '
        'padding:28px 16px; text-align:center; border-radius:6px 6px 0 0; '
        'margin:-12px -14px 8px; color:white;">'
        '<div style="font-size:32px; margin-bottom:4px;">\U0001F3D4\uFE0F</div>'
        '<div style="font-size:10px; opacity:.85;">Template Header Image</div></div>'
    )


def _preview_wa(template_id, segment_choice, countries, tags, lifecycles, consents, limit, mode) -> str:
    from services.wa_config import get_wa_config
    from services.broadcast_engine import _resolve_wa_variable

    tpl = get_wa_config().get_template(template_id)
    if not tpl:
        return f'<div style="color:{COLORS.TEXT_MUTED}; font-size:11px;">Template not found.</div>'

    body = (tpl.body_text or tpl.description).strip()

    if mode == "Rendered view":
        contact = _first_contact(segment_choice, countries, tags, lifecycles, consents, limit)
        if contact:
            render_vars = {v.name: _resolve_wa_variable(v.name, contact) for v in tpl.variables}
            body_html = _render_with_contact(body, render_vars)
            mode_note = f'Showing values for {contact.first_name or "contact"} ({contact.wa_id})'
        else:
            body_html = _highlight_placeholders(body)
            mode_note = "No eligible contact — showing placeholders"
    else:
        body_html = _highlight_placeholders(body)
        mode_note = "Placeholders shown as highlighted tokens"

    header_html = _render_header_media(tpl)

    buttons_html = ""
    if tpl.buttons:
        btns = "".join(
            f'<div style="text-align:center; padding:10px; margin-top:6px; '
            f'background:#ffffff; border-radius:6px; color:#1daa61; font-size:13px; '
            f'font-weight:500; border:1px solid rgba(29,170,97,.2);">'
            f'{html_lib.escape(b.text)}</div>'
            for b in tpl.buttons
        )
        buttons_html = f'<div style="margin-top:8px;">{btns}</div>'

    cat_color = "#f59e0b" if tpl.category == "MARKETING" else "#60a5fa"
    cat_bg = "rgba(245,158,11,.12)" if tpl.category == "MARKETING" else "rgba(96,165,250,.12)"

    # Variables mapping table
    var_table = ""
    if tpl.variables:
        rows = "".join(
            f'<tr style="border-bottom:1px solid rgba(255,255,255,.05);">'
            f'<td style="padding:6px 10px; font-size:11px;">'
            f'<code style="background:#fde68a; color:#78350f; padding:2px 6px; border-radius:3px; font-weight:600;">'
            f'{{{{{v.name}}}}}</code></td>'
            f'<td style="padding:6px 10px; font-size:11px; color:{COLORS.TEXT_SUBTLE};">{html_lib.escape(v.description)}</td>'
            f'<td style="padding:6px 10px; font-size:11px; color:{COLORS.TEXT_MUTED};">{html_lib.escape(v.example)}</td>'
            f'</tr>'
            for v in tpl.variables
        )
        var_table = (
            f'<div style="margin-top:12px; background:rgba(255,255,255,.02); border-radius:6px; '
            f'padding:10px 12px; border:1px solid rgba(255,255,255,.05);">'
            f'<div style="font-size:10px; font-weight:600; color:{COLORS.TEXT_MUTED}; '
            f'text-transform:uppercase; letter-spacing:.3px; margin-bottom:6px;">'
            f'Variable Mapping (auto-filled from contact)</div>'
            f'<table style="width:100%; border-collapse:collapse;">'
            f'<thead><tr>'
            f'<th style="text-align:left; padding:4px 10px; font-size:10px; color:{COLORS.TEXT_MUTED};">Placeholder</th>'
            f'<th style="text-align:left; padding:4px 10px; font-size:10px; color:{COLORS.TEXT_MUTED};">Maps to</th>'
            f'<th style="text-align:left; padding:4px 10px; font-size:10px; color:{COLORS.TEXT_MUTED};">Example</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
        )

    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; padding:14px; '
        f'border:1px solid rgba(255,255,255,.06); max-height:820px; overflow-y:auto;">'
        # Title row
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">'
        f'<div>'
        f'<div style="font-size:14px; font-weight:700; color:{COLORS.TEXT};">{html_lib.escape(tpl.display_name)}</div>'
        f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; margin-top:2px;">'
        f'{tpl.language} · {tpl.use_case or "—"}</div>'
        f'</div>'
        f'<div style="font-size:10px; color:{cat_color}; background:{cat_bg}; '
        f'padding:4px 10px; border-radius:10px; font-weight:600; text-transform:uppercase; '
        f'letter-spacing:.4px;">{tpl.category}</div>'
        f'</div>'
        f'<div style="font-size:10px; color:{COLORS.TEXT_MUTED}; margin-bottom:10px; font-style:italic;">{mode_note}</div>'
        # Chat canvas
        f'<div style="background:#0b141a; border-radius:10px; padding:20px; '
        f'background-image:radial-gradient(rgba(255,255,255,.015) 1px, transparent 1px); '
        f'background-size:14px 14px;">'
        f'<div style="background:#d9fdd3; border-radius:8px; padding:12px 14px; max-width:460px; '
        f'box-shadow:0 1px 1px rgba(0,0,0,.1);">'
        f'{header_html}'
        f'<div style="font-size:14px; color:#111; line-height:1.6; white-space:pre-wrap;">{body_html}</div>'
        f'{buttons_html}'
        f'<div style="text-align:right; font-size:9px; color:#667781; margin-top:6px;">'
        f'12:34 \u2713\u2713</div>'
        f'</div></div>'
        f'{var_table}'
        f'</div>'
    )
