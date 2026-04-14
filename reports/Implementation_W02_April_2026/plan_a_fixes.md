# Plan A — Dashboard Bug Fixes & UX

> Ship first. Pure bugs and layout fixes on the Contacts and WhatsApp Inbox pages.
> Plan B (Template Studio) lives in `plan_b_template_studio.md` as a separate sprint.

## Context

Working on the `hf_dashboard` Gradio + FastAPI app. Recent user testing surfaced a cluster of bugs and UX gaps on the Contacts and WhatsApp Inbox pages:

- Contact edit button dead (JS bridge not firing)
- Contacts table missing City / Country even though the `Contact` model has those fields
- Contacts search is case-sensitive — "john" misses "John"
- WhatsApp Inbox: three panels have uneven heights (only `.chat-panel` has `min-height`)
- No way to start a conversation with a contact that has no prior WhatsApp messages
- Messages sent from the inbox never appear in the chat view — they are posted to Meta but never persisted to `WAMessage`

All fixes reuse existing code. No new abstractions.

---

## A1. Contact edit button — drawer opens, edits don't persist

**Observed symptom (confirmed with user).** User clicks ✎ Edit on a row → drawer opens correctly pre-filled with that contact's data → user edits a field → clicks Save → nothing persists. The drawer-open path works; the save path is broken.

**Root cause.** The hidden-textbox JS bridge pattern used to shuttle the contact_id between events is **incompatible with Gradio 6's state model**.

Current flow (`hf_dashboard/pages/contacts.py:466-474`):
1. Per-row `<button onclick="hf_editContact('<cid>')">` (line 216)
2. JS bridge (`navigation_engine.py:58-74`): writes `cid` into hidden `gr.Textbox` via native setter + `input` event, then clicks hidden `edit_trigger_btn`
3. `edit_trigger_btn.click(fn=_open_edit_drawer, inputs=[edit_contact_id], ...)` — **this call succeeds** because Gradio reads the hidden textbox's live DOM value at dispatch time, so the drawer opens with the correct contact
4. User edits drawer fields, clicks Save
5. `edit_save_btn.click(fn=_save_edit, inputs=[edit_contact_id, ...])` — **this call sees an empty string** because Gradio 6's Svelte state was never mutated by the native-setter hack (only the DOM value was). On a fresh event dispatch, Gradio re-syncs from its internal state store, not the DOM, and the store still has the initial `""`
6. `_save_edit` (`contacts.py:833`) short-circuits: `if not cid: return '<div>No contact id</div>', ...`. User sees the tiny error, drawer closes on their next click, nothing saved

**Fix — replace the hidden Textbox with `gr.State`.** `gr.State` is a Python-side-only value that persists across events without touching the DOM, so there's no setter-vs-store mismatch. The drawer-open handler writes to it; the save handler reads from it.

Implementation changes in `hf_dashboard/pages/contacts.py`:

1. **Replace** hidden textbox at line 466-470:
   ```python
   # before:
   edit_contact_id = gr.Textbox(value="", show_label=False, container=False,
       elem_id="hf-edit-contact-id", elem_classes=["hf-bridge-hidden"])
   # after:
   edit_cid_state = gr.State("")
   ```

2. **Update** `_open_edit_drawer` (line 565) to **return** the cid as its first output:
   ```python
   return (
       contact_id,                                              # edit_cid_state (NEW)
       gr.update(elem_classes=_MODAL_OPEN["edit"]),             # edit_panel
       title, ...                                                # rest unchanged
   )
   ```

3. **Update** `_edit_drawer_outputs` (line 649) to start with `edit_cid_state`:
   ```python
   _edit_drawer_outputs = [
       edit_cid_state, edit_panel, edit_title_html,
       edit_first, edit_last, edit_phone, edit_email, edit_company,
       ...
   ]
   ```

4. **Update** hidden trigger button's click so its `js` pulls the pending cid from `window` and returns it to Python as the input. No hidden textbox needed:
   ```python
   edit_trigger_btn = gr.Button("trigger", elem_id="hf-edit-trigger-btn",
                                 elem_classes=["hf-bridge-hidden"])
   edit_trigger_btn.click(
       fn=_open_edit_drawer,
       inputs=None,
       js="() => { const cid = window.__hfPendingEditCid || ''; "
          "window.__hfPendingEditCid = ''; return [cid]; }",
       outputs=_edit_drawer_outputs,
   )
   ```
   Gradio's `js=` return value is used as the input tuple for `fn`. This is the supported Gradio-6 way to pass a frontend-only value to a Python handler.

