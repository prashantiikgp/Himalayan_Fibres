# Email Broadcast page refactor — layout, Individual send mode, mobile preview

## Context

The current `hf_dashboard/pages/email_broadcast.py` has several UX problems that the user called out while using the live HF Space:

1. The page header + subtitle eats vertical space for no value.
2. The left "filter" column is too wide and the right preview too small — the preview is what you actually look at while composing.
3. The two columns have no clean visual demarcation.
4. Inside the "Invoice attachments" accordion there is a second **Recipient** dropdown that's confusing — it looks like an individual-send path but is actually per-recipient invoice attachment for a broadcast. The UI doesn't tell you which.
5. The giant recipients-list HTML table (`_build_attachments_table_html`) is noise — the founder does not want to see every person's name/email scrolling inside the compose page.
6. There is **no way to send to a single individual**. Today you can only send to a segment. The founder wants this as a first-class option: either pick an existing contact by name/company, or inject an arbitrary email address directly.
7. There is no way to preview how the email will look on mobile. The founder wants a Desktop / Mobile radio toggle. Templates must render well on phones.

**Good news:** all email templates under `hf_dashboard/templates/emails/` (welcome, order_confirmation, order_shipped, order_delivered_feedback, operational_update) already share `layout/base.html`, which has `<meta name="viewport" content="width=device-width,initial-scale=1">` and uses the standard nested-table pattern with `max-width:640px`. So mobile rendering works automatically **if the preview is inside a real `<iframe srcdoc="...">`** (the current `<div>` wrapper does not honor the viewport meta, which is why no prior mobile preview could ever work).

Intended outcome: a clean two-column compose page where the preview dominates, sending to one person is obvious, and the founder can sanity-check the mobile look before clicking Send.

## File changes

### 1. `hf_dashboard/pages/email_broadcast.py` — main refactor

This is the only file that needs real changes. The refactor is layout + one new mode + a preview wrapper — no schema changes, no new services.

#### Remove
- The page header `<div>Email Broadcast</div>` + subtitle block (lines 272–276).
- `_build_attachments_table_html` (lines 180–234) and every output wired to `attachments_table_html`. The giant recipients-list table is gone entirely.
- `recipient_ids_state` gr.State (no longer needed after the table dies).

#### New session state
- `send_mode_state = gr.State("broadcast")` — `"broadcast"` or `"individual"`
- `preview_device_state = gr.State("desktop")` — `"desktop"` or `"mobile"`
- `individual_contact_state = gr.State(None)` — selected Contact id (or None when using raw email)

#### New layout (two columns, visually demarcated)

Left column `scale=1, min_width=340` wrapped in a `CARD_BG` panel (rounded border, subtle `rgba` border). Right column `scale=3, min_width=560` wrapped in its own panel with a gap between them.

```
LEFT (controls)                                RIGHT (preview, dominant)
┌────────────────────────────┐                ┌──────────────────────────────────────┐
│  Send to: ( ) Broadcast    │                │  Preview  [Desktop] [Mobile]         │
│           ( ) Individual   │                │  ┌────────────────────────────────┐  │
│                            │                │  │                                │  │
│  Template ▼                │                │  │   <iframe srcdoc="...">        │  │
│                            │                │  │                                │  │
│  ── Broadcast group ──     │                │  │   (full width on desktop,      │  │
│  Segment ▼                 │                │  │    390px phone frame on       │  │
│  816 recipients            │                │  │    mobile)                     │  │
│                            │                │  │                                │  │
│  ── Individual group ──    │                │  │                                │  │
│  Search name/company       │                │  │                                │  │
│  Contact ▼ (filtered)      │                │  │                                │  │
│  — or —                    │                │  │                                │  │
│  Direct email              │                │  │                                │  │
│                            │                │  └────────────────────────────────┘  │
│  Subject                   │                │                                      │
│                            │                │                                      │
│  📎 Invoice (optional) ▾   │                │                                      │
│    [ctx-aware body]        │                │                                      │
│                            │                │                                      │
│  [ Send Now ]  [ Test ]    │                │                                      │
│  Test email: ___________   │                │                                      │
└────────────────────────────┘                └──────────────────────────────────────┘
```

#### Mode radio + group visibility

A single `gr.Radio(choices=["Broadcast","Individual"], value="Broadcast")` at the very top of the left column. Its `.change` handler flips `send_mode_state` and returns `gr.update(visible=...)` for two container groups:

- `broadcast_group = gr.Group()` wraps `segment_dropdown` + `audience_kpi_html`
- `individual_group = gr.Group(visible=False)` wraps the new Individual controls

#### Individual mode controls (inside `individual_group`)

Per user's note ("different section in the filter column where we get the result by name or company name and select the user, or we can directly inject the email"):

1. `individual_search = gr.Textbox(label="Search by name or company", placeholder="e.g. Sushank, or Lakhanpal")` — debounced on `.change`.
2. `individual_contact_dropdown = gr.Dropdown(label="Contact", choices=[])` — populated from the search. Reuses the existing `_format_recipient` helper + the `_RECIPIENT_VALUE_SEP` encoding so the handler can look the contact up by id.
3. A small `<div>— or —</div>` divider.
4. `individual_email_input = gr.Textbox(label="Direct email", placeholder="name@example.com")` — lets the founder type any address without picking a contact.

Precedence rule used by Send: if `individual_email_input` is non-empty it wins; otherwise use the selected contact from the dropdown.

Search handler (new `_on_individual_search`): queries `Contact` filtered by `consent_status in ('opted_in','pending')`, `or_(first_name ILIKE %q%, last_name ILIKE %q%, company ILIKE %q%, email ILIKE %q%)`, limit 20. Returns `gr.update(choices=...)` for the dropdown.

#### Invoice attachment — context-aware

Keep the `📎 Invoice attachments (optional)` accordion but make it mode-aware via two subgroups whose visibility is toggled by the mode radio:

