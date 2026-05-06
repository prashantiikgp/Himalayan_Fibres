# PLAN — Day 5: Phase 7.8 Flows UI for visibility + control

> **Scope:** make Phase 7.7 (per-contact flow memberships, tag/lifecycle
> triggers, multi-channel steps, event-gated waits, Sample Dispatch
> seed) usable through the Vite v2 dashboard. Today the engine works
> and the API is live, but no operator surface lets you assign flows,
> see progress, mark a sample shipped, or stop a membership without
> hitting the API directly.
>
> **Non-scope:** flow editor (Phase 7.9), bulk operations + auto-tag
> cron (Phase 7.10), drag-and-drop graph builders, real-time websocket
> updates.

---

## Section 1 — State of the dashboard today

### 1.1 Backend (Phase 7.7) is fully shipped and live on v2

`https://prashantiitkgp08-himalayan-fibrer-v2.hf.space/`

| Endpoint | Status |
|---|---|
| `GET    /api/v2/flows` | extended: trigger_type, trigger_config, active_count |
| `GET    /api/v2/flows/{id}/memberships` | per-contact rows for the Members tab |
| `GET    /api/v2/flows/{id}/step-runs` | per-step audit for the Step Runs tab |
| `GET    /api/v2/flows/{id}/runs` | legacy cohort runs — deprecated |
| `POST   /api/v2/flows/{id}/memberships` | manual enroll — body `{contact_id}` |
| `POST   /api/v2/flow-memberships/{id}/stop` | operator halt |
| `GET    /api/v2/contacts/{id}/flow-memberships` | drawer Flows-tab data |
| `POST   /api/v2/contacts/{id}/mark-sample-shipped` | tag + tracking + resume |

What does NOT exist on the backend yet:

- **`POST /api/v2/flow-memberships/{id}/pause`** and the matching
  `/resume`. The data model has `status='paused'` but no endpoint
  toggles it. Pause is conceptually different from stop: stop is
  terminal, pause re-arms when resumed.
- **`GET /api/v2/contacts/active-flows?ids=...`** — batch lookup for
  the Contacts list "Flow" column (PLAN_flows §6.5). Without this we
  can't avoid an N+1 on a 50-row contacts page.

### 1.2 Frontend is still Phase 5.0 read-only

| File | What it does today | Gap for 7.8 |
|---|---|---|
| `vite_dashboard/src/pages/flows/FlowsPage.tsx` (20 lines) | Renders `<HowToUse>` + `<FlowsTable>` | Just needs the new HowToUse copy |
| `vite_dashboard/src/pages/flows/components/FlowsTable.tsx` (236 lines) | Columns: Status / Name / Channel / Steps / Created. Click row → inline `<FlowRunsPanel>` reading the **legacy cohort `flow_runs`** | Add Trigger pill + Active members columns; click row → `useNavigate` to `/flows/:id`; remove inline `FlowRunsPanel` |
| `vite_dashboard/src/pages/flows/FlowDetailPage.tsx` | **MISSING** | Build it: Members tab (default), Steps tab, Step Runs tab |
| `vite_dashboard/src/api/flows.ts` (67 lines) | Only `useFlows` + `useFlowRuns` (legacy) | Add: `useFlowMemberships`, `useFlowStepRuns`, `useContactFlowMemberships`, mutations `assignFlow`, `stopMembership`, `pauseMembership`, `resumeMembership`, `markSampleShipped` |
| `vite_dashboard/src/routes/index.tsx` | `{ path: "flows", element: <FlowsPage /> }` | Add `{ path: "flows/:flowId", element: <FlowDetailPage /> }` |
| `vite_dashboard/src/pages/contacts/components/ContactDrawer.tsx` (553 lines) | 4 tabs: Profile / Tags / Notes / Activity | **Add a 5th `Flows` tab.** Plus a "Mark sample shipped" button conditionally shown when the contact has a waiting Sample Dispatch membership |
| `vite_dashboard/src/config/pages/flows.yml` | `landed_phase: 5`, copy describes read-only cohort runs | Full rewrite — Sample Dispatch walkthrough + the new mental model |

### 1.3 Routing context

Routes are built in `vite_dashboard/src/routes/index.tsx::buildRoutes()`
from `react-router-dom`. The sidebar + nav are driven by
`navigationEngine` (loaded YAML); we don't need to edit sidebar config
for `/flows/:id` because detail pages are reached by clicking a row,
not by sidebar nav.

### 1.4 Component patterns to reuse

