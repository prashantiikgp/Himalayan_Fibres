# WhatsApp Inbox Page Rebuild — W02 April 2026

## Context

The WhatsApp Inbox page (`hf_dashboard/pages/wa_inbox.py`) has four UX
problems that showed up during daily use this week:

1. **The attachment drop-zone eats half of Panel 2 (the chat column).**
   The `gr.File` component with label "Drop File Here / Click to Upload"
   has no height constraint in CSS, so Gradio renders it at ~120px and
   pushes the text input + Send button far below the message bubbles.
   The chat area looks ridiculous compared to any real messaging UI.

2. **Templates have no variable-entry UI.** Selecting
   `order_confirmation` shows the raw body with `{{customer_name}}`,
   `{{order_id}}`, etc. but there is no way to fill them in before
   sending. `WhatsAppSender.send_template()` already accepts a
   `variables` kwarg (`hf_dashboard/services/wa_sender.py:94-177`) —
   it's just not wired to any UI.

3. **The three columns don't align.** Panel 1 starts taller than
   Panel 2 (because of the upload zone pushing its content down),
   Panel 3 ends shorter than both. The layout looks ragged, and long
   conversation lists push the "Start New Conversation" section off
   the bottom of Panel 1 entirely.

4. **The Refresh button is buried at the bottom of Panel 3** next to
   template controls, even though its job is to reload Panel 1's
   conversation list. Users don't discover it.

Goal: rebuild Panels 1–3 so the layout is stable, the attachment
flow is compact, and templates can be filled in and sent end-to-end
from a category → template → variables → preview → send flow.

## Scope (what's changing)

| # | Change | Files |
|---|---|---|
| 1 | Column alignment + internal scroll regions | `hf_dashboard/shared/theme_css.py`, `hf_dashboard/pages/wa_inbox.py` |
| 2 | Move Refresh button to Panel 1 header + caption | `hf_dashboard/pages/wa_inbox.py`, `hf_dashboard/config/pages/wa_inbox.yml` |
| 3 | Attachment popover (📎 icon next to Send) | `hf_dashboard/pages/wa_inbox.py`, `hf_dashboard/shared/theme_css.py` |
| 4 | Panel 3 rebuild: compact activity + category filter + template + variables + preview | `hf_dashboard/pages/wa_inbox.py`, `hf_dashboard/components/tools_panel.py`, `hf_dashboard/shared/theme_css.py` |

Nothing outside these files needs to change. No schema migrations.
No new YAML configs (existing `templates.yml` already has `category`
and `variables` on every `TemplateDefinition`).

## Pre-existing debt (not addressed in this PR)

- `wa_inbox.py:_cfg()` uses inline `yaml.safe_load(...).get(...)` —
  technically violates the CLAUDE.md "every engine must load YAML
  through Pydantic" rule. We add one new YAML key (`refresh_caption`)
  through the same path. Cleaning this up belongs in a separate
  refactor; flagged here so a future reader doesn't think we're
  knowingly drifting.

---

## Change 1 — Column alignment + scroll regions

### Root cause of misalignment

`hf_dashboard/shared/theme_css.py:467-505` sets `.chat-panel` as a
flex column with `.chat-messages-slot { flex: 1 1 auto }` and
`.chat-send-row { margin-top: auto }` to pin the send row to the
bottom. That works for Panel 2. But:
- `.chat-media-input` (the `gr.File` drop zone) has **no CSS rule**,
  so Gradio renders it at its default ~120px height, inserted
  between `.chat-messages-slot` and `.chat-send-row`. This is what
  squeezes the chat bubbles and makes Panel 2 look taller than it
  should.
- `.conv-list-panel` uses `overflow-y: auto` on the whole panel
  (from `_build_panel_css()` at `theme_css.py:538-566`), so the
  entire column scrolls as one — Active Chats and Start New share
  one scroll context, and the search boxes scroll away with the list.
- `.tools-panel` has no internal flex layout, so Refresh can't be
  pinned anywhere and the preview box grows unbounded.

### Approach

