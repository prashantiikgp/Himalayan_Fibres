# PLAN — Phase 7 Flows: Auto-assigned, time-delayed sequences with full visibility

> **Scope:** automation flows (multi-step, time-delayed sequences) that get auto-assigned to a contact when a trigger fires. Each contact's flow membership is observable per-step on contact, flow, and aggregate pages.
>
> **Non-scope (see §10):** branching, A/B, real-time UI, drag-drop graph editors.
>
> **Architectural assumption:** single-replica deploy (HF Space). The scheduler claim trick in §5 relies on this. If we ever scale horizontally, revisit §5.3 — the "park rows by nulling `next_fire_at`" trick conflates "in-flight in another worker" with "stranded by restart".

---

## Section 1 — Current state audit

### 1.1 Tables that already exist

`/home/prashant-agrawal/projects/email_marketing/hf_dashboard/services/models.py`:

| Table | Status | Suitability for Phase 7 |
|---|---|---|
| `flows` (id, name, description, channel, steps:JSON, is_active, created_at) | Exists | Cohort-style, NOT contact-keyed. `steps` is a JSON blob with shape `[{day, template_slug, subject}]`. Re-usable as the **definition** table; needs slug, trigger fields added. |
| `flow_runs` (flow_id, segment_id, status, current_step, total_contacts, total_sent, total_failed, next_step_at, started_at) | Exists | **Wrong shape for the new model.** Today one FlowRun spans a whole segment cohort and advances `current_step` once for everyone — there is no per-contact state. Cannot answer "where is contact X in flow Y?" Replace with `flow_memberships` (per-contact) + `flow_step_runs` (per-step, per-contact). Keep `flow_runs` for legacy v1 batch flows or migrate them. |
| `contacts.lifecycle` (string, default `new_lead`) | Exists | Values seen: `new_lead`, `contacted`, `interested`, `customer`, `churned` (config: `/home/prashant-agrawal/projects/email_marketing/config/dashboard/contacts/schema.yml`). Used today by `_compute_lifecycle()` in `services/database.py` (lines 205-215) and `POST /api/v2/contacts/{id}/lifecycle` in `api_v2/routers/contacts.py:391`. **Trigger candidate.** |
| `contacts.tags` (JSONType list) | Exists | Predefined tags include `samples_sent`, `samples_received`, `quoted`, `order_placed` (schema.yml lines 47-60). **Trigger candidate.** |
| `contact_interactions` | Exists | Audit-trail table; we'll write `flow_assigned`, `flow_step_sent`, `flow_completed`, `flow_stopped` rows here so the existing Activity tab in the contact drawer surfaces flow events for free. |
| `email_templates` + on-disk `<slug>.html` | Exists | Template catalog (see §2). |
| `wa_templates` + `config/whatsapp/templates.yml` + `config/whatsapp/new_templates.yml` | Exists | Template catalog (see §2). |

### 1.2 What `flows_engine.py` does today (read of `/home/prashant-agrawal/projects/email_marketing/hf_dashboard/services/flows_engine.py`)

- `start_flow(db, flow_id, segment_id, start_date)` — creates ONE `FlowRun` for an entire segment, calls `execute_flow_step(0, contacts)` synchronously.
- `execute_flow_step(...)` — iterates the cohort, sends step's email/WA to all contacts in a tight loop with `time.sleep(3)` per email and `time.sleep(1)` per WA, mutates `run.current_step += 1`, computes `run.next_step_at = now + (next_day - current_day) days`, saves.
- `check_pending_steps(db)` — polls active runs whose `next_step_at <= now` and re-fires for the entire cohort.
- `_send_email_step` uses `EmailSender.render_template()` and `generate_idempotency_key(f"flow_{run.id}", contact.id, str(run.current_step))` so re-firing a step is safe.
- `_send_wa_step` uses `WhatsAppSender.send_template()` with named-param renderer — works outside the 24h window.

**Critical gaps for the new model:**

1. **No per-contact membership.** A new contact joining the segment between step 1 and step 2 either gets nothing or gets step 2 without step 1, depending on timing.
2. **No trigger model.** Flows are started manually from a Gradio dropdown. There is no event bus.
3. **`check_pending_steps()` is never called by api_v2 scheduler** (`api_v2/services/scheduler.py` only fires `Broadcast` and `Campaign` rows).
4. **No conditions on steps** (e.g. "skip if no email" / "send WA only if has wa_id").
5. **Single channel per flow** (`flow.channel` is `email | whatsapp`), so a multi-channel Sample-Dispatch flow cannot be expressed.

### 1.3 What `/flows` shows today

- **v2 (`vite_dashboard/src/pages/flows/FlowsPage.tsx` + `components/FlowsTable.tsx`)** — Phase 5.0 read-only list: status pill, name, channel, step count, created. Click row → drawer with last 20 `FlowRun` rows (cohort-based, no per-contact view). Comment in source: "Phase 5.1+ will add Start/Pause/Cancel and the steps editor."
- **v1 (`hf_dashboard/pages/flows.py`)** — Gradio page; left col select-flow + start-on-segment; right col HTML rendered step list + last-10 runs table.
- **API (`api_v2/routers/flows.py`)** — `GET /api/v2/flows` (list) and `GET /api/v2/flows/{id}/runs` (recent runs). No POST/PATCH/DELETE.
- **Schemas (`api_v2/schemas/flows.py`)** — `FlowOut` carries `step_count` only; the steps array isn't on the wire yet.
- **Hooks (`vite_dashboard/src/api/flows.ts`)** — `useFlows`, `useFlowRuns`. Cache key `["flows", q]`, 30 s stale.
- **Page config (`vite_dashboard/src/config/pages/flows.yml`)** — declares Phase 5 read-only state and links to a planned Phase 5.1 steps editor.

### 1.4 Existing scheduler / async worker

**`api_v2/services/scheduler.py` exists** and is wired into FastAPI lifespan (`api_v2/main.py:110-152`). One task started by `lifespan()` runs `scheduler_loop()` which sleeps 60 s and calls `tick_once()`. Today `tick_once()` only fires due `Broadcast` (WA) and `Campaign` (email) rows using `FOR UPDATE SKIP LOCKED` (Postgres) for atomic claim.

**This is the right hook for Phase 7 flows.** We extend `tick_once()` to also fire due `FlowMembership` rows. No new worker, no Celery.

### 1.5 Triggers currently emitted

`/home/prashant-agrawal/projects/email_marketing/hf_dashboard/services/interactions.py` already has the right vocabulary — `manual_edit`, `imported`, `note_added`, `email_sent`, `tag_added`, `lifecycle_<value>`. Sites that call `log_interaction()` today:

- `api_v2/routers/contacts.py:414` — POST `/contacts/{id}/lifecycle` writes `kind=lifecycle_<value>`.
- `api_v2/routers/contacts.py:510` — POST `/contacts` writes `kind=imported`.
- `api_v2/routers/contacts.py:551` — `update_contact` PATCH `/contacts/{id}` writes `kind=manual_edit` at line 652.
- `api_v2/routers/contacts.py:721` — POST notes writes `kind=note_added`.
- `hf_dashboard/pages/contacts.py:787,909,995` — Gradio drawer paths.
- `hf_dashboard/pages/email_broadcast.py:941` — broadcast send.

**There is no event bus and no `tag_added` standalone event.** The interactions table is the closest thing to a write-ahead log; it's a reliable hook for triggers. **Strategy:** the trigger evaluator reads recent `contact_interactions` rows after each scheduler tick (or — preferred — flow assignment is co-located with the lifecycle/tag mutator in the same DB transaction, see §4). No event bus needed for v1.

---

## Section 2 — Template inventory

### 2.1 Email templates — what's seeded vs. what's on disk

`/home/prashant-agrawal/projects/email_marketing/hf_dashboard/config/email/templates_seed/` (six `.meta.yml` files — these define what the DB knows):

