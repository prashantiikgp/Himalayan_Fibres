# Email Broadcast Phase 2 — dynamic template variables + layout polish

> **Phase 1 (shipped 2026-04-14, commit `e78ba3f`)**: two-column refactor, Individual send mode (name/company search + direct email upsert), Desktop/Mobile iframe preview toggle. Verified live, test-send confirmed. Obsolete plan context removed.

## Context

The founder used the shipped Phase 1 page on a live Space and flagged three concrete gaps (screenshots `temp/clipboard-image-20260415_08*.png`):

1. **Can't edit template variables on the page.** Every template (order_confirmation, order_shipped, operational_update, etc.) has user-meaningful variables — order_number, order_date, ship_to_html, items_html, subtotal, shipping, total, payment_method, courier_name, tracking_id, update_title, update_body_html, update_cta_label, update_cta_url. Right now they're filled from a hardcoded `_build_sample_vars_for_preview()` stub (the infamous "Alisha Panda" + "10014" defaults that also leak into real Test Sends). The founder wants to type the real per-send values on the page and have the preview refresh live, matching the WhatsApp Broadcast pattern that already works (`hf_dashboard/pages/broadcasts.py:279-284` + `hf_dashboard/services/wa_config.py::TemplateVariable`).
2. **Left column wastes space.** The "Send to" header is filler. The Broadcast/Individual radio doesn't span the full column so a dead zone sits next to it. The "Search by name or company, or type any email" helper text is a whole line that could collapse into the search field placeholder. The preview panel also has empty space at the bottom.
3. **Layout decision the founder wants visualized and then picked.** Where should the new variable inputs live — left column under Subject, or right column above the Desktop/Mobile radio. **Answered via AskUserQuestion: Option B (above preview).** Also answered: show **all** template vars (not a curated subset), and store the schema in **`templates_seed/*.meta.yml`** (YAML + Pydantic) — matches the engine-config rule in CLAUDE.md.

Intended outcome: the founder can pick `order_confirmation` in Individual mode, type an actual order number / ship-to / total, see the preview update in real time, click Send Test to Me to sanity-check it on their phone, then click Send Now to deliver exactly what's in the preview — no more hardcoded Alisha sample data leaking through. The compose column gets tighter; the preview column gets the new work.

## File changes

### 1. `hf_dashboard/config/email/templates_seed/*.meta.yml` — extend with `variables:` block

Each per-template meta YAML already contains `slug`, `name`, `category`, `subject_template`, `required_variables: [list of names]`, `optional_variables: [list of names]`. I'll add a new `variables:` block with the rich per-variable schema so the UI can render typed inputs:

```yaml
template:
  slug: order_confirmation
  name: "Order Confirmation"
  category: transactional
  subject_template: "Order confirmed — thank you, {{ first_name }}!"
  is_active: true
  required_variables: [first_name, order_number, order_date, items_html, total]
  optional_variables: [ship_to_html, subtotal, shipping, payment_method, invoice_url]
  variables:
    - name: order_number
      label: "Order number"
      type: text          # text | textarea | url | date
      placeholder: "10014"
      example: "10014"
      required: true
    - name: order_date
      label: "Order date"
      type: date
      placeholder: "30-Aug-2025"
      example: "30-Aug-2025"
      required: true
    - name: ship_to_html
      label: "Ship to"
      type: textarea
      placeholder: "Mrs. Alisha Panda<br>Brahmapur, Odisha 760004"
      example: "Mrs. Alisha Panda<br>Brahmapur, Odisha 760004"
      required: false
    - name: items_html
      label: "Items (HTML)"
      type: textarea
      placeholder: '<p>Himalayan Woollen Yarn × 500 g</p>'
      example: '<p>Himalayan Woollen Yarn × 500 g</p>'
      required: true
    - name: subtotal
      label: "Subtotal"
      type: text
      placeholder: "Rs 750"
      required: false
    - name: shipping
      label: "Shipping"
      type: text
      placeholder: "Rs 200"
      required: false
    - name: total
      label: "Total"
      type: text
      placeholder: "Rs 950"
      required: true
    - name: payment_method
      label: "Payment method"
      type: text
      placeholder: "UPI"
      required: false
```

One analogous block per existing meta file. `first_name` is deliberately **not** in the `variables:` list — it comes from the Contact record at send time, not from the UI. Same for all shared branding vars (company_name, whatsapp_url, icon URLs, etc. — loaded from `shared.yml` via `build_send_variables`).

