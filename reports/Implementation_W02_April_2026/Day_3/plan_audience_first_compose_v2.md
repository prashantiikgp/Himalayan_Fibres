# Audience-first Compose flow — **v2** (Vite + api_v2)

> Companion to `plan_audience_first_compose.md` (v1). This plan ships the
> same audience-first design but targets v2 only: React/Vite frontend at
> `vite_dashboard/` + FastAPI backend at `api_v2/`. The v1 Gradio UI in
> `hf_dashboard/pages/email_broadcast.py` is **not modified** by this plan.

## Context

The user wants the new audience-first compose flow inside v2, not v1.

V2 is a separate app: React/Vite frontend (`vite_dashboard/`) talking to
its own FastAPI surface (`api_v2/`), deployed to a separate HF Space
(`himalayan-fibers-dashboard-v2`) via `scripts/deploy_hf_v2.py` and
`Dockerfile.v2`. V2 reuses v1's domain layer — `api_v2` imports from
`hf_dashboard/services/` and `hf_dashboard/engines/` directly (sys.path
injection in `api_v2/main.py:24-27`). DB and Pydantic schemas are shared.

What this means for the plan:

- **Shared layer changes** (loader convention fix, new
  `wa_campaign_loader`, `target_segments` on `WhatsAppTemplate`)
  remain in `hf_dashboard/services/` and `hf_dashboard/engines/`.
  These are dual-use; v2 picks them up automatically via api_v2 imports.
  V1's Gradio page just doesn't call them.
- **No edits** to `hf_dashboard/pages/email_broadcast.py` or
  `hf_dashboard/pages/wa_template_studio.py`.
- **New work** lives in `api_v2/routers/`, `api_v2/schemas/`, and
  `vite_dashboard/src/`.

### What v2 already has (re-use, don't rebuild)

- **Route slot**: `/broadcasts` is registered in
  `vite_dashboard/src/routes/index.tsx`, currently rendering
  `<MigrationPage>` as a placeholder. Sidebar entry already exists in
  `vite_dashboard/src/config/dashboard/sidebar.yml`.
- **Page config stub**:
  `vite_dashboard/src/config/pages/broadcasts.yml` declares
  `tabs: [compose, history, performance]` — Compose is a tab inside the
  Broadcasts page.
- **Page anatomy convention**: `pageEngine.getMeta()` /
  `pageEngine.getConfig()` / `pageEngine.getStyleVars()` —
  `ContactsPage.tsx` is the canonical example.
- **API client conventions**: `apiFetch<T>` wrapper in
  `vite_dashboard/src/api/client.ts`, React Query v5, auth via Bearer
  token from `getToken()`.
- **Backend conventions**: routers under `api_v2/routers/`,
  `Depends(require_auth)`, schemas in `api_v2/schemas/`,
  `Depends(get_db_session)` for DB access.
- **Design mockups**: `Pages/5. Broadcast/` (7 PNGs) — show a 2-step
  audience → message flow with template-variable preview and a saved-
  drafts side panel. Aligns with our wireframes.
- **Variable form pattern**: `TemplateSheet.tsx` in `wa-inbox` already
  renders one `<Input>` per template variable in declaration order
  (post B1 fix) — perfect to lift verbatim into the Compose page.
- **WA send wiring**: `api_v2/routers/wa.py` already calls
  `WhatsAppSender.send_template` for one-off sends.

### Filter convention (pinned, same as v1 plan)

**Empty `target_segments` = applies to all audiences.** Non-empty list
= restricted to those segments. Requires the same 1-line loader change
as v1's plan; it's still in shared code so v2 inherits it.

---

## Approach

```
v2 Compose page (BroadcastsPage → "Compose" tab)
   │
   ├── AudiencePicker      → GET /api/v2/segments/canonical
   ├── ChannelPicker       → email | whatsapp
   ├── TemplateBrowser     → GET /api/v2/templates/{channel}?audience=...
   │   ├── tab "For this audience"   (segment-explicit)
   │   └── tab "Shared library"      (target_segments empty)
   ├── VariableForm        → derived from chosen template
   └── SendControls        → POST /api/v2/broadcasts/{channel}/send
```