| Slug | Purpose | Required vars | Optional vars | Category | Good for which flow step |
|---|---|---|---|---|---|
| `welcome` | Brand intro email for a new subscriber | `first_name` | — | nurture | Step 0 of **B2B Welcome**, Step 0 of **Newsletter Welcome** |
| `b2b_introduction` | First-touch outreach to carpet exporters | `company_name` | — | campaign | Step 0 of **Cold B2B Outreach** |
| `order_confirmation` | Order placed acknowledgement | `first_name`, `order_number`, `order_date`, `items_html`, `total` | `ship_to_html`, `subtotal`, `shipping`, `payment_method`, `invoice_url` | transactional | Step 0 of **Order Lifecycle** |
| `order_shipped` | Tracking dispatch | `first_name`, `courier_name`, `tracking_id` | `dispatch_date`, `delivery_date`, `tracking_url`, `invoice_url` | transactional | Step 1 of **Order Lifecycle** only. Sample Dispatch needs a dedicated `sample_shipped.html` — see §2.4 / §7.1, do not re-purpose this slug. |
| `order_delivered_feedback` | "How was your order?" | `first_name` | — | transactional | Step 2 of **Order Lifecycle** (T+7 after delivery) |
| `operational_update` | One-off ops/news email | `first_name`, `update_title`, `update_body_html` | `update_cta_label`, `update_cta_url` | announcement | Not flow-suited (manual-broadcast template) |

### 2.2 Email templates on disk but NOT seeded into DB

`hf_dashboard/templates/emails/` (these have `.html` but no `.meta.yml` so the DB has no row — `template_seed.py:123` calls `template_file_exists(meta.slug)` and **skips meta files for which the slug `.html` is missing**, but the inverse — `.html` with no `.meta.yml` — means the file is renderable but the DB has no `EmailTemplate` row, so the broadcast UI / flow editor cannot offer it as a choice).

Templates that are **on-disk only** today and would unlock new flows once seeded:

| Slug (filename) | Purpose | Vars (from header comment) | Flow step value |
|---|---|---|---|
| `sample_invitation` | "Try a free yarn sample" CTA | `sample_request_link` (optional) | Step 1 of **Cold B2B Sample-Offer** flow |
| `post_sample_followup` | T+5/7 after sample dispatch — "did it feel right?" | `first_name`, `fibre_sent`, `sample_dispatched_at?`, `proforma_link?`, `book_call_link?` | **Step 3 (T+7) of Sample Dispatch flow — this is exactly the user's example.** |
| `welcome_day_3_sustainability` | T+3 welcome continuation | `first_name` | Step 1 of **B2B Welcome** flow |
| `onboarding_day_14_first_order` | T+14 nudge to first order | `first_name` | Step 2 of **B2B Welcome** flow |
| `winback_60d_silent` | Re-engagement after 60 d silence | `first_name`, `last_engaged_at?` | Step 0 of **Re-engage Cold Lead** flow |
| `proforma_invoice` | Proforma PDF email | `first_name`, `proforma_*`, items | Step 1 of **Quote Follow-up** flow |
| `abandoned_cart_recovery` | Cart abandonment nudge | unknown | Probably E-comm — out of scope |
| `harvest_announcement` | Seasonal product drop | unknown | Manual broadcast, not flow |
| `diwali_greetings`, `year_end_recap` | Seasonal | — | Manual broadcast |
| `hemp_focus`, `wool_focus`, `nettle_focus`, `collections_focus`, `yarn_categories_intro` | Product-line spotlights | unknown | Manual broadcast |
| `blog_*` (4 files) | Blog-as-email digests | unknown | Manual broadcast |

### 2.3 WhatsApp templates

From `/home/prashant-agrawal/projects/email_marketing/config/whatsapp/templates.yml` (the **registry** — these are the templates the registry says are deployable; live status/approval comes from `WATemplate` DB rows):