**CSS cascade fix first:** `_build_panel_css()` at `theme_css.py:538-566`
emits `overflow-y: auto !important` on `.conv-list-panel` and
`.tools-panel` *after* `_STATIC_CSS`, so any overflow override added
to `_STATIC_CSS` would lose the cascade. We fix this by **editing
`_build_panel_css()` itself to stop emitting `overflow-y: auto` on
those two selectors** — we're replacing that behavior wholesale, so
the line goes away. The `.chat-panel` rule there is fine and stays.

Then add these rules to `_STATIC_CSS` in `theme_css.py` (inside the
existing `.conv-list-panel` / `.chat-panel` / `.tools-panel` block
that starts around line 467):

```css
/* Change 1 — column alignment */

/* Hide the inline gr.File — it only lives in the DOM so the upload
   popover can read its value. The label + drop zone are invisible.  */
.chat-panel .chat-media-input {
    display: none !important;
}

/* Panel 1 — two scroll regions sharing the panel, header pinned */
.conv-list-panel {
    overflow: hidden !important;  /* override panel default */
}
.conv-list-panel .conv-header-row {
    flex: 0 0 auto !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
}
.conv-list-panel .conv-refresh-caption {
    flex: 0 0 auto !important;
    font-size: 9px !important;
    color: #64748b !important;
    font-style: italic !important;
    margin: 2px 2px 8px 2px !important;
    line-height: 1.3 !important;
}
.conv-list-panel .wa-active-scroll,
.conv-list-panel .wa-new-scroll {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.04) !important;
    border-radius: 6px !important;
    padding: 4px !important;
}
.conv-list-panel .wa-active-scroll { flex-grow: 3 !important; }  /* 60% */
.conv-list-panel .wa-new-scroll    { flex-grow: 2 !important; }  /* 40% */

/* Panel 3 — flex column with fixed-proportion activity + flex preview */
.tools-panel {
    overflow: hidden !important;
}
.tools-panel .tp-activity-box {
    flex: 0 0 25% !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 6px !important;
    padding: 6px 8px !important;
    margin-bottom: 8px !important;
}
.tools-panel .tp-category,
.tools-panel .tp-template,
.tools-panel .tp-send-btn { flex: 0 0 auto !important; }
.tools-panel .tp-vars-box {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    padding: 4px 0 !important;
}
.tools-panel .tp-preview-box {
    flex: 0 0 auto !important;
    max-height: 30% !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-left: 2px solid rgba(34,197,94,.4) !important;
    background: rgba(34,197,94,.04) !important;
    border-radius: 6px !important;
    padding: 8px 10px !important;
    margin: 8px 0 !important;
}
```

### Wiring in `wa_inbox.py`

Panel 1 structure (top-to-bottom, all flex children of `.conv-list-panel`):

```
gr.Row(elem_classes=["conv-header-row"])    ← flex 0 0 auto
  gr.HTML("ACTIVE CHATS")                   ← title
  gr.Button("🔄", scale=0, min_width=40)    ← refresh icon
gr.HTML(refresh_caption)                    ← flex 0 0 auto, italic muted
gr.Textbox(search_box)                      ← flex 0 0 auto, PINNED
gr.Column(elem_classes=["wa-active-scroll"])  ← flex 1 1 auto, SCROLLS
  gr.Radio(conversation_radio)
gr.HTML('<div class="conv-section-divider">') ← flex 0 0 auto
gr.HTML("Start New Conversation")           ← flex 0 0 auto
gr.Textbox(new_conv_search)                 ← flex 0 0 auto, PINNED
gr.Column(elem_classes=["wa-new-scroll"])   ← flex 1 1 auto, SCROLLS
  gr.Radio(new_conv_radio)
gr.HTML(empty_hint)                         ← flex 0 0 auto
```

Critical: the two search boxes sit **outside** the scroll columns so
they stay pinned when the radio lists scroll. The two scroll columns
share remaining vertical space via `flex-grow: 3` (active) and
`flex-grow: 2` (new) — see CSS rules above.

Panel 3 structure is rebuilt entirely — see Change 4 below.