Same UX as the v1 plan (5 audience cards including `all_opted_in`,
two-tab template browser, sub-tabs by tier, dynamic variable form),
re-implemented in React + shadcn/ui and powered by new api_v2 endpoints.

---

## Step 0 — Shared schema + loader changes (in `hf_dashboard/`)

These are the same changes as v1's Step 0 / Step 2 / Step 3, but the
*reason* is "api_v2 imports them". Touching `hf_dashboard/pages/*` is
**not** required and is **out of scope** here.

### 0.1 Fix `templates_for_segment` filter convention

**File:** `hf_dashboard/services/email_campaign_loader.py`, lines
138–143.

Split into two functions:

```python
def templates_for_segment(segment: str, *, status: str = "READY"):
    """Templates explicitly targeted at this segment."""
    return [
        t for t in load_email_templates().values()
        if t.target_segments
        and segment in t.target_segments
        and (status is None or t.status == status)
    ]


def shared_templates(*, tier: str | None = None, status: str = "READY"):
    """Templates with empty target_segments (apply to all audiences)."""
    return [
        t for t in load_email_templates().values()
        if not t.target_segments
        and (tier is None or t.tier == tier)
        and (status is None or t.status == status)
    ]
```

### 0.2 Add `target_segments` to `WhatsAppTemplate`

**File:** `hf_dashboard/engines/campaign_schemas.py`, after line 113:

```python
target_segments: list["Segment"] = Field(default_factory=list)
```

Do not add `status` (collides with the WA Meta-approval status on the
DB-side `WATemplate` model).

### 0.3 New `services/wa_campaign_loader.py`

**File:** `hf_dashboard/services/wa_campaign_loader.py` (new).

Mirror `email_campaign_loader.py` line-for-line. Surface:
`load_wa_templates()`, `templates_for_segment(segment)`,
`shared_templates(tier=None)`, `templates_by_tier(tier)`,
`get_template(name)`, `reload()`. Walk
`campaign/whatsapp_campaign/shared/{company,category,product,utility}_templates/**/*.yml`.

### 0.4 Annotate `followup_interest_v2.yml`

**File:**
`campaign/whatsapp_campaign/shared/utility_templates/followup_interest_v2.yml`.

Add `target_segments: [potential_domestic, international_email]`. All
other WA YAMLs leave the field absent (= applies to all under the new
convention).

---

## Step 1 — `api_v2` schemas

**New file:** `api_v2/schemas/compose.py`

Pydantic models using the existing `ConfigDict(from_attributes=True)`
convention from `api_v2/schemas/contacts.py`:

```python
class CanonicalSegment(BaseModel):
    id: str                  # one of: existing_clients, churned_clients,
                             # potential_domestic, international_email,
                             # all_opted_in
    name: str                # display label
    description: str
    member_count: int

class CanonicalSegmentsResponse(BaseModel):
    segments: list[CanonicalSegment]

class TemplateSummary(BaseModel):
    name: str
    tier: str
    voice: str
    subject: str | None        # email only
    preview_text: str | None   # email only
    body: str | None           # WhatsApp only
    meta_category: str | None  # WhatsApp only — MARKETING/UTILITY/AUTH
    hero_image: str | None     # email only
    required_variables: list[str]
    optional_variables: list[str]
    target_segments: list[str]
    status: str
    description: str

class TemplatesResponse(BaseModel):
    for_audience: list[TemplateSummary]   # segment-explicit
    shared: dict[str, list[TemplateSummary]]  # keyed by tier

class SendEmailRequest(BaseModel):
    audience: str               # canonical segment id
    template_name: str
    variables: dict[str, str]
    test_recipient: str | None  # if set: send to this address only
    invoice_attachment_id: str | None

class SendWhatsAppRequest(BaseModel):
    audience: str
    template_name: str
    variables: dict[str, str]
    test_phone: str | None

class SendResponse(BaseModel):
    queued: int
    failed: int
    sample_message_ids: list[str]
    errors: list[str]
```

