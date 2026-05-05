# Phase 7 — WhatsApp Implementation Plan

## Implementation strategy

Phase 7 closes the three remaining usability gaps in the WhatsApp side of the Himalayan Fibres dashboard, all of which were exposed by Phase 6.5's TemplateSheet rewrite. Two of them (Problems 1 and 3) are pure-UI changes — they reuse code paths that already exist on the backend. The third (Problem 2) is the one real backend bug: `WhatsAppSender.sync_templates_from_meta` writes Meta's raw `components` JSON to the `WATemplate.components` column but never decomposes it back into the flat `body_text` / `header_text` / `header_format` / `header_asset_url` / `footer_text` / `buttons` columns the rest of the app reads from. Every other surface (TemplateSheet preview, WaPhonePreview, send pipeline) reads the flat columns, which is why `b2b_fiber_intro` / `thank_you_note` / `welcome_message` show "Body not synced from Meta" even though sync ran successfully.

The order of work is 7.4 (sync fix — biggest leverage, unblocks 7.5 + 7.6) → 7.5 (Studio preview parity with TemplateSheet — pure-extract refactor) → 7.6 (start-new-conversation flow — needs no schema changes, just a contact picker that writes `?contact=<id>` to the URL). Risk is concentrated in 7.4 because we're parsing Meta's component shape; we'll mitigate by keeping the existing `components` column as the source of truth and treating the new flat-column writes as a derived projection so a buggy decomposition never destroys data.

---

## Phase 7.4 — Sync from Meta populates flat columns

### Problem recap
After running "Sync from Meta", `WATemplate.components` is filled but `body_text`, `header_text`, `header_format`, `header_asset_url`, `footer_text`, and `buttons` (the flat columns the UI reads) stay empty. TemplateSheet's preview and Studio's WaPhonePreview both render "(empty body)" / "Body not synced from Meta", and any actual send still works (Meta builds the message from the approved template by name) but the operator cannot see what they're about to send.

### Root cause
`hf_dashboard/services/wa_sender.py` lines 342–406, `sync_templates_from_meta`, only writes `category`, `status`, `quality_score`, `components`, `last_synced_at`, `is_draft`, `rejection_reason`. It never iterates `components` to populate the flat columns. The reverse mapping (Meta components → flat columns) does not exist anywhere in the repo. The forward mapping is `wa_template_builder.build_components` (flat-ish spec dict → components). We need an inverse.

### Files to modify

- `hf_dashboard/services/wa_sender.py` — add a private `_decompose_components(components: list[dict]) -> dict` helper that returns `{body_text, header_format, header_text, header_asset_url, footer_text, buttons}` from Meta's components shape. Call it inside `sync_templates_from_meta` for both the create branch and the update branch and write each field onto the WATemplate row.
- `hf_dashboard/services/wa_template_builder.py` — co-locate the inverse with the existing forward `build_components` so they cannot drift. Export `decompose_components(components)`. `wa_sender.py` imports and calls it.

### Files to create

- `scripts/migrations/2026_05_06_backfill_wa_template_flat_columns.py` — one-shot migration that loads every `WATemplate` row with non-empty `components` and an empty `body_text`, runs `decompose_components`, and persists the flat fields. Idempotent: re-running it after sync overwrites the same values. Lets the user backfill existing rows without re-hitting Meta. Optional once the user runs Sync from the UI again, but cheap insurance. (Path matches the existing `scripts/migrations/YYYY_MM_DD_<slug>.py` convention — directory and naming pattern verified against `2026_05_05_add_broadcast_scheduled_at.py` and siblings.)

### Components mapping table (the contract `decompose_components` must implement)

Meta's `components` is a list of objects keyed by `type` (uppercase). The mapping back to flat columns is:

