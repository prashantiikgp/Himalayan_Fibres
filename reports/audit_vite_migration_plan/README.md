# Himalayan Fibres Dashboard — Audit & Vite + Shadcn Migration Plan

**Author:** Claude (audit pass)
**Date:** 2026-05-04
**Scope:** Full audit of the Gradio dashboard at `hf_dashboard/`, identification of UX / UI / logic issues, and a phased plan for migrating the front-end to Vite + Shadcn (modeled on the PortalAgent architecture) while keeping the FastAPI backend intact.

---

## 0. Executive summary

The current Hugging Face Space runs a **FastAPI + Gradio** dashboard out of `hf_dashboard/`. The Gradio UI was the right choice early — it let us ship a working ops surface for email + WhatsApp marketing in weeks, not months — but the system has now outgrown the framework. There are 9 nav pages totalling **~6,400 lines** of Python; an estimated 30-40% of that is inline HTML f-strings (the rest is event handlers, DB queries, and state management). Five separate workarounds for Gradio mounting / state-sync bugs are commented in-line throughout `pages/contacts.py`, `wa_inbox.py`, `email_broadcast.py`.

The team's three running pain-points all map cleanly to Gradio's structural limitations:

1. **"Templates don't render their fields properly"** → likely cause traced: variable inputs *are* captured (5 slots allocated, 4 used by `order_confirmation`), and the constrained `tp-vars-box` height in `theme_css.py` plausibly forces them into an invisible scroll. **Reproduce on the live Space with Playwright before sizing the fix** — the CSS analysis is sound but pixel-level behavior depends on viewport. (See `B1` in §4.)
2. **"WhatsApp broadcast page doesn't show the audience clearly"** → confirmed: the audience funnel is computed (`broadcasts.py::_render_audience_kpis`) but rendered in the *left* column under all the filter controls, while the right column leads with cost KPIs. There is no "Targeting **N** people in **Segment X**" headline at the top. (See `B3`.)
3. **"Can't start a chat with a simple message"** → this one is a **WhatsApp Business API constraint**, not our bug — Meta refuses outbound text messages outside the 24-hour customer-service window. The dashboard already enforces this, but it lets the user *type* a message and *then* errors on send, which feels like a bug. (See `B2`.)

**Recommendation: rebuild the front-end as a separate `vite_dashboard/` workspace using Vite + React + Shadcn UI**, deployed to a *second* HF Space alongside the existing one. Migrate page-by-page in priority order. Keep the entire `hf_dashboard/services/`, `engines/`, `loader/`, `templates/` Python code untouched and expose it through a thin JSON API surface (`/api/v2/*`) on the same FastAPI app. Once feature parity is reached, the Gradio Space is decommissioned.

Estimated effort: **6.5-12 weeks of focused work** for a single developer (the lower bound assumes the developer has shipped a Shadcn + TanStack Query project before; the upper bound assumes learning-on-the-job). Broken into a foundation phase, a bug-reproduction phase, and 5 page-migration phases. Each phase is independently shippable to its own HF Space, so there is never a "big bang" cutover.

---

## 1. Current state — page inventory

The 9 navigation entries (declared in `hf_dashboard/config/dashboard/sidebar.yml`):

| # | Nav id | Label | File | LOC | Channel | Notes |
|---|---|---|---|---|---|---|
| 1 | `home` | Home | `pages/home.py` | 385 | mixed | KPIs + lifecycle bars + activity feed; uses Plan D `@ttl_cache` |
| 2 | `contacts` | Contacts | `pages/contacts.py` | 1,095 | mixed | Filters + table + add/import/edit modals; JS-bridge for row-edit |
| 3 | `wa_inbox` | WhatsApp | `pages/wa_inbox.py` | 998 | WA | 3-panel: Conversations / Chat / Tools-with-templates |
| 4 | `broadcasts` | WhatsApp Broadcasts | `pages/broadcasts.py` | 790 | WA | Audience funnel + cost KPIs + preview |
| 5 | `broadcast_history` | History | `pages/broadcast_history.py` | 260 | mixed | Status sidebar + table; channel filter is broken (B6) |
| 6 | `email_broadcast` | Email Broadcast | `pages/email_broadcast.py` | 1,104 | email | Broadcast + Individual modes + invoice attach |
| 7 | `email_analytics` | Email Analytics | `pages/email_analytics.py` | 408 | email | KPI strip + tab + campaign detail + recipient table |
| 8 | `flows` | Flows | `pages/flows.py` | 184 | mixed | Flow picker + segment + start; minimal |
| 9 | `wa_template_studio` | Template Studio | `pages/wa_template_studio.py` | 1,188 | WA-only | List + editor form + phone preview + Meta sync |
| | | | **TOTAL** | **6,412** | | |

Sidebar grouping today: `home → contacts → [wa_inbox, broadcasts, broadcast_history] → [email_broadcast, email_analytics, flows, wa_template_studio]`. Note that **Template Studio is WA-only but lives outside the WA group** at the bottom of the sidebar — a small but real consistency issue.

---

## 2. How each page is built (per-page audit)

### 2.1 Home (`pages/home.py`, 385 LOC)

**Purpose.** Single-screen dashboard surface — connection status, two KPI rows, lifecycle progress bars, recent activity feed, getting-started + system info.

**Implementation.**
- Page-level YAML at `config/pages/home.yml` provides labels and the activity-icon map.
- Three TTL-cached helpers: `_home_counters_cached` (single batched COUNT/SUM via `case(...)` aggregation), `_lifecycle_counts_cached` (single `group_by(lifecycle)`), `_activity_feed_cached` (combined EmailSend + WAMessage feed). Buckets defined in `config/cache/ttl.yml`.
- Status row reads `GMAIL_REFRESH_TOKEN` and `WA_TOKEN` env vars to render green/red dots.
- Lifecycle bars iterate `services.contact_schema.get_lifecycle_stages()` and render inline-styled HTML progress bars.

**Issues.**
- Pure inline-HTML construction — every visual element is an f-string with hardcoded RGB colors. Looks fine but is ~150 lines of HTML out of 385.
- The *Getting Started* and *System* cards on the right show **stale hardcoded counts** ("Templates: 7 email, 13 WA. Daily limits: 500 email, 1000 WA"). Both numbers are baked into the f-string at line 366-367. As soon as you add/remove a template, the dashboard lies.
- "Active flows" math: `_home_counters_cached` does the count, but the activity feed never includes flow events.
- The status row at the top uses 12px font and tiny dots — easy to miss. Likely the most actionable info on the page is the least visible.

**v2 sketch.** Replace with a `<DashboardGrid>` component: top status strip, two `<KpiRow>` rows, a `<LifecycleBars>` card, an `<ActivityFeed>` card. All data comes from one new endpoint `GET /api/v2/dashboard/home` returning the cached payload as JSON.

---

### 2.2 Contacts (`pages/contacts.py`, 1,095 LOC)

**Purpose.** The CRM-ish surface: filter contacts by segment / lifecycle / country / channel / tags / search; paginate; add new contacts; import CSV/Excel; edit per-contact (Profile / Tags / Notes / Activity).

**Implementation.**
- Filters in left column, table + top bar (search / Add / Import) + footer (pagination) on right.
- Two modal overlays (Add Contact, Import Contacts) and one drawer (Edit Contact) — all toggled via CSS class swap (`hf-modal-closed`) instead of `visible=` because Gradio's `visible=False → True` race orphans Svelte components.
- Edit drawer has tabs: Profile / Tags / Notes (threaded via `ContactNote` model) / Activity (timeline from `services.interactions.get_interactions`).
- **Plan D Phase 1.3 optimization:** the table query uses `with_entities(...)` to pull only 15 of the 38 Contact columns. Comments document the egress reduction (~60% bytes/render).
- **Row-edit JS bridge:** the Edit button on each table row writes the contact_id into a hidden Textbox via `Object.getOwnPropertyDescriptor(...).value setter`, dispatches an `input` event, waits 80ms, then clicks a hidden trigger button. This is the only way to do row-level actions in Gradio without re-rendering the whole table.
- **Tag autocomplete:** `gr.Dropdown(allow_custom_value=True)` with all existing tags as choices.
- Segments computed in Python via `segments_for_contact(c, all_segments)` (rules engine evaluating against already-loaded ORM rows, no extra queries).