Files edited (5):
- `operational_update.meta.yml` — 4 vars (update_title, update_body_html [textarea], update_cta_label, update_cta_url [url])
- `order_confirmation.meta.yml` — 8 vars (as above)
- `order_shipped.meta.yml` — 5 vars (courier_name, tracking_id, dispatch_date [date], delivery_date [date], tracking_url [url])
- `welcome.meta.yml` — 0 vars (only uses first_name, nothing user-editable)
- `order_delivered_feedback.meta.yml` — 0 vars

The Phase 1 file is the only thing left for the other two templates I haven't enumerated (`b2b_introduction`, `b2b_followup` if present in DB but not seeded) — I'll add meta YAMLs for them too during implementation if they ship with the HF Space.

### 2. `hf_dashboard/services/template_seed.py` — extend Pydantic schema

Add one new Pydantic class + extend the existing `SeedTemplateMeta`, following the WhatsApp `TemplateVariable` shape (`services/wa_config.py:24-30`):

```python
class TemplateVariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    label: str = ""
    type: str = "text"          # text | textarea | url | date
    placeholder: str = ""
    example: str = ""
    required: bool = False

class SeedTemplateMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    name: str
    category: str = "campaign"
    subject_template: str = ""
    is_active: bool = True
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    variables: list[TemplateVariableSpec] = Field(default_factory=list)  # NEW
```

Because `variables` defaults to `[]`, all existing meta YAMLs without a `variables:` block keep loading cleanly — no migration needed for `welcome` and `order_delivered_feedback`.

Also add a new module-level function the page will call:

```python
from functools import lru_cache

@lru_cache(maxsize=32)
def get_template_meta(slug: str) -> SeedTemplateMeta | None:
    """Load a template's meta YAML for runtime UI use. Cached per-process."""
    path = _CFG_DIR / f"{slug}.meta.yml"
    if not path.exists():
        return None
    try:
        return _load_meta(path)
    except Exception:
        log.exception("Failed to load template meta: %s", path)
        return None
```

Everything else in `template_seed.py` (the boot seeder, `seed_email_templates`) is untouched — the new `variables` field is additive.

### 3. `hf_dashboard/pages/email_broadcast.py` — the real work

#### Layout polish (Phase 2 punch list)
- Delete the `<div>Send to</div>` header (current lines ~266–271).
- Move the mode radio to the very top of the left column, `container=False`, so it spans the full column width. No more dead zone next to the buttons.
- Individual mode: delete the helper `<div>Search by name or company, or type any email below.</div>`. Fold the same text into the Search textbox's `placeholder=` ("Search by name or company — or type any email below"). Narrow the Search and Contact fields (they don't need full width).
- Preview column: clamp the preview iframe `max-height` so the empty space at the bottom of the panel collapses on short templates.

#### Variable editor — Option B layout (right column, above Desktop/Mobile radio)

```python
# Right column structure:
with gr.Column(scale=3, min_width=560):
    # ── 1. Template variables block (NEW, dynamic) ──
    with gr.Group():
        gr.HTML('<div>── Template variables ──</div>')
        subject_input = gr.Textbox(label="Subject", ...)   # MOVED from left column
        with gr.Row():
            var_slot_0 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
            var_slot_1 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
        with gr.Row():
            var_slot_2 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
            var_slot_3 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
        with gr.Row():
            var_slot_4 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
            var_slot_5 = gr.Textbox(label="", visible=False, lines=1, interactive=True)
        var_slot_6 = gr.Textbox(label="", visible=False, lines=2, interactive=True)   # textarea-ish
        var_slot_7 = gr.Textbox(label="", visible=False, lines=2, interactive=True)   # textarea-ish
        # 8 slots total — max needed is order_confirmation's 8

    # ── 2. Preview header + device toggle ──
    with gr.Row():
        gr.HTML('<div>Preview</div>')
        device_radio = gr.Radio(["Desktop", "Mobile"], value="Desktop", ...)

    # ── 3. Iframe preview ──
    preview_html = gr.HTML(value=_render_preview_html("", "desktop"))
```

**Why 8 fixed slots:** Gradio components are declared at build() time — you cannot add/remove components dynamically. Pre-declaring 8 slots is the standard Gradio pattern for this, and 8 is `max(len(meta.variables) for meta in all_templates)` (order_confirmation).

**Slot assignment** — templates map their `variables` list to slots 0..N-1 in declaration order from the YAML. The remaining slots stay `visible=False`. The template author controls ordering by re-ordering the YAML. Short text (`type=text|url|date`) fills slots 0–5; long content (`type=textarea`) fills slots 6–7 (which are pre-declared with `lines=2`). The loader assigns types to slots automatically so the founder never sees a single-line box for `update_body_html`.

