# Phase 7 — Email Side Implementation Plan (revised)

> **Revision history:** revised 2026-05-05 after review. Changes vs first draft:
> - Sidebar path corrected (`vite_dashboard/src/config/dashboard/sidebar.yml`).
> - "Shared" components moved from `pages/email-send/components/` to `components/email/`.
> - Idempotency acceptance criterion fixed (per-day, not per-minute) + "Force resend" follow-up flagged.
> - Phase 7.2 split into **7.2a** (Send Now works) and **7.2b** (Campaign.variables column + Schedule works).
> - Compose variables UX decided: auto-resolved per-recipient variables (`first_name`, `last_name`, `name`, `email`, `contact_company`) are HIDDEN from the Compose form; they're never global.
> - **Decision D3 flipped:** variable spec inlined as a field on `EmailTemplateOut` instead of a dedicated `/variable-spec` endpoint.
> - **Decision D6 flipped:** "Send Email" sidebar entry sits ABOVE `email_broadcasts` so the email cluster reads top-down.
> - Added: error-state acceptance criteria, the deploy → Playwright-verify gate, query-cache invalidation behavior.

Phase scope: `vite_dashboard` (Vite + React + Shadcn) email surfaces. Three problems, sequenced in dependency order. No DB schema changes for 7.1 + 7.2a + 7.3. **One small migration** in 7.2b adds `Campaign.variables JSON` so scheduled broadcasts don't drop typed variables. One new POST endpoint is added to FastAPI v2; the variable spec lives on the existing `EmailTemplateOut` payload.

## Implementation strategy summary

The three problems share one root cause: the Vite dashboard never built a per-recipient email render-preview surface, so each surface that needs one (Studio, Broadcast Compose, single-contact send) re-skips the problem. The plan therefore factors out two reusable pieces — a small `EmailRenderPreview` component (right pane) and an `EmailVariablesForm` component (left pane) — and consumes them from all three surfaces. Both pieces lean on (a) the existing `GET /api/v2/email/templates/{id}` enriched with a `variable_spec` field that lifts `services/template_seed.py::get_template_meta(slug)` out of v1's Gradio page and (b) one new endpoint `POST /api/v2/email/render-preview` that runs `EmailSender.render_template` (subject) + `render_template_by_slug` (body) server-side because Jinja `{% extends %}` cannot render client-side.

Single-contact email send (Problem 1) is a NEW page because the cleanest UX matches the WhatsApp Inbox shape — pick contact → pick template → fill vars → preview → send — and that surface should not be hidden behind a Contacts drawer tab where users won't think to look for it. The page reuses the same `EmailRenderPreview` and `EmailVariablesForm` building blocks, plus a new contact-picker component (search-as-you-type over `useContacts`) and a new endpoint `POST /api/v2/email/test-sends` that wraps the existing `EmailSender.send_email` + `render_template_by_slug` path used by v1's `_on_test_send`. Sends are NOT recorded as 1-recipient broadcasts; they go through a new `email_sends` row only (recommended below). Email Broadcast Compose (Problem 2) and the Studio (Problem 3) inherit the shared components and stop diverging.

**Latent bug surfaced by this work:** `_send_email_broadcast` (broadcast_engine.py:474) builds its own narrow `{name, first_name, company_name, email}` dict and bypasses `build_send_variables` + the shared branding config. Today's broadcasts of seeded templates render with missing `banner_url`, social links, etc. — silently broken in production. Phase 7.2a includes the fix (rewire to `build_send_variables` + `render_template_by_slug`).

---

## Phase 7.1 — Single-contact email send

A new top-level route `/email-send` (sidebar entry "Send Email") that lets the founder fire one template at one contact, with a live rendered preview before clicking Send. Modeled directly on the WA Inbox `TemplateSheet` UX pattern, unfolded into a full-page two-pane layout.

### Files to CREATE — shared components (used by 7.1 + 7.2 + 7.3)