---

## Change 2 — Refresh on Panel 1 header

### Current

`refresh_btn = gr.Button("🔄 Refresh", size="sm", variant="secondary")`
lives at the bottom of Panel 3 (`wa_inbox.py:376`). Its `.click`
handler at line 695 wires it to `_do_refresh` which updates 10
outputs.

### Change

- Move the button to the top of Panel 1, inside a `gr.Row` that also
  contains the `gr.HTML` for the "ACTIVE CHATS" title.
- Render as a compact icon button: `gr.Button("🔄", size="sm",
  variant="secondary", scale=0, min_width=40)`.
- Add a `gr.HTML` caption directly below the header row with class
  `conv-refresh-caption`: **"Click Refresh to see updated conversation."**
  Source the text from `wa_inbox.yml` under
  `page.column_1.refresh_caption` so it stays config-driven per the
  engine rule in CLAUDE.md.
- **Rewrite `_do_refresh` outputs** — the current output list
  references `tpl_dropdown` and `tpl_preview` which Change 4 removes.
  New output list:
  ```
  [conversation_radio, new_conv_radio, new_conv_search,
   selected_cid_state, chat_header, chat_messages, tools_html,
   send_result, tp_category, tp_template, *var_slots, tp_preview_box,
   tp_send_result]
  ```
  Reset values: category → "All", template choices repopulated to
  full list, all 5 var slots `gr.update(visible=False, value="",
  label="")`, preview → empty placeholder.

### YAML addition

`hf_dashboard/config/pages/wa_inbox.yml` → under `page.column_1`:

```yaml
refresh_caption: "Click Refresh to see updated conversation."
```

Read it in `_cfg()` alongside the existing `title` and `search_placeholder`.

---

## Change 3 — Attachment popover

### Current

`gr.File(..., elem_classes=["chat-media-input"])` renders a ~120px
drop zone above the send row (`wa_inbox.py:351-361`).

### Approach

Keep the `gr.File` component (its value is still how we pass the
uploaded path into `_send_message`), but:

1. **Hide it visually** via the `.chat-media-input { display: none }`
   rule added in Change 1.
2. **Add a 📎 icon button** in `.chat-send-row` between the textbox
   and the Send button: `attach_btn = gr.Button("📎", size="sm",
   variant="secondary", scale=0, min_width=36,
   elem_classes=["chat-attach-btn"])`.
3. **Add a hidden popover column** (`gr.Column(visible=False,
   elem_classes=["hf-modal", "wa-attach-modal"])`) following the
   existing `.hf-modal` pattern in `theme_css.py:404-434`. Contains:
   - Title "Attach a file"
   - The real `gr.File` component (now visible, because it's inside
     the modal — the `display: none` rule is scoped to
     `.chat-panel .chat-media-input`, not `.wa-attach-modal .chat-media-input`)
     → actually simpler: add a `:not(.wa-attach-modal .chat-media-input)`
     exclusion, or just move the `gr.File` *into* the modal column
     and drop the `display: none` rule entirely. **Picking: move it
     into the modal.** Cleaner, no selector gymnastics.
   - A "Cancel" button and a "Done" button that closes the modal.
4. **Show a file chip in the send row** when a file is attached.
   Two components in the send row:
   - `attach_chip = gr.HTML("")` — renders `📄 filename.pdf` text only
   - `clear_attach_btn = gr.Button("✕", scale=0, min_width=24,
     visible=False, elem_classes=["chat-attach-clear"])` — real
     Gradio button so the click can fire a Python handler
   On `media_input.change`, set chip HTML + show clear button. On
   `clear_attach_btn.click`, return `(gr.update(value=None), "",
   gr.update(visible=False))` for `[media_input, attach_chip,
   clear_attach_btn]`.
5. **Toggle modal visibility** via `attach_btn.click(fn=lambda:
   gr.update(visible=True), outputs=[attach_modal])` and the
   Done/Cancel buttons do `visible=False`.

**Send row overflow guard:** the row already has `flex-wrap: nowrap`
(`theme_css.py:485`). Add textbox flex shrink so it absorbs space
when chip + button are present:

```css
.chat-panel .chat-send-row .chat-send-input { flex: 1 1 0 !important; min-width: 0 !important; }
```

No new CSS classes needed beyond reusing `.hf-modal`. Add one small
rule for the attach chip:

```css
.chat-panel .chat-attach-chip {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    padding: 2px 6px !important;
    background: rgba(99,102,241,.12) !important;
    border: 1px solid rgba(99,102,241,.3) !important;
    border-radius: 6px !important;
    font-size: 10px !important;
    color: #c7d2fe !important;
    max-width: 140px !important;
}
```

### Send handler changes

`_send_message` at `wa_inbox.py:460` already accepts `media_path`.
No change to the function body. Only inputs change: the
`media_input` reference still comes from the (now modal-embedded)
`gr.File`. On successful send we clear `media_input` via
`gr.update(value=None)` — already in the current return tuple at
line 585-586.

---

## Change 4 — Panel 3 rebuild

This is the biggest change. Today Panel 3 is:

```
tools_html (render_full_tools → contact card + activity)
  → divider
  → tpl_dropdown (Select Template)
  → tpl_preview
  → send_tpl_btn
  → send_tpl_result
  → divider
  → refresh_btn
```

New structure:

```
tp_activity_box:   gr.HTML ← render_activity_compact(db, contact_id)
tp_category:       gr.Dropdown(choices=["All","UTILITY","MARKETING","AUTHENTICATION"])
tp_template:       gr.Dropdown(choices=[], interactive=True)
tp_vars_box:       gr.Column(visible=True) containing 5 pre-allocated gr.Textbox slots
tp_preview_box:    gr.HTML ← render_wa_template_filled(template, values)
tp_send_btn:       gr.Button("Send Template", variant="primary")
tp_send_result:    gr.HTML
```

### 4a — Compact activity renderer

**New function** in `tools_panel.py`:

```python
def render_activity_compact(db, contact_id: str, limit: int = 12) -> str:
    """Timestamp + action only. No contact name, no emojis, no icons.
    Used by the WA inbox tools panel where the contact is already
    implicit from Panel 2's header."""
    if not contact_id:
        return '<div style="color:#64748b; font-size:10px; padding:4px;">No activity</div>'
    from services.models import WAMessage, EmailSend
    rows = []
    for wm in db.query(WAMessage).filter(WAMessage.contact_id == contact_id).order_by(WAMessage.created_at.desc()).limit(limit).all():
        ts = wm.created_at.strftime("%b %d %H:%M") if wm.created_at else ""
        label = "WA received" if wm.direction == "in" else f"WA sent · {wm.status or ''}".rstrip(" ·")
        rows.append((wm.created_at, ts, label))
    for es in db.query(EmailSend).filter(EmailSend.contact_id == contact_id).order_by(EmailSend.created_at.desc()).limit(limit).all():
        ts = (es.sent_at or es.created_at).strftime("%b %d %H:%M") if (es.sent_at or es.created_at) else ""
        status = (es.status or "queued").lower()
        rows.append((es.sent_at or es.created_at, ts, f"Email {status}"))
    rows.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    rows = rows[:limit]
    if not rows:
        return '<div style="color:#64748b; font-size:10px; padding:4px;">No activity</div>'
    items = "".join(
        f'<div style="display:flex; justify-content:space-between; gap:8px; padding:2px 0; font-size:10px; border-bottom:1px dashed rgba(255,255,255,.04);">'
        f'<span style="color:#64748b; flex:0 0 auto;">{ts}</span>'
        f'<span style="color:#e7eaf3; flex:1; text-align:right;">{label}</span>'
        f'</div>'
        for _, ts, label in rows
    )
    header = '<div style="font-size:9px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px;">Past Activity</div>'
    return header + items
```

**Imports**: `tools_panel.py` does NOT currently import `datetime`
or `timezone` — add `from datetime import datetime, timezone` at
the top of the file. The existing `render_activity()` dodges this
with `__import__("datetime").datetime.min`; we add the proper import
since the new function uses these names directly.