5. **Update** per-row Edit button markup (line 215-219). It no longer needs to write to any DOM element — it just parks the cid on `window` and clicks the hidden trigger:
   ```html
   <button class="hf-row-edit-btn"
           onclick="window.__hfPendingEditCid='{contact.id}';
                    document.querySelector('#hf-edit-trigger-btn button').click();">
     ✎ Edit
   </button>
   ```
   No more `window.hf_editContact` function wrapper. No more native-setter hack. No more retry-on-missing textbox.

6. **Update** `edit_save_btn.click` inputs (line 910) to read from `edit_cid_state` instead of the removed `edit_contact_id` — everywhere `edit_contact_id` appears in the file, replace with `edit_cid_state`:
   ```python
   edit_save_btn.click(
       fn=_save_edit,
       inputs=[edit_cid_state, edit_first, edit_last, ...],
       outputs=[...],
   )
   add_note_btn.click(
       fn=_add_note,
       inputs=[edit_cid_state, new_note_input],
       outputs=[...],
   )
   ```

7. **Delete dead code in `navigation_engine.py`:**
   - The `_HF_BRIDGE_JS` constant and its `app.load(fn=None, ..., js=_HF_BRIDGE_JS)` call at line 228 — no longer needed
   - The `app.css = DASHBOARD_CSS` and `app.theme = gradio_theme` lines at `navigation_engine.py:96-97` — these are **silently ignored** in Gradio 6 (verified: `gr.Blocks.__init__` lists `theme`, `css`, `js`, `head`, `head_paths` as `deprecated_params`). CSS currently works only because `mount_gradio_app(css=DASHBOARD_CSS)` is passed in `app.py:130`. Cleanup, not a behavior change.

**Why this works.** `gr.State` is the Gradio-native way to pass values between events without going through the DOM. The `js=` return on a Button click is the Gradio-native way to pump a frontend-only value into a Python handler as an input. Combining them sidesteps both the deprecated `Blocks(head=...)` path and the Svelte-state-sync bug entirely.

**Files:**
- `hf_dashboard/pages/contacts.py` — replace hidden Textbox with `gr.State`, update `_open_edit_drawer` outputs, update `edit_trigger_btn.click` to use `js=`, update per-row button HTML, rename `edit_contact_id` → `edit_cid_state` in all handler inputs
- `hf_dashboard/engines/navigation_engine.py` — delete `_HF_BRIDGE_JS` constant, the `app.load(..., js=...)` call at line 228, and the dead `app.css =` / `app.theme =` lines at 96-97

**Browser-level sanity check during implementation.** Open DevTools Console on the Contacts page, click Edit, then:
- Before save: `JSON.stringify(gradio_client_state)` or inspect the `edit_cid_state` value via the Gradio network payload when the Save button is clicked — it should contain the cid
- Click Save, watch the network tab for the `/gradio_api/call/_save_edit` POST — confirm `cid` is the first argument in the payload, not `""`

**Verification:** open Contacts, click ✎ Edit on any row, drawer opens pre-filled; change first name; click Save; green "Saved" toast appears; drawer closes; the row in the table shows the new first name without a page refresh. Repeat for email, company, country, lifecycle, tags, and notes — all fields should round-trip.

---

## A2. Contacts table missing city / country

**Root cause.** `Contact` model (`services/models.py:41-88`) already has `city`, `state`, `country`, `postal_code`, `website`. The limitation is purely in `config/pages/contacts.yml` (9 columns listed). `_build_table` at `pages/contacts.py:220-222` has a generic `getattr` fallback for unknown fields — **no code changes needed**.

**Fix.** Edit `hf_dashboard/config/pages/contacts.yml` only:
- Add `city` column (width ~7%)
- Add `country` column (width ~7%)
- Rebalance widths so total = 100% (shrink email to 14%, tags to 10%, segments to 10%)

Scope: **city + country only** (not website or state).

**Verification:** reload Contacts page, confirm two new columns render values from the DB.

---

## A3. Case-insensitive search + filter-expansion recommendation

**Root cause.** `pages/contacts.py:91-96` uses SQLAlchemy `.like(term)` which is case-sensitive on PostgreSQL (and on SQLite with `PRAGMA case_sensitive_like=ON`). The code already searches first_name, last_name, company, and email — but misses all mixed-case rows.

**Fix.** Replace the 4 `.like(term)` calls with `.ilike(term)`:

```python
q = q.filter(
    Contact.email.ilike(term) | Contact.first_name.ilike(term) |
    Contact.last_name.ilike(term) | Contact.company.ilike(term)
)
```

