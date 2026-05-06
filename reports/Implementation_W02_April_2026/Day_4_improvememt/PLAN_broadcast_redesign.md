# Phase 8 — WhatsApp Broadcast Page Redesign

## Implementation strategy

Phase 8 redesigns `/wa-broadcasts` around a two-column layout — filters on the left, a sticky key-card row plus a phone-style template preview on the right — driven by a shared template picker that introduces two-level filtering (Meta `category` + intent `use_case`). The same picker is reused in the inbox `TemplateSheet` so the operator's mental model is identical across both surfaces. The redesign is mostly UI work on top of components already shipped in Phase 7.5 (`<TemplatePreview>` with `style="phone"`), with one small backend addition: a `/api/v2/wa/template-registry` endpoint that surfaces the YAML registry's `use_case` and `display_name` fields the API does not currently expose.

The order of work is 8.1 (registry endpoint — unblocks the picker's intent filter) → 8.2 (extract `<WaTemplatePicker>` shared component) → 8.3 (inbox `TemplateSheet` adopts the picker) → 8.4 (broadcast `ComposeTab` redesign) → 8.5 (small cleanup of the dead third column on `/wa-inbox` plus the HowToUse full-width fix). Risk is concentrated in 8.4 because we're moving working components around and the broadcast page has the most state. Mitigation: keep mutation logic, audience-funnel band, and `SendConfirmDialog` untouched — only the JSX layout and the template-picker portion change.

The wireframe at `wireframes/broadcast_page_redesign.excalidraw` is the source of truth for the 8.4 layout.

---

## Phase 8.1 — `template-registry` endpoint

### Problem recap
Today `GET /api/v2/wa/templates` returns only the `WATemplate` DB columns: `name`, `category` (MARKETING / UTILITY / AUTHENTICATION), `body_text`, `variables`, `buttons`, etc. The richer human-classification — `use_case` (`onboarding`, `transactional`, `retention`, `product_showcase`, `catalog`, `testing`) and `display_name` — lives only in `config/whatsapp/templates.yml` and is not exposed to the frontend. Without it, the new picker cannot offer the "Intent" filter row.

### Root cause
The registry YAML was added Phase 1 as a developer reference; nothing reads it at runtime. The frontend has no source for `use_case`.

### Files to modify

- `api_v2/routers/wa.py` — add `GET /api/v2/wa/template-registry` returning the parsed YAML keyed by template name, validated through a Pydantic model. Re-uses `services/wa_config.py` if a loader already exists; otherwise add a minimal `load_template_registry()` helper there.
- `api_v2/schemas/wa.py` — add `TemplateRegistryEntry` (`name`, `display_name`, `description`, `use_case`, `category` echoed for convenience, `notes`). Add `TemplateRegistryOut` wrapping `entries: list[TemplateRegistryEntry]`.
- `vite_dashboard/src/api/wa.ts` — add `useTemplateRegistry()` query (key `["wa", "template-registry"]`, `staleTime: 60_000` since it changes only on deploys).
- `vite_dashboard/src/schemas/api.ts` — add the matching zod schema, `.strict()`.

### Files to create

None (the YAML already exists; we're just exposing it).

### Intent label map

The picker needs **user-facing** labels, not the YAML's engineer-y `use_case` strings. Map server-side in the endpoint so the frontend never needs to know the raw values:

| YAML `use_case` | UI label |
|---|---|
| `onboarding` | Intro |
| `transactional` | Order |
| `product_showcase` | Sample |
| `catalog` | Catalog |
| `retention` | Follow-up |
| `testing` | Test |
| (missing / unknown) | Other |

The endpoint returns both the raw `use_case` and the display label (`intent_label` field) so the frontend doesn't duplicate the map.

### API additions

- `GET /api/v2/wa/template-registry` → `TemplateRegistryOut`. No request body. No auth changes (mirrors `/wa/templates`).

### Schema/DB additions

None.

### Acceptance criteria

- **AC-8.1.1** `curl /api/v2/wa/template-registry` returns one entry per YAML key with `intent_label` filled.
- **AC-8.1.2** Entries with no `use_case` field in YAML get `intent_label: "Other"` (no 500).
- **AC-8.1.3** Adding a new template to YAML and redeploying surfaces it on next query — the YAML is read on every request (no caching layer; see D2).
- **AC-8.1.4** A unit test in `api_v2/tests/test_wa.py` covers the mapping table above plus the missing-use_case fallback.

### Decisions to surface

- **D1** Should `intent_label` map live in the YAML itself (per-entry override) or in code? Recommendation: code-level default + optional per-entry `intent_label` override in YAML for flexibility. Keeps the common case simple.
- **D2** Cache the YAML or read on every request? Recommendation: read on every request for v1 — the file is tiny (<5KB) and changes only on deploy. Revisit if profiling shows it.

### Risks / unknowns

- **R1** The YAML registry can drift from the DB — a template can exist in `wa_templates` but not in YAML (e.g. created via Studio + Submit-to-Meta without a registry entry). The picker needs to handle this: show the template anyway with `intent_label = "Other"`. The frontend join is left-join semantics on DB rows.

---

## Phase 8.2 — Shared `<WaTemplatePicker>` component

### Problem recap
Today template selection is a flat `<select>` in two places: `ComposeTab.tsx:303-318` and `TemplateSheet.tsx`. There is no filtering. The user has to scroll through everything ever submitted to Meta, including drafts, rejected templates, and unrelated test templates. With ~30+ templates this is already painful.

### Root cause
First version was minimal. No shared abstraction, no filter state, no awareness of `use_case`.

### Files to modify

None initially.

### Files to create

- `vite_dashboard/src/components/wa/WaTemplatePicker.tsx` — the shared component. Props:
  ```ts
  type Props = {
    value: string | null;                // selected template name
    onChange: (name: string | null) => void;
    /** Only show templates with this status (default APPROVED). */
    status?: "APPROVED" | "PENDING" | "ALL";
    /** Layout density. "list" for broadcast (full-width), "compact" for the inbox sheet (denser rows). */
    density?: "list" | "compact";
    /** Optional: hide templates by name prefix (e.g. drafts the inbox shouldn't see). */
    excludePrefixes?: string[];
  };
  ```
  Internal state:
  - `categoryFilter: "ALL" | "MARKETING" | "UTILITY" | "AUTHENTICATION"`
  - `intentFilter: "ALL" | string` (the `intent_label` value)
  - `search: string` (debounced 200ms — name + body_text full-text)

  Renders:
  1. Pill row: Type — `All / Marketing / Utility` (Authentication hidden unless any template uses it)
  2. Pill row: Intent — `All / Intro / Order / Sample / Catalog / Follow-up / Other` (only render labels that have ≥1 template after the type filter)
  3. Search input
  4. Vertical list of `<TemplatePickerRow>` — one per template; selected row has `bg-primary/10 border-primary`
  5. Empty state: "No templates match. Try clearing filters."

- `vite_dashboard/src/components/wa/TemplatePickerRow.tsx` — card row with name, badges (`MKT`/`UTL` + intent), variable count, single-line body preview (first 60 chars). Click → `onChange(name)`.

- `vite_dashboard/src/lib/wa-template-filters.ts` — pure filter helpers (`filterByCategory`, `filterByIntent`, `filterBySearch`) and one `joinWithRegistry(templates, registry)` helper that produces `EnrichedTemplate[]` with `intent_label` attached. Exported separately for unit-testing.

- `vite_dashboard/src/components/wa/__tests__/wa-template-filters.test.ts` — unit coverage for each helper + the join behavior when a template is missing from the registry (defaults to `Other`).

### API additions

None (uses 8.1's endpoint plus existing `/wa/templates`).

### Schema/DB additions

None.

### Component tree sketch

```
<WaTemplatePicker>
├── <PillRow label="Type" options={['All','Marketing','Utility']} />
├── <PillRow label="Intent" options={dynamicIntentLabels} />
├── <SearchInput debounced />
└── <ul role="listbox">
      ├── <TemplatePickerRow name="b2b_fiber_intro" badges={['MKT','Intro']} />
      ├── <TemplatePickerRow name="order_confirmation" badges={['MKT','Order']} />
      └── ...
```

### Acceptance criteria

- **AC-8.2.1** Mount the picker with no props. It renders with both pill rows defaulting to "All", an empty search box, and the full template list.
- **AC-8.2.2** Click a Type pill → list filters to only that category. Pill highlight changes; "All" resets.
- **AC-8.2.3** Type-filter narrows the available Intent labels (intent labels with zero matches in the current type filter are hidden). Reverse not required — Intent never narrows Type.
- **AC-8.2.4** Search "intro" filters the list to templates whose name OR body matches; debounced 200ms.
- **AC-8.2.5** Selecting a row fires `onChange(name)`. Re-clicking the same row deselects (`onChange(null)`).
- **AC-8.2.6** Empty state when no template matches.
- **AC-8.2.7** Density: `compact` mode reduces row height from 64px to 48px and hides the body-preview line. Pill rows stay the same.
- **AC-8.2.8** A11y: pills are `<button>` with `aria-pressed`. List has `role="listbox"`, rows have `role="option"` + `aria-selected`.

### Decisions to surface

- **D3** Should the picker live inside a Sheet/Dialog or always inline? Recommendation: inline — it's used inline in broadcasts and inside an existing Sheet on the inbox. The component itself does not own the chrome.
- **D4** Two distinct interactions can affect the selection — keep them separate:
  - **Filter change** (clicking a Type or Intent pill while a template is selected and the new filter would hide it): keep the selection, show a small "current selection is hidden by filters — clear filters" hint above the list. Don't auto-deselect (would lose user state on accidental click).
  - **Row re-click** (clicking the already-selected row in the list, AC-8.2.5): clears the selection (`onChange(null)`). This is a deliberate user action targeting the selected row, not a filter side-effect.

### Risks / unknowns

- **R2** Performance with 100+ templates — currently we have ~30, so plain `.filter()` is fine. If we ever pass 200, switch to a `useMemo` over a pre-indexed `Map<intent_label, Template[]>` map.
- **R3** Pill labels mid-sentence-case (`Intro`, `Order`) vs all-caps (`MARKETING`) is visually inconsistent. Mitigation: use `Marketing` / `Utility` as the user-facing case (already in the wireframe). Keep `MARKETING` only as the wire value sent to the API.

---

## Phase 8.3 — Inbox `TemplateSheet` adopts the picker

### Problem recap
The inbox sheet's current `<select>` for picking a template is the same flat list as broadcasts. Adopting the new picker keeps both surfaces consistent and makes inbox sends faster (operator can filter by Intent: Order when responding to a customer asking about an order).

### Root cause
N/A — this is a refactor.

### Files to modify

- `vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx` — replace the `<select>` with `<WaTemplatePicker density="compact" status="APPROVED" />`. Keep `selected` state, contact-aware variable prefill, the existing `TemplatePreview style="card"`, and the send mutation untouched.
- `vite_dashboard/src/config/pages/wa_inbox.yml` — add `template_picker_help: "Filter by type or intent, then pick a template."` under `panels.template_sheet`. Optional but matches the rest of the page's labels-from-YAML pattern.
- `vite_dashboard/src/schemas/pages.ts` — extend `WaInboxPageConfig.page.panels.template_sheet` with the new label.

### Files to create

None.

### Acceptance criteria

- **AC-8.3.1** Open the sheet from a chat. Picker renders with pills + search + list, no flat select anywhere.
- **AC-8.3.2** Compact density: rows are 48px tall, body preview hidden, badges visible.
- **AC-8.3.3** Selecting a template still triggers the variable form + preview render (existing 7.5 behavior preserved).
- **AC-8.3.4** No regression in the contact-aware prefill of `var_1` to the contact name.

### Decisions to surface

- **D5** Should the inbox picker default to filtering by Intent: Order if the chat already has order-related keywords? Recommendation: out of scope for v1 — premature pattern matching. Revisit when we have search/intent classification on inbound messages.

### Risks / unknowns

- **R4** The sheet has a fixed width (~480px); the picker must fit. Mitigation: pill rows wrap; `density="compact"` keeps each row narrow.

---

## Phase 8.4 — Broadcast `ComposeTab` redesign (the main piece)

### Problem recap
Today's `ComposeTab.tsx` is a single-column form (`grid-cols-[2fr_1fr]`) with a small notes aside. The cost estimate is buried inline below the form. There is no live phone preview of the template — the operator types the variables and hits Send Now without seeing what will actually arrive on the customer's phone. Quote: "I want to first bring the preview section, we need to change the layout … and also … you can have a phone screen."

### Root cause
First-version layout. We had `WaPhonePreview` but never wired it into broadcasts; Phase 7.5's `<TemplatePreview style="phone">` exists but is only used in the Studio editor.

### Files to modify

- `vite_dashboard/src/pages/broadcasts/components/ComposeTab.tsx` — rewrite the JSX layout (the state machine and all mutation handlers stay). New structure (matches `wireframes/broadcast_page_redesign.excalidraw`):
  ```
  <div className="flex flex-col gap-4 p-card">
    <AudienceFunnel />                // sticky band, full-width
    <CompletedBanner /> <ScheduledOk /> <SendProgress />   // existing alerts row, conditional

    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[3fr_5fr]">
      <FiltersColumn>                 // LEFT
        <Field "Broadcast name" />
        <Field "Channel" /> {/* if not locked */}
        <Field "Audience" />
        <Divider "TEMPLATE" />
        <WaTemplatePicker />          {/* WhatsApp branch */}
        <EmailTemplatePicker />       {/* Email branch — stays a select for now */}
        <Divider "VARIABLES" />
        <VariablesForm />             {/* WA: minimal (raw) — Email: existing EmailVariablesForm */}
        <ActionsRow [Schedule] [Send Now] />
      </FiltersColumn>

      <PreviewColumn>                 // RIGHT — flex flex-col, NOT a nested grid (see R5)
        <KeyCardsRow>                 {/* flex-shrink-0 — stays pinned at top */}
          <Card "Recipients" {audience.final} />
          <Card "Per-msg cost" {cost.per_msg} />
          <Card "Estimated total" {cost.total_display} />
          <Card "Window opens" {audience.final} />
        </KeyCardsRow>
        <PreviewPane>                 {/* fills rest */}
          {channel === 'whatsapp' && <TemplatePreview style="phone" />}
          {channel === 'email'    && <EmailRenderPreview />}  // existing component, just bigger
          {!templateSelected && <EmptyHint />}
        </PreviewPane>
      </PreviewColumn>
    </div>
  </div>
  ```
- `vite_dashboard/src/pages/broadcasts/components/CostEstimateCards.tsx` — rename to `KeyCardsRow.tsx`. The legacy `/broadcasts` route is just a `<Navigate to="/wa-broadcasts" replace />` redirect (`vite_dashboard/src/routes/index.tsx:42`), so there's no second consumer to keep on the old name. Renders 4 cards horizontally in a `grid-cols-2 lg:grid-cols-4` (stacks on narrow viewports). Each card: tiny label, big value, sub-label.
- `vite_dashboard/src/components/email/EmailRenderPreview.tsx` — accept an optional `frame?: "phone" | "card"` prop so the email preview can also render in a phone-shaped frame for parity with WA. Default `"card"` (no behavior change). Phase 8.4 sets `frame="phone"` from `ComposeTab`.

### Files to create

- `vite_dashboard/src/pages/broadcasts/components/KeyCardsRow.tsx` — the four-card horizontal strip described above. Pure presentational; props: `recipients`, `costPerMsg`, `costTotal`, `category`. Handles the loading skeleton.
- `vite_dashboard/src/pages/broadcasts/components/PreviewColumn.tsx` — the right column wrapper. Hosts `KeyCardsRow` (sticky top) + `PreviewPane` (scrolls if tall).

### API additions
None.

### Schema/DB additions
None.

### Component tree sketch
See the rewritten JSX block above. Wireframe at `wireframes/broadcast_page_redesign.excalidraw` is canonical.

### Acceptance criteria

- **AC-8.4.1** `/wa-broadcasts` Compose tab renders in two columns at viewports ≥ 1024px. Single column at narrow viewports (mobile-friendly fallback).
- **AC-8.4.2** Left column contains, top-to-bottom: name, audience, template picker (with pill filters), variables, action buttons.
- **AC-8.4.3** Right column has the 4 key cards pinned at the top and the phone-style preview filling the rest. Cards remain visible regardless of preview scroll position (achieved via flex layout, not `position: sticky` — see R5).
- **AC-8.4.4** When the operator picks `b2b_fiber_intro`, the phone preview updates to show the green WA bubble with the actual body text and substituted variables.
- **AC-8.4.5** When no template is picked, the preview pane shows: "Pick a template to see the rendered preview." (no broken empty bubble).
- **AC-8.4.6** Audience funnel band stays full-width above the two columns.
- **AC-8.4.7** Send confirmation, schedule sheet, and send-progress UI continue to work — none of them are touched by this phase.
- **AC-8.4.8** Switching channel (WhatsApp ↔ Email, on the legacy `/broadcasts` route) swaps both the template picker and the preview; cards and layout stay.

### Decisions to surface

- **D6** Email-side template picker — does it also get the pill filters in this phase, or stays a flat `<select>`? Recommendation: stays a flat select for now — email templates have a different structure (no Meta `category`), and the user's request is WA-focused. Add `<EmailTemplatePicker>` as a Phase 8.6 if needed.
- **D7** What happens to the legacy `/broadcasts` (the route with the channel toggle)? Recommendation: redesign applies there too — the layout is shared via `ComposeTab`. The toggle stays at the top of the left column.
- **D8** Phone preview renders inside the right column at full available width or capped at 320px? Recommendation: capped at 320px with a max-width wrapper, centered. Real phones aren't 800px wide; bigger looks fake.

### Risks / unknowns

- **R5** Sticky positioning in a CSS grid cell is consistently fiddly across browsers. **Pre-decided:** the right column is a flex column from the start — `<div className="flex flex-col gap-3 min-h-0">` containing `<KeyCardsRow className="flex-shrink-0">` and `<PreviewPane className="flex-1 overflow-y-auto">`. The cards stay pinned by virtue of being the non-growing sibling; the preview scrolls within the remaining space. No `position: sticky` needed.
- **R6** Audience-funnel band currently sits inside `<ComposeTab>` — keeping it full-width above the 2-col grid means moving it outside the grid wrapper. Trivial JSX change but worth calling out.
- **R7** History tab (`HistoryTab.tsx`) and Performance tab (`PerformanceTab.tsx`) — out of scope. The wireframe shows them as tabs; we keep them rendering as-is. A redesign for those could be Phase 8.7.

---

## Phase 8.5 — Inbox cleanup

### Problem recap
`/wa-inbox` has a third "Tools" panel with an "Open template picker" button that duplicates the chat panel's "Send a template" button (and is also redundant with the new-conversation auto-open behavior shipped in Phase 7.6). The HowToUse accordion's expanded body uses `flex flex-col` — at wide viewports it stacks sections in a narrow column, leaving the right two-thirds of the screen empty.

### Root cause
The third panel was a Phase 2.1 placeholder that survived. The HowToUse stack was a Phase 6.2 default that nobody revisited at wide viewports.

### Files to modify

- `vite_dashboard/src/pages/wa-inbox/WAInboxPage.tsx` — drop the `<section aria-label="Tools">` block (lines 90-110). Change grid template from `[1fr][2fr][2fr]` to `[1fr][4fr]`.
- `vite_dashboard/src/components/layout/HowToUse.tsx` — change the expanded body's `<div className="mt-3 flex flex-col gap-3 ...">` to `<div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 rounded-lg border border-border bg-card/40 p-card text-sm">`. Sections fill horizontal width on wider viewports.

### Files to create
None.

### API additions
None.

### Schema/DB additions
None.

### Acceptance criteria

- **AC-8.5.1** `/wa-inbox` renders two panels (Conversations + Chat). No third column.
- **AC-8.5.2** Chat panel takes the full recovered width.
- **AC-8.5.3** Expanding HowToUse on any page (`/wa-inbox`, `/contacts`, `/wa-broadcasts`, `/email-broadcasts`, `/wa-templates`, `/email-templates`, `/email-send`, `/flows`) fills the full horizontal width with a 1/2/3-column grid that responds to viewport.
- **AC-8.5.4** No regression on narrow viewports (single-column stack still works).

### Decisions to surface

None.

### Risks / unknowns

- **R8** HowToUse is used on 8 pages. Visual regression testing is by-eye. Mitigation: spot-check three pages with short content (1 section), medium (2-3 sections), long (4+ sections) post-deploy.

---

## Out of scope (deferred to later phases)

- HistoryTab and PerformanceTab redesigns
- Email-template picker with pills
- Template thumbnails (images / icons next to each picker row)
- Picker keyboard navigation (arrow keys, enter to select)
- Search highlighting in matching rows

---

## Sequencing summary

```
8.1 (registry endpoint) ──► 8.2 (picker component) ──┬─► 8.3 (inbox adopts)
                                                     └─► 8.4 (broadcast redesign)
8.5 (cleanup) — independent, can land anytime
```

Single deploy at the end. Backfill: none required (no schema changes).