| Name | Cat | Lang | Vars | Use case | Good for which flow step |
|---|---|---|---|---|---|
| `hello_world` | UTILITY | en_US | — | testing | health check only |
| `welcome_message` | MARKETING | en | `customer_name` | onboarding | Step 0 WA of **B2B Welcome (multi-channel)** |
| `order_confirmation` | MARKETING | en | `customer_name`, `order_id`, `product_names`, `amount` | transactional | Step 0 WA of **Order Lifecycle** |
| `payment_confirmation` | UTILITY | en | `customer_name`, `amount`, `order_id` | transactional | Step 1 WA of **Order Lifecycle** |
| `order_tracking` | UTILITY | en | `customer_name`, `order_id`, `tracking_id`, `tracking_link` | transactional | Step 1 WA of **Order Lifecycle**, step 1 WA of **Sample Dispatch** (with sample IDs as order IDs) |
| `order_delivered` | UTILITY | en | `1`, `2` (positional — Meta deprecated unnamed positional params for new templates; verify the registry's renderer maps them, and consider re-submitting with named params before this template is wired into a flow) | transactional | Step 2 WA of **Order Lifecycle** |
| `thank_you_note` | MARKETING | en | `1` | retention | Step 1 of **Post-purchase Retention** |
| `snow_white` | MARKETING | en | — | product showcase | Manual broadcast |
| `interactive_whatsap_buttons_new` | MARKETING | en | — | catalog | Manual broadcast |

From `config/whatsapp/new_templates.yml` (templates **defined but submission status TBD**, found by reading the file directly):

| Name | Cat | Vars | Status | Flow value |
|---|---|---|---|---|
| `b2b_fiber_intro` | MARKETING | `{{1}}` (header company), `{{1}}` (body name) | unknown — needs `WATemplate.status` check | Step 0 WA of **Cold B2B WA Outreach** |
| `followup_interest` | MARKETING | `{{1}}`, `{{2}}` | unknown | Step 1 WA of **Cold B2B WA Outreach** (T+3) |
| `sample_shipped` | UTILITY | `{{1}}` (name), `{{2}}` (tracking), `{{3}}` (eta) | unknown | **Step 1 of Sample Dispatch flow — the user's example** |
| `price_list_share` | MARKETING | `{{1}}` | unknown | Step 1 of **Quote Follow-up** flow |

### 2.4 Identified template gaps (what we'd need to author)

| Gap | Needed for flow | Channel | Suggested slug | Notes |
|---|---|---|---|---|
| **"Thanks-for-interest" sample-acknowledgement email** | Sample Dispatch step 0 | email | `sample_request_received` | Bridges the gap between request and shipment. No existing template fits — `sample_invitation` is the *invite*, not the *ack*. |
| **WA equivalent of sample-request ack** | Sample Dispatch step 0 (multi-channel) | whatsapp | `sample_request_received` | Submit to Meta. UTILITY category. 24h-window-safe. |
| **Sample T+14 / T+30 deeper follow-up** | Sample Follow-up flow | email | `sample_followup_d14`, `sample_followup_d30` | `post_sample_followup` covers T+7; deeper checkin if no response. |
| **Quote sent acknowledgement + 3d, 7d, 14d follow-ups** | Quote Follow-up | email | `quote_sent`, `quote_followup_d3`, `quote_followup_d7`, `quote_followup_d14` | Don't exist. `proforma_invoice` covers the **send** but not the **followups**. |
| **Trade show "great meeting you"** | Trade-show Follow-up | email | `tradeshow_great_to_meet`, `tradeshow_brochure` | Don't exist. |
| **Order delivered → review request (T+28)** | Order completion review | email | `order_review_request_d28` | `order_delivered_feedback` is T+0 of delivery; we want T+28 review-ask. |
| **Re-engagement T+90 / T+180** | Re-engage Cold Lead deeper | email | `winback_90d`, `winback_180d` | `winback_60d_silent` exists; need follow-ons. |
| **Brochure delivery email** | Trade-show Follow-up step 1 | email | `brochure_delivery` | A version of `operational_update` could be hand-rolled for now, but the flow editor wants a stable slug. |

The plan **does not** require all gaps to be filled in 7.7. We ship Sample Dispatch first (only one new email template + one new WA template needed), then iterate.

---

## Section 3 — Schema (delta against current `models.py`)

### 3.1 Goals

- Per-contact state ("contact X is on step 2 of Sample Dispatch, next fire at T").
- Idempotent re-firing (scheduler restart never double-sends).
- Auditable per-step send history.
- Re-use existing tables/columns; only add what's missing.

### 3.1.1 What's already shipped

A previous merge already landed most of the Phase 7.7 schema. As of the current `main` (`hf_dashboard/services/models.py:209-307`):

- **`Flow` extensions present:** `slug` (line 216, indexed but not yet UNIQUE), `trigger_type` (line 223, default `manual`), `trigger_config` (line 224), `updated_at` (line 226), and `Index("flows_trigger_idx", "trigger_type", "is_active")` (line 229).
- **`FlowMembership` table present** (line 255) with all proposed columns including a dedicated `consecutive_failures` integer column (line 272). The Python attribute `metadata_json` is mapped to SQL column `"metadata"` (line 270) to dodge SQLAlchemy's reserved `metadata` attr — engine code must use `.metadata_json`, not `.metadata`.
- **`FlowStepRun` table present** (line 285) with `idempotency_key` declared `unique=True` on the column. Actual key format per the existing comment is `flowmem_<membership_id>_step_<step_index>_<channel>` (note the trailing channel suffix — multi-channel steps need it).
- **`FlowRun` (legacy)** is preserved (line 235) for the v1 cohort reads.

### 3.1.2 What's actually left to do on schema

| Item | Status | Notes |
|---|---|---|
| `flows.slug` UNIQUE | **Missing** — column is indexed but not UNIQUE | Add a uniqueness migration; backfill `slug = lower(replace(name, ' ', '_'))` for any pre-existing rows in `_seed_default_flows` (services/database.py:364). |
| `fm_contact_flow_uniq` partial unique index on `(contact_id, flow_id) WHERE status IN ('active', 'waiting_event', 'paused')` | **Missing** — only `fm_due_idx`, `fm_contact_active_idx`, `fm_flow_status_idx` exist | The strongest defence against duplicate enrollment. Without it, §4.5's idempotency claim degrades to an app-level race-prone check. **Add this; it's the only structural schema gap left.** Postgres: partial index. SQLite (local dev): falls back to a pre-insert query. |
| Lifecycle stage additions | **Do NOT add** | See §9.6 — keep canonical 5; use tags for granularity. The previous draft of this plan proposed `sample_requested`/`sample_shipped`/`sample_received` lifecycles; that's reverted in §4.2. |

### 3.2 `flows` table (current state)

```
flows
  id              INTEGER PRIMARY KEY                  -- existing
  name            VARCHAR(255)                         -- existing
  slug            VARCHAR(64), indexed, NOT YET UNIQUE -- column exists; UNIQUE migration pending
  description     TEXT                                 -- existing
  channel         VARCHAR(32) DEFAULT 'email'          -- valid values {email, whatsapp, multi}
  steps           JSON                                 -- shape per §3.3
  is_active       BOOLEAN DEFAULT true                 -- existing
  trigger_type    VARCHAR(32) NOT NULL DEFAULT 'manual' -- existing
  trigger_config  JSON DEFAULT {}                      -- existing
  created_at      TIMESTAMP                            -- existing
  updated_at      TIMESTAMP                            -- existing
```

**Indexes already present:**
- `flows_trigger_idx` on `(trigger_type, is_active)`.

**One pending migration (see 3.1.2):**
- Add UNIQUE constraint on `(slug)`. Backfill any null slugs in `_seed_default_flows` first.

### 3.3 Step shape (lives inside `flows.steps` JSON; not a separate table)

**Decision: keep steps as JSON inside `flows.steps`.** Rationale: steps are always loaded with the parent flow, and a flow rarely has more than ~10 steps. A separate `flow_steps` table would complicate the editor and add a join on every fire. The existing engine already uses this shape.

New step JSON schema (keys are forward-compatible with v1's `{day, template_slug, subject}`):

```json
{
  "step_index": 0,
  "channel": "email",                       // email | whatsapp | both
  "template_slug": "sample_request_received", // for email
  "subject_override": null,                 // optional; falls back to template's subject_template
  "wa_template": null,                      // for WA
  "wa_variables": [],                       // ["{{first_name}}", "{{tracking_id}}", ...]
  "wa_template_lang": "en",
  "delay_after_prev": {"value": 0, "unit": "days"},  // 0 = immediate; supports days, hours, minutes
  "trigger_event": null,                    // optional: {type: "lifecycle", value: "sample_shipped"} — fire on event, not timer
  "conditions": [                           // ALL must pass; otherwise skip + advance
    {"field": "email", "op": "exists"},
    {"field": "consent_status", "op": "in", "values": ["opted_in", "pending"]}
  ],
  "vars_template": {"fibre_sent": "{{tags_first_matching:hemp,nettle,wool}}"}  // computed at fire time
}
```

**`delay_after_prev`** is relative to the previous step's actual fire time (or to membership start for step 0). This avoids absolute "day N" arithmetic that breaks if a step gets paused.

**`trigger_event`** is the killer for Sample Dispatch step 1: instead of "T+ship-event" being a timer, the step holds at status `waiting_event` until a `tag_added:samples_shipped` interaction is logged for that contact (per §4.2 / §9.6, granular state is tag-based, not lifecycle), then fires immediately. Falls back to a configurable `max_wait` to auto-skip after e.g. 30 days.

### 3.4 Table 2 — `flow_memberships` (already in `models.py:255`)

```
flow_memberships  (existing — engine code uses .metadata_json, NOT .metadata,
                   because SQLAlchemy reserves the `metadata` attr name)
  id                    INTEGER PRIMARY KEY AUTOINCREMENT
  flow_id               INTEGER NOT NULL  FK flows(id) ON DELETE CASCADE
  contact_id            VARCHAR(64) NOT NULL  FK contacts(id) ON DELETE CASCADE
  status                VARCHAR(32) NOT NULL DEFAULT 'active'
                        -- active | waiting_event | paused | completed | failed | stopped
  current_step_index    INTEGER NOT NULL DEFAULT 0
  started_at            TIMESTAMP NOT NULL DEFAULT now()
  last_step_at          TIMESTAMP
  next_fire_at          TIMESTAMP, indexed
  trigger_source        VARCHAR(32) NOT NULL DEFAULT 'manual'
  trigger_actor         VARCHAR(64) DEFAULT ''
  trigger_payload       JSON DEFAULT {}
  metadata (col) /
   metadata_json (attr) JSON DEFAULT {}
  error                 TEXT DEFAULT ''
  consecutive_failures  INTEGER NOT NULL DEFAULT 0   -- already a column; do NOT shoehorn into metadata JSON
  created_at            TIMESTAMP NOT NULL
  updated_at            TIMESTAMP NOT NULL
```

**Indexes already present:**
- `fm_due_idx` on `(status, next_fire_at)` — the scheduler hot path.
- `fm_contact_active_idx` on `(contact_id, status)` — drawer "Active flows" tab.
- `fm_flow_status_idx` on `(flow_id, status)` — flow detail page membership counts.

**Index missing — add in 7.7:**
- `fm_contact_flow_uniq` UNIQUE on `(contact_id, flow_id)` WHERE `status IN ('active', 'waiting_event', 'paused')`. **Without this the §4.5 idempotency claim is just an app-level check that races under concurrent triggers.** Postgres: partial unique index. SQLite (local dev): a pre-insert SELECT under the same transaction (acceptable because dev loads are tiny; production is Postgres).

**Lifecycle:**
1. Trigger fires → row inserted with `status='active', current_step_index=0, next_fire_at=now()`.
2. Scheduler claims → fires step 0 → either advances `current_step_index=1, next_fire_at=now()+delay`, or sets `status='waiting_event'` if step 1 has a `trigger_event`.
3. On `waiting_event`: an event handler (lifecycle change, tag added) flips `status='active', next_fire_at=now()` for matching memberships.
4. After last step fires → `status='completed', next_fire_at=NULL`.
5. User can manually `status='stopped'` from drawer.

### 3.5 Table 3 — `flow_step_runs` (already in `models.py:285`)

```
flow_step_runs
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  membership_id   INTEGER NOT NULL  FK flow_memberships(id) ON DELETE CASCADE
  step_index      INTEGER NOT NULL
  channel         VARCHAR(16) NOT NULL              -- email | whatsapp
  fired_at        TIMESTAMP NOT NULL
  status          VARCHAR(16) NOT NULL              -- sent | failed | skipped
  message_ref     VARCHAR(128) DEFAULT ''           -- email_sends.id (str) or wa_messages.wa_message_id
  template_slug   VARCHAR(128) NOT NULL DEFAULT ''
  error           TEXT DEFAULT ''
  idempotency_key VARCHAR(96), UNIQUE on column
```

**Idempotency key format (per existing comment in `models.py:301`):**

```
flowmem_<membership_id>_step_<step_index>_<channel>
```

The trailing `_<channel>` segment is **required** for multi-channel steps where the same step_index has both an email and a WA send (e.g. Sample Dispatch step 0). Engine code building this key must include the channel; otherwise the second channel's insert would collide with the first.

**Indexes already present:**
- `fsr_membership_idx` on `(membership_id, step_index)` — drawer + flow detail audit reads.
- UNIQUE on `(idempotency_key)` (column-level) — the safety net against double-fire across scheduler restarts.

The idempotency key is the hard guarantee. Even if `tick_once()` runs twice in parallel (or a Space restart re-claims), only one `flow_step_runs` row inserts per (membership, step, channel); the second hits the unique constraint and the engine treats it as "already sent, advance".

### 3.6 Existing tables we will write to (read-only from the engine's POV today)

- `email_sends` — flow engine inserts a row per email step (already done in v1 `flows_engine._send_email_step`). Pass `idempotency_key = "flowmem_<membership_id>_step_<step_index>"` to dedupe across the existing constraint.
- `wa_messages` — flow engine logs outbound WA via `WhatsAppSender.send_template()` which already writes to `wa_messages`.
- `contact_interactions` — write `kind=flow_assigned`, `flow_step_sent`, `flow_completed`, `flow_stopped`. The contact drawer's Activity tab picks these up automatically (already wired through `services/interactions.py`).
- `contacts.last_email_sent_at`, `contacts.total_emails_sent`, `contacts.last_wa_outbound_at` — keep updating these from the flow engine like v1 already does.

### 3.7 What about the existing `flow_runs` table?

Two options. **Recommendation: leave it.** The scheduler doesn't touch it. The Phase 5.0 read API at `GET /api/v2/flows/{id}/runs` keeps returning rows from it for backward compatibility (legacy v1 batch flows). Phase 7's UI surfaces are membership-keyed, not run-keyed. We can deprecate `flow_runs` in a future cleanup.

---

## Section 4 — Trigger model

### 4.1 Trigger types (declared per-flow in `flows.trigger_type` + `flows.trigger_config`)

| Type | Config example | Where it fires from |
|---|---|---|
| `manual` | `{}` | "Add to flow" button (contact drawer) → `POST /api/v2/flows/{id}/memberships {contact_id}` |
| `lifecycle` | `{"to": "interested"}` or `{"to": ["interested", "customer"]}` | When `Contact.lifecycle` changes — see §4.2 |
| `tag` | `{"tag": "samples_requested"}` | When a tag is added to a contact — see §4.3 |
| `inbound_keyword` (v2) | `{"keyword": "sample"}` | WA inbound webhook regex match — out of scope for 7.7 |

### 4.2 Lifecycle trigger — wiring point

Today `POST /api/v2/contacts/{id}/lifecycle` (`api_v2/routers/contacts.py:391-444`) sets `c.lifecycle = body.lifecycle` (line 409), calls `log_interaction(... commit=False)` (line 414, with the `kind=lifecycle_<value>` interaction running through line 426), and commits at line 429 inside its own `try`.

**Wiring decision:** the trigger evaluator runs inline, between `log_interaction` (line 426) and `db.commit()` (line 429), in the same transaction. If `evaluate_lifecycle_trigger` fails, the lifecycle change rolls back too — flow-trigger consistency is more valuable than letting a partial state ship. The handler's existing `try/except HTTPException` already wraps the commit.

```
# pseudocode — between line 426 (log_interaction) and line 429 (db.commit)
from api_v2.services.flows_trigger import evaluate_lifecycle_trigger
evaluate_lifecycle_trigger(db, contact=c, old_lifecycle=old_lifecycle, new_lifecycle=body.lifecycle)
# db.commit() at line 429 commits both the lifecycle change and any new memberships atomically.
```

`evaluate_lifecycle_trigger()` queries `flows` where `trigger_type='lifecycle' AND is_active=true` and `trigger_config->>'to'` matches the new lifecycle (or the new value is in the configured list). For each match it inserts a `flow_memberships` row.

**Lifecycle stages stay at the canonical 5.** Per §9.6, we keep `new_lead | contacted | interested | customer | churned` and **do not add** `sample_requested`/`sample_shipped`/`sample_received`. Granular sample state lives in tags (`samples_requested`, `samples_shipped`, `samples_received`) — see §4.3. This means Sample Dispatch (§7.1) is a **tag trigger**, not a lifecycle trigger.

Lifecycle triggers remain useful for the canonical milestones — e.g. Order Lifecycle (§7.5) fires on `lifecycle=customer`, B2B Welcome (§7.2) on `lifecycle=new_lead AND customer_type=potential_b2b`.

### 4.3 Tag trigger — needs a new sliver

Today `tags` are written via `PATCH /api/v2/contacts/{id}` (`update_contact` at `api_v2/routers/contacts.py:551`); the handler writes a single `kind="manual_edit"` interaction at line 652 covering the entire patch. There is no dedicated tag-added API and `tag_added` interactions are listed as "future" in the docstring of `services/interactions.py:15`.

**Plan:**
1. In the PATCH handler, after the contact save and before the `manual_edit` log, diff `before.tags` vs `after.tags`. For each newly-added tag:
   - Write `kind=tag_added` interaction (separate row per tag).
   - Call `evaluate_tag_trigger(db, contact_id, tag_name)` inline.
2. `evaluate_tag_trigger` queries `flows` where `trigger_type='tag' AND trigger_config->>'tag' = ?` and creates memberships, in the same transaction as the PATCH.

**Behavior change to call out in the PR:** the contact's Activity tab will now show one `tag_added` row per tag plus the existing `manual_edit` row, where today it shows only the `manual_edit`. This is intentional (it's how tag-trigger flows surface their cause in the audit trail) but operators will see the change, so document it in the 7.7 release notes.

### 4.4 Manual trigger — drawer action

`POST /api/v2/flows/{flow_id}/memberships` body `{contact_id}` → inserts a `flow_memberships` row, returns the new membership. Validates that no active membership for `(flow_id, contact_id)` already exists.

`POST /api/v2/contacts/{contact_id}/flows/{flow_id}` is a friendlier alias for the contact-drawer button.

### 4.5 Trigger idempotency

The `fm_contact_flow_uniq` partial index (§3.4) means the same contact can only have ONE active membership in a given flow. If a lifecycle change toggles back-and-forth, the second insert is a no-op (caught + ignored, log a debug line).

Re-entering a flow after completion is allowed — the index excludes `completed | stopped | failed`. So a contact who completed Sample Dispatch and later requests another sample triggers a fresh membership.

### 4.6 Trigger config in the editor

The flow editor (Phase 7.9) renders trigger config based on `trigger_type`:

- `lifecycle` → dropdown of lifecycle values (loaded from the contacts schema config).
- `tag` → autocomplete of existing tags (`/api/v2/contacts/tags`).
- `manual` → no config; only the "Add to flow" button surfaces.

---

## Section 5 — Worker / scheduler design

### 5.1 Recommendation: **extend the existing async loop. No Celery, no APScheduler dep.**

The reasons:
- `api_v2/services/scheduler.py` already runs an asyncio task in the FastAPI lifespan, hits the DB once a minute, uses `FOR UPDATE SKIP LOCKED` on Postgres, and is wired to a kill-switch (`HF_SCHEDULER_ENABLED`).
- HF Spaces is single-replica; there is no horizontal scale-out problem to solve.
- Adding Celery means a Redis dep, a worker process in the Dockerfile, and another env var. Not justified for the load (≪ 1000 contacts × ≪ 10 active flows = at most a few thousand active memberships).

### 5.2 Cadence

**Every 60 s** (same `_TICK_SECONDS` as today). At that cadence, even if 200 memberships fire in the same minute, the WA rate-limit (1 msg/sec — `broadcast_engine.py:464`) means the next batch finishes in ≤ 200 s, ahead of the next tick's competing claim. For email (`time.sleep(3)` per send), we can pace bursts better — see §5.6.

### 5.3 Tick algorithm (extension to `tick_once()`)

```
def tick_once_flows() -> dict:
    db = get_db()
    try:
        # 1. Claim due memberships atomically.
        now = utcnow()
        q = db.query(FlowMembership).filter(
            FlowMembership.status == "active",
            FlowMembership.next_fire_at <= now,
        )
        # Postgres: with_for_update(skip_locked=True). SQLite: BEGIN IMMEDIATE.
        rows = q.with_for_update(skip_locked=True).limit(20).all()  # see §5.6
        # Snapshot ids only — close session after claim.
        snaps = [{"membership_id": r.id, "flow_id": r.flow_id, ...} for r in rows]
        # Mark claimed (status stays 'active'; we use a `last_tick_claim_at` advance instead — see below).
        for r in rows:
            r.next_fire_at = None  # park them so a concurrent tick won't re-claim
        db.commit()
    finally:
        db.close()

    fired = 0
    for snap in snaps:
        try:
            _fire_membership_step(snap)   # opens its own session
            fired += 1
        except Exception:
            log.exception("flow membership %s failed", snap["membership_id"])
    return {"fired_flows": fired}
```

**Claim trick — null-out `next_fire_at` in the claim transaction.** This lets the existing `(status, next_fire_at)` filter exclude the claimed row from future claims while we work, with no new column. `_fire_membership_step` either:
- Sets `next_fire_at = now() + step.delay_after_prev` and `current_step_index += 1`, OR
- Sets `status='waiting_event'` (no `next_fire_at`), OR
- Sets `status='completed'` (no `next_fire_at`).

### 5.4 Computing `next_fire_at`

When step N fires successfully, look at step N+1's `delay_after_prev`:

```
if step_n_plus_1.trigger_event:
    next_fire_at = NULL
    status = 'waiting_event'
else:
    next_fire_at = now() + parse_duration(step_n_plus_1.delay_after_prev)
    status = 'active'
```

`parse_duration({"value": 7, "unit": "days"}) → timedelta(days=7)`. Units: `minutes | hours | days`. No cron expressions — keep it simple.

### 5.5 Idempotency

Three layers:

1. **Claim atomicity** — `FOR UPDATE SKIP LOCKED` (Postgres) or `BEGIN IMMEDIATE` serial transactions (SQLite). Two ticks never claim the same row.
2. **`flow_step_runs.idempotency_key` UNIQUE** — even if the claim fails and we re-fire, the unique constraint blocks the duplicate `flow_step_runs` insert. Same key blocks duplicate `email_sends` too (already used by v1's `generate_idempotency_key("flow_<run.id>", contact_id, step_index)` — we keep the convention but key by membership: `flowmem_<membership_id>_step_<step_index>`).
3. **Process-restart safety** — HF Space restart mid-fire: any membership whose `next_fire_at IS NULL` AND `status='active'` AND has no `flow_step_runs` row for the current step is a "stranded claim". A reaper at scheduler startup re-arms them: `UPDATE flow_memberships SET next_fire_at=now() WHERE status='active' AND next_fire_at IS NULL AND id NOT IN (SELECT membership_id FROM flow_step_runs WHERE step_index = current_step_index)`. Run once on lifespan start.

### 5.6 Burst handling — concrete numbers

The senders block:
- `EmailSender` does `time.sleep(3)` per send.
- `WhatsAppSender` enforces 1 msg/sec (per `broadcast_engine.py:317,464`).

A naïve `q.limit(100)` per tick can therefore block the loop for **5 minutes** of email or 100 s of WA — well past the 60 s tick interval. That's unacceptable for a scheduler that also handles broadcasts and campaigns in the same `tick_once()`.

**Hard limits adopted in 7.7:**

- `q.limit(20)` for flow memberships per tick. At 3 s/email this caps a worst-case all-email tick at ≈ 60 s, matching the cadence. Mixed channels finish well under that.
- **Fire each membership's send via `loop.run_in_executor(None, fire_step, snap)`.** The claim-and-update transaction stays in the main event loop; the blocking `time.sleep(...)` inside the senders runs on the threadpool. This is a one-line change in `tick_flows()` and means concurrent broadcast/campaign ticks aren't starved by a flow burst.
- **Backpressure via `next_fire_at`:** memberships not claimed this tick keep their existing `next_fire_at`, so they're naturally re-attempted on the next tick. No retry queue needed.

If real load ever justifies 100+ flow sends/min, the next step is moving sends out of the scheduler entirely (Redis + worker process). Out of scope for 7.7 — flagged in §9.2.

### 5.7 Failure handling

- Per-step send failure (e.g. WA template rejected, email bounced) → `flow_step_runs.status='failed', error=...`. Membership: increment a `consecutive_failures` counter (extend metadata JSON). After 3 consecutive failures on the same step, set membership `status='failed', error='3 consecutive step failures'`. UI shows red badge; user can manually retry.
- Template not found → `flow_step_runs.status='skipped', error='template_missing'`, advance to next step. (Don't block the whole flow on a missing template.)
- Trigger evaluator failure → log, don't block the original write. Triggers are best-effort; the user can manually add the contact to the flow if they notice it's missing.

### 5.8 Alerting

`Sentry` is already integrated (`api_v2/main.py:97`). Capture-message on `status='failed'` flips so the operator sees flow regressions in the same dashboard as everything else. No new alerting infra.

---

## Section 6 — UI surfaces

### 6.1 `/flows` (list page) — extend existing

`vite_dashboard/src/pages/flows/FlowsPage.tsx` + `components/FlowsTable.tsx`.

**Existing columns:** Status, Name, Channel, Steps, Created.

**Add columns:**

| Column | Source | Notes |
|---|---|---|
| Trigger | `flow.trigger_type` + summary of `trigger_config` | Pill: "Manual" / "Lifecycle: customer" / "Tag: samples_requested" |
| Active members | `COUNT(flow_memberships) WHERE flow_id=? AND status='active'` | Loaded by extending `FlowsResponse` to include `active_count`. |
| Completed last 30d | `COUNT(flow_memberships) WHERE status='completed' AND last_step_at > now()-30d` | Optional — useful trend signal. |

**New row action:** click row navigates to `/flows/:id` (detail page, §6.2). Today click opens an inline runs panel — replace.

**New page action:** "+ New flow" button (top right) → opens `FlowEditorDrawer` (§6.4). Phase 7.9 work; in 7.7 Sample Dispatch is hard-coded via a seed.

### 6.2 `/flows/:id` (flow detail page — NEW)

New file: `vite_dashboard/src/pages/flows/FlowDetailPage.tsx`.

**Layout (left/right split, matches the rest of the dashboard):**

```
+--------------------+--------------------------------------------+
| Flow card          | Tabs: Steps | Members | Step Runs          |
| - name             |--------------------------------------------|
| - description      | (Members tab default)                      |
| - trigger summary  |                                            |
| - is_active toggle | DataTable<FlowMembership>:                 |
| - "Edit" button    |   - Contact (name + email)                 |
| - "Test send"      |   - Status pill                            |
|--------------------|   - Current step                           |
| KPI cards          |   - Next fire                              |
| - Active: 12       |   - Started                                |
| - Completed: 47    |   - Actions: Pause / Resume / Stop         |
| - Failed: 1        |                                            |
+--------------------+--------------------------------------------+
```

**Steps tab** — readable view of the steps array; for 7.9 this becomes editable (drag to reorder, edit delays, pick template).

**Step Runs tab** — flat audit log: `flow_step_runs` for this flow, last 200 rows, filterable by status. Useful when a step fails and the user wants "show me all failures last week".

### 6.3 Contact drawer "Flows" tab — NEW

`vite_dashboard/src/pages/contacts/components/ContactDrawer.tsx` (or wherever the drawer tabs live). Add a tab `Flows`.

**Sections inside the tab:**

1. **Active flows** — for each membership where `status IN ('active', 'waiting_event', 'paused')`:
   - Flow name
   - Step progress bar: "Step 2 of 4 — Sample shipped"
   - Next fire timestamp (or "Waiting for sample_shipped event")
   - "Stop flow" button → `POST /api/v2/flow-memberships/{id}/stop`
2. **Past flows** (collapsed by default) — completed/stopped memberships, with completion date + summary "3/3 steps sent, 0 failed".
3. **Add to flow** dropdown + button — lists `flows WHERE is_active AND trigger_type='manual'` (manual + tag + lifecycle flows can also be force-added). On click: `POST /api/v2/contacts/{contact_id}/flows/{flow_id}`.

### 6.4 Flow editor drawer — Phase 7.9

`vite_dashboard/src/pages/flows/components/FlowEditorDrawer.tsx`. Linear steps editor (no graph). Each step row:

- Channel toggle (email | wa)
- Template picker (calls `/api/v2/email-templates` or WA templates list)
- Delay input ("0 days" / "2 hours" / "7 days")
- Conditions chips ("only if email exists", "only if opted_in")
- "Send on event" mode toggle → swaps the delay control for an event picker

CRUD via `POST /api/v2/flows`, `PATCH /api/v2/flows/{id}`, `DELETE /api/v2/flows/{id}`. The `steps` JSON validates against a Pydantic schema (`api_v2/schemas/flows.py:FlowStep`) before save.

### 6.5 Contacts page — "Active flow" column (NEW)

`vite_dashboard/src/pages/contacts/components/ContactsTable.tsx`. New column "Flow", showing the latest `active`/`waiting_event` membership per contact ("Sample Dispatch · step 2/4").

**Query strategy — do NOT inline into the contacts list endpoint.** A correlated subquery on a paginated list of 5000+ contacts is a hot-path performance hazard. Instead:

1. Contacts list endpoint stays as-is.
2. New endpoint `GET /api/v2/contacts/active-flows?ids=<csv>` returns `{contact_id: {flow_name, current_step_index, total_steps, status}}` for the (≤ 50) contact IDs visible on the current page.
3. Frontend issues this lookup in parallel with the contacts list (separate React Query hook, keyed on the visible page's IDs). The cell renders a skeleton while it resolves.

This keeps the contacts list query simple and bounds the active-flow lookup to one indexed scan over `fm_contact_active_idx` for the visible page only.

### 6.6 Page config (`vite_dashboard/src/config/pages/flows.yml`)

Update `landed_phase: 7.7` and rewrite `how_to_use` to describe the new model. The current copy is Phase 5.0 read-only; replace with sample-dispatch walkthrough.

---

## Section 7 — Proposed flow catalog

### 7.1 Sample Dispatch (the user's example) — **PRIMARY**

| Field | Value |
|---|---|
| Slug | `sample_dispatch` |
| Trigger | `tag` → `tag=samples_requested` (granular state in tags, not lifecycle — see §4.2 / §9.6) |
| Channel | multi |
| Value | **High** — directly asked for |

**Steps:**

| # | Channel | Template | Delay | Conditions | Notes |
|---|---|---|---|---|---|
| 0 | email | `sample_request_received` (**GAP — author**) | 0 (immediate) | email exists, consent in (opted_in, pending) | "We've received your request, samples being prepared" |
| 0 | whatsapp | `sample_request_received` (**GAP — submit to Meta**) | 0 | wa_id exists, wa_consent_status != opted_out | UTILITY category so 24h-window-safe |
| 1 | email | `sample_shipped` (**GAP — author**) | event: `tag_added:samples_shipped` (max wait 30d) | email exists | Sample-specific copy; vars from `flow_memberships.metadata_json.tracking_id`, `.courier_name`. Do NOT re-purpose `order_shipped.html`. |
| 1 | whatsapp | `sample_shipped` (**EXISTS in `new_templates.yml` — confirm Meta approval status via `WATemplate` row**) | event: `tag_added:samples_shipped` | wa_id exists | |
| 2 | email | `post_sample_followup` (**EXISTS on disk — needs seeding to DB**) | 7 days after step 1 | email exists | "Did the samples reach you?" — the user's T+7d follow-up |

**Step-1 trigger event:** the membership parks at `status='waiting_event'` after step 0. When operators tag the contact `samples_shipped` (via the drawer "Mark sample shipped" action — see below), the tag-trigger evaluator flips matching memberships back to `status='active', next_fire_at=now()`.

**How step 1 gets the `tracking_id`:** new "Mark sample shipped" button on the contact drawer. It takes `tracking_id` + `courier_name` as inputs, then in one transaction:
1. Adds tag `samples_shipped` (which fires the tag trigger and resumes any waiting Sample Dispatch membership for this contact).
2. Writes `tracking_id` + `courier_name` into `flow_memberships.metadata_json` for those memberships (engine reads from there at fire time).

This is option (b) from the previous draft — chosen because the inputs are explicit and the operator's intent is unambiguous. Option (a) (extending the lifecycle endpoint with `tracking_id`) is rejected because we don't want lifecycle changes to carry transactional payload.

**Template-gap accounting:** Sample Dispatch needs **two new email templates** (`sample_request_received`, `sample_shipped`) plus **one new approved WA template** (`sample_request_received` UTILITY). `sample_shipped` WA already exists in `new_templates.yml`; verify approval before Sample Dispatch is enabled.

### 7.2 New B2B Lead Welcome

| Field | Value |
|---|---|
| Slug | `b2b_welcome` |
| Trigger | `lifecycle` → `to=new_lead` AND `customer_type=potential_b2b` (compound condition, `trigger_config={"lifecycle": "new_lead", "customer_type": ["potential_b2b"]}`) |
| Channel | multi |
| Value | **High** |

**Steps:**

| # | Channel | Template | Delay | Notes |
|---|---|---|---|---|
| 0 | whatsapp | `welcome_message` (EXISTS) | 0 | Immediate, has wa_id |
| 1 | email | `welcome` (EXISTS) | 1 day | |
| 2 | email | `welcome_day_3_sustainability` (EXISTS — needs seeding) | 2 days | |
| 3 | email | `onboarding_day_14_first_order` (EXISTS — needs seeding) | 11 days | |

### 7.3 Sample Follow-up (deeper checkin)

| Field | Value |
|---|---|
| Slug | `sample_followup_long` |
| Trigger | `lifecycle` → `to=sample_received` (need to add lifecycle) |
| Channel | email |
| Value | **Medium** |

**Steps:**

| # | Template | Delay | Notes |
|---|---|---|---|
| 0 | `post_sample_followup` (EXISTS) | 7 days | |
| 1 | `sample_followup_d14` (**GAP**) | 7 days | "Two weeks in — what's the verdict?" |
| 2 | `sample_followup_d30` (**GAP**) | 16 days | "One last check-in" |

### 7.4 Re-engage Cold Leads

| Field | Value |
|---|---|
| Slug | `winback` |
| Trigger | `tag` → `tag=cold_60d` (set by a future cron job that tags contacts with `last_email_opened_at` or `last_wa_inbound_at` older than 60d) |
| Channel | email |
| Value | **Medium** — depends on a tagger job; could ship with manual trigger first |

**Steps:**

| # | Template | Delay | Notes |
|---|---|---|---|
| 0 | `winback_60d_silent` (EXISTS — needs seeding) | 0 | |
| 1 | `winback_90d` (**GAP**) | 30 days | |
| 2 | `winback_180d` (**GAP**) | 90 days | "Last hello — happy to drop you from the list if you'd prefer" |

### 7.5 Order Lifecycle (post-purchase)

| Field | Value |
|---|---|
| Slug | `order_lifecycle` |
| Trigger | `lifecycle` → `to=customer` |
| Channel | multi |
| Value | **Medium** |

**Steps:**

| # | Channel | Template | Delay | Notes |
|---|---|---|---|---|
| 0 | email | `order_confirmation` (EXISTS) | 0 | |
| 0 | whatsapp | `order_confirmation` (EXISTS in registry) | 0 | |
| 1 | email | `order_shipped` (EXISTS) | event: `tag_added:order_shipped` | per §9.6, granular state lives in tags |
| 1 | whatsapp | `order_tracking` (EXISTS) | event: `tag_added:order_shipped` | |
| 2 | email | `order_delivered_feedback` (EXISTS) | event: `tag_added:order_delivered` | |
| 3 | email | `order_review_request_d28` (**GAP**) | 28 days after step 2 | |

### 7.6 Quote Follow-up

| Field | Value |
|---|---|
| Slug | `quote_followup` |
| Trigger | `tag` → `tag=quoted` |
| Channel | email |
| Value | **Medium-high** |

**Steps:**

| # | Template | Delay | Notes |
|---|---|---|---|
| 0 | `proforma_invoice` (EXISTS) | 0 | Sends the quote (or marks it sent) |
| 1 | `quote_followup_d3` (**GAP**) | 3 days | "Any questions on the quote?" |
| 2 | `quote_followup_d7` (**GAP**) | 4 days | "Bumping this up" |
| 3 | `quote_followup_d14` (**GAP**) | 7 days | "Last gentle nudge — different fibre / smaller MOQ?" |

### 7.7 Trade-show Follow-up

| Field | Value |
|---|---|
| Slug | `tradeshow_followup` |
| Trigger | `tag` → `tag=tradeshow_<event_name>` (e.g. `tradeshow_techtextil_2026`) |
| Channel | email |
| Value | **Low-medium** — depends on cadence of trade shows |

**Steps:**

| # | Template | Delay | Notes |
|---|---|---|---|
| 0 | `tradeshow_great_to_meet` (**GAP**) | 0 | "Great meeting you at {{ tradeshow_name }}" |
| 1 | `brochure_delivery` (**GAP**) | 1 day | with PDF attachment via `EmailAttachment` (already supported) |
| 2 | `quote_followup_d14` (**GAP** — reused) | 14 days | |

### 7.8 Catalog summary

| Flow | New email templates needed | New WA templates needed | Time to ship if templates exist |
|---|---|---|---|
| Sample Dispatch | `sample_request_received`, `sample_shipped` | `sample_request_received` (Meta approval) | High value, blocked on two new email templates + WA approval |
| B2B Welcome | (seed `welcome_day_3_sustainability`, `onboarding_day_14_first_order`) | — | Days |
| Sample Follow-up Long | `sample_followup_d14`, `sample_followup_d30` | — | Days |
| Re-engage | `winback_90d`, `winback_180d` (seed `winback_60d_silent`) | — | Days |
| Order Lifecycle | `order_review_request_d28` | — | Days |
| Quote Follow-up | `quote_followup_d3`, `_d7`, `_d14` | — | Week |
| Trade-show | `tradeshow_great_to_meet`, `brochure_delivery` | — | Week |

---

## Section 8 — Phasing

### Phase 7.7 — Foundation (1 PR; 3-5 days)

Goal: Sample Dispatch runs end-to-end on tag change. Most of the schema is already on `main` (see §3.1.1); 7.7 is "finish the wiring + small migration + author templates".

1. **Schema migration** (`scripts/migrations/2026_05_XX_finish_flow_schema.py`):
   - Add UNIQUE constraint on `flows.slug`. Backfill any null slugs for the 3 rows in `_seed_default_flows` (`services/database.py:364`) before the constraint goes on.
   - Add the partial unique index `fm_contact_flow_uniq` on `flow_memberships(contact_id, flow_id) WHERE status IN ('active', 'waiting_event', 'paused')` — the only structural schema gap left (§3.1.2).
   - **No lifecycle stage additions.** Per §4.2/§9.6, granular sample state lives in tags.
   - **No new tables.** `flow_memberships` and `flow_step_runs` are already in `models.py`; `ensure_db_ready` will create them on first boot of any DB that doesn't have them yet.
2. **Author missing templates:**
   - Email: `sample_request_received.html` + `.meta.yml` and `sample_shipped.html` + `.meta.yml` in `hf_dashboard/templates/emails/` and `hf_dashboard/config/email/templates_seed/` (two new templates — see §7.1 gap accounting).
   - WA: add `sample_request_received` (UTILITY) to `config/whatsapp/new_templates.yml`; submit via `scripts/submit_wa_templates.py` for Meta approval. Verify `sample_shipped` WA template's approval status before flow goes live.
   - Seed `post_sample_followup`, `welcome_day_3_sustainability`, `onboarding_day_14_first_order`, `winback_60d_silent` by writing `.meta.yml` files (HTML files already exist on disk per §2.2).
3. **Engine** (`api_v2/services/flows_engine_v2.py` — keep `hf_dashboard/services/flows_engine.py` v1 untouched for legacy `flow_runs` reads):
   - `assign_flow(db, flow_id, contact_id, trigger_source, payload)` → inserts membership; relies on the new partial unique index to swallow duplicate-active-membership inserts.
   - `tick_flows(db)` → claims due memberships (limit 20 per §5.6), fires steps in `run_in_executor`, advances or completes.
   - `fire_step(membership, flow, step)` → email path uses `EmailSender.render_template_by_slug` + `EmailSend` write; WA path uses `WhatsAppSender.send_template`. Idempotency key format per §3.5: `flowmem_<membership_id>_step_<step_index>_<channel>`. Engine code uses `membership.metadata_json` (NOT `.metadata` — see §3.4).
   - `evaluate_lifecycle_trigger(db, contact, old, new)` and `evaluate_tag_trigger(db, contact_id, tag_name)` helpers.
4. **Wire scheduler:** add `tick_flows()` call inside `api_v2/services/scheduler.py:tick_once()` (line 147) after the existing broadcast/campaign claims.
5. **Wire trigger evaluators (per §9.5):**
   - From `api_v2/routers/contacts.py:set_contact_lifecycle` — between `log_interaction` (line 414/426) and `db.commit()` (line 429).
   - From `update_contact` (line 551) — diff `before.tags` vs `after.tags`, write per-tag `tag_added` interactions, call `evaluate_tag_trigger` per new tag.
   - **Do NOT** wire into `POST /contacts` (line 510) or any bulk-import path.
6. **Seed Sample Dispatch flow** in `_seed_default_flows` (`services/database.py:364`). Trigger config: `{"trigger_type": "tag", "trigger_config": {"tag": "samples_requested"}}`.
7. **"Mark sample shipped" drawer action** (per §7.1): one drawer button + endpoint that adds tag `samples_shipped` and writes `tracking_id`/`courier_name` into `flow_memberships.metadata_json` for matching active memberships, atomically.
8. **API additions:**
   - `POST /api/v2/flows/{flow_id}/memberships` body `{contact_id}` (manual assign).
   - `POST /api/v2/flow-memberships/{id}/stop`.
   - `GET /api/v2/contacts/{id}/flow-memberships` (drawer's Flows tab data).
   - `GET /api/v2/flows/{id}/memberships` (flow detail page).
9. **Tests:**
   - Unit: `evaluate_tag_trigger` creates membership; double-call is blocked by `fm_contact_flow_uniq`; `tick_flows` advances state machine; idempotency key blocks double-fire across all channels of a multi-channel step.
   - Integration: tag added → membership created → tick fires step 0 (email + WA) → assert two `flow_step_runs` rows with distinct idempotency keys, one `email_sends` row, one `wa_messages` row, one `flow_assigned` interaction.
   - Property: random scheduler restart in mid-fire never produces duplicate sends.

### Phase 7.8 — UI for visibility (1 PR; 3-5 days)

1. Contact drawer "Flows" tab + Active flow column on Contacts table.
2. Flow detail page (`/flows/:id`) with Members + Step Runs tabs.
3. Manual "Add to flow" button.
4. Update `flows.yml` page config + `HowToUse` copy.
5. Tests: Playwright walkthrough — change lifecycle in drawer → see membership appear in Flows tab → see flow detail page reflect the new member.

### Phase 7.9 — Flow editor (1 PR; 5-7 days)

1. CRUD endpoints: `POST/PATCH/DELETE /api/v2/flows`.
2. Pydantic step-shape validation in `api_v2/schemas/flows.py` (define `FlowStep`, `FlowStepCondition`, `FlowTriggerConfig`).
3. `FlowEditorDrawer` with linear step list, drag-to-reorder, template picker, delay/event toggle, condition chips.
4. Test-send button: fires the flow against a single contact (creates a membership tagged `metadata={"test": true}` so it doesn't pollute analytics).

### Phase 7.10 — Auto-tag triggers + bulk operations (1 PR; 3-5 days)

1. New cron-style tagger job: every hour, tag contacts as `cold_60d` if no engagement for 60d, etc. Can ship as another method in `api_v2/services/scheduler.py:tick_once()`.
2. Bulk-stop a flow ("stop all active members" button on flow detail).
3. Reaper for stranded memberships (§5.5 layer 3) baked into lifespan startup.
4. Sentry alerting on `status='failed'` rows.

---

## Section 9 — Risks / unknowns

### 9.1 HF Space restart mid-fire

**Risk:** scheduler claims a membership (sets `next_fire_at=NULL`), starts firing, the Space restarts mid-loop → membership is in "claimed but unfired" state forever.

**Mitigation:** the reaper in §5.5 layer 3, plus the `flow_step_runs.idempotency_key` UNIQUE that ensures even re-firing produces one effect.

### 9.2 WA rate-limit interactions

**Risk:** 60 memberships hit step 1 at the same minute, all WA-channel; the in-process `time.sleep(1)` between sends pegs the tick for 60+ s.

**Mitigation:** `q.limit(100)` per tick, plus consider eventually moving send-loops out of the tick task (background queue). For now, monitor and only act if real load demands.

### 9.3 24h-window invariant for WA

**Hard rule:** WA flow steps **must** use approved templates. `WhatsAppSender.send_template()` works outside the 24h window; `send_text()` does not. Plan-shape decision: **the flow editor's WA channel selector only lists `WATemplate` rows where `status='APPROVED'`**. Free-text WA messages cannot be a flow step. Document this in the editor's "How to use" copy.

### 9.4 Template gaps block flows

**Risk:** the operator wants a flow today but the template is in §2.4. Operator's only option is to add a template via the existing `/email-templates` UI or wait for engineering.

**Mitigation:** the flow editor is permissive — let operators reference any seeded slug. The plan documents the gaps explicitly so they can be authored independently of the engine work.

### 9.5 Trigger storm on data import

**Risk:** importing 5000 contacts with `lifecycle=new_lead` could create 5000 B2B Welcome memberships, then step 0 fires 5000 emails over many ticks (with the §5.6 limit of 20/tick that's ≈ 4 hours of catch-up sends, plus rate-limit risk).

**Mitigation — structural, not a flag:** **trigger evaluators are wired only into the dedicated mutator endpoints, not into bulk paths.**

| Mutator | Trigger evaluation? |
|---|---|
| `POST /api/v2/contacts/{id}/lifecycle` (line 391) | **Yes** — lifecycle trigger fires here |
| `PATCH /api/v2/contacts/{id}` (line 551) | **Yes, tag-diff only** — fires tag trigger when tags change |
| `POST /api/v2/contacts` (creation, line 510) | **No** — never fires triggers, even if body sets `lifecycle=new_lead` |
| `POST /api/v2/contacts/import` (bulk) | **No** — never fires triggers |

If an operator wants to enroll an imported cohort into a flow, that's an explicit "Add to flow" operation on the segment view — not an emergent side effect of import. This means the storm scenario is **structurally impossible** without a deliberate bulk-trigger UI step, which is out of scope for 7.7.

A future bulk-trigger feature would gate enrollment by a confirmation modal and write memberships with `next_fire_at = now() + jittered_delay` to spread the burst.

### 9.6 Lifecycle stages explosion (resolved)

**Decision (also reflected in §4.2):** keep the 5-stage canonical lifecycle (`new_lead`, `contacted`, `interested`, `customer`, `churned`) and use **tags** for granular sub-state — `samples_requested`, `samples_shipped`, `samples_received`, `quoted`, `order_shipped`, `order_delivered`, etc.

**Why:** lifecycle bloat (15+ values) creates mutually-exclusive nonsense ("a customer who requested new samples is `sample_requested` AND `customer`?"). Tags compose cleanly (`samples_shipped AND premium`), already exist in the schema (`config/dashboard/contacts/schema.yml:47-60`), and don't pollute the dropdown.

**Consequences for the flow catalog:**
- Sample Dispatch (§7.1): trigger is `tag: samples_requested`, step-1 wait event is `tag_added: samples_shipped`. Already updated.
- Order Lifecycle (§7.5): trigger is `lifecycle: customer` (canonical milestone); step-1 / step-2 waits use `tag_added: order_shipped` / `order_delivered` (§7.5 table updated to match).
- Re-engage (§7.4): already tag-triggered, no change.

### 9.7 Cohort-based legacy `flow_runs` confusion

**Risk:** `/api/v2/flows/{id}/runs` still returns the old cohort-row shape, which is unrelated to memberships.

**Mitigation:** keep the endpoint but mark it deprecated; the v2 UI surfaces only show memberships. After a release of stability, remove the endpoint.

---

## Section 10 — Out of scope

- Branching / if-else flows. Conditions are limited to per-step `skip-or-fire`. No "send A if X else send B".
- A/B testing (variants per step, statistical winner).
- Real-time websocket dashboard updates (the existing 30 s React Query stale window is fine).
- Drag-and-drop graph editor (Zapier-style canvas). Linear list only.
- Cron-expression scheduling (every Tuesday at 9 AM). Flows fire relative to membership start; absolute schedules belong on broadcasts.
- Cross-flow dependencies ("complete flow A before joining flow B").
- Inbound-keyword triggers (WA reply matches regex). Listed as future trigger type but not built.
- Per-step locale variants (use `template.language`-aware picking, not flow logic).
- Step preview / dry-run UI beyond the test-send button.
- Per-step rate-limit overrides. Rate is global in `EmailSender` / `WhatsAppSender`; flows inherit it.
- Horizontal scaling. The §5.3 claim trick assumes a single replica. Multi-replica needs a dedicated `claim_id` column or a Redis-based queue, both out of scope.
- Bulk-trigger UI (enroll a 5000-contact segment into a flow via one click). Today the only path is per-contact "Add to flow"; bulk is deliberately gated to prevent §9.5 storms.

---

## Critical Files for Implementation

- `/home/prashant-agrawal/projects/email_marketing/hf_dashboard/services/models.py` — add `FlowMembership`, `FlowStepRun`; extend `Flow` with `slug`, `trigger_type`, `trigger_config`, `updated_at`.
- `/home/prashant-agrawal/projects/email_marketing/api_v2/services/scheduler.py` — extend `tick_once()` with `tick_flows()` claim + fire loop.
- `/home/prashant-agrawal/projects/email_marketing/api_v2/routers/contacts.py` — wire `evaluate_lifecycle_trigger` into `set_contact_lifecycle` (between line 426 and line 429) and tag-diff in `update_contact` (line 551, before the `manual_edit` log at line 652).
- `/home/prashant-agrawal/projects/email_marketing/api_v2/routers/flows.py` + `/home/prashant-agrawal/projects/email_marketing/api_v2/schemas/flows.py` — add membership endpoints + step/trigger Pydantic models.
- `/home/prashant-agrawal/projects/email_marketing/vite_dashboard/src/pages/flows/FlowsPage.tsx` and `components/FlowsTable.tsx` — add trigger pill column, active-member count, navigation to `/flows/:id`. New sibling `FlowDetailPage.tsx`.