- `vite_dashboard/src/components/email/EmailVariablesForm.tsx` — renders one input per variable from `EmailTemplateOut.variable_spec` (`type=text|textarea|date|url`). Auto-prefills from contact context (mirroring `services/email_personalization.py::build_send_variables`) when a contact is provided; falls back to YAML `example` when no contact (Studio case). **Hides auto-resolved-per-recipient variable names** (`first_name`, `last_name`, `name`, `email`, `contact_company`) when called with `mode="broadcast"` so they don't appear as typeable global inputs. Visible in `mode="single"` and `mode="studio"`.
- `vite_dashboard/src/components/email/EmailRenderPreview.tsx` — posts the template id + the merged variable dict to `POST /api/v2/email/render-preview` and renders the returned HTML in a sandboxed `<iframe srcDoc>`. Has a desktop / mobile (412px phone-frame) toggle, copying v1's frame from `hf_dashboard/pages/email_broadcast.py::_render_iframe` (the frame is just HTML markup; portable). Shows the rendered subject above the iframe in a separate row. Debounces variable changes 200ms before re-firing the mutation.
- `vite_dashboard/src/api/email_send.ts` — new hooks file. `useRenderEmailPreview()` (mutation), `useSendOneEmail()` (mutation). Lives in its own file (not `email_templates.ts`) because these are runtime-send concerns, not template-CRUD.

### Files to CREATE — page-specific

- `vite_dashboard/src/pages/email-send/EmailSendPage.tsx` — page entry. Two-pane layout: left = contact picker + template picker + variable form; right = render preview + Send button. Wraps `<HowToUse>` like other pages.
- `vite_dashboard/src/pages/email-send/components/ContactPicker.tsx` — search input over `useContacts({ search, channel: "email", page_size: 25 })`. Debounced 250ms. Filtered to contacts that have a non-empty `email`. Selected contact pinned at top with Clear. Shows name, email, company. Mirrors `ConversationList` styling. **Note**: the v1 `_resolve_wa_variable` analogue for email is `build_send_variables`; we don't expose it client-side because the spec endpoint already returns auto-prefill candidates.
- `vite_dashboard/src/pages/email-send/components/EmailTemplatePicker.tsx` — `<select>` over `useEmailTemplates({ active_only: true })`. Same shape as the WA TemplateSheet picker (`<option>name (category, N vars)</option>`).
- `vite_dashboard/src/config/pages/email_send.yml` — page config (title, subtitle, how_to_use sections matching the conventions in `email_broadcasts.yml`).

### Files to MODIFY

- `vite_dashboard/src/routes/index.tsx` — add `{ path: "email-send", element: <EmailSendPage /> }`.
- `vite_dashboard/src/config/dashboard/sidebar.yml` — add `id: email_send` nav item **above `email_broadcasts`** (D6 flipped). Icon `📨`. Add `separator_before: true` if visually appropriate.
- `vite_dashboard/src/loaders/configLoader.ts` — register `email_send` page id so `configLoader.getPage("email_send")` resolves.
- `vite_dashboard/src/schemas/pages.ts` — add `email_send` to the `PAGE_SCHEMAS` registry.
- `api_v2/main.py` — register the new `email_send` router (see API additions below).
- `api_v2/schemas/email_templates.py` — add `variable_spec: list[EmailVariableSpec] | None = None` to `EmailTemplateOut` so `GET /api/v2/email/templates/{id}` returns it (D3 flipped).
- `api_v2/routers/email_templates.py` — `_to_out()` populates `variable_spec` from `services.template_seed.get_template_meta(slug)`. Falls back to synthesizing a default spec from `required_variables` when no `.meta.yml` exists (so DB-only Studio-created templates still render variable inputs).
- `vite_dashboard/src/api/email_templates.ts` — `EmailTemplateOut` type adds `variable_spec?: EmailVariableSpec[]`. The list endpoint already returns this in PHASES.md's terminology; this just adds a field.

### API additions

1. `POST /api/v2/email/render-preview` → `RenderPreviewResponse`. Body: `{ template_id, variables, contact_id?, html_content_override?, subject_template_override? }`. Wraps `EmailSender.render_template` (subject) + `render_template_by_slug` (body). When `html_content_override` is set, renders the override via `render_template_string(...)` instead — used by Studio's Advanced edit mode (Phase 7.3). Server-side because Jinja2 ships server-only and seeded templates use `{% extends %}`. Runs `EmailSender._preprocess_html` so the preview matches what gets sent (font @import handling, etc.).
2. `POST /api/v2/email/test-sends` → `TestSendResponse`. Body: `{ template_id, contact_id, variables, subject_override? }`. Resolves contact → calls `build_send_variables(contact, {}, extra=variables)` → renders → `EmailSender.send_email`. Writes one `EmailSend` row with `campaign_id=None`, `idempotency_key` from `generate_idempotency_key("single_send", contact_id)`. Returns `{ success, message, email_send_id }`.