**Filter expansion recommendation:** **Do not expand.** Name + email + company already covers 95% of real-world lookups. Adding phone, city, tags to free-text search makes the query slower and the UX noisier (irrelevant hits). The existing sidebar filters already cover country, segment, lifecycle, channel, and tags explicitly — use those for structured filtering. If later demand appears for "search by phone", add a small prefix like `phone:98765` rather than lumping it into the free-text search.

**Verification:** search "john" → finds "John Smith"; search "Nepal" → finds "Nepal Textiles" in the company field.

---

## A4. WhatsApp Inbox — panel heights mismatch

**Root cause.** `shared/theme_css.py:413-472`:
- `.chat-panel` has `min-height: calc(100vh - 160px)` and `display:flex`
- `.conv-list-panel` and `.tools-panel` have **no min-height** — they collapse to content.

**Fix.** Edit `hf_dashboard/shared/theme_css.py`:
- Add `min-height: calc(100vh - 160px)` + `display:flex; flex-direction:column` to `.conv-list-panel` and `.tools-panel`
- Add an inner `overflow-y:auto; flex:1 1 auto` scroll wrapper so content doesn't overflow the box

No Python changes required.

---

## A5. WhatsApp Inbox — add "Start New Conversation" section

**Root cause.** `pages/wa_inbox.py:38-65` (`_get_active_conversations`) only returns contacts with existing WAMessage rows. Panel 1 never exposes contacts without prior chats, so the user cannot initiate a first conversation from the UI.

**Fix.** Split Panel 1 into two vertically stacked sections:

```
┌─ Panel 1 ─────────────┐
│ Active Chats          │  ← existing list (search inside active)
│   [search] [radio…]   │
│ ─────────────────     │
│ Start New             │  ← new section
│   [search] [radio…]   │  ← queries all Contacts by name/company
└───────────────────────┘
```

Implementation in `hf_dashboard/pages/wa_inbox.py`:
- New helper `_search_all_contacts(db, term)` that queries `Contact.wa_id.isnot(None)` AND `(Contact.first_name.ilike(f"%{term}%") | Contact.last_name.ilike(...) | Contact.company.ilike(...))` and returns `[(label, id), ...]` — reuses the label builder from `_get_active_conversations`. **Filter: only contacts with a non-null `wa_id`** — you can't message someone who isn't WhatsApp-capable, and it keeps the list short.
- New `new_conv_search = gr.Textbox(...)` + `new_conv_radio = gr.Radio(...)` below the existing Active Chats widgets
- Wire `new_conv_radio.change` to call the same `_on_select(contact_id)` handler (lines 197-210) so Panels 2 and 3 behave identically regardless of which list the user selected from
- Also mirror the selection back into `conversation_radio` via `gr.State` so Send Text/Send Template handlers (lines 261, 281) continue to work unchanged

**Charge warning for new conversations.** The existing `_build_chat_messages` (lines 109-162) already shows a window warning when `last_wa_inbound_at` is missing. Extend that banner so, when there are zero WAMessage rows for this contact, it reads:
> "⚠ No conversation yet. Sending a template will open a 24-hour service window and incur a conversation fee per WhatsApp pricing (category-dependent)."

Pull copy from a new YAML key `page.column_2.new_conversation_warning.detail` in `config/pages/wa_inbox.yml` so it stays editable.

**Gradio constraint.** Two `gr.Radio` widgets inside the same column is fine; they're just independent inputs. Using `gr.State` as a shared "selected contact" channel is the cleanest cross-radio coordination pattern.

---

## A6. Sent WA messages don't appear in the chat view ⚠ CRITICAL

**Root cause.** `pages/wa_inbox.py:234-261` (`_send_text`) and `263-281` (`_send_tpl`) call `WhatsAppSender` but **never persist the outbound row**. Compare with `services/broadcast_engine.py:414-421` which does it correctly.

**Fix** (both handlers):
1. On successful send, insert `WAMessage(chat_id=..., contact_id=cid, direction="out", status="sent", wa_message_id=msg_id, text=msg_or_preview)` — use the template's `body_text` as `text` for template sends
2. Upsert the `WAChat` row: set `last_message_at = now`, `last_message_preview = text[:100]`
3. Set `contact.last_wa_outbound_at = now`
4. `db.commit()`
5. Change the handler return signature to also output refreshed `chat_messages` HTML by calling `_build_chat_messages(db, cid)` again
6. Clear the `msg_input` textbox after success
7. Wire the extra outputs in `send_btn.click(...)` at line 261 and `send_tpl_btn.click(...)` at line 281
8. **Auto-scroll to bottom**: Gradio 6's `gr.HTML` sanitizes `<script>` tags out of user-supplied content by default, so an inline `<script>` inside the rendered chat HTML will NOT execute. Use one of these instead:
   - **Preferred — CSS only**: give `.chat-messages-slot` `display: flex; flex-direction: column-reverse;` and reverse the iteration order of messages in `_build_chat_messages` (emit newest-first). Browser-native "pin to bottom" behavior, zero JS.
   - **Fallback — one-shot JS via Button `js=`**: after send, return `gr.update(value=...)` for the chat HTML as usual, but also fire a zero-input button `.click` whose `js=` is `() => { const el = document.querySelector('.chat-messages-slot'); if (el) el.scrollTop = el.scrollHeight; return []; }`. Slightly more plumbing but works without touching the message-ordering logic.
   - Verify during implementation that scripts inside `gr.HTML` are actually stripped by the installed Gradio 6.12 before committing to the CSS path.