The existing `render_activity()` stays in place (still used by the
email inbox tools panel via `render_full_tools` — confirmed via grep).

### 4b — Category filter + template dropdown

Categories come from `TemplateDefinition.category`. To avoid
hardcoding, derive from config:

```python
def _template_categories() -> list[str]:
    from services.wa_config import get_wa_config
    cfg = get_wa_config()
    cats = sorted({t.category for t in cfg._templates.values() if t.category})
    return ["All"] + cats
```

Add this as a public method on `WAConfigManager` instead — respects
the project's "no private access" convention:

```python
# in hf_dashboard/services/wa_config.py
def get_template_categories(self) -> list[str]:
    return sorted({t.category for t in self._templates.values() if t.category})
```

Wire `tp_category.change` to filter `tp_template.choices`:

```python
def _filter_templates_by_category(category: str):
    cfg = get_wa_config()
    if not category or category == "All":
        names = cfg.get_template_names()
    else:
        names = [n for n, t in cfg._templates.items() if t.category == category]
        # or add a get_templates_by_category() method to WAConfigManager
    return gr.update(choices=names, value=None)
```

Prefer: add `get_templates_by_category(cat: str) -> list[str]` to
`WAConfigManager` and call that.

### 4c — Pre-allocated variable slots (the key design decision)

Gradio components must exist at page-build time. Pre-allocate **5
slots** (max real variable count is 4, per
`config/whatsapp/templates.yml` — `order_confirmation` and
`order_tracking` both have 4):

```python
MAX_VARS = 5
var_slots: list[gr.Textbox] = []
for i in range(MAX_VARS):
    slot = gr.Textbox(
        label=f"var_{i}",
        placeholder="",
        visible=False,
        interactive=True,
        elem_classes=["wa-var-slot"],
    )
    var_slots.append(slot)
```

CSS to make them compact (two-row mini-inputs):

```css
.tools-panel .wa-var-slot {
    margin: 2px 0 !important;
}
.tools-panel .wa-var-slot textarea,
.tools-panel .wa-var-slot input {
    min-height: 28px !important;
    height: 28px !important;
    font-size: 11px !important;
    padding: 4px 8px !important;
}
.tools-panel .wa-var-slot label span {
    font-size: 9px !important;
    color: #94a3b8 !important;
}
```

### 4d — Template-change handler reconfigures slots

```python
def _on_template_change(template_name: str):
    """Return updates for all MAX_VARS slots + preview."""
    if not template_name:
        updates = [gr.update(visible=False, value="", label="") for _ in range(MAX_VARS)]
        return (*updates, render_wa_template_filled("", {}))
    tpl = get_wa_config().get_template(template_name)
    if not tpl:
        updates = [gr.update(visible=False, value="", label="") for _ in range(MAX_VARS)]
        return (*updates, render_wa_template_filled("", {}))
    updates = []
    for i in range(MAX_VARS):
        if i < len(tpl.variables):
            v = tpl.variables[i]
            updates.append(gr.update(
                visible=True, value="",
                label=v.name,
                placeholder=v.example or v.description,
            ))
        else:
            updates.append(gr.update(visible=False, value="", label=""))
    return (*updates, render_wa_template_filled(template_name, {}))

tp_template.change(
    fn=_on_template_change,
    inputs=[tp_template],
    outputs=[*var_slots, tp_preview_box],
)
```

### 4e — Live preview on variable keystroke