Both live in a new router file `api_v2/routers/email_send.py` (new tag `email_send`) so `email_templates.py` stays focused on CRUD. Variable-spec inlined on `EmailTemplateOut` (D3 flipped) — no third endpoint.

### Schema additions (`api_v2/schemas/email_send.py`)

```text
EmailVariableSpec        — { name, label, type, placeholder, example, required }
                            (mirrored on EmailTemplateOut.variable_spec)
RenderPreviewRequest     — { template_id, variables: dict[str, str],
                             contact_id?: str | None,
                             html_content_override?: str | None,
                             subject_template_override?: str | None }
RenderPreviewResponse    — { html, subject }
TestSendRequest          — { template_id, contact_id, variables,
                             subject_override?: str }
TestSendResponse         — { success, message, email_send_id?: int | null }
```

### Component tree sketch

```
EmailSendPage
├─ HowToUse (config-driven)
└─ grid 2-col [pickers | preview]
   ├─ left:
   │  ├─ ContactPicker            (debounced search, results list, Clear chip)
   │  ├─ EmailTemplatePicker       (select over active templates)
   │  ├─ EmailVariablesForm        (mode="single" — auto-prefilled from contact)
   │  ├─ subject override Input    (optional, prefilled with rendered subject)
   │  └─ Send + Cancel buttons + error <p role="alert">
   └─ right:
      ├─ desktop / mobile toggle
      ├─ subject line readout (rendered)
      └─ EmailRenderPreview (iframe)
```

### Acceptance criteria (testable in the live Space)