Already in the codebase (don't reinvent):

- `<DataTable>` from `@/components/tables/DataTable` — `<FlowsTable>` already uses it
- `<Tabs>` from `@/components/ui/tabs` — `<ContactDrawer>` shows the pattern
- `<Sheet>` from `@/components/ui/sheet` — drawer pattern
- `formatRelative()` from `@/lib/format`
- `<HowToUse>` from `@/components/layout/HowToUse`
- `cn()` from `@/lib/utils`
- The pill pattern (border + bg + text in matching tone) — `ChannelPill`, `RunStatusPill` in `FlowsTable.tsx`
- `apiFetch` from `@/api/client`
- `useQuery` + `useMutation` from `@tanstack/react-query`

### 1.5 STRINGS convention

User-facing strings live in `@/lib/strings` under `STRINGS.<page>.<key>`.
The Contacts drawer is the canonical example. New copy for the Flows
detail page + drawer Flows tab goes under `STRINGS.flows.detail.*` and
`STRINGS.contacts.drawer.flowsTab.*`.

---

## Section 2 — Goal in plain operator language

After this phase:

1. Operator opens a contact drawer → sees a **Flows tab** listing
   every flow this contact is in, which step they're on, when the next
   send fires, and a Stop / Pause button.
2. Operator can **manually enrol a contact** in any flow ("Add to
   flow" dropdown) — useful when the trigger conditions aren't a fit
   but the operator wants the sequence anyway.
3. Operator opens `/flows` → sees a list with trigger pill + active
   member count → clicks → lands on **`/flows/:id`** which shows every
   contact in this flow as a paginated table with their current step,
   per-row Stop / Pause action, and the Sample Dispatch "Mark sample
   shipped" button when the contact is parked at `waiting_event`.
4. Operator can **drill into Step Runs** — flat audit log of every
   send attempt across the flow, filterable by status (sent / failed /
   skipped).
5. Operator can **pause** a membership ("samples not ready yet, hold
   for 3 days") and **resume** later. Stop is still terminal.

The flow definitions themselves remain code-driven for now (Phase 7.9
ships the editor). 7.8 is purely about visibility + per-contact
control.

---

## Section 3 — UI surfaces

### 3.1 `/flows` list page — extend `<FlowsTable>`

`vite_dashboard/src/pages/flows/components/FlowsTable.tsx`

**Column changes:**

| Column | Source | Notes |
|---|---|---|
| Status | `flow.is_active` | Existing — keep |
| Name | `flow.name` + description | Existing — keep |
| **Trigger** *(new)* | `flow.trigger_type` + summary of `trigger_config` | New `<TriggerPill>` component. Shows: `Manual`, `Lifecycle: customer`, `Tag: samples_requested`. Falls back to `Manual` if the type is unknown. |
| Channel | `flow.channel` | Extend `<ChannelPill>` to handle `multi` (purple) |
| Steps | `flow.step_count` | Existing — keep |
| **Active** *(new)* | `flow.active_count` | Right-aligned integer. `0` rendered in muted color. |
| Created | `flow.created_at` | Existing — keep |

**Row click behavior — replace, not extend:**

```tsx
const navigate = useNavigate();
// ...
onRowClick={(row) => navigate(`/flows/${row.id}`)}
```

Delete the inline `<FlowRunsPanel>` and the cohort `useFlowRuns` import
(still keeps the legacy hook in `flows.ts` for the deprecated endpoint
— just unreferenced from this component).

### 3.2 `/flows/:id` detail page — NEW

New file: `vite_dashboard/src/pages/flows/FlowDetailPage.tsx`.

**Layout:**

```
┌─ /flows/:id ──────────────────────────────────────────────┐
│                                                            │
│  ← Back to flows                                           │
│                                                            │
│  Sample Dispatch                                           │
│  Triggered when a contact is tagged samples_requested.     │
│  [TriggerPill] [ChannelPill]  •  3 steps  •  Active       │
│                                                            │
│  ┌─ KPI cards ──────────────────────────────────────────┐ │
│  │  Active: 12  │  Completed: 47  │  Failed: 1          │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌─ Tabs ────────────────────────────────────────────────┐│
│  │ Members │ Steps │ Step Runs                          ││
│  │                                                       ││
│  │ <DataTable> of FlowMembershipOut rows                 ││
│  │   columns: Contact | Status | Step | Next fire |     ││
│  │            Started | Actions(Pause/Resume/Stop)       ││
│  │                                                       ││
│  └───────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

**Loading model — panel-independent skeletons.** The detail page
fires three queries in parallel: `useFlow(id)`, `useFlowMemberships`,
`useFlowStepRuns`. Each tab/panel renders its own skeleton based on
its own query state — Members loading should NOT block Steps from
rendering. The header (flow name, KPI cards) blocks on `useFlow(id)`
only; tabs swap to skeletons independently. If a panel's query fails,
that panel shows an inline error; the page does NOT cascade-fail.

**Tab 1 — Members (default)**

Data source: `useFlowMemberships(flowId, { status })`.

Filters above the table:
- Status dropdown: All / Active / Waiting event / Paused / Completed / Failed / Stopped
- Search by contact name/email (client-side filter; the result set is
  capped at 200 rows so client-side is fine)

Table columns:

| Col | Cell |
|---|---|
| Contact | `{first_name} {last_name}` + email below in muted |
| Status | `<MembershipStatusPill>` (active=primary, waiting_event=warning, paused=muted, completed=success, failed=danger, stopped=muted) |
| Step | `Step {current_step_index + 1} of {total_steps}` with a thin progress bar |
| Next fire | `formatRelative(next_fire_at)` or "Waiting for {trigger_event.value}" or "—" if completed |
| Started | `formatRelative(started_at)` |
| Actions | `<ActionMenu>`: Pause/Resume/Stop. The active set depends on status. |

Row click opens the contact drawer (open the existing
`<ContactDrawer>` with the membership's contact_id).

**Tab 2 — Steps**

Read-only render of `flow.steps`. For each step:

```
┌─ Step 0 ────────────────────────────────────────┐
│ EMAIL  • sample_request_received                │
│ WHATSAPP • sample_request_received              │
│ Delay: immediate                                │
│ Conditions: consent in (opted_in, pending)      │
└──────────────────────────────────────────────────┘
┌─ Step 1 ────────────────────────────────────────┐
│ EMAIL  • sample_shipped                         │
│ WHATSAPP • sample_shipped                       │
│ Trigger event: tag_added: samples_shipped       │
│ Wait: until operator marks shipped (max 30d)    │
└──────────────────────────────────────────────────┘
┌─ Step 2 ────────────────────────────────────────┐
│ EMAIL • post_sample_followup                    │
│ Delay: 7 days                                   │
└──────────────────────────────────────────────────┘
```

Phase 7.9 makes this editable. For 7.8 it's a small read-only card
component reused from the existing `step_card_padding` styling token
in `flows.yml`.

**Tab 3 — Step Runs**

Data: `useFlowStepRuns(flowId, { status })`.

Flat audit log table:

| Col | Cell |
|---|---|
| Fired | `formatRelative(fired_at)` |
| Contact | resolved from `membership.contact_id` (need a contact lookup — see §4) |
| Step | `step_index + 1` |
| Channel | EMAIL / WA pill |
| Template | `template_slug` |
| Status | sent (success) / failed (danger) / skipped (muted) |
| Error | `error` (truncated, full on hover) |

Filter: status dropdown.

### 3.3 Contact drawer — NEW `Flows` tab

`vite_dashboard/src/pages/contacts/components/ContactDrawer.tsx`

Add a 5th tab between Notes and Activity:

```tsx
<TabsTrigger value="flows">
  {STRINGS.contacts.drawer.tabFlows}
  {detail.flow_memberships?.active_count > 0 && (
    ` (${detail.flow_memberships.active_count})`
  )}
</TabsTrigger>
```

Tab body sections:

1. **Active flows** — for memberships in `{active, waiting_event,
   paused}`:

   ```
   ┌─ Sample Dispatch ─────────────────────────────────┐
   │ [Status pill] Step 2 of 3                         │
   │ ▓▓░ progress                                      │
   │ Next: Waiting for samples_shipped event           │
   │ Started: 3 days ago                               │
   │ ──────────────────────────────────────────────    │
   │ [Mark sample shipped]  [Pause]  [Stop]            │
   └────────────────────────────────────────────────────┘
   ```

   The "Mark sample shipped" button only renders when:
   - flow.slug == `sample_dispatch`
   - membership.status == `waiting_event`
   - the current step's `trigger_event.value` == `samples_shipped`

   It opens an inline form (tracking_id + courier_name) → calls
   `markSampleShipped()` → invalidates queries.

2. **Past flows** (collapsed accordion by default) —
   completed/stopped/failed memberships, with a one-line summary
   "3/3 steps sent · ended 2d ago".

3. **Add to flow** — dropdown of `useFlows({ active_only: true })`
   (excluding flows the contact already has a live membership in) +
   "Add" button calling `assignFlow(flowId, contactId)`. After
   success, invalidate `["contacts","detail",contactId,"flow-memberships"]`.

### 3.4 Mark Sample Shipped — discoverability decision

The button lives **inside the Sample Dispatch card in the Flows tab**
(not at the drawer top level). Trade-offs:

| Option | Why we picked / rejected |
|---|---|
| A. Top-level drawer button always visible | Rejected — adds clutter for the >90% of contacts not in Sample Dispatch. |
| **B. Inside the Sample Dispatch flow card** *(picked)* | Action is contextual — appears only when the membership is parked at `waiting_event` with `trigger_event.value == "samples_shipped"`. One extra tab click is acceptable. |

The button's render shape is specified in §3.7 (inline-expand form).

### 3.5 `<MembershipStatusPill>` — explicit 6-status spec

Mirror `RunStatusPill` in `FlowsTable.tsx:210` (border + bg + text in
matching tone). Status → tone mapping is hard-coded — these 6 statuses
are the engine's complete state machine:

| Status | Tone | Hex (Tailwind token) | Icon hint |
|---|---|---|---|
| `active` | primary | `border-primary/40 bg-primary/10 text-primary` | — |
| `waiting_event` | warning | `border-warning/40 bg-warning/10 text-warning` | ⏸ (event-gated) |
| `paused` | muted | `border-border bg-card text-text-muted` | ⏯ |
| `completed` | success | `border-success/40 bg-success/10 text-success` | ✓ |
| `failed` | danger | `border-danger/40 bg-danger/10 text-danger` | ⚠ |
| `stopped` | muted | `border-border bg-card text-text-muted` | ⊘ (distinct icon from paused) |

Render as `STATUS` uppercase tracked-wide pill (matches existing
`ChannelPill` typography). `paused` and `stopped` share the same tone
but **must use different icons** so operators can distinguish at a
glance — `paused` is reversible, `stopped` is terminal.

### 3.6 Confirmation dialog — use existing `<ConfirmDialog>`

`vite_dashboard/src/components/feedback/ConfirmDialog.tsx` already
exists with the right shape (`destructive` flag, `isPending` for the
button while the mutation is in flight, `confirmLabel`, etc.). All
new destructive actions route through it — never `window.confirm`.

```tsx
const [confirm, setConfirm] = useState<{
  kind: "stop" | "pause";
  membership: FlowMembershipOut;
} | null>(null);

<ConfirmDialog
  open={confirm !== null}
  onOpenChange={(o) => !o && setConfirm(null)}
  title={
    confirm?.kind === "stop"
      ? STRINGS.flows.detail.confirmStopTitle
      : STRINGS.flows.detail.confirmPauseTitle
  }
  description={
    confirm?.kind === "stop"
      ? STRINGS.flows.detail.confirmStopBody
      : STRINGS.flows.detail.confirmPauseBody
  }
  confirmLabel={
    confirm?.kind === "stop"
      ? STRINGS.flows.detail.stopAction
      : STRINGS.flows.detail.pauseAction
  }
  destructive={confirm?.kind === "stop"}
  isPending={mutation.isPending}
  onConfirm={() => mutation.mutate(confirm!.membership.id)}
/>
```

`Stop` is destructive (terminal — no recovery); `Pause` is not.
`Resume` doesn't need confirmation — it's a positive action.

### 3.7 Mark Sample Shipped form — inline-expand inside the flow card

Decided in favor of inline-expand over modal so the operator keeps
the drawer's scroll position and the Flows tab visible while filling
the form. The flow card has two modes:

```
Default state:
┌─ Sample Dispatch ─────────────────────────────────┐
│ [Status pill] Step 2 of 3                         │
│ Next: Waiting for samples_shipped event           │
│ ──────────────────────────────────────────────    │
│ [Mark sample shipped]  [Pause]  [Stop]            │
└────────────────────────────────────────────────────┘

After clicking "Mark sample shipped" — expanded:
┌─ Sample Dispatch ─────────────────────────────────┐
│ [Status pill] Step 2 of 3                         │
│ Next: Waiting for samples_shipped event           │
│ ──────────────────────────────────────────────    │
│ Mark sample shipped                                │
│   Tracking ID:  [_______________________]          │
│   Courier:      [_______________________]          │
│   [Cancel]                       [Mark shipped]    │
└────────────────────────────────────────────────────┘
```

Form state is local to the card; closes on submit success or Cancel.
Validation: both fields required, length ≤ 64 chars (matches backend
`MarkSampleShippedRequest` constraints in
`api_v2/schemas/flows.py:130-133`).

### 3.8 Error UX — inline next to the action (no toast component exists)

The codebase has no `useToast` hook. Existing `ContactDrawer` pattern
is `setError(err.message)` rendered directly under the failing
button. New mutations follow the same pattern:

```tsx
{error && (
  <p role="alert" className="text-xs text-danger mt-2">{error}</p>
)}
```

Specific error messages to surface:

| Mutation | Status | Inline message |
|---|---|---|
| `assignFlow` | 409 | "Already enrolled in this flow." |
| `assignFlow` | 400 | "This flow is inactive." |
| `markSampleShipped` | 404 | "Contact not found." |
| `markSampleShipped` | 409 | "Already marked shipped." (if backend ever returns it) |
| `pauseMembership` | 409 | "Membership is not in an active state." |
| `resumeMembership` | 409 | "Membership is not paused." |
| any | 5xx / network | "Something went wrong. Please try again." |

If a toast component lands later (Phase 7.10 or beyond), refactor
these inline errors to fire `toast.error(message)` instead — the
single message-source-per-mutation pattern makes the migration
mechanical.

### 3.9 Contacts list "Flow" column — DEFER to Phase 7.10

Per PLAN_flows §6.5 this needs a `GET /contacts/active-flows?ids=<csv>`
batch endpoint to avoid N+1. Building it adds backend work that
distracts from the 7.8 visibility goal. Mark as deferred and revisit
in 7.10 alongside the auto-tag jobs.

---

## Section 4 — API hooks needed in `vite_dashboard/src/api/flows.ts`

### 4.1 Type definitions to add

```ts
export type FlowMembershipOut = {
  id: number;
  flow_id: number;
  flow_name: string;
  flow_slug: string | null;
  contact_id: string;
  contact_name: string;
  contact_email: string | null;
  status:
    | "active"
    | "waiting_event"
    | "paused"
    | "completed"
    | "failed"
    | "stopped";
  current_step_index: number;
  total_steps: number;
  started_at: string;
  last_step_at: string | null;
  next_fire_at: string | null;
  trigger_source: string;
  trigger_actor: string;
  error: string;
};

export type FlowStepRunOut = {
  id: number;
  membership_id: number;
  step_index: number;
  channel: "email" | "whatsapp";
  fired_at: string;
  status: "sent" | "failed" | "skipped";
  template_slug: string;
  message_ref: string;
  error: string;
};
```

Also widen the existing `FlowOut` type:

```ts
export type FlowOut = {
  id: number;
  name: string;
  slug: string | null;        // new
  description: string;
  channel: "email" | "whatsapp" | "multi";  // widened
  is_active: boolean;
  step_count: number;
  trigger_type: string;       // new
  trigger_config: Record<string, unknown>;  // new
  active_count: number;       // new
  created_at: string;
};
```

### 4.2 Hooks to add — with explicit cache policy

`useFlows` already uses `staleTime: 30 * 1000`. Apply the same cadence
where the data changes on every operator action; allow longer for
audit-style reads.

| Hook | Endpoint | `staleTime` | Why |
|---|---|---|---|
| `useFlow(flowId)` | `GET /flows/{id}` | `30 * 1000` | Membership counts change with each tick; matches list. |
| `useFlowMemberships(flowId, {status?, limit?})` | `GET /flows/{id}/memberships` | `30 * 1000` | Hot-path for the detail page Members tab. |
| `useFlowStepRuns(flowId, {status?, limit?})` | `GET /flows/{id}/step-runs` | `60 * 1000` | Audit log — append-only, less time-critical. |
| `useContactFlowMemberships(contactId, {include_past?})` | `GET /contacts/{id}/flow-memberships` | `30 * 1000` | Drawer Flows-tab hot path. |

Query-key conventions (mirrors existing patterns):

```ts
["flows"]                                      // useFlows
["flows", "detail", flowId]                    // useFlow
["flows", "memberships", flowId, status]       // useFlowMemberships
["flows", "step_runs", flowId, status]         // useFlowStepRuns
["contacts", "detail", contactId, "flow-memberships"]  // useContactFlowMemberships
```

### 4.3 Mutations to add — with optimistic strategy

```ts
assignFlow(flowId, contactId)             // POST /flows/{id}/memberships
stopMembership(membershipId)              // POST /flow-memberships/{id}/stop
pauseMembership(membershipId)             // POST /flow-memberships/{id}/pause
resumeMembership(membershipId)            // POST /flow-memberships/{id}/resume
markSampleShipped(contactId, body)        // POST /contacts/{id}/mark-sample-shipped
```

| Mutation | Optimistic? | Invalidates on settle |
|---|---|---|
| `assignFlow` | **No** — server returns the membership; insert into cache via `setQueryData` after success so the new card appears instantly | `["flows"]`, `["flows", "memberships", flowId]`, `["contacts", "detail", contactId, "flow-memberships"]` |
| `stopMembership` / `pauseMembership` | **Yes** — flip `status` locally on the membership row before the round-trip; rollback on error | `["flows", "memberships", flowId]`, `["contacts", "detail", contactId, "flow-memberships"]` |
| `resumeMembership` | **Yes** — same pattern, status `paused` → `active`, set `next_fire_at = now()` for UI continuity | `["flows", "memberships", flowId]`, `["contacts", "detail", contactId, "flow-memberships"]` |
| `markSampleShipped` | **No** — server response carries `memberships_updated` + `new_memberships_from_trigger` which the UI uses to decide whether to show "Step will fire within 60s" | `["contacts", "detail", contactId, "flow-memberships"]`, `["contacts", "detail", contactId]` (for tags + activity) |

The optimistic-flip pattern uses React Query's `onMutate` to snapshot
+ patch the cached data, `onError` to rollback, `onSettled` to
invalidate. Existing `setContactLifecycle` does NOT use optimistic
updates today — Phase 7.8 introduces the pattern, document the helper
in a shared `lib/optimistic.ts` so it doesn't have to be re-derived
per mutation.

### 4.4 Single-flow detail endpoint

There's no `GET /api/v2/flows/{id}` single-row endpoint today; the
list endpoint returns the full flow including steps. Two options:

| Option | Trade-off |
|---|---|
| Add `GET /api/v2/flows/{id}` (small backend addition) | One extra query per detail-page load, but the URL is clean and it's `O(1)` |
| Reuse the list response: detail page calls `useFlows()` and `find(f => f.id === id)` | No backend work; but every detail page load fetches all flows |

**Recommend the new endpoint** — 5 minutes of backend work, cleaner
caching story. Add to `api_v2/routers/flows.py`.

### 4.5 Analytics events — match the existing `track()` convention

ContactDrawer wires `track()` for every existing action
(`contact_lifecycle_quick_action`, `contact_edited`,
`contact_edited{fields_changed:["tags"]}`). New mutations and surfaces
must emit equivalent events so the funnel stays measurable.

| Event | Payload | Where it fires |
|---|---|---|
| `flow_membership_created` | `{flow_id, flow_slug, contact_id, source: "drawer" \| "flow_detail"}` | `assignFlow` mutation `onSuccess` |
| `flow_membership_stopped` | `{flow_id, flow_slug, contact_id, current_step_index, source}` | `stopMembership` mutation `onSuccess` |
| `flow_membership_paused` | `{flow_id, flow_slug, contact_id, current_step_index, source}` | `pauseMembership` mutation `onSuccess` |
| `flow_membership_resumed` | `{flow_id, flow_slug, contact_id, source}` | `resumeMembership` mutation `onSuccess` |
| `sample_marked_shipped` | `{contact_id, courier_name, tracking_id_present: true}` | `markSampleShipped` mutation `onSuccess`. **Do NOT send `tracking_id` itself** — operator-typed PII; we only need the boolean for funnel analytics. |
| `flow_detail_viewed` | `{flow_id, flow_slug, tab: "members" \| "steps" \| "step_runs"}` | `<FlowDetailPage>` mount + tab change |
| `contact_drawer_flows_tab_viewed` | `{contact_id, active_count, past_count}` | When the Flows tab in the drawer is opened (not on initial drawer mount) |

`source: "drawer" \| "flow_detail"` distinguishes whether the action
came from the contact drawer or the flow detail page — useful for
deciding which surface to invest in further.

---

## Section 5 — Backend additions

### 5.1 Pause / resume endpoints

`api_v2/routers/flows.py` (in the `membership_router`):

```python
@membership_router.post(
    "/flow-memberships/{membership_id}/pause",
    response_model=FlowMembershipOut,
)
def pause_membership(membership_id: int) -> FlowMembershipOut:
    """Operator-driven pause. Sets status='paused', clears next_fire_at,
    writes a `flow_paused` interaction. Idempotent."""
    # body mirrors stop_membership but sets status='paused' instead.


@membership_router.post(
    "/flow-memberships/{membership_id}/resume",
    response_model=FlowMembershipOut,
)
def resume_membership(membership_id: int) -> FlowMembershipOut:
    """Operator-driven resume. From 'paused' → 'active' with
    next_fire_at=now() so the next tick picks it up. Refuse on any
    non-paused status (404 detail: "membership not paused")."""
```

Engine impact in `flows_engine_v2.py`:

- `tick_flows()`'s claim filter is `status == 'active'` already, so
  paused rows are correctly excluded. **Verify with a test**.
- The reaper at lifespan start (`reap_stranded_memberships`) currently
  only re-arms `status='active' AND next_fire_at IS NULL`. Paused
  memberships stay paused — good.
- Add a `flow_paused` / `flow_resumed` interaction kind to
  `services/interactions.py::_KIND_ICON` + `_KIND_COLOR` so the
  Activity tab shows them.

### 5.2 Single-flow detail endpoint

```python
@router.get("/flows/{flow_id}", response_model=FlowDetailOut)
def get_flow(flow_id: int) -> FlowDetailOut:
    """Single-flow read with the full steps array + per-status counts."""
```

`FlowDetailOut` extends `FlowOut` with the `steps` array and
`{active, waiting_event, paused, completed, failed, stopped}` counts —
one GROUP BY on `flow_memberships` for that flow.

### 5.3 Schema additions in `api_v2/schemas/flows.py`

```python
class FlowDetailOut(FlowOut):
    steps: list[dict[str, Any]]           # raw flow.steps JSON
    counts: dict[str, int]                # per-status count map


class FlowMembershipDetail(FlowMembershipOut):
    """Drawer-friendly variant — includes flow + step shape so the UI
    knows whether to render the Mark Sample Shipped button without a
    second round-trip."""
    flow_trigger_type: str
    current_step: dict[str, Any] | None   # the step JSON at current_step_index
```

`useContactFlowMemberships` returns `FlowMembershipDetail[]` — the
drawer needs `current_step.trigger_event.value == 'samples_shipped'`
to decide whether to render the Mark Sample Shipped button.

---

## Section 6 — Page configs + route registration

### 6.1 `vite_dashboard/src/config/pages/flows.yml` — full rewrite

```yaml
page:
  title: "Flows"
  subtitle: "Multi-step automated send sequences"
  how_to_use:
    summary: "Auto-enroll contacts on a tag/lifecycle change and run a multi-step send sequence with operator intervention points."
    sections:
      - title: "How a flow runs"
        body: |
          A flow is a list of steps. When a contact's lifecycle changes
          or a configured tag is added, they're enrolled in any matching
          flow. The scheduler tick fires the steps with the configured
          delays. Some steps wait for an operator action (e.g. "Mark
          sample shipped") instead of a timer.
      - title: "Sample Dispatch — the canonical flow"
        body: |
          1. Tag a contact `samples_requested` → step 0 fires
             immediately (thank-you email + WA template).
          2. Membership parks at `waiting_event`. Prepare the sample.
          3. Click "Mark sample shipped" in the contact drawer with
             tracking + courier — step 1 sends the dispatch email + WA.
          4. Seven days later, step 2 sends the follow-up.
      - title: "See per-contact progress"
        body: |
          Click any flow row to see every contact in that flow, the
          step they're on, when the next send fires, and per-row
          Pause / Resume / Stop actions. Or open a contact's drawer →
          Flows tab to see all their memberships.
      - title: "Pause vs. Stop"
        body: |
          Pause re-arms when you click Resume — useful if samples
          aren't ready and you want to hold communication for a few
          days. Stop is terminal — the membership won't fire any more
          steps.
  landed_phase: 7.8
  table:
    page_size: 25
  detail:
    members_default_status: "active"
    step_runs_default_status: ""
    members_page_size: 50
```

### 6.2 New route in `vite_dashboard/src/routes/index.tsx`

```tsx
import { FlowDetailPage } from "@/pages/flows/FlowDetailPage";
// ...
{ path: "flows", element: <FlowsPage /> },
{ path: "flows/:flowId", element: <FlowDetailPage /> },
```

### 6.3 STRINGS additions in `@/lib/strings`

```ts
flows: {
  detail: {
    backToList: "← Back to flows",
    membersTab: "Members",
    stepsTab: "Steps",
    stepRunsTab: "Step Runs",
    statusFilter: "Status",
    membersEmpty: "No contacts in this flow yet.",
    pauseAction: "Pause",
    resumeAction: "Resume",
    stopAction: "Stop",
    confirmStop: "Stop this flow for {{name}}? This is irreversible.",
    confirmPause: "Pause this flow for {{name}}?",
  },
},
contacts: {
  drawer: {
    tabFlows: "Flows",
    flowsTab: {
      activeHeader: "Active flows",
      pastHeader: "Past flows",
      addToFlow: "Add to flow",
      noActiveFlows: "No active flows.",
      markSampleShipped: "Mark sample shipped",
      markShippedTrackingLabel: "Tracking ID",
      markShippedCourierLabel: "Courier",
      markShippedSubmit: "Mark shipped",
    },
  },
},
```

---

## Section 7 — Testing strategy

### 7.0 Test file conventions (existing)

| Layer | Framework | File pattern | Example |
|---|---|---|---|
| Frontend hooks/utils | Vitest | `vite_dashboard/src/api/<name>.test.ts` (colocated) | `vite_dashboard/src/api/contacts.test.ts` |
| Backend (api_v2) | pytest | `api_v2/tests/test_<area>.py` | `api_v2/tests/test_flows_engine_v2.py` |
| Frontend e2e | Playwright | `vite_dashboard/tests/<name>.spec.ts` | (none yet — testDir per `playwright.config.ts:13`) |

The Playwright `tests/` directory does NOT exist today; **scaffolding
it is part of Phase 7.8.3** (the first phase that lands a Playwright
spec). Set up the directory with one `tests/auth-helper.ts` for the
shared bearer-token-or-no-auth login path that the spec needs.

### 7.1 Unit (Vitest) — `vite_dashboard/src/api/flows.test.ts`

- `useFlowMemberships` paginates correctly when status filter changes
- `assignFlow` mutation invalidates the right keys
- `markSampleShipped` mutation invalidates `["contacts","detail",id,"flow-memberships"]`
- `<MembershipStatusPill>` renders correct tone for each of the 6 statuses
- Mark-shipped form validates that tracking_id + courier are
  non-empty before enabling submit
- `pauseMembership` optimistic update flips status locally then
  rolls back if the API returns 409
- `assignFlow` 409 surfaces "Already enrolled in this flow." inline

### 7.2 Backend (pytest)

Add to `api_v2/tests/test_flows_engine_v2.py`:

- `pause_membership` flips status='paused' and clears next_fire_at;
  next `tick_flows()` does NOT claim it
- `resume_membership` from `paused` → `active` with next_fire_at=now,
  next tick claims and fires
- `resume_membership` on a non-paused membership returns 409
- `GET /flows/{id}` returns the steps array + per-status counts

### 7.3 Playwright golden path

`vite_dashboard/tests/flows-phase-7-8.spec.ts` (testDir is `./tests`
per `vite_dashboard/playwright.config.ts:13` — not `./e2e`):

```
1. Login.
2. Open contact "Sample Tester" drawer → Tags tab → add `samples_requested`.
3. Wait 70s for the scheduler tick (or trigger via the test-mode endpoint).
4. Re-open the drawer → Flows tab → assert Sample Dispatch is listed
   with status `waiting_event`, step 2 of 3, Mark sample shipped button visible.
5. Click Mark sample shipped → fill tracking + courier → submit.
6. Assert: tag `samples_shipped` appears in Tags tab; Activity tab
   shows `tag_added` row.
7. Wait another 70s for step 1 to fire.
8. Re-open drawer → Flows tab → assert membership advanced to step 3
   of 3, status `active`, next fire ~7 days out.
9. Navigate to /flows → click Sample Dispatch row → /flows/:id loads.
10. Assert Members tab includes the test contact at step 3.
11. Click row Stop action → confirm dialog → assert membership status
    becomes `stopped` and disappears from active filter.
```

Test runs against the live v2 Space (no auth, mirrors v1 testing
convention). Sleeping 70s twice is acceptable for an e2e smoke; for
faster CI, expose a `POST /api/v2/_test/tick-flows` admin endpoint
that runs `tick_flows()` synchronously when `APP_ENV=test`.

---

## Section 8 — Phasing

One PR per sub-phase, each shippable independently. Each ends with a
deploy + Playwright check on the v2 Space.

### 7.8.1 — List page extensions + legacy seed cleanup (1 day)

1. Widen `FlowOut` type + add `useFlow(id)` hook + add `GET /flows/{id}`
   endpoint
2. Update `FlowsTable` columns: trigger pill, active count
3. `onRowClick` → `useNavigate` to `/flows/:id`
4. Remove inline `FlowRunsPanel` import (component stays, just
   unreferenced)
5. Update `flows.yml` `landed_phase: 7.8` + new how_to_use copy
6. **Deactivate legacy seed flows** — flip `is_active=False` on the 3
   pre-Phase-7 flows in `services/database.py:_seed_default_flows`
   (per §9.6 mitigation). One-line change per flow; sample_dispatch
   stays active.

### 7.8.2 — Flow detail page (1.5 days)

1. New `<FlowDetailPage>` component + register `/flows/:flowId` route
2. Members tab (default) — DataTable with status filter + actions menu
3. Steps tab — read-only step cards
4. Step Runs tab — flat audit log with status filter
5. KPI cards using `flow.counts`

### 7.8.3 — Contact drawer Flows tab + Mark Sample Shipped (1.5 days)

1. Add 5th tab to `<ContactDrawer>` with active/past sections.
   **Extract the new tab body** to `pages/contacts/components/ContactDrawer/FlowsTab.tsx` rather than growing the 553-line drawer further (§9.2).
2. "Add to flow" dropdown
3. Mark sample shipped action card (conditional on
   waiting_event + sample_dispatch slug, inline-expand per §3.7)
4. STRINGS additions
5. Wire mutations + cache invalidations + analytics events (§4.5)
6. Scaffold the Playwright `tests/` directory + auth helper for the
   first e2e spec (lands in 7.8.4 when the full path is exercisable).

### 7.8.4 — Pause / resume backend + UI (0.5 days)

1. `POST /flow-memberships/{id}/pause` and `/resume`
2. New interaction kinds (`flow_paused`, `flow_resumed`) wired through
   `interactions.py::_KIND_ICON` + `_KIND_COLOR`
3. Pause/Resume buttons in the drawer Flows tab card and the
   `/flows/:id` Members tab actions menu
4. Backend tests for the two new endpoints + tick-flows-skips-paused

**Total estimate: 5 days** (the 4-day floor assumes no scope creep on
the legacy `<FlowRunsPanel>` cleanup or the early `FlowsTab.tsx`
extraction; budget the upper bound).

---

## Section 9 — Risks / open questions

### 9.1 Optimistic UI vs. 60s scheduler tick lag

**Risk:** operator clicks "Mark sample shipped" → expects to see step
1 fire — but the scheduler tick is 60s away. Confusing UX.

**Mitigation:** the response from `markSampleShipped` already returns
`new_memberships_from_trigger` count; show a toast like "Step will
fire within the next minute." Better long-term: a small
`POST /_test/tick-flows` admin endpoint exposed in non-prod for
operator-triggered ticks. For prod, document the 60s expectation in
the HowToUse copy.

### 9.2 ContactDrawer is already 553 lines

The Flows tab body is ~120 lines including the Mark Sample Shipped
form. Extract `<FlowsTabBody>` to a sibling file
`pages/contacts/components/ContactDrawer/FlowsTab.tsx` rather than
growing the drawer further. Phase 7.8 is a good moment to also split
the existing tabs into separate files (each ~80 lines), but mark that
as a follow-up cleanup, not a blocker.

### 9.3 The legacy `<FlowRunsPanel>` becomes orphaned

Today it reads from the deprecated `useFlowRuns` hook. After 7.8.1 the
list page no longer renders it. Two options:

| Option | Trade-off |
|---|---|
| Delete the component + the legacy hook + `GET /flows/{id}/runs` endpoint | Cleanest, loses the cohort-runs view permanently |
| Leave them dead until Phase 7.10 | Smaller diff for 7.8, easier rollback if the new detail page has bugs |

**Recommend leave-dead-until-7.10.** Reduces PR risk; the dead code
costs nothing at runtime.

### 9.4 Pause status not yet wired into the engine claim filter

`tick_flows()` filters `status == 'active'`. Paused rows are correctly
skipped. But there's no test that proves it today. Adding the test in
7.8.4 is non-negotiable so we don't ship a regression.

### 9.5 What if a contact has 5+ active flow memberships?

The drawer Flows tab renders one card per active membership. With 5+
it gets long. Decision: scroll vertically (the drawer already scrolls
via `overflow-auto`), no card collapse for v1. Revisit if real usage
pushes past 5.

### 9.6 Sample Dispatch is the only seeded flow

The "Add to flow" dropdown will show ~4 flows (sample_dispatch, b2b
introduction flow legacy, welcome & nurture flow legacy, whatsapp
welcome flow legacy). Operators may not understand the legacy three.

**Mitigation (2 layers):**

1. **Code-level retirement of the legacy seed flows** — extend the
   single edit in `services/database.py:_seed_default_flows` to set
   `is_active=False` on the 3 legacy flows. The list page's
   `active_only` filter and the drawer's "Add to flow" dropdown both
   honor `is_active`, so legacy flows simply disappear from operator
   view. **Sub-30-line change; landed in Phase 7.8.1 alongside the
   page-config rewrite.**
2. **Render a `<TriggerPill>` in the dropdown** so operators see
   "Manual" vs "Tag: samples_requested" and pick intelligently — even
   if a future flow shares ambiguous naming.

Phase 7.9's flow editor adds the operator-facing path to retire flows
without a code change.

---

## Section 10 — Out of scope for Day 5 / Phase 7.8

- **Flow editor (Phase 7.9):** create / edit / delete flows from the
  UI. Steps tab is read-only.
- **Bulk operations (Phase 7.10):** "Stop all members of this flow",
  "Enrol an entire segment".
- **Auto-tag cron (Phase 7.10):** `cold_60d` tagging job, automated
  segment-matched enrollment.
- **Active flow column on `/contacts` table:** needs the batch
  active-flows lookup endpoint; defer to 7.10.
- **Real-time updates:** polling on a 30s `staleTime` is fine; no
  websocket / SSE.
- **Drag-and-drop step editor:** linear list only when 7.9 lands.
- **Per-membership variable overrides:** today only the operator-set
  `metadata_json` (tracking_id, courier_name) is exposed; variable
  overrides for arbitrary template vars wait for 7.9.

---

## Section 11 — Acceptance criteria

Day 5 ships when:

1. `/flows` list shows trigger pills and active member counts and
   navigates to detail on row click.
2. `/flows/:id` renders the three tabs (Members default, Steps, Step
   Runs) and the Members tab supports status filter + per-row Pause /
   Resume / Stop actions.
3. ContactDrawer has a Flows tab listing active and past memberships
   with the Mark Sample Shipped form rendering correctly when the
   contact is parked at the matching step.
4. Pause and Resume endpoints exist + are tested + tick_flows is
   confirmed to skip paused memberships.
5. The Playwright golden path in §7.3 passes against a fresh deploy
   of the v2 Space.
6. All existing tests still pass.

---

## Critical files for Day 5

**Frontend:**

- `vite_dashboard/src/api/flows.ts` — extend hooks + types
- `vite_dashboard/src/pages/flows/FlowDetailPage.tsx` — NEW
- `vite_dashboard/src/pages/flows/components/FlowsTable.tsx` — extend
  columns + navigate on click
- `vite_dashboard/src/pages/contacts/components/ContactDrawer.tsx` —
  add 5th tab
- `vite_dashboard/src/pages/contacts/components/ContactDrawer/FlowsTab.tsx`
  — NEW
- `vite_dashboard/src/routes/index.tsx` — register `/flows/:flowId`
- `vite_dashboard/src/config/pages/flows.yml` — rewrite copy
- `vite_dashboard/src/lib/strings.ts` — add flows + drawer strings

**Backend:**

- `api_v2/routers/flows.py` — add `GET /flows/{id}`, pause + resume
  endpoints
- `api_v2/schemas/flows.py` — add `FlowDetailOut`,
  `FlowMembershipDetail`
- `api_v2/services/flows_engine_v2.py` — add small `pause_membership` /
  `resume_membership` helpers (optional; routers can do it inline
  since the logic is trivial)
- `hf_dashboard/services/interactions.py` — add `flow_paused` /
  `flow_resumed` icon + color entries
- `api_v2/tests/test_flows_engine_v2.py` — pause/resume + tick-skips-paused
  tests
- `vite_dashboard/e2e/phase7-8.spec.ts` — NEW Playwright golden path