```python
import html as _html

def render_wa_template_filled(template_name: str, values: dict[str, str]) -> str:
    """Render the template body with variable placeholders replaced.
    XSS-safe: escapes the body text BEFORE substitution and escapes
    each variable value before insertion. The placeholder marker
    `{{name}}` survives escaping unchanged because { and } are not
    special HTML characters."""
    from services.wa_config import get_wa_config
    if not template_name:
        return '<div style="color:#64748b; font-size:10px;">Pick a template</div>'
    tpl = get_wa_config().get_template(template_name)
    if not tpl:
        return f'<div style="color:#ef4444; font-size:10px;">"{_html.escape(template_name)}" not found</div>'
    body = _html.escape(tpl.body_text or "")
    for v in tpl.variables:
        placeholder = "{{" + v.name + "}}"  # safe — `name` comes from trusted YAML
        raw = (values.get(v.name) or "").strip()
        val = _html.escape(raw) if raw else f"⟨{_html.escape(v.name)}⟩"
        body = body.replace(placeholder, val)
    return (
        f'<div style="font-size:9px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:6px;">Preview</div>'
        f'<div style="font-size:11px; color:#e7eaf3; line-height:1.5; white-space:pre-wrap; word-wrap:break-word;">{body}</div>'
    )
```

Wire each var slot's `.change` to a handler that reads all 5 slot
values + the current template and re-renders:

```python
def _preview_update(template_name, *slot_values):
    tpl = get_wa_config().get_template(template_name) if template_name else None
    values: dict[str, str] = {}
    if tpl:
        for i, v in enumerate(tpl.variables):
            if i < len(slot_values):
                values[v.name] = slot_values[i]
    return render_wa_template_filled(template_name, values)

for slot in var_slots:
    slot.change(
        fn=_preview_update,
        inputs=[tp_template, *var_slots],
        outputs=[tp_preview_box],
    )
```

### 4f — Send handler

Outputs (must match `outputs=[tp_send_result, chat_messages,
*var_slots, tp_preview_box]` on the click handler):

```python
def _send_tpl_filled(contact_id, template_name, *slot_values):
    """Send a filled template. On success: persist filled body to
    WAMessage.text, refresh chat, clear all var slots, reset preview."""
    n_slots = MAX_VARS
    no_change_slots = [gr.update() for _ in range(n_slots)]

    def _err(msg):
        return (f'<div style="color:#ef4444; font-size:10px;">{msg}</div>',
                gr.update(), *no_change_slots, gr.update())

    if not contact_id or not template_name:
        return _err("Select chat + template")

    from services.wa_config import get_wa_config
    tpl = get_wa_config().get_template(template_name)
    if not tpl:
        return _err("Template not found")

    # Build named variables from slot values (only those tpl actually uses)
    variables: list[tuple[str, str]] = []
    for i, v in enumerate(tpl.variables):
        if i < len(slot_values):
            variables.append((v.name, (slot_values[i] or "").strip()))

    # Required-field validation
    missing = [name for name, val in variables
               if not val and any(v.name == name and v.required for v in tpl.variables)]
    if missing:
        return (f'<div style="color:#f59e0b; font-size:10px;">Missing: {", ".join(missing)}</div>',
                gr.update(), *no_change_slots, gr.update())

    from services.database import get_db
    from services.models import Contact, WAChat, WAMessage
    from services.wa_sender import WhatsAppSender
    db = get_db()
    try:
        c = db.query(Contact).filter(Contact.id == contact_id).first()
        if not c or not c.wa_id:
            return _err("No WhatsApp ID on contact")

        # Templates bypass the 24h customer-service window.
        ok, msg_id, err = WhatsAppSender().send_template(
            c.wa_id, template_name, lang=tpl.language, variables=variables,
        )
        if not ok:
            return _err(err or "Send failed")

        # Filled body for chat log + preview
        filled_body = tpl.body_text or ""
        for name, val in variables:
            filled_body = filled_body.replace("{{" + name + "}}", val)

        now = datetime.now(timezone.utc)
        chat = db.query(WAChat).filter(WAChat.contact_id == c.id).first()
        if not chat:
            chat = WAChat(contact_id=c.id)
            db.add(chat)
            db.flush()
        chat.last_message_at = now
        chat.last_message_preview = filled_body[:100]
        db.add(WAMessage(
            chat_id=chat.id,
            contact_id=c.id,
            direction="out",
            status="sent",
            text=filled_body,
            wa_message_id=msg_id,
        ))
        c.last_wa_outbound_at = now
        db.commit()

        cleared_slots = [gr.update(value="") for _ in range(n_slots)]
        return (
            '<div style="color:#22c55e; font-size:10px;">Template sent ✓</div>',
            _build_chat_messages(db, contact_id),
            *cleared_slots,
            render_wa_template_filled(template_name, {}),
        )
    finally:
        db.close()
```