**Verification:** select an active chat → type a message → click Send → message bubble appears immediately in the chat view, input clears, status shows "Sent ✓".

---

## Files touched

- `hf_dashboard/pages/contacts.py` (A1 — hidden Textbox → `gr.State`, per-row button markup, handler inputs renamed; A3 — `.like` → `.ilike`)
- `hf_dashboard/engines/navigation_engine.py` (A1 — delete `_HF_BRIDGE_JS`, the `app.load(js=...)` call, and the dead `app.css =` / `app.theme =` lines)
- `hf_dashboard/config/pages/contacts.yml` (A2 — add `city` + `country` columns, rebalance widths)
- `hf_dashboard/shared/theme_css.py` (A4 — `min-height` + flex on `.conv-list-panel` and `.tools-panel`)
- `hf_dashboard/pages/wa_inbox.py` (A5 — Start New Conversation section; A6 — persist outbound `WAMessage` + upsert `WAChat` + refresh chat HTML + auto-scroll)
- `hf_dashboard/config/pages/wa_inbox.yml` (A5 — `new_conversation_warning` copy)

## Deployment & verification workflow

**Hard rule: do NOT run the app locally.** The verification path is deploy-to-HF-Spaces first, then drive the live URL with the Playwright MCP tools in headless mode. Only hand off to the user after every Playwright check has passed.

### Step 1 — Deploy to Hugging Face Spaces