## Step 2 — `api_v2` router

**New file:** `api_v2/routers/compose.py`

Five endpoints, all gated by `Depends(require_auth)`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/segments/canonical` | The 5 cards (4 segments + all_opted_in) with member counts |
| `GET` | `/templates/email` | `?audience=<id>` returns `TemplatesResponse` |
| `GET` | `/templates/whatsapp` | same shape, WA channel |
| `POST` | `/broadcasts/email/send` | Send email broadcast (or test send) |
| `POST` | `/broadcasts/whatsapp/send` | Send WA broadcast (or test send) |

**Implementation notes:**

- Member counts: reuse `services.flows_engine._get_segment_contacts(db, seg_id)` for the 4 canonical segments; for `all_opted_in` filter
  `Contact.consent_status IN ("opted_in", "pending")`.
- Email templates: call `email_campaign_loader.templates_for_segment(audience)` for `for_audience`; iterate the 6 known tiers and call
  `shared_templates(tier=t)` for `shared`. Skip the `for_audience` block when `audience == "all_opted_in"`.
- WA templates: same shape via `wa_campaign_loader` from Step 0.3.
- Send paths:
  - Email: import `services.email_sender` (already exists in v1; not yet wired into api_v2). Loop recipients with `EmailSender().send(...)`; return aggregate counts.
  - WhatsApp: reuse `WhatsAppSender().send_template(...)` exactly the way `api_v2/routers/wa.py` already does for one-off sends.
- Test-send branch: when `test_recipient` / `test_phone` is set, send to that single target only and return `queued=1`.

## Step 3 — Register the router

**File:** `api_v2/main.py` — add alongside the existing 6 routers:

```python
from api_v2.routers import compose
app.include_router(compose.router, prefix="/api/v2", dependencies=[Depends(require_auth)])
```

## Step 4 — Backend tests

**New file:** `api_v2/tests/test_compose.py`

Following `test_wa.py` pattern (TestClient + SQLite fixture from
`conftest.py`):

- `test_canonical_segments_returns_five_with_counts` — asserts 5 ids,
  `member_count` is int, `all_opted_in` is the largest.
- `test_email_templates_for_existing_clients` — picks a fixture template
  with `target_segments: [existing_clients]` and asserts it's in the
  `for_audience` list, NOT in `shared`.
- `test_email_templates_for_all_opted_in_skips_for_audience` —
  `for_audience == []`, `shared` is fully populated.
- `test_wa_templates_followup_interest_only_for_prospects` — asserts the
  Step 0.4 annotation is honored.
- `test_send_email_test_recipient` — POST with `test_recipient`,
  monkeypatch `EmailSender.send` to a stub, assert `queued=1, failed=0`.
- `test_auth_required` — 401 without bearer token.

## Step 5 — Frontend types and API hooks

**New file:** `vite_dashboard/src/api/compose.ts`

Mirror `vite_dashboard/src/api/contacts.ts` conventions (typed
`apiFetch<T>` calls wrapped in React Query hooks):

```typescript
export type CanonicalSegment = {
  id: "existing_clients" | "churned_clients" | "potential_domestic"
    | "international_email" | "all_opted_in";
  name: string;
  description: string;
  member_count: number;
};

export type TemplateSummary = { /* matches api_v2 schema */ };
export type TemplatesResponse = {
  for_audience: TemplateSummary[];
  shared: Record<string, TemplateSummary[]>;
};

export function useCanonicalSegments() {
  return useQuery({
    queryKey: ["compose", "segments"],
    queryFn: () => apiFetch<{ segments: CanonicalSegment[] }>(
      "/api/v2/segments/canonical"),
    staleTime: 60_000,
  });
}