**New helper in email_broadcast.py:**

```python
MAX_VAR_SLOTS_SHORT = 6   # slot indices 0..5, lines=1
MAX_VAR_SLOTS_LONG = 2    # slot indices 6..7, lines=2

def _build_slot_updates(meta: SeedTemplateMeta | None) -> list:
    """Return 8 gr.update() objects assigning the template's variables
    to the 8 pre-declared slots, hiding the rest.
    """
    short_vars = [v for v in (meta.variables if meta else []) if v.type != "textarea"]
    long_vars  = [v for v in (meta.variables if meta else []) if v.type == "textarea"]
    updates = [gr.update(visible=False, value="", label="", placeholder="")] * 8
    for i, v in enumerate(short_vars[:MAX_VAR_SLOTS_SHORT]):
        updates[i] = gr.update(
            visible=True,
            label=v.label or v.name,
            placeholder=v.placeholder,
            value=v.example,        # pre-fill with example so first render is meaningful
        )
    for j, v in enumerate(long_vars[:MAX_VAR_SLOTS_LONG]):
        updates[MAX_VAR_SLOTS_SHORT + j] = gr.update(
            visible=True,
            label=v.label or v.name,
            placeholder=v.placeholder,
            value=v.example,
        )
    return updates
```

**New state:** `var_names_state = gr.State([])` — an 8-element list of the variable name that each slot currently represents (or `""` for unused slots). Needed so `_on_variables_change` and `_on_send_now` can zip the current slot values back into a `{name: value}` dict.

#### Handler changes

- **`_on_template_change(slug, device)`** returns: subject (existing), preview HTML (existing), **+ 8 `gr.update()` slot updates + var_names_state list**. Loads `get_template_meta(slug)`, calls `_build_slot_updates()`, tracks names.
- **New `_on_variables_change(slug, device, *values)`**: wires every var slot's `.change` to this. Zips `var_names_state` with `values`, filters out empty/hidden slots, calls `_render_preview_html(slug, device, extra=vars_dict)`.
- **`_render_preview_html(slug, device, extra=None)`**: signature gets an optional `extra` dict. If `extra` is given, passes it as `extra=...` to `build_send_variables()` instead of the hardcoded `_build_sample_vars_for_preview()`. If `extra` is None (template just loaded, no edits yet), fall back to the per-variable `example` values from the meta YAML. **The "Alisha Panda" stub is deleted entirely** — preview always uses the real meta YAML examples, which double as the UI's default fill, so what you see is what you'll send.
- **`_on_send_now`**: takes the new `var_names_state` + 8 slot values as extra inputs. Builds `vars_dict` same way as `_on_variables_change`, passes as `extra=` to `build_send_variables(contact, attachments, extra=vars_dict)`. Per-recipient `contact.first_name` etc. still come from the Contact row — slot values only override template-specific fields.
- **`_on_test_send`**: same treatment. **This is the fix for the Alisha leak.** Today it calls `build_send_variables(stub, {}, extra=_build_sample_vars_for_preview(template_slug))` — the stub + hardcoded Alisha. After the change it's `build_send_variables(stub, {}, extra=vars_dict)` where `vars_dict` is whatever is currently in the slot inputs.
- **`_on_device_change`**: takes the current `var_names_state` + 8 slot values so re-renders after a Mobile↔Desktop toggle keep the founder's edits intact.

#### State wiring summary

```
session state:
  draft_campaign_state, send_mode_state, preview_device_state,
  individual_contact_state, var_names_state   (NEW)

var slots (right column, above preview):
  var_slot_0 … var_slot_7  (gr.Textbox, visible=False initially)

on template change:
  (subject, preview, *8 slot_updates, var_names_state) =
    _on_template_change(slug, device)

on any var slot .change:
  preview = _on_variables_change(slug, device, var_names_state, *slot_vals)

on device toggle:
  (device_state, preview) =
    _on_device_change(dev_label, slug, var_names_state, *slot_vals)

on send / test send:
  dict(zip(var_names, slot_vals)) — empty names skipped —
  passed as extra= to build_send_variables()
```

### 4. No change: `hf_dashboard/services/email_personalization.py`

`build_send_variables(contact, attachments, extra=None)` already accepts an `extra` dict and merges it on top of shared + contact vars (verified in Phase 1 exploration). It's the perfect plumbing point for the variable editor.

### 5. No change: email templates themselves

Already responsive (verified Phase 1). Viewport meta + `max-width:640px` tables. The dynamic variable values flow in via Jinja rendering which is already how it works today.