1. Commit Plan A changes on a single branch with a descriptive message (e.g. `Plan A: contacts edit fix, city/country, ilike search, WA inbox fixes`)
2. Push to the HF Spaces remote — the Space rebuilds automatically on push
3. Poll the Space status (via `gh`/curl on the Space's `/api/spaces/<owner>/<name>` endpoint, or visually check `https://huggingface.co/spaces/<owner>/<name>` runtime status) until the runtime transitions to `RUNNING`. **Do not start Playwright until the build is green.**
4. Note the live URL (typically `https://<owner>-<space-name>.hf.space`) — this is the target for every subsequent `browser_navigate` call

### Step 2 — Playwright MCP verification (headless, on the live HF Space URL)

All checks below use the `mcp__playwright__browser_*` tools. Run them in order. For each step, capture a screenshot via `browser_take_screenshot` and keep the console log from `browser_console_messages` so failures are debuggable. If a check fails, **stop** and report — do not continue to the next check, do not hand off.

**Preflight**
- `browser_navigate` → live HF Space URL
- If the app has auth (`APP_PASSWORD` set), `browser_type` into the password input and click Login
- `browser_snapshot` → confirm the sidebar + default page render
- `browser_console_messages` → confirm zero errors at rest

**A1 — Contact edit Save round-trip**
- `browser_click` the Contacts sidebar item → `browser_snapshot` the table
- `browser_click` the ✎ Edit button on the first row
- `browser_wait_for` the drawer to be visible (look for "Edit ·" title)
- `browser_snapshot` → confirm drawer is pre-filled with that contact's name, email, company
- `browser_fill_form` or `browser_type` → change First Name to `<name>-TEST-A1` (unique marker to avoid collision with existing data)
- `browser_click` **Save changes**
- `browser_wait_for` the drawer to close AND the row in the table to show the new first name
- `browser_snapshot` → confirm the first-name change is visible in the table row
- `browser_evaluate` → `document.querySelector('.contacts-table-host table').innerText.includes('TEST-A1')` should be `true`
- **Cleanup**: open the drawer again, revert the change to the original name, Save — leaves the DB in its pre-test state
- `browser_console_messages` → should have no errors like "No contact id"

**A2 — city + country columns**
- On Contacts page, `browser_evaluate` → query the `<thead>` cells: `[...document.querySelectorAll('.contacts-table-host thead th')].map(e => e.innerText)` → must include `City` and `Country`
- `browser_snapshot` → visually confirm both columns render values (non-empty for rows that have them, the "Missing" placeholder otherwise)

**A3 — case-insensitive search**
- `browser_type` "JOHN" (all caps) into the search box → `browser_wait_for` table to refresh
- `browser_evaluate` row count: if there's a lowercase-"john" row in the DB, at least one row must appear
- `browser_type` clear search → `browser_type` a partial company match in wrong case (e.g. "TEXTILE" if "Textile" exists) → rows appear
- Clear search before moving on

**A4 — panel heights**
- `browser_click` the WhatsApp Inbox sidebar item → `browser_snapshot`
- `browser_evaluate` → compute `.getBoundingClientRect().height` of `.conv-list-panel`, `.chat-panel`, `.tools-panel` → all three heights must be equal (tolerance: within 4px for sub-pixel rendering)
- `browser_take_screenshot` → visual confirmation

**A5 — Start New Conversation**
- `browser_snapshot` the WA inbox → confirm both "Active Chats" and "Start New" sections are visible in Panel 1
- `browser_type` a known contact name (with mixed case) into the Start New search box → `browser_wait_for` radio options to appear
- `browser_click` the first matching radio option
- `browser_snapshot` → Panel 2 must show the chat view with the "No conversation yet" charge-warning banner
- `browser_evaluate` → the warning text includes the string "conversation fee" (or whichever phrase ends up in the YAML)

**A6 — Sent message persistence + auto-scroll** ⚠ Only run if a **test contact inside an open 24h window** exists in the deployed DB. Otherwise mark this step as "skipped — requires live test contact" in the handoff report and request the user verify it manually. Do NOT send WhatsApp messages to arbitrary real contacts from CI.
- `browser_click` an active chat whose `last_wa_inbound_at` is within 24h
- `browser_type` `A6 playwright verification <timestamp>` into the chat input → `browser_click` Send
- `browser_wait_for` a green "Sent ✓" status AND a new outbound bubble containing that exact text in the chat view
- `browser_evaluate` → `document.querySelector('.chat-messages-slot').scrollTop >= document.querySelector('.chat-messages-slot').scrollHeight - document.querySelector('.chat-messages-slot').clientHeight - 4` → auto-scroll confirmed (within 4px of bottom)
- `browser_take_screenshot` → attach to handoff report

### Step 3 — Hand off

Once every check above passes, compose the handoff message for the user:
- Live HF Space URL
- Git commit SHA deployed
- A numbered list of the six checks with ✅ / ⚠ (skipped) / ❌ status
- Inline screenshots from `browser_take_screenshot` for each passing check
- Any console errors captured by `browser_console_messages`

If **any** check fails, do not hand off. Instead: roll back the commit or push a follow-up fix, re-deploy, re-run Playwright, and only hand off when all checks are green.

## User decisions (locked in)

- **A1 symptom** (user-confirmed): drawer opens, edits don't persist on Save. Fix is to replace the hidden-textbox JS bridge with `gr.State` + a `js=`-return on the trigger button.
- **Auto-scroll** after sending: yes. Preferred path is CSS `flex-direction: column-reverse` (no `<script>` injection, which Gradio 6 strips from `gr.HTML`); fallback is a button-click `js=` scroll snippet.
- **New-chat list** filter: contacts with non-null `wa_id` only.

## Gradio 6 compatibility notes (verified against installed version 6.12.0)

- `gr.Blocks.__init__` in Gradio 6 lists `theme`, `css`, `css_paths`, `js`, `head`, `head_paths` as **`deprecated_params`** — accepted as kwargs but silently ignored with a `UserWarning`. The correct injection points are `gr.mount_gradio_app(...)` (for `head`, `js`, `css`) or `Blocks.launch(...)`.
- `mount_gradio_app` in `app.py:125-131` **does** accept `head=` and `js=` in 6.x — verified via `help(gradio.mount_gradio_app)`.
- `gr.Button.click(fn=..., js="() => {...; return [val]}", inputs=None, outputs=...)` passes the JS return value as the positional inputs for the Python handler. This is the canonical way to pump a browser-only value (e.g., a globally-stashed `window.__hfPendingEditCid`) into a backend event without using a hidden Textbox.
- `gr.HTML` sanitizes `<script>` tags by default in Gradio 6. Any "inline script inside the HTML value" approach will be a no-op. Use CSS or a button-click `js=` instead.
- The existing `app.css = DASHBOARD_CSS` and `app.theme = gradio_theme` lines at `navigation_engine.py:96-97` are **dead code** — they have no effect. CSS only works because it's also passed via `mount_gradio_app(css=DASHBOARD_CSS)` in `app.py:130`. Safe to delete while touching that file.