- **Broadcast subgroup** (current behaviour): keep the existing "pick a recipient from the segment → upload PDF → Attach/Remove" flow. Relabel the helper text to make it clear this is "attach an invoice to *one specific person* in the segment; it will only appear in their email". The recipient picker is populated from the segment (same as today, but built on-the-fly from the segment resolve rather than from the killed table's state).
- **Individual subgroup**: just `invoice_file = gr.File(...)` and a single Attach/Remove pair — no recipient picker, because the recipient is already the one selected above. Auto-binds to the selected contact (or to the ad-hoc email after upsert — see Send Now below).

#### Preview wrapper — the mobile fix

Replace the current `<div style="overflow:auto">` wrapper in `_render_preview_html` with a real iframe. New helper signature:

```python
def _render_preview_html(template_slug: str, device: str = "desktop") -> str:
    ...
    html = render_template_by_slug(template_slug, vars_for_preview)
    # Escape for srcdoc attribute
    srcdoc = html.replace("&", "&amp;").replace('"', "&quot;")
    if device == "mobile":
        # 390px iPhone-ish frame, centred
        return (
            f'<div style="display:flex;justify-content:center;padding:12px 0;">'
            f'<div style="width:412px;border:10px solid #1a1a1a;border-radius:36px;'
            f'box-shadow:0 8px 24px rgba(0,0,0,.4);overflow:hidden;background:#000;">'
            f'<iframe srcdoc="{srcdoc}" '
            f'style="width:390px;height:720px;border:0;background:#fff;display:block;">'
            f'</iframe></div></div>'
        )
    return (
        f'<div style="background:#fff;border:1px solid rgba(255,255,255,.08);'
        f'border-radius:10px;overflow:hidden;">'
        f'<iframe srcdoc="{srcdoc}" '
        f'style="width:100%;height:78vh;border:0;display:block;"></iframe></div>'
    )
```

The real iframe is what makes the existing `<meta name="viewport">` in `templates/emails/layout/base.html` actually kick in — the browser treats the srcdoc as its own document and applies the table `max-width:640px` rules the templates already have. No template edits needed.

#### Desktop / Mobile radio (right column)

```python
device_radio = gr.Radio(
    choices=["Desktop", "Mobile"],
    value="Desktop",
    show_label=False,
    container=False,
)
```

Placed at the top of the right column next to a small "Preview" label. Its `.change` handler:

```python
def _on_device_change(device_label, template_slug):
    device = "mobile" if device_label == "Mobile" else "desktop"
    return device, _render_preview_html(template_slug, device)
```

The template change handler (`_on_template_change`) also needs to accept the current `preview_device_state` so re-renders stay in the selected device.

#### Send Now handler — new branches

Refactor `_on_send_now` to take `send_mode`, `individual_contact_value`, `individual_email` as extra inputs, and branch:

- **Broadcast** (unchanged): resolve segment, loop over contacts, same flow as today.
- **Individual → existing contact**: resolve exactly one `Contact` from the dropdown value. Reuse the same per-recipient loop body (single iteration), creating a 1-recipient Campaign. Keeps history/idempotency consistent with broadcasts.
- **Individual → direct email injection**: upsert a Contact row keyed by email (`db.query(Contact).filter_by(email=...).first()` → create with `consent_status='pending'` if missing). Then treat it as the "existing contact" path. This is needed because `EmailSend.contact_id` is `nullable=False` (models.py:163), and upserting means repeat sends to the same address reuse the contact and populate history cleanly.

Test-send is left as-is — it's already a one-off with no DB writes.

#### Attach/Remove handlers — prune

`_on_attach` / `_on_remove` lose their `contact_ids` input and no longer return an `attachments_table_html`. They still return `draft_campaign_state` and a small inline "✓ Attached to Sushank Lakhanpal" status line. In Individual mode, the handler skips parsing `recipient_dropdown` and uses the currently selected individual contact id directly.

### 2. `hf_dashboard/templates/emails/layout/base.html` — verify, don't edit

Already responsive (viewport meta + table `max-width:640px`). No changes needed. The Explore subagent confirmed all five templates + all partials use the same base.

### 3. No other files touched

- No service / engine changes.
- No schema changes — `EmailAttachment`, `Campaign`, `EmailSend`, `Contact` all unchanged.
- No YAML / config edits.
- No CSS file edits — all styling stays inline in the page, consistent with the rest of `hf_dashboard/pages/`.

## Functions to reuse (do not reinvent)

| Existing | Location | Reused for |
|---|---|---|
| `_format_recipient`, `_parse_recipient_value` | `email_broadcast.py:46–63` | Individual contact dropdown encoding |
| `_resolve_segment_contacts` | `email_broadcast.py:66–94` | Unchanged broadcast send path |
| `_build_sample_vars_for_preview` | `email_broadcast.py:97–137` | Preview vars (desktop + mobile) |
| `_ensure_draft_campaign` | `email_broadcast.py:237–264` | Draft lazy-creation in Individual path too |
| `build_send_variables`, `load_campaign_attachments` | `services/email_personalization.py` | Unchanged |
| `render_template_by_slug`, `EmailSender`, `generate_idempotency_key` | `services/email_sender.py` | Unchanged |
| `_get_segment_contacts` | `services/flows_engine.py` | Unchanged (broadcast only) |
| `upload_file`, `delete_file` | `services/supabase_storage.py` | Unchanged |
| `COLORS` theme tokens | `shared/theme.py` | Panel/divider styling |

## Verification (per CLAUDE.md "Verification workflow")

No local runs. The flow is: commit → deploy → Playwright-drive live Space.

1. `git commit` the refactor locally.
2. `python scripts/deploy_hf.py` — uploads `hf_dashboard/` to the HF Space.
3. Wait for `https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/` to report **Running** (poll the Space's top-right status).
4. Drive the live URL headless with Playwright MCP:
   - Navigate to `/email-broadcast` (or whatever the sidebar route resolves to).
   - Screenshot (1): default state. Assert no page header, two clearly-demarcated columns, Desktop preview visible, Broadcast mode on.
   - Click the **Mobile** radio → screenshot (2). Assert the 412px device frame is rendered and the inner template is 390px wide.
   - Flip **Send to → Individual** → screenshot (3). Assert segment dropdown hides, search + contact + direct-email fields appear, invoice accordion shows the simplified per-contact body.
   - Type `sushank` in search → assert the contact dropdown populates.
   - Type a raw email in Direct email → assert it takes precedence in the send button state.
   - Flip back to **Broadcast** → assert the original broadcast flow is intact (segment dropdown populated, recipient-count card shows).
   - Open the attachment accordion in Broadcast mode → upload a dummy PDF for one segment contact → assert the success line appears and no giant recipients table renders anywhere.
5. For the actual send path (risky — real Gmail API, real contacts): do **not** click Send Now with a real segment during verification. Use **Send Test to Me** with a personal email to validate template rendering + subject + attachment flow end-to-end. Only do a real broadcast after the user explicitly confirms.
6. Report back with the three screenshots and a one-line pass/fail.

## Out of scope (explicitly)

- Template edits — already responsive.
- Any DB / schema migration.
- Any change to `services/email_personalization.py`, `services/email_sender.py`, `services/flows_engine.py`.
- Any change to other pages under `hf_dashboard/pages/`.
- Any rework of the Test Send button beyond what the new layout requires.