export function useTemplatesForAudience(
  channel: "email" | "whatsapp", audience: string
) {
  return useQuery({
    queryKey: ["compose", "templates", channel, audience],
    queryFn: () => apiFetch<TemplatesResponse>(
      `/api/v2/templates/${channel}?audience=${audience}`),
    enabled: !!audience,
  });
}

export function useSendBroadcast() {
  return useMutation({
    mutationFn: (req: SendRequest) => apiFetch(
      `/api/v2/broadcasts/${req.channel}/send`,
      { method: "POST", body: JSON.stringify(req) }),
  });
}
```

## Step 6 — Compose page shell

**New file:** `vite_dashboard/src/pages/broadcasts/BroadcastsPage.tsx`

Top-level component for `/broadcasts`. Follows `ContactsPage.tsx`
anatomy:

- Reads `pageEngine.getMeta("broadcasts")` for title/subtitle.
- Renders shadcn `<Tabs>` with `compose / history / performance`,
  values from the YAML config.
- The "Compose" tab body composes:
  `<AudiencePicker /> → <ChannelPicker /> → <TemplateBrowser /> → <VariableForm /> → <SendControls />`.
- The other two tabs render an "(coming soon)" placeholder for now —
  History and Performance are explicitly out of scope.

State (page-local `useState`):
- `audience: CanonicalSegment["id"] | null`, defaulting to
  `"all_opted_in"`.
- `channel: "email" | "whatsapp"`, default `"email"`.
- `selectedTemplate: TemplateSummary | null`.
- `variableValues: Record<string, string>`.
- `testTarget: string` (email or phone, depending on channel).

## Step 7 — `AudiencePicker.tsx`

**New file:** `vite_dashboard/src/pages/broadcasts/components/AudiencePicker.tsx`

5 cards rendered with shadcn `<Card>` + click handler (no native
`<RadioGroup>` exists in v2 yet — use selected-state styling on Card).

- Order: Existing → Churned → Carpet exporters → Intl yarn stores →
  All opted-in.
- "All opted-in" card uses an amber accent border to mark it as the
  blanket option.
- Each card shows: name, description (one line), `member_count` (right-
  aligned, monospace). Empty / loading state via skeleton.
- Selecting a card calls `onChange(segment.id)`. Hides the "For this
  audience" tab when `audience === "all_opted_in"`.

Data: `useCanonicalSegments()` from Step 5.

## Step 8 — `ChannelPicker.tsx`

**New file:** `vite_dashboard/src/pages/broadcasts/components/ChannelPicker.tsx`

Two-button toggle group (shadcn `<Button variant="outline">` with
selected-state styling), Email / WhatsApp. Existing `<ChannelBadge>` in
`src/components/badges/` is the visual reference for icon+label.

## Step 9 — `TemplateBrowser.tsx`

**New file:** `vite_dashboard/src/pages/broadcasts/components/TemplateBrowser.tsx`

shadcn `<Tabs>` with two top tabs:

- **For this audience** — flat list of `for_audience[]`. Hidden when
  `audience === "all_opted_in"`.
- **Shared library** — nested `<Tabs>` with one sub-tab per tier
  (Company / Product / Category / Seasonal / Lifecycle / Transactional
  for email; Company / Product / Category / Utility for WhatsApp).
  Sub-tab body lists `shared[tier]`. Empty sub-tabs render
  "(no templates yet)" placeholder, never disappear.

Each template renders as a `<Card>` with: name, tier badge, voice tag,
"applies to" hint (segments names or "All audiences"), and — for
WhatsApp — a Meta-category badge (Marketing / Utility / Authentication).
Click selects the template.

Data: `useTemplatesForAudience(channel, audience)` from Step 5.

## Step 10 — `VariableForm.tsx`

**New file:** `vite_dashboard/src/pages/broadcasts/components/VariableForm.tsx`

Lift the variable-form pattern from
`vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx`
verbatim:

- One `<Input>` per `required_variables` entry, in declaration order.
- A second collapsible group for `optional_variables`.
- Live email subject preview from `template.subject` rendered above the
  inputs (read-only display — subject editing is deferred to v3).

## Step 11 — `SendControls.tsx`

**New file:** `vite_dashboard/src/pages/broadcasts/components/SendControls.tsx`

Three controls in a row:
- "Test send" button + target input (email or phone, depending on
  channel) — calls `useSendBroadcast()` with `test_recipient` set.
- "Send to {N} {audience}" primary button — full broadcast.
- A confirmation `<Dialog>` before the full broadcast fires (shows
  audience name, member count, template name).

Disabled until `selectedTemplate` and all `required_variables` are
filled.

## Step 12 — Replace placeholder route

**File:** `vite_dashboard/src/routes/index.tsx`

Change the entry currently rendering `<MigrationPage />` for path
`broadcasts` → render `<BroadcastsPage />`. Keep the `MigrationPage`
component import in case the migration view still has a use; otherwise
move to `/migration` route only.

## Step 13 — Page YAML config

**File:** `vite_dashboard/src/config/pages/broadcasts.yml`

The stub already declares title, subtitle, and tabs. Extend with
audience-card config so labels live in YAML rather than TSX:

```yaml
page:
  title: "Broadcasts"
  subtitle: "Compose, schedule, and review email + WhatsApp broadcasts"
  landed_phase: 3
  tabs:
    - { id: compose,     label: "Compose" }
    - { id: history,     label: "History" }
    - { id: performance, label: "Performance" }