**Issues.**
- **JS bridge is fragile.** Comments document at least two prior attempts that broke (Svelte store sync issue → switched to native setter; the "load contact" transaction took >2s in some cases → added `time.time()` logging). React solves this entirely with `onClick={() => openDrawer(contact.id)}`.
- **Modal mount race.** `hf-modal` + `hf-modal-closed` CSS toggle sidesteps a Gradio bug, but the comments make clear this took several iterations to land.
- **Segment matching displays per-contact pills.** Cool feature, but evaluating 11 active segment rules × 50 visible contacts on every filter/page change is borderline. Currently amortized by the 5-min `get_active_segments_cached`, but it's still Python-side rule eval per render.
- **Table renders inline `<table>` with hover via inline JS** (`onmouseover="this.style.background='...'"`). Would be a single CSS class in v2.
- **Pagination control is awkward** — `gr.Number` for page input + Prev/Next buttons. Not keyboard-friendly.
- **Country dropdown has 200+ entries** but no typeahead in Gradio's default Dropdown (it does have client-side filter, but the ergonomics are poor at scale).
- The download-all-CSV button leaks no progress feedback on big tables; for 10k+ contacts the user thinks it hung.

**v2 sketch.** A standard CRM table:
- `<DataTable>` (TanStack Table) with column visibility toggle, virtualized rows, sticky header, sortable columns, multi-select with bulk actions in a sticky footer.
- Filters as a `<FilterBar>` above the table; URL-syncs (`?segment=domestic_b2b&lifecycle=engaged_lead&page=2`) so filters survive reloads and are shareable.
- `<ContactDrawer>` opened by row click — same Profile / Tags / Notes / Activity tabs, but rendered as a Shadcn `<Sheet>` component.
- CSV download as a streaming endpoint with toast progress.

---

### 2.3 WhatsApp Inbox (`pages/wa_inbox.py`, 998 LOC)

**Purpose.** The team's most-used page. Three-panel chat surface:
1. **Panel 1** — Active Chats list + Start New Conversation list (each with its own search box).
2. **Panel 2** — Chat header + bubbles + input row (text, attach, send) + attachment modal.
3. **Panel 3** — Refresh button + past activity (compact) + Category & Template dropdowns + variable input slots + filled-template preview + Send Template.

**Implementation.**
- Pre-allocates **5 variable input slots** (`MAX_VARS = 5`) at build time, sets them all `visible=False` on first refresh, then selectively shows / labels them per template via `_on_template_change`.
- Plan D Phase 1.1 optimization: the "active conversations" list is now one JOIN query (Contact + WAChat) instead of `1 + 2N` queries. Comment notes the previous load was ~100 queries per page render.
- Plan D Phase 1.4: search boxes use `.submit` (Enter key) instead of `.change` (per keystroke) — was previously firing a DB query per character.
- 24-hour-window awareness: `_build_chat_header` reads `Contact.last_wa_inbound_at`, computes time-remaining or "closed" status, renders a green/amber chip in the chat header.
- New-conversation banner: when the picked contact has zero `WAMessage` history, a yellow warning explains that sending a template will open a billable 24h window.
- Send paths split into `_send_message` (text or media, requires open window) and `_send_tpl_filled` (template, bypasses window).
- Media uploads: client picks file → modal opens → file saved locally → `WhatsAppSender.upload_media()` to Meta → Meta returns `wa_media_id` → `send_media()` references it.

**Issues — the user's reported ones, and what they actually are.**
- **B1 — "templates don't render fields properly."** Confirmed scroll bug. CSS at `theme_css.py:754`:
  ```css
  .tools-panel .tp-vars-box {
      flex: 1 1 auto !important;
      min-height: 0 !important;
      overflow-y: auto !important;
      padding: 2px 0 !important;
  }
  ```
  The vars box is sandwiched between the refresh hint, the activity box (`flex: 0 0 16%`), the filter row, the preview box (`flex: 0 0 22%`), and the Send button. With those constraints, the vars area gets ~30-35% of the panel — enough for ~2 visible Textboxes before scroll engages. Dark-theme scrollbar is near-invisible, so users assume the missing fields are absent. **Fix:** in v2, render variables in a non-scrolling stack and shrink the preview box to fit. Or use a separate "Compose template" sheet entirely.
- **B2 — "can't start with a simple message."** Not our bug. WhatsApp Business API enforces this server-side; we already detect it client-side and show "Outside 24h window — use a template" or "No inbound yet — use a template". The UX problem is that the text composer is **enabled** when sending isn't possible, so users type a message and feel betrayed when it fails. **Fix:** disable the text input when no open window exists; show a contextual "Send a template to open a conversation" CTA in its place; surface the Template panel as the primary action.