Wiring:

```python
tp_send_btn.click(
    fn=_send_tpl_filled,
    inputs=[selected_cid_state, tp_template, *var_slots],
    outputs=[tp_send_result, chat_messages, *var_slots, tp_preview_box],
).then(fn=None, inputs=None, outputs=None, js=_SCROLL_CHAT_JS)
```

---

## Files modified (summary)

| File | Nature of change | Approx lines |
|---|---|---|
| `hf_dashboard/pages/wa_inbox.py` | Major rewrite of `build()`. Keep `_cfg`, `_avatar_for`, `_get_active_conversations`, `_search_all_contacts`, `_build_chat_header`, `_build_chat_messages`, `_render_message_body`, `_MEDIA_KIND_BY_EXT`, `_media_info_for_filename`, `_send_message`. Rewrite `build()` layout + `_send_tpl` + `_do_refresh`. | ~200 |
| `hf_dashboard/components/tools_panel.py` | Add `render_activity_compact()` and `render_wa_template_filled()`. Leave `render_activity`, `render_wa_template_preview`, `render_full_tools` in place (still used by email inbox — grep to confirm before touching). | ~60 |
| `hf_dashboard/services/wa_config.py` | Add `get_template_categories()` and `get_templates_by_category(cat)` to `WAConfigManager`. | ~15 |
| `hf_dashboard/shared/theme_css.py` | Append new rules to `_STATIC_CSS`: the Panel 1 / Panel 3 flex scroll rules, the compact var slot rules, the attach chip rule. | ~80 |
| `hf_dashboard/config/pages/wa_inbox.yml` | Add `column_1.refresh_caption`, `column_3.activity_title`, `column_3.send_template_label`. | ~5 |

**No changes to:** `services/wa_sender.py` (already supports
variables), `services/models.py`, `app/whatsapp/*`, any deploy
config.

---

## Reused existing code

- `WhatsAppSender.send_template()` at `hf_dashboard/services/wa_sender.py:94-177` — accepts named `list[tuple[str, str]]` variables, builds the Meta `components` payload. **No change.**
- `WAConfigManager.get_template()` at `hf_dashboard/services/wa_config.py:143` — returns `TemplateDefinition` with `.variables`, `.body_text`, `.category`, `.language`.
- `TemplateDefinition.variable_names` property at `wa_config.py:52` — already exists.
- `.hf-modal` CSS class at `theme_css.py:404-434` — reused for the attachment popover.
- `components.styles.badge()` — for the category badge in the preview.
- Existing `_cfg()`, `_get_active_conversations()`, `_search_all_contacts()`, `_build_chat_header()`, `_build_chat_messages()`, `_render_message_body()`, `_send_message()`, `_MEDIA_KIND_BY_EXT`, `_media_info_for_filename()` in `wa_inbox.py` — untouched.
- `render_contact_card()`, `render_activity()`, `render_wa_template_preview()`, `render_full_tools()`, `render_tools_empty()` in `tools_panel.py` — untouched (still used by email inbox; confirmed via grep before planning).

---

## Verification

Per CLAUDE.md: never run the app locally. Flow is always commit →
deploy → Playwright-verify on the live Space.

