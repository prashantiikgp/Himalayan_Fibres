"""Contacts page — dropdown filters, clean table, add contact form.

Layout from config/pages/contacts.yml. Schema from config/contacts/schema.yml.
Styles from config/theme/components.yml.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pandas as pd
import gradio as gr
import yaml

from components.kpi_card import render_kpi_row
from components.styles import (
    table_container, table_wrapper, table_header_cell,
    table_cell, table_row, table_row_hover, table_footer,
    badge, channel_badge_email, channel_badge_wa, empty_state,
)
from services.contact_schema import (
    get_segments, get_segment_choices, get_segment_id_by_label, get_segment_color,
    get_segment_description,
    get_lifecycle_stages, get_lifecycle_choices, get_lifecycle_id_by_label,
    get_lifecycle_color, get_lifecycle_icon,
    get_predefined_tags, get_country_options, get_field_config,
)
from services.segments import (
    get_all_active_segments, get_contact_segments_map, segment_color,
    count_segment_members, get_all_tags_from_contacts, segments_for_contact,
)
from services.interactions import (
    log_interaction, summarize_diff, get_interactions,
    render_activity_html, render_notes_html,
)

_PAGE_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "pages" / "contacts.yml"


def _load_page_config() -> dict:
    with open(_PAGE_CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("page", {})


def _missing_html() -> str:
    label = _load_page_config().get("missing_label", "Missing")
    return f'<span style="color:#64748b; font-style:italic;">{label}</span>'


def _is_real_email(email: str | None) -> bool:
    if not email:
        return False
    if "@placeholder.local" in email or email.startswith("wa_"):
        return False
    return True


def _display_or_missing(value: str | None) -> str:
    return value if value else _missing_html()


def _build_table(db, segment="All", lifecycle="All", country="All", channel="All",
                 tags=None, search="", page=0):
    from services.models import Contact

    cfg = _load_page_config()
    page_size = cfg.get("table", {}).get("page_size", 50)
    columns = cfg.get("table", {}).get("columns", [])

    # Plan D Phase 1.3: select only the 15 Contact columns this renderer
    # + segment rule evaluator needs, not the full 38-col Contact row.
    # That's a ~60% reduction in bytes per page render, and this path
    # fires on every filter / search / page change.
    #
    # Columns the row renderer uses: id, first_name, last_name, company,
    #   email, phone, wa_id, lifecycle, tags, city, country
    # Columns segments_for_contact() rule engine uses: customer_type,
    #   customer_subtype, geography, consent_status (plus lifecycle,
    #   country, tags which are already listed above)
    q = db.query(Contact).with_entities(
        Contact.id,
        Contact.first_name,
        Contact.last_name,
        Contact.company,
        Contact.email,
        Contact.phone,
        Contact.wa_id,
        Contact.lifecycle,
        Contact.tags,
        Contact.city,
        Contact.country,
        Contact.customer_type,
        Contact.customer_subtype,
        Contact.geography,
        Contact.consent_status,
    )

    # Filters
    if segment != "All":
        seg_id = get_segment_id_by_label(segment)
        if seg_id:
            q = q.filter(Contact.customer_type == seg_id)
    if lifecycle != "All":
        lc_id = get_lifecycle_id_by_label(lifecycle)
        if lc_id:
            q = q.filter(Contact.lifecycle == lc_id)
    if country != "All":
        q = q.filter(Contact.country == country)
    if channel == "Email Only":
        q = q.filter(Contact.email.isnot(None), ~Contact.email.like("%placeholder%"))
    elif channel == "WhatsApp Only":
        q = q.filter(Contact.wa_id.isnot(None))
    elif channel == "Both":
        q = q.filter(Contact.email.isnot(None), ~Contact.email.like("%placeholder%"), Contact.wa_id.isnot(None))
    if search:
        term = f"%{search}%"
        q = q.filter(
            Contact.email.ilike(term) | Contact.first_name.ilike(term) |
            Contact.last_name.ilike(term) | Contact.company.ilike(term)
        )

    # Tag filter — ANY match. Tags stored as JSON in SQLite so we evaluate
    # in Python for portability (SQLite + Postgres both work).
    tag_set = None
    if tags:
        if isinstance(tags, str):
            tag_set = {tags.strip()} if tags.strip() else None
        else:
            tag_set = {t.strip() for t in tags if t and t.strip()}
            if not tag_set:
                tag_set = None

    if tag_set:
        # Pull IDs matching any tag, then constrain query to that set
        id_subset = set()
        for c in db.query(Contact.id, Contact.tags).all():
            cid, ctags = c[0], c[1] or []
            if any(t in tag_set for t in ctags):
                id_subset.add(cid)
        if not id_subset:
            return f'<div style="{empty_state()}">No contacts match your filters</div>', 0, 1, 0
        q = q.filter(Contact.id.in_(id_subset))

    total = q.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page >= total_pages:
        page = 0
    contacts = q.order_by(Contact.company).offset(page * page_size).limit(page_size).all()

    if not contacts:
        empty = f'<div style="{empty_state()}">No contacts match your filters</div>'
        return empty, total, total_pages, page

    # Precompute segments per contact for the current page only.
    # Evaluate rules in Python against the already-loaded Contact rows —
    # zero extra DB round-trips, ~0ms for 50 contacts × 11 segments.
    all_segments = get_all_active_segments(db)
    segments_by_id = {s.id: s for s in all_segments}
    contact_segments_map = {
        c.id: segments_for_contact(c, all_segments) for c in contacts
    }

    col_widths = "".join(f'<col style="width:{c.get("width", "auto")}">' for c in columns)
    headers = "".join(f'<th style="{table_header_cell()}">{c["label"]}</th>' for c in columns)

    missing = _missing_html()
    rows_html = ""
    for contact in contacts:
        cells = ""
        for col in columns:
            field = col["field"]
            if field == "name":
                name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or missing
                company_line = contact.company or ""
                cells += (
                    f'<td style="{table_cell()}">'
                    f'<div style="font-weight:600; color:#e7eaf3;">{name}</div>'
                    f'<div style="font-size:10px; color:#64748b;">{company_line}</div></td>'
                )
            elif field == "company":
                cells += f'<td style="{table_cell()}">{_display_or_missing(contact.company)}</td>'
            elif field == "channels":
                ch = ""
                if _is_real_email(contact.email):
                    ch += f'<span style="{channel_badge_email()}">Email</span>'
                if contact.wa_id:
                    ch += f'<span style="{channel_badge_wa()}">WA</span>'
                cells += f'<td style="{table_cell()}">{ch or missing}</td>'
            elif field == "lifecycle":
                lc_color = get_lifecycle_color(contact.lifecycle or "new_lead")
                lc_icon = get_lifecycle_icon(contact.lifecycle or "new_lead")
                lc_label = (contact.lifecycle or "new_lead").replace("_", " ").title()
                cells += f'<td style="{table_cell()}"><span style="{badge(lc_color)}">{lc_icon} {lc_label}</span></td>'
            elif field == "email":
                font = col.get("font", "")
                display = contact.email if _is_real_email(contact.email) else missing
                cells += f'<td style="{table_cell(font=font)}; color:#94a3b8;">{display}</td>'
            elif field == "phone":
                display = contact.phone if contact.phone else missing
                cells += f'<td style="{table_cell()}; color:#94a3b8;">{display}</td>'
            elif field == "segments":
                seg_ids = contact_segments_map.get(contact.id, [])
                if seg_ids:
                    pills_html = []
                    for sid in seg_ids[:2]:
                        seg = segments_by_id.get(sid)
                        if not seg:
                            continue
                        color = segment_color(sid)
                        pills_html.append(
                            f'<span style="background:{color}22; color:{color}; '
                            f'border:1px solid {color}55; padding:1px 6px; '
                            f'border-radius:10px; font-size:9px; font-weight:600; '
                            f'margin-right:3px; display:inline-block;">{seg.name}</span>'
                        )
                    if len(seg_ids) > 2:
                        pills_html.append(
                            f'<span style="color:#64748b; font-size:9px;">+{len(seg_ids)-2}</span>'
                        )
                    cells += f'<td style="{table_cell()}">{"".join(pills_html)}</td>'
                else:
                    cells += f'<td style="{table_cell()}">{missing}</td>'
            elif field == "tags":
                tags_val = contact.tags or []
                if isinstance(tags_val, list) and tags_val:
                    pills = " ".join(
                        f'<span style="background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1); '
                        f'padding:1px 5px; border-radius:3px; font-size:9px; color:#94a3b8;">{t}</span>'
                        for t in tags_val[:3]
                    )
                    if len(tags_val) > 3:
                        pills += f' <span style="color:#64748b; font-size:9px;">+{len(tags_val)-3}</span>'
                    cells += f'<td style="{table_cell()}">{pills}</td>'
                else:
                    cells += f'<td style="{table_cell()}">{missing}</td>'
            elif field == "actions":
                # Hybrid bridge: write contact_id into the hidden Textbox via
                # the native setter + dispatch an `input` event so Svelte's
                # store updates, then click the hidden trigger button. The
                # trigger button's Python handler reads the textbox value as
                # its input AND copies it into a gr.State for the save flow.
                cells += (
                    f'<td style="{table_cell()}; text-align:center;">'
                    f'<button type="button" class="hf-row-edit-btn" '
                    f'onclick="(function(cid){{'
                    f'var box=document.querySelector(\'#hf-edit-contact-id textarea, #hf-edit-contact-id input\');'
                    f'if(!box){{return;}}'
                    f'var proto=box.tagName===\'INPUT\'?HTMLInputElement.prototype:HTMLTextAreaElement.prototype;'
                    f'var setter=Object.getOwnPropertyDescriptor(proto,\'value\').set;'
                    f'setter.call(box,cid);'
                    f'box.dispatchEvent(new Event(\'input\',{{bubbles:true}}));'
                    f'setTimeout(function(){{'
                    f'var trig=document.querySelector(\'#hf-edit-trigger-btn button\')||'
                    f'document.querySelector(\'#hf-edit-trigger-btn\');'
                    f'if(trig){{trig.click();}}'
                    f'}},80);'
                    f'}})(\'{contact.id}\')" '
                    f'title="Edit {contact.first_name or contact.id}">✎ Edit</button>'
                    f'</td>'
                )
            else:
                value = getattr(contact, field, None)
                cells += f'<td style="{table_cell()}">{_display_or_missing(value)}</td>'

        hover = table_row_hover()
        rows_html += (
            f'<tr style="{table_row()}" '
            f'onmouseover="this.style.background=\'{hover}\'" '
            f'onmouseout="this.style.background=\'transparent\'">'
            f'{cells}</tr>'
        )

    start = page * page_size + 1
    end = min((page + 1) * page_size, total)

    pag = cfg.get("pagination", {})
    range_text = pag.get("range_template", "Showing {start}–{end} of {total}").format(
        start=start, end=end, total=total,
    )
    page_text = f"Page {page + 1} of {total_pages}"

    # The row button parks contact.id on window.__hfPendingEditCid, then
    # programmatically clicks the hidden trigger button. The trigger's js=
    # callback pulls the value off window and returns it as the Python
    # handler's input — sidesteps Gradio 6 Svelte-state sync issues with
    # hidden-textbox bridges.
    table_html = (
        f'<table style="{table_container()}">'
        f'<colgroup>{col_widths}</colgroup>'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
    )
    return table_html, total, total_pages, page


def _build_legend() -> str:
    """Collapsible legend explaining Customer Types, Segments, and Tags.

    YAML-driven headings/copy from contacts.yml; segment descriptions from
    schema.yml; live segments + counts from the DB.
    """
    cfg = _load_page_config()
    legend_cfg = cfg.get("legend", {})
    ct_cfg = legend_cfg.get("customer_types", {})
    seg_cfg = legend_cfg.get("segments", {})
    tag_cfg = legend_cfg.get("tags", {})

    segments = get_segments()
    tags = get_predefined_tags()

    # Live segments from DB with member counts
    from services.database import get_db
    db = get_db()
    try:
        active_segments = get_all_active_segments(db)
        live_seg_items = ""
        for s in active_segments:
            count = count_segment_members(db, s)
            color = segment_color(s.id)
            live_seg_items += (
                f'<div style="margin-bottom:4px; display:flex; align-items:center; gap:6px;">'
                f'<span class="legend-pill" style="background:{color}22; color:{color}; border:1px solid {color}55;">{s.name}</span>'
                f'<span style="color:#64748b; font-size:10px;">· {count} contacts</span>'
                f'</div>'
            )
    finally:
        db.close()

    # Customer Types column — pills + descriptions from schema.yml
    ct_items = ""
    for seg in segments:
        color = seg.get("color", "#64748b")
        label = seg.get("label", seg.get("id", ""))
        desc = get_segment_description(seg.get("id", ""))
        ct_items += (
            f'<div style="margin-bottom:6px;">'
            f'<span class="legend-pill" style="background:{color}22; color:{color}; border:1px solid {color}55;">{label}</span>'
            f'<div style="margin-top:2px; color:#94a3b8;">{desc}</div>'
            f'</div>'
        )

    tag_pills = " ".join(f'<span class="legend-tag">{t}</span>' for t in tags)

    summary = legend_cfg.get("summary", "Legend")
    ct_heading = ct_cfg.get("heading", "Customer Types")
    ct_intro = ct_cfg.get("intro", "")
    seg_heading = seg_cfg.get("heading", "Segments")
    seg_intro = seg_cfg.get("intro", "")
    seg_note = seg_cfg.get("note", "")
    tag_heading = tag_cfg.get("heading", "Tags")
    tag_intro = tag_cfg.get("intro", "")

    return f'''
<div class="contacts-legend contacts-legend-modal">
<div class="hf-modal-title">{summary}</div>
<div class="legend-body">
  <div class="legend-col">
    <h4>{ct_heading}</h4>
    <p>{ct_intro}</p>
    {ct_items}
  </div>
  <div class="legend-col">
    <h4>{seg_heading}</h4>
    <p>{seg_intro}</p>
    <div style="margin-top:8px;">{live_seg_items}</div>
  </div>
  <div class="legend-col">
    <h4>{tag_heading}</h4>
    <p>{tag_intro}</p>
    <div>{tag_pills}</div>
  </div>
</div>
</div>
'''


def _build_pagination_label(page: int, total_pages: int, total: int) -> str:
    cfg = _load_page_config()
    page_size = cfg.get("table", {}).get("page_size", 50)
    start = min(page * page_size + 1, total) if total else 0
    end = min((page + 1) * page_size, total)
    template = cfg.get("pagination", {}).get("info_template", "{start}–{end} of {total}")
    text = template.format(
        start=start, end=end, total=total,
        page=page + 1, total_pages=total_pages,
    )
    return f'<div style="color:#94a3b8; font-size:11px; text-align:right; line-height:28px;">{text}</div>'


def build(ctx) -> dict:
    cfg = _load_page_config()

    # Load tag choices from the DB at build time — safe because the contacts
    # page is rebuilt on each navigation.
    from services.database import get_db as _get_db_for_tags
    _db_tags = _get_db_for_tags()
    try:
        _all_tags = get_all_tags_from_contacts(_db_tags)
    finally:
        _db_tags.close()

    with gr.Row():
        # -- Left: Filters + KPIs --
        with gr.Column(scale=1, min_width=200, elem_classes=["page-left-col"]):
            segment_filter = gr.Dropdown(
                label="Segment", choices=get_segment_choices(), value="All", interactive=True,
            )
            lifecycle_filter = gr.Dropdown(
                label="Lifecycle", choices=get_lifecycle_choices(), value="All", interactive=True,
            )
            country_filter = gr.Dropdown(
                label="Country", choices=["All"] + get_country_options(), value="All", interactive=True,
            )
            channel_filter = gr.Dropdown(
                label="Channel", choices=["All", "Email Only", "WhatsApp Only", "Both"], value="All", interactive=True,
            )
            tag_filter = gr.Dropdown(
                label="Tags", choices=_all_tags, value=[],
                multiselect=True, interactive=True,
                info="Empty = any. Pick tags to narrow.",
            )
            gr.HTML('<div style="height:1px; background:rgba(255,255,255,.06); margin:8px 0;"></div>')
            left_kpis = gr.HTML(value="")

        # -- Right: Top bar + table + compact footer (legend + pagination) --
        top_bar_cfg = cfg.get("top_bar", {})
        pag_cfg = cfg.get("pagination", {})
        with gr.Column(scale=4, elem_classes=["contacts-right-col"]):
            with gr.Row(elem_classes=["contacts-top-bar"]):
                search = gr.Textbox(
                    placeholder=cfg.get("search", {}).get("placeholder", "Search..."),
                    label="", container=False, scale=int(top_bar_cfg.get("search_scale", 2)),
                )
                add_btn = gr.Button(
                    top_bar_cfg.get("add_label", "+ Add Contact"),
                    variant="primary", size=top_bar_cfg.get("button_size", "md"), scale=1,
                )
                import_btn = gr.Button(
                    top_bar_cfg.get("import_label", "Import"),
                    size=top_bar_cfg.get("button_size", "md"), scale=1,
                )

            with gr.Column(elem_classes=["contacts-table-host"]):
                table_html = gr.HTML(value="")

            # Compact footer: legend button on the left, pagination on the right
            with gr.Row(elem_classes=["contacts-footer-bar"]):
                legend_btn = gr.Button(
                    top_bar_cfg.get("legend_label", "ℹ Legend"),
                    size="sm", scale=0, min_width=90,
                )
                pag_label = gr.HTML(value="")
                prev_btn = gr.Button(pag_cfg.get("prev_label", "‹"), size="sm", scale=0, min_width=40)
                page_num = gr.Number(
                    value=1, label="", show_label=False,
                    precision=0, minimum=1, scale=0, min_width=55, interactive=True,
                )
                next_btn = gr.Button(pag_cfg.get("next_label", "›"), size="sm", scale=0, min_width=40)

    # Hidden state: 0-indexed page, total pages
    page_state = gr.State(0)
    total_pages_state = gr.State(1)

    # -- Add Contact modal overlay --
    with gr.Column(visible=True, elem_classes=["hf-modal", "hf-modal-closed"]) as add_panel:
        add_cfg = cfg.get("add_contact", {})
        gr.HTML(f'<div class="hf-modal-title">{add_cfg.get("title", "Add Contact")}</div>')
        with gr.Row():
            new_first = gr.Textbox(label="First Name *", placeholder="First name")
            new_last = gr.Textbox(label="Last Name", placeholder="Last name")
        with gr.Row():
            new_phone = gr.Textbox(label="Phone * (+91)", placeholder="10 digit mobile")
            new_email = gr.Textbox(label="Email", placeholder="name@company.com")
        with gr.Row():
            new_company = gr.Textbox(label="Company", placeholder="Company name")
            new_country = gr.Dropdown(label="Country", choices=get_country_options(), value="India")
        with gr.Row():
            seg_choices = [s["label"] for s in get_segments()]
            new_segment = gr.Dropdown(label="Segment", choices=seg_choices, value=seg_choices[0] if seg_choices else None)
            lc_choices = [s["label"] for s in get_lifecycle_stages()]
            new_lifecycle = gr.Dropdown(label="Lifecycle", choices=lc_choices, value="New Lead")
        new_tags = gr.Textbox(label="Tags", placeholder="wool, premium, carpet (comma separated)")
        with gr.Row():
            cancel_btn = gr.Button("Cancel", size="sm")
            save_btn = gr.Button("Save Contact", variant="primary", size="sm")
        save_result = gr.HTML(value="")

    # -- Import modal overlay --
    with gr.Column(visible=True, elem_classes=["hf-modal", "hf-modal-closed"]) as import_panel:
        import_title = cfg.get("add_contact", {}).get("import_modal_title", "Import Contacts")
        gr.HTML(f'<div class="hf-modal-title">{import_title}</div>')
        gr.HTML(f'<div style="color:#94a3b8; font-size:11px; margin-bottom:8px;">{cfg.get("add_contact", {}).get("import_instructions", "")}</div>')
        import_file = gr.File(label="Select CSV/Excel", file_types=[".csv", ".xlsx"])
        import_result = gr.HTML(value="")
        with gr.Row():
            import_back = gr.Button("Close", size="sm")
            download_btn = gr.Button("Download All CSV", size="sm")
        download_file = gr.File(visible=False)

    # -- Legend modal overlay --
    with gr.Column(visible=True, elem_classes=["hf-modal", "hf-modal-wide", "hf-modal-closed"]) as legend_panel:
        gr.HTML(value=_build_legend())
        legend_close = gr.Button("Close", size="sm")

    # -- Hybrid edit bridge --
    # The row Edit button writes contact_id into `edit_contact_id_box` via
    # native setter + 'input' event (so Svelte's store updates), then clicks
    # `edit_trigger_btn`. The trigger fires `_open_edit_drawer` which reads
    # the textbox value AND copies it into `edit_cid_state` (a Python-only
    # gr.State). All downstream events (Save, Add Note) read from the State,
    # not the textbox — that sidesteps the store-sync bug that was losing
    # the cid between drawer-open and save in the previous implementation.
    edit_contact_id_box = gr.Textbox(
        value="", show_label=False, container=False,
        elem_id="hf-edit-contact-id",
        elem_classes=["hf-bridge-hidden"],
    )
    edit_cid_state = gr.State("")
    edit_trigger_btn = gr.Button(
        "trigger", elem_id="hf-edit-trigger-btn",
        elem_classes=["hf-bridge-hidden"],
    )

    # -- Edit drawer modal (Profile / Tags / Notes tabs) --
    # visible=True at build time so Svelte components mount cleanly;
    # the "hf-modal-closed" CSS class hides it until the user opens it.
    # Toggling this class via Python (gr.update(elem_classes=...)) avoids
    # the visible=False → True mount race that stranded processing spinners.
    with gr.Column(visible=True, elem_classes=["hf-modal", "hf-modal-drawer", "hf-modal-closed"]) as edit_panel:
        edit_title_html = gr.HTML(value='<div class="hf-modal-title">Edit Contact</div>')
        with gr.Tabs():
            with gr.Tab("Profile"):
                with gr.Row():
                    edit_first = gr.Textbox(label="First Name *")
                    edit_last = gr.Textbox(label="Last Name")
                with gr.Row():
                    edit_phone = gr.Textbox(label="Phone")
                    edit_email = gr.Textbox(label="Email")
                with gr.Row():
                    edit_company = gr.Textbox(label="Company")
                    edit_country_dd = gr.Dropdown(
                        label="Country",
                        choices=get_country_options(),
                        interactive=True,
                    )
                with gr.Row():
                    edit_lifecycle_dd = gr.Dropdown(
                        label="Lifecycle",
                        choices=[s["label"] for s in get_lifecycle_stages()],
                        interactive=True,
                    )
                    edit_consent_dd = gr.Dropdown(
                        label="Consent",
                        choices=["pending", "opted_in", "opted_out"],
                        interactive=True,
                    )
            with gr.Tab("Tags"):
                edit_tags_ms = gr.Dropdown(
                    label="Tags",
                    choices=_all_tags,
                    value=[],
                    multiselect=True,
                    allow_custom_value=True,
                    interactive=True,
                    info="Type a new tag + Enter to create it. Existing tags autocomplete.",
                )
                edit_matched_segments = gr.HTML(
                    value='<div style="color:#94a3b8; font-size:11px;">Matched segments will appear here.</div>'
                )
            with gr.Tab("Notes"):
                edit_notes_html = gr.HTML(
                    value='<div style="color:#64748b; font-size:11px;">Loading notes...</div>'
                )
                new_note_input = gr.Textbox(
                    label="Add note",
                    lines=3,
                    placeholder="Append a timestamped note to this contact's thread...",
                )
                with gr.Row():
                    add_note_btn = gr.Button("+ Add note", size="sm", variant="primary")
                # Legacy single-field notes (read-only, shown for back-compat)
                edit_notes = gr.Textbox(
                    label="Legacy note field (contacts.notes)",
                    lines=3,
                    interactive=False,
                    info="Read-only. New notes go into the thread above.",
                )
            with gr.Tab("Activity"):
                edit_activity_html = gr.HTML(
                    value='<div style="color:#64748b; font-size:11px;">Loading activity...</div>'
                )
        with gr.Row():
            edit_cancel_btn = gr.Button("Cancel", size="sm")
            edit_save_btn = gr.Button("Save changes", variant="primary", size="sm")
        edit_result = gr.HTML(value="")

    # -- Modal toggles via CSS class (avoids Svelte mount race on first open) --
    _MODAL_OPEN = {"add": ["hf-modal"],
                    "import": ["hf-modal"],
                    "legend": ["hf-modal", "hf-modal-wide"],
                    "edit": ["hf-modal", "hf-modal-drawer"]}
    _MODAL_CLOSED = {k: v + ["hf-modal-closed"] for k, v in _MODAL_OPEN.items()}

    add_btn.click(fn=lambda: gr.update(elem_classes=_MODAL_OPEN["add"]), outputs=[add_panel])
    cancel_btn.click(fn=lambda: gr.update(elem_classes=_MODAL_CLOSED["add"]), outputs=[add_panel])
    import_btn.click(fn=lambda: gr.update(elem_classes=_MODAL_OPEN["import"]), outputs=[import_panel])
    import_back.click(fn=lambda: gr.update(elem_classes=_MODAL_CLOSED["import"]), outputs=[import_panel])
    legend_btn.click(fn=lambda: gr.update(elem_classes=_MODAL_OPEN["legend"]), outputs=[legend_panel])
    legend_close.click(fn=lambda: gr.update(elem_classes=_MODAL_CLOSED["legend"]), outputs=[legend_panel])
    edit_cancel_btn.click(fn=lambda: gr.update(elem_classes=_MODAL_CLOSED["edit"]), outputs=[edit_panel])

    # -- Open edit drawer (called by JS bridge via hidden trigger button) --
    def _open_edit_drawer(contact_id):
        import time, logging
        _log = logging.getLogger("drawer")
        t_start = time.time()
        from services.database import get_db
        from services.models import Contact, ContactNote
        if not contact_id:
            return ("", gr.update(elem_classes=_MODAL_CLOSED["edit"])) + (gr.update(),) * 15
        db = get_db()
        try:
            t0 = time.time()
            c = db.query(Contact).filter(Contact.id == contact_id).first()
            _log.warning("drawer load contact: %.2fs", time.time() - t0)
            if not c:
                return ("", gr.update(elem_classes=_MODAL_CLOSED["edit"])) + (gr.update(),) * 15

            t0 = time.time()
            all_segs = get_all_active_segments(db)
            seg_ids = segments_for_contact(c, all_segs)
            _log.warning("drawer segments: %.2fs (%d matched)", time.time() - t0, len(seg_ids))
            if seg_ids:
                by_id = {s.id: s for s in all_segs}
                pills = "".join(
                    f'<span style="background:{segment_color(sid)}22; color:{segment_color(sid)}; '
                    f'border:1px solid {segment_color(sid)}55; padding:2px 8px; border-radius:10px; '
                    f'font-size:10px; font-weight:600; margin:2px 4px 2px 0; display:inline-block;">'
                    f'{by_id[sid].name}</span>'
                    for sid in seg_ids if sid in by_id
                )
                matched_html = (
                    f'<div style="margin-top:10px;">'
                    f'<div style="color:#94a3b8; font-size:10px; margin-bottom:4px;">'
                    f'Matched segments ({len(seg_ids)}) — read-only, rules decide membership:</div>'
                    f'{pills}</div>'
                )
            else:
                matched_html = (
                    '<div style="margin-top:10px; color:#64748b; font-size:11px; font-style:italic;">'
                    'Not matched to any segment yet.</div>'
                )

            # Threaded notes + legacy note
            t0 = time.time()
            thread = (
                db.query(ContactNote)
                .filter(ContactNote.contact_id == c.id)
                .order_by(ContactNote.created_at.desc())
                .all()
            )
            notes_html = render_notes_html(thread, legacy_note=c.notes or "")
            _log.warning("drawer notes: %.2fs", time.time() - t0)

            # Activity timeline
            t0 = time.time()
            activity = get_interactions(db, c.id, limit=50)
            activity_html = render_activity_html(activity)
            _log.warning("drawer activity: %.2fs", time.time() - t0)
            _log.warning("drawer TOTAL: %.2fs", time.time() - t_start)

            lc_label = (c.lifecycle or "new_lead").replace("_", " ").title()
            title = f'<div class="hf-modal-title">Edit · {(c.first_name or "") + " " + (c.last_name or "")}</div>'

            email_val = c.email if c.email and "placeholder" not in c.email else ""
            return (
                contact_id,                                             # edit_cid_state
                gr.update(elem_classes=_MODAL_OPEN["edit"]),            # edit_panel
                title,                                                  # edit_title_html
                gr.update(value=c.first_name or ""),                    # edit_first
                gr.update(value=c.last_name or ""),                     # edit_last
                gr.update(value=c.phone or ""),                         # edit_phone
                gr.update(value=email_val),                             # edit_email
                gr.update(value=c.company or ""),                       # edit_company
                gr.update(value=c.country or "India"),                  # edit_country_dd
                gr.update(value=lc_label),                              # edit_lifecycle_dd
                gr.update(value=c.consent_status or "pending"),         # edit_consent_dd
                gr.update(value=c.tags or []),                          # edit_tags_ms
                matched_html,                                           # edit_matched_segments
                notes_html,                                             # edit_notes_html
                gr.update(value=""),                                    # new_note_input
                gr.update(value=c.notes or ""),                         # edit_notes (legacy)
                activity_html,                                          # edit_activity_html
            )
        finally:
            db.close()

    _edit_drawer_outputs = [
        edit_cid_state, edit_panel, edit_title_html,
        edit_first, edit_last, edit_phone, edit_email, edit_company,
        edit_country_dd, edit_lifecycle_dd, edit_consent_dd,
        edit_tags_ms, edit_matched_segments,
        edit_notes_html, new_note_input, edit_notes, edit_activity_html,
    ]
    edit_trigger_btn.click(
        fn=_open_edit_drawer,
        inputs=[edit_contact_id_box],
        outputs=_edit_drawer_outputs,
    )

    # -- Add note (threaded) --
    def _add_note(cid, body):
        from services.database import get_db
        from services.models import ContactNote, Contact
        body = (body or "").strip()
        if not cid or not body:
            return (gr.update(), gr.update(), gr.update())
        db = get_db()
        try:
            note = ContactNote(contact_id=cid, body=body, author="user")
            db.add(note)
            db.commit()
            log_interaction(
                db, contact_id=cid, kind="note_added",
                summary=body[:120], actor="user",
            )
            # Re-read thread + legacy + activity to refresh the tab
            thread = (
                db.query(ContactNote)
                .filter(ContactNote.contact_id == cid)
                .order_by(ContactNote.created_at.desc())
                .all()
            )
            c = db.query(Contact).filter(Contact.id == cid).first()
            notes_html = render_notes_html(thread, legacy_note=(c.notes or "") if c else "")
            activity_html = render_activity_html(get_interactions(db, cid, limit=50))
            return (notes_html, "", activity_html)
        finally:
            db.close()

    add_note_btn.click(
        fn=_add_note,
        inputs=[edit_cid_state, new_note_input],
        outputs=[edit_notes_html, new_note_input, edit_activity_html],
    )

    # -- Apply filters / render table --
    def _apply(search_val, seg, lc, country, channel, tags, page):
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            total = db.query(Contact).count()
            opted_in = db.query(Contact).filter(Contact.consent_status == "opted_in").count()
            pending = db.query(Contact).filter(Contact.consent_status == "pending").count()
            wa_ready = db.query(Contact).filter(Contact.wa_id.isnot(None)).count()

            kpis = render_kpi_row([
                (str(total), "Total", "", "#e7eaf3"),
                (str(opted_in), "Opted In", "", "#22c55e"),
                (str(pending), "Pending", "", "#f59e0b"),
                (str(wa_ready), "WA Ready", "", "#6366f1"),
            ])
            table, row_total, total_pages, effective_page = _build_table(
                db, segment=seg, lifecycle=lc, country=country, channel=channel,
                tags=tags, search=search_val, page=int(page or 0),
            )
            label = _build_pagination_label(effective_page, total_pages, row_total)
            return kpis, table, label, effective_page, total_pages, effective_page + 1
        finally:
            db.close()

    apply_inputs = [search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter, page_state]
    apply_outputs = [left_kpis, table_html, pag_label, page_state, total_pages_state, page_num]

    # Filter/search changes reset to page 0
    def _apply_reset(search_val, seg, lc, country, channel, tags):
        return _apply(search_val, seg, lc, country, channel, tags, 0)

    for component in [search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter]:
        component.change(
            fn=_apply_reset,
            inputs=[search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter],
            outputs=apply_outputs,
        )

    # Pagination button handlers
    def _go_prev(search_val, seg, lc, country, channel, tags, page, total_pages):
        new_page = max(0, int(page or 0) - 1)
        return _apply(search_val, seg, lc, country, channel, tags, new_page)

    def _go_next(search_val, seg, lc, country, channel, tags, page, total_pages):
        tp = int(total_pages or 1)
        new_page = min(tp - 1, int(page or 0) + 1)
        return _apply(search_val, seg, lc, country, channel, tags, new_page)

    def _go_num(search_val, seg, lc, country, channel, tags, total_pages, page_input):
        tp = int(total_pages or 1)
        new_page = max(0, min(tp - 1, int(page_input or 1) - 1))
        return _apply(search_val, seg, lc, country, channel, tags, new_page)

    _pag_inputs = [search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter]

    prev_btn.click(
        fn=_go_prev,
        inputs=_pag_inputs + [page_state, total_pages_state],
        outputs=apply_outputs,
    )
    next_btn.click(
        fn=_go_next,
        inputs=_pag_inputs + [page_state, total_pages_state],
        outputs=apply_outputs,
    )
    page_num.submit(
        fn=_go_num,
        inputs=_pag_inputs + [total_pages_state, page_num],
        outputs=apply_outputs,
    )

    # -- Save contact --
    def _save(first, last, phone, email, company, country, segment_label, lifecycle_label, tags_str,
              search_val, seg_f, lc_f, country_f, channel_f, tag_f):
        if not first:
            return f'<div style="color:#ef4444; font-size:11px;">First name is required</div>', *([gr.update()] * 7)
        if not phone:
            return f'<div style="color:#ef4444; font-size:11px;">Phone is required</div>', *([gr.update()] * 7)

        clean_phone = "".join(c for c in phone if c.isdigit())
        if len(clean_phone) == 10:
            wa_id = f"91{clean_phone}"
        elif len(clean_phone) > 10:
            wa_id = clean_phone
        else:
            return f'<div style="color:#ef4444; font-size:11px;">Phone must be 10 digits</div>', *([gr.update()] * 7)

        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            if email and db.query(Contact).filter(Contact.email == email).first():
                return f'<div style="color:#ef4444; font-size:11px;">Email already exists</div>', *([gr.update()] * 7)

            seg_id = get_segment_id_by_label(segment_label) or "other"
            lc_id = get_lifecycle_id_by_label(lifecycle_label) or "new_lead"
            tags = [t.strip() for t in (tags_str or "").split(",") if t.strip()]

            new_id = str(uuid.uuid4())[:8]
            db.add(Contact(
                id=new_id,
                email=email or f"wa_{wa_id}@placeholder.local",
                first_name=first, last_name=last or "", company=company or "",
                phone=clean_phone, country=country or "India",
                customer_type=seg_id, lifecycle=lc_id, tags=tags,
                wa_id=wa_id, consent_status="pending",
            ))
            db.commit()
            log_interaction(
                db, contact_id=new_id, kind="imported",
                summary=f"Added via Add Contact modal · {first} {last or ''}".strip(),
                actor="user",
            )
        finally:
            db.close()

        kpis, table, label, new_page, tot_pages, num = _apply(search_val, seg_f, lc_f, country_f, channel_f, tag_f, 0)
        msg = f'<div style="color:#22c55e; font-size:11px;">Contact {first} {last} added</div>'
        return msg, kpis, table, label, new_page, tot_pages, num, gr.update(elem_classes=_MODAL_CLOSED["add"])

    save_btn.click(
        fn=_save,
        inputs=[new_first, new_last, new_phone, new_email, new_company, new_country, new_segment, new_lifecycle, new_tags,
                search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter],
        outputs=[save_result, left_kpis, table_html, pag_label, page_state, total_pages_state, page_num, add_panel],
    )

    # -- Save edited contact (inline drawer) --
    def _save_edit(cid, first, last, phone, email, company, country, lc_label, consent,
                   tags_list, notes,
                   search_val, seg_f, lc_f, country_f, channel_f, tag_f):
        from services.database import get_db
        from services.models import Contact
        if not cid:
            return (
                '<div style="color:#ef4444; font-size:11px;">No contact id</div>',
                gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
            )
        db = get_db()
        try:
            c = db.query(Contact).filter(Contact.id == cid).first()
            if not c:
                return (
                    '<div style="color:#ef4444; font-size:11px;">Contact not found</div>',
                    gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                )

            # Enforce email uniqueness (only if changing to a new non-empty value)
            if email and email != c.email:
                other = db.query(Contact).filter(Contact.email == email, Contact.id != cid).first()
                if other:
                    return (
                        '<div style="color:#ef4444; font-size:11px;">Email already in use</div>',
                        gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
                    )

            # Capture before-state for diff summary
            before = {
                "first_name": c.first_name, "last_name": c.last_name,
                "phone": c.phone, "email": c.email, "company": c.company,
                "country": c.country, "lifecycle": c.lifecycle,
                "consent_status": c.consent_status, "tags": list(c.tags or []),
                "notes": c.notes,
            }

            c.first_name = (first or "").strip()
            c.last_name = (last or "").strip()
            c.phone = (phone or "").strip()
            # Recompute wa_id from phone for India numbers
            clean_phone = "".join(ch for ch in c.phone if ch.isdigit())
            if len(clean_phone) == 10:
                c.wa_id = f"91{clean_phone}"
            elif len(clean_phone) > 10:
                c.wa_id = clean_phone.lstrip("+")
            c.email = email.strip() if email and email.strip() else c.email
            c.company = (company or "").strip()
            c.country = (country or "India").strip()
            c.lifecycle = get_lifecycle_id_by_label(lc_label) or c.lifecycle or "new_lead"
            c.consent_status = (consent or "pending").strip()
            c.tags = [t.strip() for t in (tags_list or []) if t and t.strip()]
            c.notes = (notes or "").strip()

            db.commit()

            # Audit log: one row per save with a human-readable diff summary.
            after = {
                "first_name": c.first_name, "last_name": c.last_name,
                "phone": c.phone, "email": c.email, "company": c.company,
                "country": c.country, "lifecycle": c.lifecycle,
                "consent_status": c.consent_status, "tags": list(c.tags or []),
                "notes": c.notes,
            }
            diff_summary = summarize_diff(before, after)
            if diff_summary != "no-op save":
                log_interaction(
                    db, contact_id=cid, kind="manual_edit",
                    summary=f"Changed: {diff_summary}",
                    actor="user",
                )
        finally:
            db.close()

        kpis, table, label, new_page, tot_pages, num = _apply(
            search_val, seg_f, lc_f, country_f, channel_f, tag_f, 0,
        )
        msg = f'<div style="color:#22c55e; font-size:11px;">Saved · table refreshed</div>'
        return msg, kpis, table, label, new_page, tot_pages, num, gr.update(elem_classes=_MODAL_CLOSED["edit"])

    edit_save_btn.click(
        fn=_save_edit,
        inputs=[
            edit_cid_state, edit_first, edit_last, edit_phone, edit_email, edit_company,
            edit_country_dd, edit_lifecycle_dd, edit_consent_dd, edit_tags_ms, edit_notes,
            search, segment_filter, lifecycle_filter, country_filter, channel_filter, tag_filter,
        ],
        outputs=[
            edit_result, left_kpis, table_html, pag_label, page_state, total_pages_state, page_num, edit_panel,
        ],
    )

    # -- Import CSV --
    def _import(file):
        if not file:
            return ""
        from services.database import get_db
        from services.models import Contact
        try:
            df = pd.read_csv(file.name, dtype=str).fillna("") if file.name.endswith(".csv") else pd.read_excel(file.name, dtype=str).fillna("")
        except Exception as e:
            return f'<div style="color:#ef4444; font-size:11px;">Error: {e}</div>'

        db = get_db()
        try:
            imported, skipped = 0, 0
            for _, row in df.iterrows():
                email = row.get("email", row.get("Email", "")).strip()
                if not email or "@" not in email or db.query(Contact).filter(Contact.email == email).first():
                    skipped += 1
                    continue
                phone = row.get("phone", "").strip()
                clean_phone = "".join(c for c in phone if c.isdigit())
                wa_id = f"91{clean_phone}" if len(clean_phone) == 10 else (clean_phone if len(clean_phone) > 10 else None)
                db.add(Contact(
                    id=str(uuid.uuid4())[:8], email=email,
                    first_name=row.get("first_name", row.get("name", "")),
                    last_name=row.get("last_name", ""),
                    company=row.get("company", ""),
                    phone=phone, country=row.get("country", ""),
                    wa_id=wa_id, consent_status="pending", lifecycle="new_lead",
                ))
                imported += 1
            db.commit()
            return f'<div style="color:#22c55e; font-size:11px;">Imported {imported}, skipped {skipped}</div>'
        finally:
            db.close()

    import_file.change(fn=_import, inputs=[import_file], outputs=[import_result])

    # -- Download CSV --
    def _download():
        from services.database import get_db
        from services.models import Contact
        db = get_db()
        try:
            # Plan D Phase 1.2: select only the 9 columns the CSV uses,
            # not the full 38-col Contact row. Was pulling ~3-5 MB per
            # click (notes, address, response_notes, tags JSON, etc.
            # all came over the wire and were discarded).
            rows = db.query(
                Contact.email, Contact.first_name, Contact.last_name,
                Contact.company, Contact.phone, Contact.country,
                Contact.lifecycle, Contact.consent_status, Contact.wa_id,
            ).all()
            data = [
                {
                    "email": r.email, "first_name": r.first_name,
                    "last_name": r.last_name, "company": r.company,
                    "phone": r.phone, "country": r.country,
                    "lifecycle": r.lifecycle, "consent_status": r.consent_status,
                    "wa_id": r.wa_id or "",
                }
                for r in rows
            ]
            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
            pd.DataFrame(data).to_csv(tmp.name, index=False)
            return gr.update(value=tmp.name, visible=True)
        finally:
            db.close()

    download_btn.click(fn=_download, outputs=[download_file])

    def _refresh():
        return _apply("", "All", "All", "All", "All", [], 0)

    return {"update_fn": _refresh, "outputs": apply_outputs}