## Functions to reuse (do not reinvent)

| Existing | Location | Reused for |
|---|---|---|
| `SeedTemplateMeta`, `_load_meta`, `_CFG_DIR` | `services/template_seed.py:37-60` | Extended schema + new `get_template_meta` wrapper |
| `TemplateVariable` (WA schema shape) | `services/wa_config.py:24-30` | Modelled `TemplateVariableSpec` on this |
| WA broadcast var-loop pattern | `pages/broadcasts.py:279-284` | Template for the `zip(var_names, values)` loop in send handler |
| `build_send_variables(contact, attachments, extra=...)` | `services/email_personalization.py` | Unchanged — already takes `extra` dict |
| `render_template_by_slug`, `EmailSender`, `generate_idempotency_key` | `services/email_sender.py` | Unchanged |
| `_format_recipient`, `_parse_recipient_value`, `_search_contacts`, `_upsert_contact_by_email`, `_resolve_segment_contacts`, `_ensure_draft_campaign`, `_render_preview_html` | `pages/email_broadcast.py` (Phase 1) | Unchanged or additively extended |
| `COLORS` theme tokens | `shared/theme.py` | Panel/divider styling |

## Verification

Per CLAUDE.md "Verification workflow" — no local runs.

1. **Local sanity**: `python -c "import ast; ast.parse(open('hf_dashboard/pages/email_broadcast.py').read())"` and a Python import smoke-test that `get_template_meta('order_confirmation')` returns a schema with 8 variables (via a one-liner from the repo root — read-only).
2. **Commit** the changes (`git add` the 5 meta YAMLs + `services/template_seed.py` + `pages/email_broadcast.py`).
3. **Deploy**: `python scripts/deploy_hf.py`. If the Space is in RUNTIME_ERROR from a stale Supabase timeout (as happened in Phase 1), force a restart: `curl -X POST -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/spaces/prashantiitkgp08/himalayan-fibers-dashboard/restart`.
4. **Playwright verification on the live Space** (headless, Desktop 1600×1000 viewport):
   - Navigate to `/` → click **Email Broadcast** sidebar.
   - **Screenshot 1** — default state. Assert: no "Send to" header; Broadcast/Individual radio spans full column width; compose column is tight; right column shows a "Template variables" block with Subject + (for default template) the matching variable inputs pre-filled with example values; Desktop preview iframe renders with the example values baked in (no more "Alisha Panda").
   - Select **order_confirmation** from Template dropdown. Assert: right column now shows 8 variable inputs (order_number, order_date, ship_to_html, items_html, subtotal, shipping, total, payment_method) with the YAML example values; the `items_html` and `ship_to_html` fields are multi-line. Screenshot 2.
   - Type a new value (e.g. `order_number` = `99999`) and confirm the preview iframe refreshes with `99999` on the next handler tick. Screenshot 3.
   - Click **Mobile** toggle → assert iframe clamps to 390×740 phone frame, the edited `99999` is still in the preview. Screenshot 4.
   - Switch to **Individual** mode → search "prashant" → pick the contact → fill a fresh set of variables → click **Send Test to Me** with `prashant.mine@gmail.com` → assert green success message AND assert the delivered email contains the typed values (this is the Alisha-leak fix). Screenshot 5.
   - Flip back to **Broadcast**. Select **operational_update**. Assert the slot inputs re-adapt (4 slots: update_title / update_body_html / update_cta_label / update_cta_url; update_body_html in the textarea slot). Screenshot 6.
   - Open Invoice accordion → confirm Phase 1 Broadcast recipient picker still populates from the segment.
5. Do **not** click Send Now on a real 816-recipient segment during verification. Test-send only. Hand off with the screenshot bundle.

## Out of scope (explicitly)

- Any schema migration (`EmailTemplate.required_variables` stays the simple string list it is today).
- Any edit to the email HTML templates (`hf_dashboard/templates/emails/*.html` unchanged — they consume the same Jinja vars they always have).
- Any change to `build_send_variables`, `render_template_by_slug`, `EmailSender`, `_get_segment_contacts`.
- A template editor (editing the Jinja templates themselves). The founder can already edit variables per send; editing the template markup is a future Template Studio concern.
- Persisting the edited values on the draft Campaign row — slot values are session-local for this PR; if the founder navigates away mid-compose they lose the typed values. Trade-off: simpler plumbing, good enough for a single compose session.
- More than 8 variable slots. If a future template needs 9+ vars, the plan is to raise `MAX_VAR_SLOTS_SHORT`/`LONG` by 1 each and add a row to the Gradio layout — not to make slots truly dynamic.