compose:
  audience_cards:
    - { id: existing_clients,      label: "Existing clients",      tone: neutral }
    - { id: churned_clients,       label: "Churned / lapsed",      tone: warning }
    - { id: potential_domestic,    label: "Carpet exporters",      tone: neutral }
    - { id: international_email,   label: "International yarn stores", tone: neutral }
    - { id: all_opted_in,          label: "All opted-in",          tone: amber }
  default_audience: all_opted_in
  default_channel: email
```

If a Zod schema for `broadcasts.yml` doesn't exist yet, add one in
`vite_dashboard/src/schemas/pages.ts` next to the existing
`contactsPageSchema`.

---

## Critical files to modify

**Shared (`hf_dashboard/`)**
- `hf_dashboard/services/email_campaign_loader.py` — split filters (Step 0.1)
- `hf_dashboard/engines/campaign_schemas.py` — add `target_segments` to WA (Step 0.2)
- `hf_dashboard/services/wa_campaign_loader.py` — new (Step 0.3)
- `campaign/whatsapp_campaign/shared/utility_templates/followup_interest_v2.yml` — annotate (Step 0.4)

**Backend (`api_v2/`)**
- `api_v2/schemas/compose.py` — new
- `api_v2/routers/compose.py` — new
- `api_v2/main.py` — register router (1 line)
- `api_v2/tests/test_compose.py` — new

**Frontend (`vite_dashboard/`)**
- `vite_dashboard/src/api/compose.ts` — new
- `vite_dashboard/src/pages/broadcasts/BroadcastsPage.tsx` — new
- `vite_dashboard/src/pages/broadcasts/components/AudiencePicker.tsx` — new
- `vite_dashboard/src/pages/broadcasts/components/ChannelPicker.tsx` — new
- `vite_dashboard/src/pages/broadcasts/components/TemplateBrowser.tsx` — new
- `vite_dashboard/src/pages/broadcasts/components/VariableForm.tsx` — new
- `vite_dashboard/src/pages/broadcasts/components/SendControls.tsx` — new
- `vite_dashboard/src/routes/index.tsx` — swap `<MigrationPage>` for `<BroadcastsPage>`
- `vite_dashboard/src/config/pages/broadcasts.yml` — extend
- `vite_dashboard/src/schemas/pages.ts` — Zod schema for broadcasts page (if missing)

## Functions and utilities to reuse

- `services.email_campaign_loader.templates_for_segment` /
  `shared_templates` (post Step 0.1) — backend lookup.
- `services.wa_campaign_loader.*` (Step 0.3) — backend lookup.
- `services.flows_engine._get_segment_contacts` — audience counts.
- `services.email_sender.EmailSender` and
  `services.wa_sender.WhatsAppSender` — dispatch.
- `api_v2/deps.py::require_auth`, `get_db_session` — auth + DB.
- `vite_dashboard/src/api/client.ts::apiFetch` — typed fetch.
- `vite_dashboard/src/components/badges/ChannelBadge.tsx` — channel
  visual.
- `vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx`
  — variable-form pattern (lift verbatim into `VariableForm.tsx`).
- shadcn primitives: `<Card>`, `<Tabs>`, `<Button>`, `<Input>`,
  `<Dialog>`, `<Sheet>`.

## Verification

V2 deploys to a separate HF Space via `scripts/deploy_hf_v2.py`
(`Dockerfile.v2` builds Vite then runs `uvicorn api_v2.main:app`).

1. Backend unit tests: `pytest api_v2/tests/test_compose.py -v` (local,
   uses SQLite fixture).
2. Schema validation: `python scripts/validate_campaigns.py` confirms
   the WA `target_segments` annotation parses cleanly.
3. Frontend type-check + build:
   `cd vite_dashboard && pnpm run typecheck && pnpm run build`.
4. Frontend unit tests: `cd vite_dashboard && pnpm test` (Vitest).
5. Deploy: `python scripts/deploy_hf_v2.py`.
6. Wait for the v2 Space to show **Running**.
7. Playwright MCP verification (headless on the v2 live URL):
   - Log in.
   - Navigate to `/broadcasts`. Confirm the page renders with three
     tabs (Compose / History / Performance), Compose selected.
   - Confirm 5 audience cards render with non-zero `member_count` and
     "All opted-in" preselected with amber accent.
   - With "All opted-in" selected, confirm the "For this audience" tab
     is hidden and only "Shared library" is shown.
   - Click each of the 4 segment cards in turn; confirm
     "For this audience" appears with the right templates and that the
     shared library template list updates accordingly.
   - Toggle channel Email ↔ WhatsApp; confirm template list and
     sub-tabs change (WA shows Utility instead of Lifecycle/Seasonal/
     Transactional, and Meta-category badges appear).
   - Pick a template; confirm variable inputs render, send button
     enables only when all required variables filled.
   - Test-send to a personal address and confirm `queued=1, failed=0`.
   - Save 12 screenshots into `verify-v2-compose-*.png`: 5 audiences
     × 2 channels = 10 + 1 for empty state (no templates) + 1 for
     test-send confirmation.

## Out of scope (explicitly deferred)

Carry-forward list for **Day_4 planning**, in priority order:

1. **History tab** of the Broadcasts page — list of past sends with
   open/click stats. Backend uses existing
   `GET /api/v2/broadcasts` (read-only Phase 3.0); needs a frontend
   table.
2. **Performance tab** of the Broadcasts page — KPIs by template /
   audience / channel.
3. **v1 Gradio compose-page restructure** — if anyone still uses v1, the
   `hf_dashboard/pages/email_broadcast.py` restructure from
   `plan_audience_first_compose.md` (v1) is parked. v2 supersedes it.
4. **Sub-segment refinement** — drill from the 4 canonical segments
   into the 13 granular CRM segments in
   `config/segments/customer_segments.yml`.
5. **Tags as cross-cutting filters** — `tags: list[str]` on both
   template schemas, surfaced as side-rail facets in
   `TemplateBrowser`.
6. **Braze-style content blocks** — reusable Jinja partials for
   product cards / company-info paragraphs.
7. **Template Studio v2** — `wa_templates.yml` is Phase 4 in
   `dashboard_v2_plan.md`. Compose targets approved templates; authoring
   stays in v1's `wa_template_studio.py` until Phase 4 ships.