#### Happy path
- Sidebar shows "Send Email" entry above "Email Broadcasts"; clicking it opens `/email-send` with the HowToUse accordion at top.
- Typing in the contact search filters to contacts with non-empty `email`. Picking one populates the contact card + clears the form errors.
- Picking a template fills the variables form with prefilled values (e.g. `first_name = "Prashant"` for a contact named Prashant). Variables form shows EXACTLY the count declared by `EmailTemplateOut.variable_spec` — no padding to N slots.
- Editing any variable updates the rendered preview within ~500ms (debounced `useRenderEmailPreview` mutation).
- Send button is disabled until contact + template are picked AND all `required` variables have a non-empty value.
- Clicking Send fires once, shows success toast (or error message inline), and writes one row to `email_sends` with `campaign_id=NULL` and the idempotency key prefix `single_send`.
- `email_sends` row is queryable via the existing `EmailSend` table; the row does NOT appear under `/email-broadcasts` History (because there's no `Campaign`).

#### Idempotency (corrected from first draft)
- The `generate_idempotency_key` granularity is **per-day** (`%Y%m%d`), not per-minute. So a second click on Send within the same UTC day for the same `(template, contact)` is a **24-hour** no-op — the second call returns the existing `email_send_id` and reports `success=true, message="duplicate, already sent today"` without firing Gmail.
- A "Force resend" affordance is **out of scope for 7.1**; flag for Phase 8 if the founder wants to bypass dedup. (Workaround: change one variable to make the request hash differ, OR wait until tomorrow UTC.)

#### Error states (new section)
- Variable-spec is missing for the picked template (no `.meta.yml`, no `required_variables`): variables form renders empty with a "(no declared variables — preview will use empty values)" notice. Preview still renders.
- `/render-preview` returns 500: the preview pane shows a red error block with the Python error message. Send button stays enabled.
- `/render-preview` returns malformed HTML: iframe still renders (browser tolerates it); no client-side validation.
- Picked contact has no `email` (shouldn't happen due to filter, but defensive): Send returns 400 with detail "Contact has no email"; UI surfaces it inline above the Send button.
- `/test-sends` Gmail send fails (wrong refresh token, quota, etc.): returns 502 with the Gmail error string; UI surfaces it inline. The `email_sends` row is still written with `status="failed"` so it's in the History audit.
- Network offline / API unreachable: TanStack-Query default error toast; Send button re-enables after error.

#### Cache invalidation (new)
- Creating a new template in `/email-templates` (Phase 7.3) invalidates `["email", "templates"]` query keys so the dropdown in `/email-send` and `/email-broadcasts` refreshes without page reload.
- Creating an `email_send` row does NOT invalidate any list query (no UI surfaces this list yet).

---

## Phase 7.2a — Email Broadcast UX gaps (Send Now)

`ComposeTab.tsx` currently lets the user type a free-text template slug, has no preview, and no variable inputs. Replace the slug input with a real picker, add the same `EmailRenderPreview` + `EmailVariablesForm` we just built, and pass user-supplied variables to the queue endpoint so the broadcast send-loop uses them as the `extra` dict (overriding the auto-resolved per-contact values).

This phase ALSO ships the broadcast-engine fix (Risk #2 in the original draft): rewire `_send_email_broadcast` to call `build_send_variables(contact, attachments, extra=req.variables)` + `render_template_by_slug(slug, vars)` so broadcasts of seeded templates stop rendering empty / misconfigured.

### Files to MODIFY

- `vite_dashboard/src/pages/broadcasts/components/ComposeTab.tsx`
  - Replace the email branch's free-text `<Input>` for `templateName` (line 272-278 today) with `<select>` populated from `useEmailTemplates({ active_only: true })`. Keep `templateName` typed as `string` (slug) so the queue request shape doesn't change.
  - When the email channel is active AND a template is picked, render `EmailVariablesForm mode="broadcast"` (auto-resolved-per-recipient names HIDDEN — see decision below) and `EmailRenderPreview` next to the form.
  - Compute `requiredVariables` (the YAML `required` ones, EXCLUDING auto-resolved ones) and gate `canOpenConfirm` on every required var being non-empty when channel is `email`.
  - Subject field: pre-fill with `selected.subject_template`, allow override (already wired). The preview shows the rendered subject line.
  - The audience funnel + cost cards stay where they are — no rework there.
- `vite_dashboard/src/api/broadcasts.ts`
  - Extend `useQueueEmailBroadcast` body to accept an optional `variables?: Record<string, string>` field (new on the request).
- `api_v2/schemas/broadcasts.py`
  - Add `variables: dict[str, str] = {}` to `SendEmailBroadcastRequest`. Backward compatible (default empty).
- `api_v2/routers/broadcasts.py`
  - Forward `req.variables` to `_run_email_broadcast`. Stash as the `extra_vars` argument.
- `hf_dashboard/services/broadcast_engine.py` — **the latent-bug fix**
  - `_send_email_broadcast` rewires to:
    ```text
    for each contact:
        merged = build_send_variables(
            contact,
            attachments={},                # broadcasts don't attach yet
            extra=extra_vars,              # new parameter
        )
        html = render_template_by_slug(template.slug, merged)
        subject = render_template_string(subject_override or template.subject_template, merged)
        sender.send_email(...)
    ```
  - Drop the inline narrow `{name, first_name, ...}` dict at lines 512-514.
  - Verify the existing test suite (`api_v2/tests/test_broadcasts.py` if it exists) still passes; add a regression test that asserts `build_send_variables` was called with the right contact.
- `vite_dashboard/src/config/pages/email_broadcasts.yml`
  - Update the "Pick a template" how-to-use section to remove the "type the slug" wording.

### Files to CREATE

- None new — reuses `EmailVariablesForm` + `EmailRenderPreview` + `useRenderEmailPreview` from Phase 7.1.

### Component tree sketch

```
ComposeTab (channel="email" branch)
├─ AudienceFunnel
├─ form
│  ├─ name + audience inputs               (unchanged)
│  ├─ template <select>                    (NEW — from useEmailTemplates)
│  ├─ subject override Input               (already there)
│  ├─ EmailVariablesForm mode="broadcast"  (NEW — auto-resolved vars hidden)
│  └─ Send Now button                      (Schedule disabled until 7.2b)
├─ CostEstimateCards
└─ aside:
   ├─ Notes block                          (existing)
   └─ EmailRenderPreview                   (NEW — preview uses example values)
```

### Variables UX decision (Risk #6 from first draft, now fixed)

`EmailVariablesForm` is invoked with `mode="broadcast"`. In this mode, the auto-resolved-per-recipient variable names are **filtered out** of the rendered input list:

```text
const AUTO_RESOLVED = ["first_name", "last_name", "name", "email", "contact_company"];
```

These never appear as typeable global inputs in Compose (they vary per recipient — `build_send_variables` resolves them server-side). The Compose preview iframe shows the rendered output using the **YAML `example`** values for those variables (so the preview reads "Hi Sample Customer," instead of empty `{{first_name}}` placeholders). Required-variable gating ignores auto-resolved names.

If a future use-case wants to override per-recipient resolution (uncommon), that's a Phase 8 enhancement. Out of scope here.

### Acceptance criteria

#### Happy path
- The Email Broadcasts Compose tab shows a dropdown of active templates (matching what `/email-templates` lists); the free-text input is gone.
- Picking a template renders variable inputs (one per declared variable EXCEPT auto-resolved ones) and a live preview iframe to the right.
- Subject text in the preview matches the typed override or the template default when override is empty.
- Send Now is disabled until name + template + every required (non-auto-resolved) variable are filled AND the audience preview shows ≥ 1 recipient.
- Submitting Send Now passes `variables` through to `/api/v2/broadcasts/email`; the JobStore result message reflects the same delivered count as before.
- **Latent-bug regression check:** broadcast-sent emails of `b2b_introduction` now render with the full shared-config variables (banner, footer links, social) — not empty strings. Verify by hitting the audit `email_sends` row's stored HTML or by sending a test broadcast to a single test contact and inspecting the rendered email.

#### Schedule (deferred to 7.2b)
- The "Schedule" button is **disabled** in 7.2a with a tooltip "Coming in 7.2b". Why: scheduled broadcasts go through `Campaign` rows for persistence, and `Campaign` has no `variables` column. Shipping schedule before the migration would silently drop typed variables. 7.2b adds the column.

#### Error states
- Picked template doesn't exist (race): API returns 400 "Template not found"; UI surfaces inline.
- Audience preview returns 0 recipients: Send Now stays disabled with text "0 recipients — adjust filters above".
- Latent-bug fix breaks an existing call site (e.g. flows_engine.py also calls `_send_email_broadcast`): the regression test in `api_v2/tests/test_broadcasts.py` catches it before deploy.

---

## Phase 7.2b — Campaign.variables column for scheduled broadcasts

Small migration that lets scheduled broadcasts persist the typed variables across the schedule-and-fire boundary.

### Files to MODIFY

- `hf_dashboard/services/models.py`
  - `class Campaign`: add `variables = Column(JSONType, default=dict, nullable=False)` after the existing `subject` column.
- `api_v2/routers/broadcasts.py`
  - When `req.scheduled_at is not None`, also persist `c.variables = dict(req.variables or {})`.
- `api_v2/services/scheduler.py`
  - When firing a scheduled email Campaign, pass `c.variables` through as the `extra_vars` for `_run_email_broadcast`.
- `vite_dashboard/src/pages/broadcasts/components/ComposeTab.tsx`
  - Re-enable the "Schedule" button.

### Files to CREATE

- `scripts/migrations/2026_05_07_add_campaign_variables_column.py` — one-shot Alembic-style migration (matches the project's existing migration pattern). Adds the column with a default of `{}` so existing rows are backfilled implicitly. Idempotent: checks if the column already exists before adding.

### Acceptance criteria

- After deploy + migration, every existing `Campaign` row has `variables = {}`.
- Scheduling an email broadcast with typed variables → the `Campaign` row's `variables` column contains those values.
- When the scheduler fires the campaign at the scheduled time, the rendered emails use those variables (verified by the audit `email_sends` row).
- Migration is re-runnable without error.

---

## Phase 7.3 — Email Templates Studio: render preview + variables, hide HTML

The user wants the Studio to NOT show the raw HTML body by default. They want a rendered preview with sample variable values + variable inputs that drive the live preview, and the raw HTML behind an "Advanced" toggle.

### Files to MODIFY

- `vite_dashboard/src/pages/email-templates/components/EmailTemplateEditor.tsx`
  - Restructure the form so the HTML textarea is hidden by default behind a `<details>`-style toggle ("Advanced — edit HTML"). Default: closed.
  - Keep the Name / Slug / Type / Category / Subject template / Required variables / Active controls visible.
  - Replace the current right-pane (raw HTML iframe at lines 256-260 today: `srcDoc={form.html_content || "(empty body)"}` with `sandbox=""`) with `EmailRenderPreview` from 7.1, fed by the variables form below it.
  - Add an `EmailVariablesForm mode="studio"` underneath the metadata form. In the Studio there's no contact context, so prefill from the YAML `example` values (the `variable_spec` payload already includes these). For DB-only templates without `.meta.yml`: form renders empty inputs with placeholder text "Sample <varname>" for each `required_variables` entry. Edits drive the preview live.
  - When the user is editing `html_content` in the Advanced textarea, the preview re-renders against the IN-MEMORY HTML (passes `html_content_override` to `/render-preview`) so the user sees their unsaved edits.
- `vite_dashboard/src/api/email_send.ts` (created in 7.1) — `useRenderEmailPreview` accepts optional `html_content_override` + `subject_template_override`.
- `vite_dashboard/src/config/pages/email_templates.yml` — rewrite the "Preview" how-to-use to describe the new render preview, and add a "Variables" section.

### Files to CREATE

- None new — Studio consumes the components built in 7.1.

### Component tree sketch

```
EmailTemplateEditor (mode=edit|create)
├─ left form (top half):
│  ├─ Name / Slug / Type / Category
│  ├─ Subject template
│  ├─ Required variables (comma list)
│  ├─ is_active checkbox
│  └─ <details> "Advanced — edit HTML"
│     └─ <textarea html_content>
├─ left form (bottom half):
│  └─ EmailVariablesForm mode="studio" (defaults from variable_spec.example)
└─ right pane:
   ├─ desktop / mobile toggle
   ├─ rendered subject readout
   └─ EmailRenderPreview (iframe — fed by html_content_override + form vars)
```

### Acceptance criteria

#### Happy path
- Opening `/email-templates?id=<existing>` shows the rendered template (with example values) in the right pane on first paint. The HTML textarea is NOT visible.
- The "Advanced — edit HTML" disclosure expands to show the textarea; collapsing it hides the HTML again. State of the disclosure does NOT alter form values.
- Editing a variable in the form updates the iframe within ~500ms.
- Editing the HTML body (Advanced) updates the iframe live; Save persists the change. Reload (`?id=X`) shows the saved version rendered with example values.
- Creating a new template (`?id=new`) renders a graceful empty preview ("(empty body)") until the user types HTML or picks a base. The variables form renders empty until `required_variables` is non-empty (then "Sample <varname>" placeholders appear).
- Saving works exactly as today (POST `/email/templates` for create, POST `/email/templates/{id}/save` for edit). The render-preview endpoint is read-only and never persists anything.

#### Cache invalidation
- Saving a template (`/email/templates/{id}/save`) invalidates `["email", "templates"]` query keys so the dropdowns in `/email-send` and `/email-broadcasts` Compose pick up the new content without page reload.
- Creating a template invalidates the same key.

#### Error states
- Saving fails (slug collision, validation error): existing inline error UX kicks in; preview pane stays unchanged.
- Variable spec missing (DB-only template, no `.meta.yml`): variables form shows "Add variables in the Required variables field above to drive the preview" hint.
- `/render-preview` returns 500 (Jinja syntax error in the user's edited HTML): preview pane shows the Python traceback in a red error block. Save button stays enabled (the user might be intentionally typing partial HTML).

---

## Decisions to surface back to user

These are the sub-choices where the original plan asked for sign-off. Two are flipped vs first draft (D3, D6); rest stand.

1. **Where does single-contact send live?** ✅ **Top-level route `/email-send`** with a sidebar entry, NOT a Contacts drawer tab. Reasons: (a) the WA Inbox precedent is a dedicated "send-something-now" surface; (b) the founder thinks "I want to send Prashant the order_confirmation" — picker-first beats contact-first; (c) a drawer tab forces an extra click to change recipient. **Alternative if you disagree:** add a "Send email" tab to `ContactDrawer.tsx` alongside Profile / Tags / Notes / Activity. Could ALSO add the drawer tab as a thin shortcut to `/email-send?contact=<id>` — costs little.

2. **Should single-contact sends be tracked as 1-recipient broadcasts?** ✅ **NO — write a single `EmailSend` row with `campaign_id=NULL`**. Reasons: (a) keeps `/email-broadcasts` History clean; (b) v1's `_on_test_send` already uses this exact shape; (c) `email_sends.idempotency_key` is sufficient to dedupe. **Alternative:** auto-derive a Campaign + EmailSend pair. Surfaces in History but fragments it.

3. **Variables endpoint vs inline payload.** 🔄 **FLIPPED — inlined `variable_spec: list[EmailVariableSpec]` on `EmailTemplateOut`**. Reasons: (a) variable spec is small (~5 fields × N variables); (b) one round-trip when fetching a template by id is faster than two; (c) `lru_cache` is server-side perf, orthogonal to wire shape; (d) avoids one whole new endpoint to maintain. **Original recommendation was a dedicated endpoint** — flipped after review.

4. **Contact-picker UX shape on `/email-send`.** ✅ **Left-rail search-as-you-type list** like `ConversationList`, not a Combobox dropdown. Reasons: (a) `vite_dashboard/src/components/ui/` has no Combobox / cmdk primitive yet; (b) consistent with WA Inbox pattern; (c) founder's contact list is small enough that a paginated list works. **Note**: the founder's largest segment (Carpet Exporters India) has 1543 contacts; debounced search + 25-row page should still be responsive.

5. **Server-side render endpoint vs client-side Jinja.** ✅ **Server-side `/render-preview` (mandatory)**. Jinja2 ships server-side only and seeded templates use `{% extends %}`. Confirmed.

6. **Sidebar position of "Send Email".** 🔄 **FLIPPED — "Send Email" sits ABOVE "Email Broadcasts"** so the email cluster reads top-down: Send Email → Email Broadcasts → Email Templates. **Original recommendation was between `wa_inbox` and `email_broadcasts`** — flipped because that splits WA from itself.

---

## Risks / unknowns (tightened from first draft)

- **`required_variables` is a flat list of names; the rich spec lives in YAML, not the DB.** The DB column `email_templates.required_variables` is just `["first_name", "company_name"]` — no type/label/placeholder metadata. Rich variable forms therefore depend on `get_template_meta(slug)` finding a `.meta.yml`. For DB-only templates created via the Studio (no YAML companion file), the variable-spec endpoint synthesizes a default spec (`type=text`, label=name, no example, no placeholder) so the UI still renders something. Worth flagging that variables for hand-rolled templates are typed-as-plain-text only until they ship a YAML.
- **Latent broadcast-engine bug — verified.** Already addressed in 7.2a's scope. NOT a "future risk"; today's broadcasts are silently shipping with missing shared-config variables. Phase 7.2a's regression test guards against future drift.
- **Iframe sandbox CSS scoping.** Current Studio uses `sandbox=""` (full sandbox) on the iframe and feeds `srcDoc=html_content`. New `EmailRenderPreview` keeps `sandbox=""` and feeds the rendered HTML the same way. No CSS-isolation worries because `<iframe srcDoc>` already isolates. Wire `EmailSender._preprocess_html` into `/render-preview` so what you see equals what gets sent (Gmail @import font handling, etc.).
- **`EmailRenderPreview` re-renders on every keystroke.** Debounce variable-form changes 200ms in the form component before firing `useRenderEmailPreview` so we don't hammer the API.
- **`/api/v2/email/test-sends` rate limiting / spam.** Founder-only Space, single user; rely on idempotency key. The per-day idempotency window is intentionally aggressive to prevent accidental double-sends; a "Force resend" affordance is a Phase 8 candidate.
- **Sidebar config consistency.** Existing sidebar.yml predates the Phase 6.3 split — verify `navigationEngine.itemToRoute` maps `email_send` → `/email-send`. Smoke-test on first deploy.
- **Cache invalidation on template edit.** Both 7.1 and 7.2 read `useEmailTemplates` for the dropdown. Save in `/email-templates` (Phase 7.3) MUST invalidate `["email", "templates"]` so the dropdowns refresh. Listed as AC; failing this means stale dropdowns until page reload.

---

## Sequencing

The phases share the `EmailRenderPreview` + `EmailVariablesForm` components and the `/render-preview` endpoint. Build order:

1. **7.1 in three sub-steps.**
   - 7.1a (backend): inline `variable_spec` on `EmailTemplateOut` + ship `POST /api/v2/email/render-preview` + `POST /api/v2/email/test-sends` + their schemas + register router. Smoke-test via curl on the live Space.
   - 7.1b (frontend shared): build `EmailVariablesForm` + `EmailRenderPreview` + `useRenderEmailPreview` + `useSendOneEmail` in `components/email/` + `api/email_send.ts`.
   - 7.1c (frontend page): build `EmailSendPage` + `ContactPicker` + `EmailTemplatePicker` + `email_send.yml` + register route + sidebar entry.
2. **7.3 second** — easier than 7.2 because it has no broadcast queue surface to coordinate with. Modifying the Studio editor is a drop-in: import the two shared components, gate the HTML textarea behind `<details>`. Validates the shared components from a different angle (no contact context, YAML examples drive defaults).
3. **7.2a third** — depends on the shared components AND ships the broadcast-engine latent-bug fix. Touches both UI AND the v1 broadcast engine.
4. **7.2b last** — small migration enabling Schedule. Independent of the rest; could be deferred a week if needed.

Why this order: 7.1 forces the API contract for the shared pieces; 7.3 is the simplest consumer (single page, no broadcast queue, no engine path); 7.2a is the most coordination-heavy because it touches both UI AND the v1 broadcast engine; 7.2b is a tidy follow-up.

---

## Deploy + verify gate (per project CLAUDE.md)

Each phase ships through:

1. Local commit (`git commit`) on `main` after type-check + tests pass.
2. `python scripts/deploy_hf_v2.py` upload.
3. Wait for Space rebuild → `Status: Running` (typically 5-8 min).
4. Drive the live URL with the Playwright MCP tools (headless) to verify the AC list above.
5. Hand off only after AC pass on the live Space.

Per the user's preference (CLAUDE.md, 2026-04-14): **never run the app locally**. Verification is always on the live Space via Playwright.

---

## Out of scope

- **Drag-and-drop or rich-text email editor.** The user explicitly said "I just want to have a set template, standardized template where I can just have the variables on it" — the studio stays slug-driven with a hidden HTML escape hatch. No MJML editor, no block-based editor.
- **Bulk single-send (CSV → many one-offs).** That's broadcasts. If the user wants this it's a flat audience selector, not a single-contact surface.
- **Email scheduling for single sends.** Single-contact sends fire immediately. Scheduling is for broadcasts (already shipped).
- **Tracking opens / clicks.** v1 doesn't track these on broadcasts either. Phase 8.
- **Force-resend bypass for idempotency.** Per-day dedup is the right default for the founder use case; bypass is Phase 8.
- **Variable spec editor in the Studio.** The `.meta.yml` spec is filesystem-only today; adding a UI to edit it is its own surface (would need to write back to the YAML file or migrate to a DB column). Skip for Phase 7.
- **Per-recipient variable overrides at compose time.** That's a CSV-mapping surface — out of scope for Phase 7.
- **Combobox / cmdk primitive.** Sticking with the rail-list contact picker. Adding `cmdk` is a different concern.

---

### Critical files for implementation

- `vite_dashboard/src/pages/email-templates/components/EmailTemplateEditor.tsx` (Phase 7.3)
- `vite_dashboard/src/pages/broadcasts/components/ComposeTab.tsx` (Phase 7.2a)
- `vite_dashboard/src/components/email/EmailVariablesForm.tsx` (NEW — 7.1)
- `vite_dashboard/src/components/email/EmailRenderPreview.tsx` (NEW — 7.1)
- `vite_dashboard/src/api/email_send.ts` (NEW — 7.1)
- `api_v2/routers/email_send.py` (NEW — 7.1)
- `api_v2/routers/email_templates.py` (modified for `variable_spec` field — 7.1)
- `api_v2/schemas/email_templates.py` (modified — 7.1)
- `hf_dashboard/services/template_seed.py` (read-only reference for `get_template_meta`)
- `hf_dashboard/services/email_personalization.py` (read-only reference for `build_send_variables`)
- `hf_dashboard/services/email_sender.py` (read-only reference for `render_template_by_slug`, `generate_idempotency_key`)
- `hf_dashboard/services/broadcast_engine.py` (modified for the latent-bug fix — 7.2a)
- `hf_dashboard/services/models.py` (modified to add `Campaign.variables` — 7.2b)
- `vite_dashboard/src/config/dashboard/sidebar.yml` (modified — 7.1)