0. **Pre-flight: copy plan to reports/**
   - `cp /home/prashant-agrawal/.claude/plans/swift-honking-harbor.md
     reports/Implementation_W02_April_2026/wa_inbox_rebuild.md`
     (creating the directory first if missing). The user asked for
     the plan to live in the project's reports directory; the harness
     plan file is the working copy.

1. **Local static checks**
   - `python -m py_compile hf_dashboard/pages/wa_inbox.py hf_dashboard/components/tools_panel.py hf_dashboard/services/wa_config.py hf_dashboard/shared/theme_css.py`
   - Confirm no stray `yaml.safe_load` inline reads added (respect engine schema rule)

2. **Commit and deploy**
   - `git add` the modified files
   - Create a single commit summarizing the rebuild
   - `python scripts/deploy_hf.py`
   - Wait for Space to report **Running**

3. **Live verification (Playwright MCP, headless)**
   Navigate to `https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/`
   and verify each change in order:

   **Column alignment**
   - Screenshot the full `/wa_inbox` page. Confirm all three columns start at the same top Y and end at the same bottom Y. The send row in Panel 2 and the Send Template button in Panel 3 should sit flush at the same Y as the bottom of Panel 1's Start New list.
   - Resize the window to a shorter height and re-screenshot. The scroll regions (both Panel 1 lists, the chat messages, and Panel 3's activity + vars + preview) must absorb the shrink, with headers/dropdowns/buttons remaining visible.

   **Refresh button**
   - Confirm 🔄 appears at the top-right of Panel 1 next to "ACTIVE CHATS".
   - Confirm the caption "Click Refresh to see updated conversation." appears directly below.
   - Click refresh. Confirm the active chats list reloads (check DB count matches visible rows via a small browser_evaluate call).

   **Attachment popover**
   - Confirm the large upload drop zone is gone from Panel 2.
   - Confirm the send row has: textbox, 📎 icon, Send button — all on one line, same height.
   - Click 📎. The modal appears centered.
   - Upload a small test file (e.g. `preview-fix-verified.png` from repo root).
   - Close the modal. A chip with the filename + ✕ appears next to the textbox.
   - Pick a conversation that is inside the 24h window. Type "test caption". Click Send.
   - Confirm the message appears in the chat as a media bubble with caption. Confirm the chip clears.
   - Click ✕ on a chip to remove a pending file before sending — confirm the `gr.File` value resets.

   **Template variable flow**
   - Click Refresh. Pick a conversation.
   - In Panel 3 Past Activity: confirm rows show timestamp + action only (no emojis, no names). Confirm the box has `~25%` of the column height and scrolls.
   - Category dropdown: confirm options are "All", "AUTHENTICATION", "MARKETING", "UTILITY" (alphabetical).
   - Pick "UTILITY". Confirm template dropdown now only lists utility templates (hello_world, order_confirmation, order_tracking, etc).
   - Pick `order_confirmation`. Confirm 4 text inputs appear labeled `customer_name`, `order_id`, `product_names`, `amount`, with the YAML examples showing as placeholders. Confirm slots 5 (and any beyond 4) stay hidden.
   - Type values. Confirm preview updates on each keystroke, showing the filled-in body.
   - Click Send Template without filling one required field: expect an amber "Missing: <name>" message.
   - Fill all fields. Click Send Template. Confirm success, and confirm the **filled** body shows up in the chat log (not `[Template: order_confirmation]`).
   - Pick `hello_world` (zero variables): confirm no variable inputs appear, preview shows the raw body ("Hello World"), Send works.

   **Regression checks**
   - Email inbox page still renders activity normally (`render_activity` and `render_wa_template_preview` are untouched — confirm via loading the email inbox and checking the tools panel).
   - `refresh_btn` click still clears the chat view and reloads conversations.

4. **Rollback plan**
   - The change is contained to 5 files. If verification finds a broken flow, revert the commit and re-deploy. No DB state to roll back.

---

## Confirmed decisions

- **Chat log shows the filled body** (not `[Template: ...]`). `WAMessage.text` stores the fully substituted body, e.g. `Hi Rajesh, Thank you for your order HF-2026-0042…`. The preview text in `WAChat.last_message_preview` also uses the filled body (truncated to 100 chars).
- **No autofill from contact fields.** Every variable input starts empty. The user types every value.

## Out of scope (not doing in this PR)

- Autofill of `customer_name` etc. from the contact profile — explicitly declined.
- Drag-and-drop onto the send row (files only via modal for now).
- Template button rendering in the preview (send handler ignores buttons — they're already defined server-side in Meta).
- Language fallback UI (send_template already handles it silently; logs indicate mismatches in the server console).