| Meta component | Flat column |
|---|---|
| `{"type": "HEADER", "format": "TEXT", "text": "..."}` | `header_format = "TEXT"`, `header_text = text` |
| `{"type": "HEADER", "format": "IMAGE"\|"VIDEO"\|"DOCUMENT", "example": {"header_handle": [url, ...]}}` | `header_format = format`, `header_asset_url = first url or ""` |
| `{"type": "BODY", "text": "..."}` | `body_text = text` |
| `{"type": "FOOTER", "text": "..."}` | `footer_text = text` |
| `{"type": "BUTTONS", "buttons": [...]}` | `buttons = list` (verbatim — the buttons schema already matches WaPhonePreview's expectation) |

Edge cases to handle in the helper:
- Component dict missing `type` → skip (defensive).
- `example` field on BODY component → ignore for now (Meta's example values are training data we don't expose to operators yet).
- Multiple HEADER or BODY entries (Meta should never return this, but be permissive — first wins, log a warning).
- `buttons` items with unknown `type` → preserve as-is so future button types don't get silently dropped.

### API additions
None. Existing `POST /api/v2/wa/templates/sync` is the entry point.

### Schema/DB additions
None. The flat columns already exist; we're just populating them. The migration script does no DDL.

### Component tree sketch
None — pure backend.

### Acceptance criteria (testable on the live Space)

- **AC-7.4.1** Click "Sync" on `/wa-templates`. After the job completes, opening any approved row in the editor shows non-empty Body, and (when present) Header / Footer / Buttons.
- **AC-7.4.2** On `/wa-inbox`, open TemplateSheet for any contact, pick `b2b_fiber_intro`. The "Body not synced from Meta" warning is gone; the source body box and the green Preview pane both render the actual template text. Variables for the body show one input each (`{{1}}`), and the header section shows the header text plus its `{{1}}` input.
- **AC-7.4.3** Re-running Sync is idempotent — no duplicate rows, no cleared flat columns when Meta returns a row that already exists locally.
- **AC-7.4.4** Drafts whose `(name, language)` does **not** appear in Meta's response are untouched by sync (existing behavior, regression check). Drafts that *do* match a Meta entry continue to be promoted (`is_draft=False`) per the existing `wa_sender.py:381` behavior, and their flat columns are populated/overwritten from the synced components — Phase 7.4 does not change this promotion contract.
- **AC-7.4.5** A Python unit test feeds a hand-rolled components list into `decompose_components` and asserts the dict shape; one test per mapping row above.

### Decisions to surface

- **D1** Should the migration script run automatically on next backend deploy (alembic revision) or stay manual (operator runs `python -m scripts.migrations.2026_05_06_backfill_wa_template_flat_columns`)? Recommendation: manual, because v1 deploys via the HF Space's startup command and we don't want a long backfill blocking boot. The user can also just click "Sync" from the UI which calls the same logic.
- **D2** When Meta's `BODY.text` differs from the existing local `body_text` (e.g. the user edited a draft, then it got approved, then we sync), should we overwrite? Recommendation: yes for non-draft rows (Meta is the source of truth for approved content), no for draft rows (preserve local edits).

### Risks / unknowns

- **R1** Some templates use Meta's "limited time offer" or "carousel" component types that aren't covered by the current button schema. We don't currently use them; if Meta returns one we should log and skip rather than crash.
- **R2** Meta sometimes returns the BODY `example` as `{"body_text": [["Prashant", "Acme"]]}` (list-of-lists). We're not consuming this today, but if Phase 8 ever uses it for "fill from example" UX, the decomposer should already capture it under a separate `example_values` field. Out of scope for 7.4.
- **R3** Header IMAGE/DOCUMENT/VIDEO assets stored under `example.header_handle` are usually short-lived Meta CDN URLs, not stable. Persisting them to `header_asset_url` is fine for preview display but the actual send still uploads media at send time. Document in the helper docstring.

---

## Phase 7.5 — Live preview pane on the Studio editor

### Problem recap
`/wa-templates` editor right pane today is `WaPhonePreview` — a static green-bubble render of `header_text` / `body_text` / `footer_text` / `buttons` where variables stay as raw `{{1}}` literals. The user wants the same affordance the TemplateSheet got in Phase 6.5: variable inputs (header + body), live substitution, the green preview bubble updating as values change. Quote: "if I select any template, right, I am not able to see the preview of the template."

### Strategy
Extract the preview-rendering logic from `TemplateSheet.tsx` into a small reusable component, then mount it on the Studio page. We do NOT want to inline-duplicate the regex / `resolveVariableForContact` / `renderPreview` logic — there are already two copies (TemplateSheet for inbox, WaPhonePreview for studio) and Phase 7.5 is the chance to consolidate.

### Files to create

- `vite_dashboard/src/components/wa/TemplatePreview.tsx` — the shared component. Props:
  - `template: WATemplateOut` (or the editor-form shape — accept a Pick of body_text/header_format/header_text/header_asset_url/footer_text/buttons).
  - `headerVariables: Record<string, string>`, `bodyVariables: Record<string, string>` — current values keyed by placeholder name.
  - `headerVarNames: string[]`, `bodyVarNames: string[]` — declaration-order list of placeholder names.
  - `onHeaderVarsChange`, `onBodyVarsChange` — controlled-component callbacks.
  - `showInputs?: boolean` (default true) — when false, render preview-only (used by the Studio's "before any edits" empty-state).
  - `style?: "phone" | "card"` (default "card") — `phone` swaps to the existing dark green-bubble visual; `card` is the lighter inline style TemplateSheet uses.

  The component owns: the placeholder regex, `renderPreview`, the variable-input list (header section + body section), and the green bubble. No data fetching — caller supplies values.

- `vite_dashboard/src/lib/wa-template-vars.ts` — pure helpers, framework-agnostic:
  - `extractPlaceholders(text: string): string[]` — first-appearance-order, deduped.
  - `renderPreview(text: string, vars: Record<string, string>): string` — current `renderPreview` from TemplateSheet.
  - `resolveVariableForContact(name: string, contact: {contact_name?, contact_company?} | null): string` — current logic from TemplateSheet.

  Putting these in `lib/` lets unit tests run them without React; both TemplateSheet and TemplatePreview consume them.

### Files to modify

- `vite_dashboard/src/pages/wa-templates/components/TemplateEditor.tsx` —
  - Replace the right-side `<WaPhonePreview template={form …} />` with `<TemplatePreview ... />`.
  - Hold `headerVars` and `bodyVars` state in the editor (sibling to `form`). Initialize empty; do NOT auto-prefill from a contact (there's no selected contact in Studio — fall back to the template's `example` values when sync provides them, otherwise leave blank and let the placeholder show as `{{name}}`).
  - Recompute `headerVarNames` and `bodyVarNames` from `form.header_text` and `form.body_text` via `extractPlaceholders` whenever those texts change.
  - Pass everything down to `<TemplatePreview>`.
- `vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx` — refactor to consume `<TemplatePreview>` plus the `lib/wa-template-vars.ts` helpers. The contact-aware prefill stays in TemplateSheet (it's the only caller that has a contact in scope). Net: TemplateSheet shrinks from ~340 lines to ~180.
- `vite_dashboard/src/pages/wa-templates/components/WaPhonePreview.tsx` — keep as-is OR delete. Recommendation: delete, because `TemplatePreview` with `style="phone"` covers the use case and we don't want two preview components. If we keep it, gate its usage behind a feature flag so we have a fallback.

### Component tree sketch (Studio editor after refactor)

```
TemplateEditor
├── form section (left)
│   ├── name / language / category / header-format
│   ├── header_text / header_asset_url
│   ├── body_text textarea
│   ├── footer_text
│   └── buttons editor (existing)
└── preview aside (right)
    └── TemplatePreview
        ├── Variables section
        │   ├── Header inputs (one per headerVarName)
        │   └── Body inputs (one per bodyVarName)
        └── Green bubble
            ├── header_text rendered with substitution
            ├── body_text rendered with substitution
            ├── footer_text
            └── buttons list
```

### API additions
None.

### Schema/DB additions
None.

### Acceptance criteria

- **AC-7.5.1** On `/wa-templates`, select any APPROVED template. Right pane shows: Variables block with header + body inputs (collapsed if zero variables), then a green bubble with the live-rendered text. Editing a body input updates the bubble in real time. **Header media policy:** when `header_format` is `IMAGE`/`VIDEO`/`DOCUMENT`, the bubble renders the existing placeholder block ("IMAGE header" / "VIDEO header" / "DOCUMENT header"), **not** an `<img src={header_asset_url}>`. Reason: `header_asset_url` is sourced from Meta's short-lived CDN handle (see R3) and would render as a broken thumbnail once it expires. Real media rendering waits for stable storage, out of scope for 7.5.
- **AC-7.5.2** Switch from `b2b_fiber_intro` (header + 1 var, body + 1 var) to `welcome_message` (body only). Header section disappears; only body inputs remain.
- **AC-7.5.3** Open a draft (status null), edit `body_text`, watch the bubble update on every keystroke. Variable inputs rebuild when the user adds a new `{{...}}` token.
- **AC-7.5.4** TemplateSheet on `/wa-inbox` still works — same UX as Phase 6.5: contact-aware prefill, header + body inputs, live preview, send button gated on all-filled. No regressions.
- **AC-7.5.5** Lint + type-check pass; no `WaPhonePreview` import survives.

### Decisions to surface

- **D3** Should the Studio's preview default to `style="phone"` (matching today's dark-green visual that mimics WhatsApp on iOS) or `style="card"` (matching the inbox TemplateSheet)? Recommendation: `phone` for Studio (it's marketing-the-design content), `card` for inbox (it's transactional). Either way, having both keeps both surfaces visually distinguishable.
- **D4** When the Studio template has no contact in scope, should the variable inputs be blank, or pre-filled with Meta's `example` values (when sync stored them)? **Decision: blank, with a `placeholder={{varName}}` hint inside each input.** Reason: 7.4's `decompose_components` deliberately does not extract the `BODY.example.body_text[[...]]` shape (R2 in 7.4), so there are no example values in the DB to fall back to. Pre-filling from examples requires a schema/decompose extension; defer to Phase 8 along with the rest of the example-authoring UX.
- **D5** Should we keep `WaPhonePreview.tsx` for one phase as a fallback, or delete it now? Recommendation: delete now — leaving dead code invites drift. Git history is the fallback.

### Risks / unknowns

- **R4** TemplateSheet's `useEffect` dependency on `selectedName + convData?.contact_id` is load-bearing for the contact-aware prefill. After the refactor, that dependency should still be in TemplateSheet (not in TemplatePreview), or we'll cause re-renders to clobber user edits.
- **R5** The variables form on TemplateSheet is non-scrolling (B1 fix from earlier phase). Studio's editor has its own scroll container. Make sure TemplatePreview's variables block can grow without breaking the editor's two-column grid layout.

---

## Phase 7.6 — Start a new conversation with any WA-eligible contact

### Problem recap
`ConversationList` queries `WAChat` rows. A contact like Narendra Dubey-ji who has `wa_id` but no inbound message yet has no row, so they're invisible from `/wa-inbox`. The user's only workaround today is the Broadcast page, which is not the right tool for a 1:1 first-touch. Quote: "I have to go send them via the broadcast, which is again not relevant in this."

### Strategy
The send pipeline already creates the WAChat row on the first template send via `_ensure_chat` (lines 372–379, 497 of `api_v2/routers/wa.py`). The fix is purely UI: give the operator a way to set `?contact=<id>` to a contact who doesn't yet appear in the conversation list. Once that URL is set, `ChatPanel` loads the contact, sees `last_inbound_at = null`, renders `ClosedWindowCta` with the existing `new_conv_warning` ("No conversation yet. Sending a template will open a 24-hour window…"), and the operator clicks "Send a template" — same flow that already works for archived chats today.

### Files to create

- `vite_dashboard/src/pages/wa-inbox/components/NewConversationDialog.tsx` — modal dialog (or right-side `Sheet`, see D6 below) containing:
  - A search input (debounced, mirrors ConversationList's pattern).
  - A scrollable contact list driven by `useContacts({ channel: "whatsapp", search: debounced, page_size: 50 })` — already-existing hook, already filters to contacts with `wa_id`.
  - Each row: `<full_name> <company>` + `<phone>` subtitle + a `wa_consent_status` pill (green if `opted_in`, gray otherwise).
  - "Optional but recommended" filter chip: "Hide existing conversations" — when checked, exclude contact_ids that already appear in `useConversations({ page_size: 200 })` data so the picker only shows truly-new contacts.
  - Pick a row → close dialog, call `onPick(contactId)`.

### Files to modify

- `vite_dashboard/src/pages/wa-inbox/WAInboxPage.tsx` —
  - Add `const [newConvOpen, setNewConvOpen] = useState(false);`.
  - When the dialog picks a contact, call `selectContact(contactId)` (existing function — sets `?contact=<id>`) and `setTemplateSheetOpen(true)` to immediately surface the picker (the chat will be empty so the operator's only useful next action IS sending a template).
  - Mount `<NewConversationDialog open={...} onOpenChange={...} onPick={...} />`.
- `vite_dashboard/src/pages/wa-inbox/components/ConversationList.tsx` —
  - Add a "+ New conversation" button at the top of the panel (above the search box, or pinned in the header next to the title) that calls a new `onNewConversation` prop bubbled from `WAInboxPage`.
  - Optionally: if the search input is non-empty AND no existing conversations match, show a "Start a new conversation with someone matching '<search>'" affordance under the empty state — clicking it opens NewConversationDialog with that search prepopulated. (D8 below.)
- `vite_dashboard/src/config/pages/wa_inbox.yml` — add labels under `panels.conversations`:
  - `new_conversation_button: "+ New conversation"`
  - `new_conversation_dialog_title: "Start a new WhatsApp conversation"`
  - `new_conversation_dialog_help: "Pick a contact who has a WhatsApp number. Only contacts with wa_id are shown."`
  - And under `panels.chat`, no changes needed — the existing `new_conv_warning` label already covers the empty-conversation state.
- `vite_dashboard/src/loaders/configLoader.ts` — no edits if YAML keys nest under existing `panels.conversations`. Loader is shape-agnostic.

### API additions
None — the existing endpoints cover the case:
- `GET /api/v2/contacts?channel=whatsapp&search=...` → list candidates.
- `GET /api/v2/wa/conversations/{contact_id}` → already returns a valid `ConversationDetail` for a contact with no WAChat (chat is None, messages = [], `window_open=false`, `last_inbound_at=null`).
- `POST /api/v2/wa/template-sends` → already calls `_ensure_chat` to create the WAChat row.

### Cache-invalidation dependency

AC-7.6.5 ("re-opening the dialog after a send no longer shows Narendra in the picker") relies on the dialog's `useConversations({ page_size: 200 })` exclusion-set query being invalidated after a successful template send. This is **already provided** by `useSendTemplate` in `vite_dashboard/src/api/wa.ts:194-195`:

```ts
qc.invalidateQueries({ queryKey: ["wa", "conversation", variables.contact_id] });
qc.invalidateQueries({ queryKey: ["wa", "conversations"] });
```

No new invalidation is required in 7.6, but the dialog **must** read from the same `["wa", "conversations"]` query key — do not introduce a separate fetch. If a future refactor splits the conversation list query, update the invalidation list at the same time.

### Schema/DB additions
None.

### Component tree sketch

```
WAInboxPage
├── ConversationList (left)
│   ├── header
│   │   ├── title + count
│   │   └── + New conversation button → setNewConvOpen(true)
│   ├── search input
│   └── rows…
├── ChatPanel (center) — unchanged; renders ClosedWindowCta when last_inbound_at is null
├── Tools panel (right) — unchanged
├── TemplateSheet (existing)
└── NewConversationDialog (new)
    ├── search input
    ├── "Hide existing conversations" toggle (default on)
    └── contact list
        └── row → onPick(contact.id) → selectContact + setTemplateSheetOpen
```

### Acceptance criteria

- **AC-7.6.1** On `/wa-inbox`, click "+ New conversation". Dialog opens.
- **AC-7.6.2** Type "Narendra" — dialog shows Narendra Dubey-ji (assuming `wa_id` is set on his contact row). Click his row.
- **AC-7.6.3** Dialog closes. URL updates to `?contact=<narendra-id>`. ChatPanel shows his name in the header, "Window closed" pill, empty message list, and the ClosedWindowCta with text "No conversation yet. Sending a template will open a 24-hour window…".
- **AC-7.6.4** TemplateSheet auto-opens (because the operator's only useful next action is sending a template). Picking a template, filling vars, hitting Send works exactly like Phase 6.5: the WAChat row is created, the message is sent, and the conversation appears in ConversationList on the next refetch.
- **AC-7.6.5** Reopening the dialog with "Hide existing conversations" toggled on does NOT show Narendra anymore (he now has a chat).
- **AC-7.6.6** Contacts without `wa_id` are NOT in the dialog list — the `channel=whatsapp` filter on `/api/v2/contacts` already enforces this (line 174 of contacts.py).

### Decisions to surface

- **D6** Dialog vs Sheet: should NewConversation be a centered modal (Shadcn `<Dialog>`) or a right-side slide-over (Shadcn `<Sheet>`, like TemplateSheet)? Recommendation: Sheet, on the same side as TemplateSheet but visually distinct (e.g. left side, or a different width). Keeps the inbox page consistent. But Dialog is fine for a one-shot picker that doesn't share screen real estate with the chat below. Defer to user.
- **D7** Should `wa_consent_status` gate sending? Today the schema has `consent_status` (`pending` / `opt_in` / `opt_out`) AND a separate `wa_consent_status` (`unknown` / etc.). Options:
  - (a) Block: if `wa_consent_status == "opt_out"`, dialog shows the row but disabled with tooltip "Customer opted out".
  - (b) Warn only: row is enabled; a small warning pill renders next to their name, but click-through is allowed.
  - (c) Ignore consent at picker level: enforcement lives in the send mutation (which today is also permissive).
  Recommendation: (b) for now — Phase 8's "Consent UX" deliverable will add the proper gating end-to-end.
- **D8** Should the picker be a separate dialog at all, or should we inline a "no results — search all contacts?" affordance into the existing ConversationList search? Recommendation: separate dialog. ConversationList's search filters existing chats; mixing "existing chat" rows with "potential new chat" rows in the same list creates a confusing mode switch (does Enter open the chat or start a new one?). Two surfaces, two purposes.
- **D9** Auto-open TemplateSheet after pick, yes/no? Recommendation: yes — every selected new contact has zero history and needs a template to start anything. Skipping the click saves one step.
- **D10** Should the dialog support multi-pick (start N conversations at once with the same template)? Recommendation: no for 7.6 — that's the Broadcast page's job. Keep this single-pick.

### Risks / unknowns

- **R6** `useContacts` returns paginated data (page_size up to 200). If a Hindi-speaking contact's name contains diacritics, the ILIKE in the API may not match cleanly. The pre-existing search filter already has this property; not a 7.6-specific risk, just a known limitation.
- **R7** A contact might have `wa_id` set but the underlying phone number isn't actually on WhatsApp. The send call will fail at Meta with code 131026. We don't pre-flight check; the existing failure surface (red bubble, error toast) is the user's signal. Acceptable for now.
- **R8** Two operators independently picking the same contact at the same moment will both succeed, both will create the same WAChat row in a race — but `_ensure_chat` does `db.flush()` not `db.commit()`, and `WAChat.contact_id` has `unique=True`, so the second insert raises and the second template send returns 500. Probability negligible (single-operator system today). Not blocking 7.6.

---

## Sequencing

1. **7.4 first** (sync fix). It's the only one that requires careful backend testing, and it unblocks 7.5 (Studio preview is meaningful only when sync produces real `body_text`) and 7.6 (the user's first-template-send needs a non-empty preview).
2. **7.5 second** (Studio preview). Refactor extracts shared components from TemplateSheet first, then mounts them in the Studio editor. The TemplateSheet refactor is a no-op behavior change that the user can verify on `/wa-inbox` independently before we touch Studio.
3. **7.6 last** (new conversation flow). Independent of 7.4 in principle, but the user experience of "click new conversation → pick contact → see template preview" is markedly worse without 7.4's preview data. Doing 7.6 last means the demo-able flow at the end of Phase 7 is: pick a fresh contact, immediately see a real template preview, send it, get a working conversation.

Within each phase, the suggested intra-phase order is:
- 7.4: implement `decompose_components` + tests → wire into `sync_templates_from_meta` → manual sync from UI → verify Studio + TemplateSheet show real bodies → write the backfill migration script for any deploy that doesn't hit Sync first.
- 7.5: extract `lib/wa-template-vars.ts` → write `TemplatePreview.tsx` → migrate TemplateSheet (verify on inbox) → migrate TemplateEditor (verify on Studio) → delete `WaPhonePreview.tsx`.
- 7.6: build `NewConversationDialog` against the existing `useContacts` hook → wire into `WAInboxPage` → add the YAML labels → smoke-test the end-to-end flow.

## Out of scope for Phase 7

- **Inbound webhook plumbing.** The wa_webhook.py handler is v1-side and creates WAChat rows on inbound. No changes needed; 7.6 only handles outbound-first conversations.
- **Deeper consent UX.** D7 above defers the opt-out gating. Phase 8 should deliver: contact-detail page consent toggles, audit log of consent changes, send-mutation enforcement, and the `wa_consent_status` vs `consent_status` reconciliation.
- **Bulk new-conversation start.** D10 above; keep multi-pick out.
- **Template example-values authoring on the Studio editor.** Meta supports `example` values per BODY/HEADER for the approval review. Today we capture them only when a draft is built via YAML; the Studio editor doesn't expose them. Phase 8 candidate.
- **SSE reconnection telemetry.** Out of scope here; the existing `useWaLiveStream` is fine.
- **Persisting the "Hide existing conversations" toggle state in the URL.** Localized component state is enough.
- **Header_variables column in the DB.** Today header placeholders are detected by re-scanning `header_text` on each render. A dedicated column would let us validate at template-creation time — out of scope.

---

### Critical Files for Implementation
- `hf_dashboard/services/wa_sender.py` — sync fix (Problem 2) lives here.
- `hf_dashboard/services/wa_template_builder.py` — co-locate `decompose_components` next to `build_components` to prevent drift.
- `vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx` — donor for the shared `TemplatePreview` extraction.
- `vite_dashboard/src/pages/wa-templates/components/TemplateEditor.tsx` — recipient of the shared preview component (Problem 1).
- `vite_dashboard/src/pages/wa-inbox/WAInboxPage.tsx` — host for the new `NewConversationDialog` and the URL-param wiring (Problem 3).