**Other issues.**
- Three-panel layout with `scale=1+2+2 = 5` and `min_width=240+380+320` means **940px content-area minimum** before scrollbars. iPad portrait (768px) is unusable.
- Auto-refresh is **manual only** — there's a refresh button + the nav engine fires `_do_refresh` on tab click, but no polling. New inbound WhatsApp messages don't appear until you click. The webhook updates the DB, but the page doesn't know.
- Search boxes for Active vs Start-New are visually identical, easy to confuse. Plus they live in the *same column*, so the user has to scroll past the active list to reach Start-New.
- The `_avatar_for(contact_id)` deterministic emoji is cute but renders inconsistently across browsers (some emoji fonts have the fox glyph, some don't).
- Attachment modal is a separate `gr.Column(visible=False)` — same modal-mount issue noted above.
- Send Template + Send Text use **completely separate handlers** (`_send_tpl_filled` vs `_send_message`) which duplicates ~80 lines of WAChat / WAMessage / contact-update boilerplate.

**v2 sketch.** Two-pane layout (conversations left, chat right) on desktop; chat-only with conversations as a slide-over on tablet/phone. The "tools panel" → a `<Sheet>` opened from a "Send template" button in the composer area when the 24h window is closed (or always, as a power-user shortcut). Real-time inbound updates via Server-Sent Events from a `/api/v2/wa/inbox/stream` endpoint that listens on the same DB row WebSocket the webhook already touches.

---

### 2.4 WhatsApp Broadcasts (`pages/broadcasts.py`, 790 LOC)

**Purpose.** Compose a one-shot WhatsApp template send to a filtered audience. Audience filters: segment / countries / tags / lifecycles / consents / max_recipients. Template picker (MARKETING-only — transactional templates are ineligible because their variables need per-order data). Cost preview. Test-send to one contact. Send to all.

**Implementation.**
- Two columns: left = Audience + Message, right = 4 cost KPIs + preview + Send/Test buttons.
- `_render_audience_kpis` shows a 3-cell funnel (Segment total / WhatsApp-eligible / Final) plus a 4-block breakdown (Geography / Lifecycle / Consent / Customer Type) when final > 0.
- `_render_cost_kpis` reads pricing from `config/whatsapp/pricing.yml` via `services.broadcast_engine.estimate_cost`. Per-message cost depends on category (MARKETING vs UTILITY) and country.
- Preview has a **Template view** (placeholders highlighted yellow) / **Rendered view** (first contact's values substituted, highlighted green) toggle.
- Template choices filter to MARKETING-only at `_wa_template_choices`.
- Sends via `services.broadcast_engine.send_broadcast(db, name, "whatsapp", template_id, filters)` which writes a `Broadcast` row and an `EmailSend`-equivalent per-recipient send log.

**Issues.**
- **B3 — audience target buried.** The funnel cells are in the left column under all the filters; the right column leads with cost. There is no top-of-page "**N** people targeted" headline. **Fix:** in v2, surface "Targeting **245** people in **Engaged Domestic B2B**" as a sticky banner above the editor.
- Country dropdown is locked to `["India"]` with help text saying "WhatsApp is only supported for India in your current setup" — but the dropdown is multiselect anyway, which is confusing.
- The `_test` button sends a real test to the first matching contact. There's no "send to my own number" affordance — you have to know which contact you'll get.
- The `BroadcastFilters` dataclass duplicates parameters that the segment rules would already evaluate. E.g., picking "Engaged Domestic B2B" already implies `geography in [India, ...]`, but the page still asks the user to also pick countries.
- Preview is **right-rail at 720px min-height** even when the template body is two lines. Wastes vertical space on smaller screens.

**v2 sketch.** A single-page wizard-ish layout:
1. **Step 1 — Audience.** Segment picker, optional refinements (lifecycle / consent), max recipients slider. Live "Targeting N" headline updates as you change filters.
2. **Step 2 — Message.** Template picker. Variables pre-filled from contact data, editable as overrides. Phone-mockup preview side-by-side.
3. **Step 3 — Send.** Cost summary, schedule-now or schedule-later (new feature), Send button.

This becomes the same structure as the Email Broadcast page in v2 — a unified `<Composer>` component parameterized by channel.

---

### 2.5 Broadcast History (`pages/broadcast_history.py`, 260 LOC)

**Purpose.** Browse past broadcasts, filterable by status (All / Draft / In Progress / Completed / Failed) and channel (All / WhatsApp / Email).

**Implementation.**
- Reads from `Broadcast` table only.
- 5 status-summary cells at the top + filtered table below.

**Issues.**
- **B6 — Email channel filter is broken.** Email broadcasts initiated via `pages/email_broadcast.py` write to the `Campaign` + `EmailSend` tables, **not** to `Broadcast`. WhatsApp broadcasts write via `services.broadcast_engine.send_broadcast` → `Broadcast`. So this page's "Email" channel filter always returns zero rows. Email send history actually lives on the **Email Analytics** page (under tabs labeled Sent / Scheduled / Drafts). The two pages cover overlapping but disjoint datasets.
- "Scheduled" status is in the email side but not visible here — broadcasts.py never sets `status="scheduled"` because there is no scheduler.
- The "Channel" column shows phone/email emoji + label, but channel-switching in the filter still shows the old data until refresh.
- 5 status pills + 3 channel pills + 1 table = a lot of UI for what is essentially a list-with-filters.

**v2 sketch.** **Merge into the Broadcasts page** as a "History" tab. One unified data source — the API returns rows from both `Broadcast` and `Campaign` tables, normalized into a single shape. Status filter spans all known statuses (incl. Scheduled when we add scheduling). This also kills `broadcast_history.py` entirely as a separate nav item.

---

### 2.6 Email Broadcast (`pages/email_broadcast.py`, 1,104 LOC)

**Purpose.** Compose and send templated emails to a segment **OR** to a single contact. Optional per-recipient PDF invoice attachment. Test-send to your own email.

**Implementation.**
- Mode toggle: "Broadcast" vs "Individual" radio.
- Broadcast mode: segment dropdown → audience KPI → recipient sub-picker (for invoice attachment).
- Individual mode: search-by-name dropdown OR direct-email input. If an email doesn't match a Contact, an `adhoc_<uuid>` Contact row is upserted.
- Template picker drives a dynamic variable editor: pre-declares 6 short Textbox slots + 2 textarea slots (`MAX_VAR_SLOTS_SHORT=6`, `MAX_VAR_SLOTS_LONG=2`). On template change, `_build_slot_updates(meta)` re-labels the slots from the meta YAML at `config/email/templates_seed/{slug}.meta.yml`.
- Subject auto-fills from `EmailTemplate.subject_template`, user can override.
- Preview renders the template inside a real `<iframe srcdoc>` so the template's own `<meta viewport>` and `max-width:640px` rules take effect. Toggle between Desktop and Mobile (mobile wraps the iframe in a 412px phone-frame div).
- Invoice attachment: PDF upload → Supabase Storage at `email-invoices/campaign_{id}/contact_{id}/{uuid}_invoice.pdf` → DB row in `EmailAttachment`. Per-recipient (broadcast mode) or single-recipient (individual mode).
- Send-now: ensures a draft `Campaign`, iterates contacts, renders template + subject per contact, calls `EmailSender.send_email`. Uses `idempotency_key` to dedupe re-sends. Sleeps 3s between sends if more than one recipient.

**Issues.**
- **B5 — 8 variable slots always visible.** Comment at line 466 explains: "initialize all slots visible=True with placeholder labels — some Gradio versions strip components declared with visible=False at build time from the component tree entirely, and later gr.update(visible=True) calls have no effect." So even templates with 1-2 variables show 6-7 empty `Variable 5`, `Variable 6` slots. Yet another framework workaround leaking into UX.
- **B9 — Search dropdown empties after one pick.** `_on_individual_search` is wired to `.change` on the search Textbox. Every keystroke fires a DB query and resets the dropdown choices with `value=None`. If you type "Raj", click the matching row, then accidentally type one more character, the selection is lost.
- **B10 — Send Now and Send Test buttons are adjacent in a row.** With "Send Now" being the primary (wider scale=2) and "Send Test to Me" being the secondary (scale=1), it is one misclick away from a real broadcast.
- The 3-second sleep between sends in `_on_send_now` is a **synchronous block on the request handler thread**, so a 100-recipient broadcast freezes the UI for 5 minutes. Should be queued via Celery (or a similar async path), not run inline.
- Adhoc Contact creation for direct-email sends pollutes the Contacts table with `adhoc_*` IDs that have empty first_name/last_name and no segment. If 50 one-off emails are sent, that's 50 ghost contacts.
- "Subject" lives outside the variable editor block, but `subject_template` is itself a Jinja string with template variables (e.g., `"Order confirmed — thank you, {{ first_name }}"`). User edits to subject break Jinja unless they understand the syntax — there's no preview of the rendered subject.
- **The whole broadcast/individual mode toggle is awkward.** Two distinct workflows sharing one page means every event handler has a `mode` parameter and a branching switch. ~200 LOC of complexity is just mode-routing.

**v2 sketch.** Split into two pages (or two tabs of one page):
- **Email Broadcast** — segment-targeted, schedulable, queued. Per-recipient invoice attach inline.
- **Send to Individual** — one-off email send to a contact OR a direct address. Optional invoice attach. The 3s rate-limit is irrelevant for n=1, so synchronous send is fine.

Both share a `<TemplateEditor>` component (slug picker + variable form + iframe preview) and a `<RecipientPicker>` component (segment selector OR contact search).

---

### 2.7 Email Analytics (`pages/email_analytics.py`, 408 LOC)

**Purpose.** Past-30-day email performance + per-campaign drill-down. KPI strip (Sent / Opened / Clicked / Scheduled / Failed). Tab (Sent / Scheduled / Drafts) → campaign list → click → metric tiles + recipient table.

**Implementation.**
- Reads `Campaign` table for the list and `EmailSend` table for the recipient breakdown.
- `opened_at` and `clicked_at` columns are `hasattr`-guarded — older schema may not have them. (Suggests open / click tracking was added late and isn't always present.)
- Campaign-detail panel renders `metric tiles + recipient table` together; recipient table caps at 100 rows.

**Issues.**
- "Scheduled" tab is filter-by-status, but the system has **no scheduler**. The only way a campaign gets `status="scheduled"` is if you manually set it via DB. So the tab is effectively dead UI.
- Recipient table caps at 100 with no pagination — large campaigns silently truncate.
- KPI cards use distinct colors per metric (Sent grey, Opened teal, Clicked sky-blue, Scheduled amber, Failed red) — fine, but the same 5 metrics are styled differently from the WA broadcast cost KPIs. Consistency lost.
- Open / click tracking implementation isn't documented in the audit, but `hasattr` guard suggests instability.

**v2 sketch.** Folded into the unified Broadcasts page as a "Performance" view. Per-campaign drill-down becomes a route (`/broadcasts/:id`). Recipient table virtualized + paginated.

---

### 2.8 Flows (`pages/flows.py`, 184 LOC)

**Purpose.** Multi-step automated send flows. Pick a flow + segment, click Start. View flow runs.

**Implementation.**
- Left column: Flow dropdown + Channel filter + Segment dropdown + Start Date + Start Flow button + Active/Completed/Total KPIs.
- Right column: Flow steps visualization (chain of step cards) + Flow runs table (Flow / Status / Step / Sent / Next).
- Background thread in `app.py:_flow_automation_loop` checks pending steps every 30 minutes.

**Issues.**
- **It's barely a feature.** 184 lines, no flow editor, no conditional branching, no A/B, no scheduling other than day offsets. Shows a flow, lets you start it, lists runs. That's it.
- Flow definitions live somewhere we haven't audited — likely in seed data or a YAML.
- Channel filter is in the dropdown but doesn't actually filter the flow choices.

**v2 sketch.** Defer. Keep the read-only "Flow runs" view in v2 as a status surface; build a real flow editor later as a separate workstream. The 30-min background poll stays in the FastAPI process untouched.

---

### 2.9 WhatsApp Template Studio (`pages/wa_template_studio.py`, 1,188 LOC)

**Purpose.** Author + submit + sync WhatsApp templates against Meta's WABA API. Three-column layout: list (left), editor form (center), live phone-style preview (right).

**Implementation.**
- Left column: New Draft button + Sync from Meta button + folder tree (campaign hierarchy display) + status filter dropdown + tier filter dropdown + template radio list + header guidelines accordion.
- Center column: editor form — name, category, language, header (NONE/TEXT/IMAGE/DOCUMENT), body, footer, 3 button slots (Type / Text / URL-or-Phone). Hidden `buttons_input` Textbox holds the JSON representation. Save Draft + Submit buttons.
- Right column: WhatsApp-styled phone mockup with chat header + sample context messages + the template-under-edit rendered as a chat bubble.
- Approved-template safety: if you load an approved template into the editor and save, **a clone is created** with `_v2` suffix; the original is never overwritten (`_save_draft` clone-on-edit logic).
- Sync from Meta: `WhatsAppSender.sync_templates_from_meta(db)` pulls all approved/pending templates from Meta and upserts WATemplate rows.
- Tier inference: name pattern → folder (company / category / product / utility). Hardcoded sets at lines 139-155.
- Status badge mapping shared with broadcast_history but defined separately.

**Issues.**
- **It's the most over-engineered page in the dashboard.** Folder tree visualization in HTML, status filter, tier filter, list radio, editor form, preview — and only ~5 templates are typically under active development at any time.
- The folder tree is a static `_render_folder_tree_html` that hard-codes the campaign/whatsapp_campaign/ directory structure. Counts come from `_counts_by_tier(db)` which infers tier from name patterns. If we add a new campaign folder, this code doesn't know.
- Tier inference at `_infer_tier` lives in two hardcoded sets (`_COMPANY_TIER_NAMES`, `_PRODUCT_TIER_NAMES`) — every new template needs a code edit.
- Buttons: 3 slots × 3 fields each = 9 components, plus a hidden JSON Textbox kept in sync via `_sync_buttons_hidden`. ~80 LOC just for buttons.
- "Sync from Meta" button doesn't show progress; for a workspace with 50+ templates this is several seconds of UI freeze.
- The phone preview is gorgeous (WhatsApp dark palette, doodle chat-bg, context messages above the template bubble) — keep this in v2.

**v2 sketch.**
- Drop the folder tree visualization. Replace with a status badge column and a simple tier tag.
- Templates list virtualized + filterable by status + free-text search.
- Editor as a form with proper Shadcn `<Form>` + Zod validation. Buttons editor as a `<FieldArray>`.
- Preview component (`<TemplatePreview>`) is reusable in WA Inbox and WA Broadcasts too.
- Approved-template clone-on-edit logic lives server-side untouched — same behavior, just behind `POST /api/v2/wa/templates/{id}/save`.

---

## 3. Cross-cutting issues (these all evaporate in v2)

### 3.1 Inline HTML f-strings everywhere

Every page builds its UI by concatenating `f'<div style="background:{COLORS.CARD_BG}; ...">...</div>'` strings. Maintaining this is grim:

- Theme tokens come from `shared.theme.COLORS` — but plenty of pages also hardcode `#22c55e`, `#ef4444`, `rgba(255,255,255,.06)` directly. So a theme change requires a multi-file find/replace.
- Hover states are inline JS (`onmouseover="this.style.background='...'"`) instead of CSS classes.
- Icons are emoji literals (🟢, 📋, ⚠) — readable but inconsistent across browsers and not accessible to screen readers.

In v2, every visual fragment becomes a Shadcn component. Theme is one Tailwind config. Icons are Lucide React. Accessibility comes for free.

### 3.2 Modal mounting workarounds

Comment at `contacts.py:592-595`:
> "visible=True at build time so Svelte components mount cleanly; the 'hf-modal-closed' CSS class hides it until the user opens it."

Same workaround in `email_broadcast.py:466-468`:
> "initialize all slots visible=True with placeholder labels — some Gradio versions strip components declared with visible=False at build time from the component tree entirely, and later gr.update(visible=True) calls have no effect."

Same in `wa_inbox.py:464-470`:
> "Pre-allocate slots as visible=True so they exist in the DOM from the start. Gradio omits visible=False components from initial render."

Three pages, three independent workarounds, all chasing the same Svelte mount-race issue. React's `<Sheet>` / `<Dialog>` solve this in one line.

### 3.3 No URL routing

Gradio uses radio buttons for nav state. There's no concept of `/contacts/abc123` or `/templates/order_confirmation`. Three consequences:

- **Can't share a link** to a specific contact / broadcast / template with a teammate. You send a screenshot and a verbal "filter by ..." instruction.
- **Browser back button is useless** — it doesn't go back to the previous page, it leaves the dashboard.
- **Bookmarking is impossible.** Daily ops teams can't `Cmd-D` "WhatsApp Inbox filtered to last-24h" or similar.

In v2, every page is a route. URL state mirrors filter state. Right-click → "Copy link" works.

### 3.4 No real-time updates

The webhook at `app.py:75-96` writes inbound WhatsApp messages to the DB. The dashboard only sees them after `_do_refresh()` runs (manual button click or nav-tab click). For an inbox that the team uses live, this is jarring.

In v2, an SSE stream from `/api/v2/wa/inbox/stream` pushes new messages to whoever is on the Inbox page; React swaps in the new message bubble without a full refresh.

### 3.5 Inconsistent caching layer

Plan D added a `@ttl_cache` decorator with named buckets in `config/cache/ttl.yml`. **Some** pages use it (Home, Contacts segment list); others bypass it entirely (Email Broadcast, Email Analytics). Half-deployed caches are worse than no cache because they hide some queries while others hammer the DB.

In v2, caching moves to the API layer (FastAPI `@cache` or simple Redis). The frontend just calls `GET /api/v2/contacts?...&page=2` and lets the server decide whether to hit cache or DB. Simpler to reason about; one place to tune.

### 3.6 Status badge mappings duplicated across pages

`broadcast_history.py`, `email_analytics.py`, and `wa_template_studio.py` each define their own dict of `{status: label}` and `{status: color}`. They drift over time — some have "Scheduled", some don't; some color "draft" grey, some color it slate.

v2: one `<StatusBadge status="..." />` component, one source of truth.

### 3.7 Synchronous send loop on broadcasts

`email_broadcast.py:_on_send_now` does:
```python
for contact in contacts:
    ...
    sender.send_email(...)
    if len(contacts) > 1:
        time.sleep(3)
```

This blocks the request thread. A 100-recipient send takes 5 minutes during which the page is frozen. Should be a Celery task or BackgroundTasks, but Gradio doesn't have a great pattern for "fire and forget; poll for status."

v2: `POST /api/v2/email/broadcasts` returns `{job_id}`; the UI polls or subscribes for progress.

### 3.8 Mixed channel concerns in pages

- Home shows email + WA stats together (fine).
- Contacts shows email + WA channel badges (fine — contacts have both).
- **Broadcast History tries to be both** (broken — see B6).
- **Sidebar mixes channels** in a flat list — Template Studio (WA-only) sits below Email Analytics.

v2: explicit channel grouping in the sidebar. WhatsApp ▸ (Inbox, Broadcasts, Templates). Email ▸ (Compose, Analytics). Shared ▸ (Contacts, Flows, Home).

---

## 4. Bug catalog with file:line citations

Numbered for stable reference across this doc and future PRs.

| ID | Severity | Where | Description | Fix in v2 |
|---|---|---|---|---|
| **B1** | High (likely) | `theme_css.py:754-758` + `wa_inbox.py:461-490` | WA template variable inputs *likely* scroll off-screen for templates with 3+ vars (e.g. `order_confirmation`). Inputs are captured correctly (slot count is right); CSS analysis suggests the constrained `tp-vars-box` height forces overflow. **Reproduce on the live Space with Playwright before sizing the fix** — pixel-level behavior depends on viewport. | Render variable stack at natural height, shrink preview |
| **B2** | UX-confusion | `wa_inbox.py:740-754` | Text composer is enabled even when 24h window is closed; user types, then send fails. | Disable composer + show "Send template to start conversation" CTA |
| **B3** | Medium | `broadcasts.py:_render_audience_kpis` | Audience funnel is rendered in left column under filters; no headline at top. | Sticky "Targeting **N** in **Segment**" header |
| **B4** | Low | `config/whatsapp/templates.yml:189-213` | `order_delivered` and `thank_you_note` use positional vars (`"1"`, `"2"`); the rest use named vars. UI shows `"1"` literally as label. | Standardize on named placeholders (re-submit those two templates to Meta) |
| **B5** | Medium | `email_broadcast.py:469-485` | All 8 variable slots always visible; templates with 1-2 vars show 6+ empty slots labeled "Variable 5". | Hide unused slots (works in React; was a Gradio mount workaround) |
| **B6** | Medium | `broadcast_history.py:151-153` | Email channel filter returns nothing because email broadcasts go to `Campaign` table, not `Broadcast`. | Unify into single Broadcasts/History page reading both tables |
| **B7** | Low | `contacts.py:268-286` | Inline JS bridge for row-edit button is fragile; comments document multiple debug iterations. | `onClick={() => openDrawer(id)}` in React |
| **B8** | Low | `contacts.py:663-674`, `email_broadcast.py:466`, `wa_inbox.py:464` | Modal mount race — all three pages have workarounds. | `<Sheet>` / `<Dialog>` from Shadcn |
| **B9** | Low | `email_broadcast.py:621` | Per-keystroke search resets dropdown selection; one extra keystroke after picking loses the selection. | Debounced search, separate "selected" state |
| **B10** | UX-risk | `email_broadcast.py:441-444` | Send Now + Send Test buttons in same row. | Separate primary action; require explicit confirm dialog for Send Now |
| **B11** | Low | `config/dashboard/sidebar.yml:40-43` | Template Studio (WA-only) sits outside the WA group. | Reorder sidebar in v2 |
| **B12** | Medium | `home.py:366-367` | "Templates: 7 email, 13 WA" hardcoded in f-string; goes stale as templates are added. | Read counts from DB |
| **B13** | High | `email_broadcast.py:_on_send_now` | Synchronous 3-second sleeps inside Send Now handler block UI for the duration. | Celery / BackgroundTasks job |
| **B14** | Low-Medium | `email_broadcast.py:140-152` | Direct-email mode upserts `adhoc_*` Contact rows. Upsert dedupes by email, so 50 unique direct sends = 50 ghost rows; re-sending to the same email reuses the existing row. Lower impact than first impression suggests, but ghost rows still pollute Contacts filters/exports. | Tag adhoc rows with a flag; surface under a "transient" pseudo-segment OR send without persisting a Contact |
| **B15** | Low | `email_analytics.py:_TABS` | "Scheduled" tab shows nothing because there's no scheduler. | Remove tab OR build the scheduler |
| **B16** | Low | `email_analytics.py:_render_recipient_table` | Recipient table caps at 100 silently; no pagination. | Virtualize + paginate |
| **B17** | Low | `wa_template_studio.py:139-155` | Tier inference relies on hardcoded name sets — every new template needs a code edit. | Tier in YAML (or compute from approved-template metadata) |
| **B18** | UX | All pages | No real-time updates; user must click Refresh / nav-tab to see new data. | SSE on key views |
| **B19** | UX | All pages | No URL routing; can't link to a specific contact/template/broadcast. | React Router |
| **B20** | UX | All pages | Mobile/tablet layouts unusable below ~940px. | Responsive design from day 1 |

---

## 5. Proposed v2 architecture

### 5.1 Repo layout

```
email_marketing/
├── hf_dashboard/              # KEEP (current Gradio Space — runs until v2 reaches parity)
│   ├── app.py                 # FastAPI + Gradio mount + WhatsApp webhook
│   ├── pages/                 # 9 Gradio pages (deprecated after migration)
│   ├── services/              # KEEP — business logic, DB, integrations
│   ├── engines/               # KEEP — broadcast / segment / theme engines
│   ├── loader/                # KEEP — Pydantic-validated config loaders
│   └── ...
│
├── vite_dashboard/            # NEW — React + Vite + Shadcn frontend
│   ├── src/
│   │   ├── routes/            # React Router routes per page
│   │   ├── components/        # Shadcn primitives + composed components
│   │   │   ├── ui/            # Shadcn-generated (Button, Sheet, Dialog, ...)
│   │   │   ├── kpi/           # KpiRow, KpiCard, FunnelCard
│   │   │   ├── tables/        # DataTable, FilterBar, Pagination
│   │   │   ├── chat/          # ConversationList, ChatPanel, MessageBubble
│   │   │   ├── editor/        # TemplateEditor, ButtonsEditor, PhonePreview
│   │   │   └── recipients/    # RecipientPicker, AudienceFunnel
│   │   ├── api/               # Type-safe fetchers (one per /api/v2/* endpoint)
│   │   ├── lib/               # Utilities, hooks
│   │   └── App.tsx
│   ├── Dockerfile             # multi-stage: node-build → python-serve
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── api_v2/                    # NEW — FastAPI routers serving JSON to vite_dashboard
│   ├── __init__.py
│   ├── main.py                # FastAPI app (separate from hf_dashboard/app.py)
│   ├── routers/
│   │   ├── contacts.py
│   │   ├── wa_inbox.py
│   │   ├── wa_templates.py
│   │   ├── broadcasts.py
│   │   ├── email_compose.py
│   │   └── analytics.py
│   ├── schemas/               # Pydantic request/response models
│   └── deps.py                # DB session, auth, etc.
│
├── scripts/
│   ├── deploy_hf.py           # KEEP — deploys hf_dashboard/ to current Space
│   └── deploy_hf_v2.py        # NEW — deploys api_v2 + vite_dashboard build to v2 Space
│
└── ...
```

### 5.2 Why a separate `vite_dashboard` Space (not co-located)

We considered co-locating Vite + Gradio in one HF Space (option A) vs two separate Spaces (option B). **Option B wins** for the migration window:

- Zero risk to the current ops surface. Gradio Space stays live as `himalayan-fibers-dashboard`.
- v2 ships incrementally to `himalayan-fibers-dashboard-v2` with progressively more pages.
- Team can A/B internally — v1 link for daily ops, v2 link for migrated pages.
- Cutover = update bookmarks + delete v1 Space. No code-coordination.
- Once v2 is at parity, `vite_dashboard` and `api_v2` can be merged back into a single Space if desired.

### 5.3 v2 Dockerfile (multi-stage)

```dockerfile
# Stage 1: build the Vite SPA
FROM node:20-alpine AS frontend
WORKDIR /app
COPY vite_dashboard/package*.json ./
RUN npm ci
COPY vite_dashboard/ ./
RUN npm run build  # produces /app/dist

# Stage 2: Python runtime serving FastAPI + the SPA
FROM python:3.11-slim
WORKDIR /app
COPY requirements_v2.txt .
RUN pip install --no-cache-dir -r requirements_v2.txt
COPY api_v2/ ./api_v2
COPY hf_dashboard/services ./services
COPY hf_dashboard/engines ./engines
COPY hf_dashboard/loader ./loader
COPY hf_dashboard/config ./config
COPY hf_dashboard/templates ./templates
COPY --from=frontend /app/dist ./static
EXPOSE 7860
CMD ["uvicorn", "api_v2.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

`api_v2/main.py` mounts the static SPA build at `/` and the JSON API at `/api/v2/*`. Single port, single container, single deploy.

### 5.4 API surface (canonical source: PHASES.md)

The full `/api/v2/*` endpoint list is owned by `PHASES.md` per-phase tables —
that's where new endpoints get added as each phase is planned, and where
existing ones get scoped (auth, request/response schemas, reused services).

Quick summary of route groups:

| Group | Phase | Endpoints |
|---|---|---|
| Auth | 0 | `/api/v2/auth/login`, `/api/v2/health` |
| Dashboard | 5 | `/api/v2/dashboard/home`, `/api/v2/system/status` |
| Contacts | 1 | 8 endpoints (list, detail, edit, create, notes, import, csv, segments) |
| WA Inbox | 2 | 9 endpoints (conversations CRUD + SSE stream + media upload + templates) |
| Broadcasts | 3 | 9 endpoints (unified list/detail, WA send, email queue, jobs status, scheduling) |
| WA Templates | 4 | 7 endpoints (list, detail, save, submit, sync, upload-header, delete) |
| Flows | 5 | 3 endpoints (list, runs, start) |

**Auth model:** Bearer token in `Authorization` header. Token = the Space's
`APP_PASSWORD`. See `STANDARDS_AND_DECISIONS.md §1` for the lifecycle decision
and `PHASES.md` Phase 0 backend tasks for the implementation.

**Type generation.** Use [`openapi-typescript`](https://github.com/openapi-ts/openapi-typescript) in Phase 0 to auto-generate TypeScript types for every endpoint from FastAPI's `/openapi.json`. The pipeline is: FastAPI defines Pydantic schemas → `/openapi.json` exposes them → `openapi-typescript` generates `vite_dashboard/src/api/schema.d.ts` → fetchers in `src/api/*.ts` import these types directly. This means a Pydantic schema change in `api_v2/schemas/contacts.py` propagates to a TypeScript compile error in any frontend code that consumed the old shape — schema drift becomes impossible. Run as a `pnpm gen:types` script and a pre-commit hook.

### 5.5 Component library plan

A short list of reusable Shadcn-composed components that show up on multiple pages:

| Component | Used on | Replaces |
|---|---|---|
| `<KpiCard>` / `<KpiRow>` | Home, Email Analytics, Broadcasts | `components/kpi_card.py` |
| `<DataTable>` | Contacts, Broadcasts/History, Email Analytics recipient table | inline `<table>` HTML in 4+ pages |
| `<FilterBar>` | Contacts, Broadcasts/History, Templates list | dropdown clusters in left columns |
| `<StatusBadge status>` | Broadcasts/History, Email Analytics, Templates list, Contacts (consent) | 3 separate badge dicts |
| `<ContactDrawer>` | Contacts, WA Inbox, Email Broadcast | edit-modal in contacts.py |
| `<TemplateEditor>` | Email Broadcast, WA Template Studio | inline form in 2 pages |
| `<TemplatePreview>` | WA Inbox, WA Broadcasts, WA Template Studio | duplicated phone-mockup HTML in 3 places |
| `<EmailPreview>` (iframe srcdoc) | Email Broadcast, Email Analytics campaign-detail | inline iframe in email_broadcast.py |
| `<RecipientPicker>` | Email Broadcast, WA Broadcasts | mode-toggle UI in email_broadcast.py |
| `<AudienceFunnel>` | WA Broadcasts, Email Broadcast | `_render_audience_kpis` |
| `<ConversationList>` | WA Inbox | radio-list in wa_inbox.py |
| `<ChatPanel>` | WA Inbox | bubble-list rendering in wa_inbox.py |

Total: ~12 *composed* components cover all 9 pages. The full Shadcn primitive count (Button, Input, Select, Sheet, Dialog, Table, Tabs, Toast, etc.) plus these composed ones lands at **25-40 components** in practice. Build time per composed component varies widely: a `<StatusBadge>` is half a day; `<DataTable>` with virtualization, multi-select, column toggles, URL-syncing filters is 3-5 days; `<ChatPanel>` with SSE + media rendering is similar. Plan accordingly.

---

## 6. Migration plan — phases

Each phase is **independently shippable** to the v2 Space. After each phase, both Spaces are live and functional; the team uses v2 for migrated pages and v1 for the rest. No flag-day cutover.

Total wall-clock: **6.5-12 weeks** depending on developer experience with the v2 stack (Shadcn + TanStack Query + React Router). The lower bound is realistic for a developer who has shipped this stack before; the upper bound assumes learning-on-the-job. Phases 1-5 can be partially parallelized with two developers (one on backend API + Phase 1, one on shared component library + Phase 2-3).

### Phase 0 — Foundation (1 week)

Scope intentionally widened from the first draft of this plan to include observability, testing, type-gen, and verification of structural assumptions — these are cheap to set up once and expensive to retrofit.

- **Scaffolding.** Vite + React + TypeScript + TailwindCSS + Shadcn UI + React Router + TanStack Query in `vite_dashboard/`. FastAPI app in `api_v2/`.
- **Verify import paths.** Write a smoke test (`api_v2/tests/test_imports.py`) that imports every module from `hf_dashboard/services/`, `engines/`, `loader/`. Catches relative-import breakage from the proposed reorganization before any feature work depends on it.
- **Type generation.** Wire `openapi-typescript` from `/openapi.json` → `vite_dashboard/src/api/schema.d.ts`. Add `pnpm gen:types` script and a pre-commit hook so frontend types track Pydantic schemas automatically.
- **Testing baseline.** `pytest` for `api_v2/` with a smoke test per endpoint group. `vitest` for `vite_dashboard/` component tests. CI runs both on every push. (v1 has no tests today; v2 starts with a non-zero baseline.)
- **Observability.** Wire Sentry (or equivalent) for both the FastAPI app and the React app — captured errors in v2 from day 1, not as an afterthought. Free tier is sufficient.
- **Bundle budget.** Set a Vite build-size budget of 500 KB gzipped for the initial route bundle. Lazy-load per-route bundles after that. Surface the size in CI so regressions are visible.
- **Auth decision finalized.** Either reuse `APP_PASSWORD` Bearer auth (matches v1, fastest) OR upgrade to cookie-based session auth as part of Phase 0. Either way, locked in here — not deferred to Phase 5. (Decision input: §9 question 6.)
- **Dockerfile + deploy script.** Multi-stage Dockerfile per §5.3. New `scripts/deploy_hf_v2.py` mirroring `scripts/deploy_hf.py`.
- **HF Space created.** `himalayan-fibers-dashboard-v2`. Auto-build from upload.
- **Hello-world deploy.** SPA returns "Coming soon" per route; `/api/v2/health` returns 200; Sentry breadcrumb fires; the openapi-typescript generation produces a non-empty `schema.d.ts`.
- **Tailwind theme tokens.** Match `shared/theme.py`'s COLORS dict — v1 and v2 look like the same product.
- **`<AppShell>`** (sidebar + content area) with placeholder routes per planned page.

**Acceptance:** v2 Space is live and password-gated. Sidebar renders. Every route shows "Coming soon". CI runs (passing) on push. Sentry receives a test event from both backend and frontend. `pnpm gen:types` produces type definitions. Smoke test confirms all `hf_dashboard/services/` modules import cleanly under the new layout.

### Phase 0.5 — Reproduce reported bugs on the live Space (2-3 days)

Before any rebuild work, reproduce B1, B5, B9, B10 against the live HF Space using Playwright MCP (per CLAUDE.md's preference to never run the app locally). Save baseline screenshots of each broken state. These become the visual regression targets that v2 must beat.

Specifically:
- **B1.** Open WA Inbox, pick `order_confirmation` template, screenshot the variable input area at default viewport (1440px) and at 1024px. Count how many of the 4 input fields are visible without scrolling. If all 4 are visible at 1440px, demote B1 from "High (likely)" to "Medium" and document the actual triggering viewport.
- **B5.** Open Email Broadcast, pick a 2-variable template, screenshot the variable slot area to confirm 6 empty `Variable N` slots are visibly rendered.
- **B9.** Open Email Broadcast in Individual mode, type "Raj" in search, click a result, then type one more character. Confirm whether the selection is lost.
- **B10.** Screenshot the Send Now / Send Test row at default zoom; confirm the buttons are visually adjacent.

Output: `reports/audit_vite_migration_plan/repro/` with 4-8 screenshots and a short notes-per-bug doc. Calibrate severities in §4 with what was actually observed.

**Acceptance:** every High/Medium-severity bug in §4 has either a confirmed reproduction screenshot or a note saying "could not reproduce — demote/remove from catalog".

### Phase 1 — Contacts (1 week)

- Build `<DataTable>`, `<FilterBar>`, `<ContactDrawer>`, `<StatusBadge>` Shadcn components.
- Implement `GET /api/v2/contacts`, `GET /api/v2/contacts/{id}`, `PATCH`, `POST`, `POST .../notes`, `POST .../import`, `GET /contacts.csv`, `GET /api/v2/segments`.
- Mirror Plan D Phase 1.3 column-narrowing in the API (only ship the 15 columns the table needs).
- Wire the Contacts route. URL state for filters (`?segment=...&page=...`).

**Acceptance:** Contacts page in v2 has feature parity with v1: filter, search, paginate, add, import, edit (Profile/Tags/Notes/Activity), download CSV. Bug B7 (JS bridge) and B8 (modal mount) are gone by construction. Internal team uses v2 Contacts for daily work; v1 Contacts becomes read-only-ish reference.

### Phase 2 — WhatsApp Inbox (1.5 weeks)

This is the team's most-used page and where the worst bugs live.

- Build `<ConversationList>`, `<ChatPanel>`, `<MessageBubble>`, `<TemplatePreview>`, `<TemplateVariablesForm>` components.
- Implement `GET /api/v2/wa/conversations`, `GET .../{contact_id}`, `POST .../messages`, `POST .../template-sends`, and `GET .../stream` (SSE for inbound webhook → frontend push).
- Build `<TemplateSheet>` — the "Send template" panel as a Shadcn Sheet, opened from a button in the chat composer (instead of a permanent third panel).
- Disable the text composer when no 24h window exists; surface "Send a template to open a conversation" CTA in its place. **Fixes B2.**
- Render variable inputs in a non-scrolling stack, sized to content. **Fixes B1.**

**Acceptance:** WA Inbox in v2 supports active conversation switching, send text, send media, send template (with all 4 vars of `order_confirmation` visible without scroll), real-time inbound-message updates via SSE.

### Phase 3 — Broadcasts (unified WA + Email + History) (1.5 weeks)

Merges 4 v1 pages into 1 v2 page with 3 tabs: Compose / History / Performance.

- Build `<RecipientPicker>`, `<AudienceFunnel>`, `<TemplateEditor>` (reused from Phase 4 prep), `<EmailPreview>` (iframe srcdoc) components.
- Implement `GET /api/v2/broadcasts`, `POST /api/v2/broadcasts/wa`, `POST /api/v2/broadcasts/email` (queues a Celery job — first time email broadcasts are non-blocking), `GET /api/v2/broadcasts/{id}/status` (poll), `GET .../audience-preview`, `GET .../cost-estimate`.
- New: scheduling — `scheduled_at` field on the broadcast model + a Celery beat job that fires due broadcasts.
- "Targeting **N** people in **Segment X**" sticky header. **Fixes B3.**
- Unified history reads both `Broadcast` and `Campaign` tables. **Fixes B6.**
- Send Now requires a confirmation dialog showing recipient count + cost. **Fixes B10.**
- Background queue + status polling. **Fixes B13.**

**Acceptance:** Broadcasts page in v2 supports composing WA broadcast, composing email broadcast (queued), browsing history of both, drilling into per-broadcast performance. Old `broadcasts`, `broadcast_history`, `email_broadcast`, `email_analytics` pages stay live in v1 as fallback.

### Phase 4 — Template Studio (1 week)

- Reuse `<TemplateEditor>`, `<TemplatePreview>`, `<ButtonsEditor>` from Phase 3.
- Implement `GET /api/v2/wa/templates`, `GET .../{id}`, `POST .../save` (clone-on-edit logic moves to API), `POST .../submit`, `POST .../sync`, `POST .../upload-header`.
- Drop the static folder tree visualization. Replace with status badge column + tier tag column + search.
- Tier inference: keep server-side for now; v3 moves it to YAML.

**Acceptance:** Template Studio in v2 supports list/filter, edit form with live phone preview, save (with clone-on-edit), submit to Meta, sync from Meta.

### Phase 5 — Home + Flows + cleanup (1 week)

- Home page in v2: `<DashboardGrid>` with KPI rows, lifecycle bars, activity feed. Reads from `GET /api/v2/dashboard/home`. Counts come from DB, not f-string. **Fixes B12.**
- Flows: minimal read-only view of flow runs. (Flow editor is out of scope for migration.)
- Sidebar grouping reorganized: Home / Contacts / WhatsApp ▸ (Inbox, Broadcasts, Templates) / Email ▸ (Compose, Analytics) / Flows. **Fixes B11.**
- All pages from v1 are now in v2. Decommission Gradio Space (or freeze it as read-only for 30 days as backup).
- **Cleanup is gated on v1 decommission.** Deleting `hf_dashboard/pages/` and the proposed rename `hf_dashboard/` → `dashboard/` happen ONLY AFTER the v1 Space is deleted (or is on a "frozen, read-only" footing where re-deploys are not expected). Until that gate, both Spaces deploy from the same repo and any directory rename would break `scripts/deploy_hf.py`. The cleanup commit is therefore the last commit in Phase 5, not the first.

**Acceptance:** v1 Space is decommissioned (or explicitly frozen). v2 is the dashboard. Sidebar is reorganized. All B-bugs from §4 are resolved or explicitly deferred. Repo cleanup commit is in.

---

## 7. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Vite build adds 2-3 min to image build time, slowing deploys | High | Low | Acceptable; HF Spaces caches docker layers |
| HF Space free-tier RAM (~16GB) insufficient for FastAPI + Vite static serve | Low | Medium | Static SPA is ~5-10MB compiled; FastAPI footprint hasn't changed |
| API surface drift — v1 and v2 backends diverge during the migration window | Medium | High | Both Spaces import from the same `hf_dashboard/services/` Python code. Schema changes go in via the existing `scripts/` migration pattern, hit both |
| Team friction during dual-Space window — "which link do I use?" | High | Low | Update the team Slack pinned message after each phase; use prominent banners on both Spaces ("v1 — falling out of use" / "v2 — migrated pages here") |
| WA webhook signature verification breaks if v2 mounts at a different path | Low | Critical | v2 keeps `/webhook/whatsapp` under FastAPI exactly as v1; Meta's webhook URL doesn't change because we're on the same HF Space domain on a different subdomain. Configure Meta's webhook to point at v2's domain after v2 is fully live |
| Database schema mismatch between v1 and v2 | Medium | High | Both backends share `services/models.py` and the same Postgres DB. Any schema change goes through `scripts/migrations` and lands in both. CI test that imports `services.models` from both would catch drift |
| Gradio session state lost during v1 deprecation | Low | Low | Sessions are local; users just re-login. No lost work because all state is in DB |
| Real-time inbox SSE doesn't work behind HF Space's proxy | Medium | Medium | Test in Phase 0 with a trivial SSE endpoint. If broken, fall back to short-poll (5s) |
| Async send queue is non-trivial on HF Spaces | High | Medium | HF Spaces run one container per Space; full Celery (worker + broker + beat) is impractical without a second Space. **Realistic plan:** stay synchronous via FastAPI `BackgroundTasks`. The current cap is 500 emails/day (Gmail API limit); a 500-recipient send takes ~25 min at the current 3s sleep, which is tolerable as a background task with progress polling. Revisit only if daily volume exceeds 500 or if multi-recipient WA broadcasts grow large enough to stress this |
| Python import paths break under the proposed shared-services layout | Medium | High | Phase 0 includes a smoke test (`api_v2/tests/test_imports.py`) that imports every module from `hf_dashboard/services/`, `engines/`, `loader/`. CI fails the build if any module won't load. Catches relative-import breakage early |
| Schema drift between v1 and v2 backends | Medium | High | Both backends import `services/models.py`. `openapi-typescript` regeneration in CI catches divergence at the API level. Migration scripts under `scripts/` apply to the single shared DB |
| Auth decision deferred too long | Medium | Medium | Auth is locked in Phase 0 (not Phase 5). Default: reuse `APP_PASSWORD` Bearer; upgrade to cookie sessions only if explicit team request |
| Plan D in-flight perf work (`@ttl_cache`, egress optimizations) gets stranded | Medium | Medium | See §10.5 — explicit coordination plan. |
| Deployments require coordination during dual-Space window | Medium | Low | `scripts/deploy_hf.py` and `scripts/deploy_hf_v2.py` are independent — deploy each on its own cadence |

---

## 8. Costs

**Time.** ~6.5-12 weeks of focused development for one engineer (the lower bound assumes prior Shadcn + TanStack Query experience; the upper bound assumes learning-on-the-job). Could be partially parallelized to 4-6 weeks with two engineers (one on API surface + Phase 1, one on shared component library + Phase 2-3). The team's current daily-ops impact is zero throughout (Gradio stays live).

**Money.**
- HF Space — currently free CPU tier. Adding a second Space stays free for the migration window.
- Vite + Shadcn + everything else — open source, $0.
- Celery worker — deferred (in-process for now).
- One-time: re-submit the two positional-variable WA templates to Meta (~10 min).

**Operational.**
- Two Space URLs to communicate to the team during the migration window.
- Two deploy commands (existing `deploy_hf.py` for v1, new `deploy_hf_v2.py` for v2).
- Slightly more discipline around schema changes — must apply to both backends (in practice, both import from same Python module, so this is automatic).

---

## 9. Decision points the user should weigh in on

Before kicking off Phase 0, get explicit answers on these:

1. **Confirm two-Space approach** (vs co-locating Vite + Gradio in one Space). I recommend two; the user said "have two different images" which I read as agreement.
2. **Confirm `vite_dashboard/` as the folder name** (the user said "white dashboard" — I think they meant Vite. Confirm before I create the folder.)
3. **Migration order priority.** Default order in §6 is: Contacts → WA Inbox → Broadcasts → Templates → Home/Flows. If the user has a different priority (e.g., the "WhatsApp broadcasts page is most broken — fix that first"), reorder.
4. **Scheduling feature.** Phase 3 introduces broadcast scheduling. Confirm this is desired now or defer to a later release.
5. **Decommissioning v1.** Phase 5 deletes the Gradio pages. Some teams prefer a "freeze for 30 days" period before deletion. Confirm preference.
6. **Authentication.** Currently `APP_PASSWORD` is unset (Space is public). Should v2 launch with the same setup, or should we add a real login (cookie-based session) as part of Phase 0?
7. **Plan D coordination.** Per §10.5, choose between (a) finish Plan D on v1 first, (b) freeze Plan D and port forward, or (c) run both in parallel. Recommendation: option (b).

---

## 10. What this plan does NOT cover (out of scope, for a follow-up)

- **Flow editor** (the visual builder for multi-step automations). Phase 5 keeps it as a read-only view. A real editor is a separate workstream.
- **Open / click tracking improvements.** `email_analytics.py:_kpi_counts` has `hasattr` guards for `opened_at` / `clicked_at` — implies open/click pixel tracking is partial. Not in scope; Phase 3 surfaces whatever data exists.
- **Mobile-first redesign.** v2 will be **responsive** (works on tablet + phone), but the page structures are still desktop-first. A pure mobile experience for the team-on-the-go would be a separate Phase 6.
- **A/B testing for broadcasts.** Phase 3 has scheduling but no variant testing.
- **WhatsApp catalog management.** The product catalog feature in WhatsApp Business isn't surfaced today; not added here.
- **Role-based access control.** All authenticated users have full access. If the team grows beyond founder + 2-3 ops people, RBAC becomes a need.
- **Audit log surfacing.** `services/interactions.py` writes `manual_edit` / `note_added` / `imported` events — visible per-contact in the drawer. A global "who did what" view would require a new page.
- **Deployment to a custom domain.** Currently relies on the HF Space subdomain. A `dashboard.himalayanfibres.com` cutover is a separate DNS + reverse-proxy task.

---

## 10.5 Plan D coordination

The codebase has active perf work tagged "Plan D" — a TTL cache layer (`@ttl_cache`, buckets in `config/cache/ttl.yml`), egress-reduction queries that ship only the columns each renderer needs (`Plan D Phase 1.x` comments throughout `pages/contacts.py`, `home.py`, `wa_inbox.py`), and per-page query batching. Some of this work is in flight and some is done. The v2 migration interacts with it three ways:

1. **Cache layer survives.** `services/ttl_cache.py` lives under `services/` which v2 reuses unchanged. Any cached helpers stay cached. v2 picks up the perf benefits for free.

2. **Page-local optimizations transfer differently.** The `Plan D Phase 1.3` Contact-column narrowing in `pages/contacts.py` is page-side — it's the Gradio table renderer choosing which columns to load. In v2, that decision moves to the API endpoint (`GET /api/v2/contacts` selects only the 15 columns the table needs and ships them as JSON). The optimization is preserved, just relocated. Same pattern for `wa_inbox.py:_get_active_conversations` (the JOIN-narrowed query becomes an API responsibility).

3. **In-flight Plan D work needs a freeze decision.** If Plan D has phases not yet shipped (e.g. Phase 2c+ are in development), the team should choose:
   - **Option A — Finish Plan D on v1, then start v2.** Cleaner, but delays Phase 0 by however long Plan D has left.
   - **Option B — Freeze Plan D at the current phase, port already-landed optimizations forward, and skip the unfinished phases entirely** (or land them as v2-native designs). Faster start; some perf work wasted if the unfinished phases were targeting page-local behavior that won't exist in v2.
   - **Option C — Continue Plan D in parallel on v1.** Risky — every change to a `services/` helper has to be evaluated for both consumers, and the team is split between two efforts.

**Recommendation: Option B.** Concretely: take stock of which Plan D phases are landed vs in-flight at the moment Phase 0 starts. Anything landed stays. Anything in-flight is paused at the API boundary instead of in pages. If a query optimization was about to ship to `pages/email_broadcast.py`, write it as an `api_v2/routers/email_compose.py` improvement instead.

This decision should be made *before* Phase 0 kicks off so there is no contention for the same files during the migration window. Add a checklist item to §9.

---

## 11. Confidence and assumptions

What this audit is **confident** about:
- All 9 page files were read in full. Bug citations have verified file:line references.
- The WA template variable scroll bug (B1) is **plausible and CSS-traced**, but pixel-level behavior wasn't reproduced on the live Space. Phase 0.5 reproduces and re-calibrates severity.
- The Email channel filter bug on broadcast history (B6) was traced to the table-mismatch between `Campaign` (used by `email_broadcast.py`) and `Broadcast` (used by `broadcast_engine.py`).
- The 24h-window send issue (B2) is correct WhatsApp Business API behavior, not a dashboard bug.

What this audit is **less confident** about — and should be verified before committing:
- Email open/click tracking — `hasattr` guards suggest partial implementation, but the actual tracking pixel / link-rewrite code wasn't audited.
- Flows engine — only the page was read, not `services.flows_engine`. The 30-min background poll is mentioned in `app.py`; the actual step-execution logic wasn't traced.
- Celery / job queue — the codebase doesn't appear to have one. The "synchronous send loop" finding (B13) assumes there's no async pathway hiding elsewhere.
- The PortalAgent project (the user's reference architecture) wasn't read. The "v2 sketch" recommendations are based on standard Vite + Shadcn patterns; if PortalAgent has specific conventions worth matching, those need to be incorporated in Phase 0.

---

## 12. Next steps

1. **User reviews this document.** Answers the §9 decision points (two-Space confirmation, folder naming, migration order, scheduling, decommissioning, auth).
2. **(Optional) Read PortalAgent's structure.** A 30-minute side-trip could surface conventions worth mirroring before Phase 0.
3. **Phase 0 execution.** Once the user gives the green light, I scaffold `vite_dashboard/`, `api_v2/`, the v2 Dockerfile, and `scripts/deploy_hf_v2.py`. The first deploy is a "Hello world" that proves the pipeline works.
4. **Phase 1 (Contacts).** First real page migrated. Roughly one week.
5. **Iterate through phases 2-5.**

Total wall-clock: **6.5-12 weeks** from green-light to v1 decommissioning (calibration depends on developer experience with the v2 stack, see §6 and §8), with a working v2 Space at every weekly checkpoint.
