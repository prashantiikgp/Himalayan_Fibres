# Flows — operator guide (Phase 7.8)

A flow is an automated multi-step send sequence. Each contact moves
through the steps independently; you can pause, resume, or stop
their progress at any time, and certain steps wait for an action
from you (like marking a sample shipped) instead of running on a
timer.

This guide covers the three places you'll use flows in the
dashboard:

1. The **`/flows` list page** — see all flows + active member counts
2. The **`/flows/:id` detail page** — drill into one flow + manage
   every contact in it
3. The **contact drawer Flows tab** — see + control flows for one
   specific contact

---

## 1. Auto-enrolling a contact via tag (the fastest path)

The Sample Dispatch flow is auto-triggered when a contact gains the
`samples_requested` tag.

### Steps

1. Open the **Contacts** page → click any row → drawer opens.
2. Go to the **Tags** tab → add the tag `samples_requested` → Save.
3. Within 60 seconds the scheduler tick fires step 0:
   - Email **`sample_request_received`** sent
   - WhatsApp **`sample_request_received`** template sent
4. Go to the drawer's **Flows** tab → you'll now see one card:
   ```
   Sample Dispatch                              [WAITING EVENT]
   Step 2 of 3
   ▓▓░ progress
   Next: Waiting for samples_shipped event
   Started: just now
   [Mark sample shipped] [Pause] [Stop]
   ```
5. The membership now sits at `waiting_event`. **Step 1 will not
   fire on a timer** — it's waiting for you.

### Why the tag-trigger? Why not lifecycle?

Lifecycle is too coarse: a contact can be at `interested` and have
asked for samples multiple times. Tags compose cleanly — Sample
Dispatch fires off `samples_requested`, the resume happens off
`samples_shipped`, and a contact can re-enter the flow weeks later
just by re-applying the trigger tag.

---

## 2. Marking a sample shipped (resuming step 1)

When the physical sample ships, you tell the dashboard so step 1
fires with the real tracking info.

### Steps

1. Open the contact drawer → **Flows** tab.
2. Click **Mark sample shipped** on the Sample Dispatch card. The
   button expands inline:
   ```
   Mark sample shipped
     Tracking ID:  [BD123456789       ]
     Courier:      [BlueDart          ]
     [Cancel]                       [Mark shipped]
   ```
3. Fill both fields → **Mark shipped**.
4. Within 60 seconds:
   - Email **`sample_shipped`** sent — with your tracking ID rendered
     into the template
   - WhatsApp **`sample_shipped`** sent — same tracking values
   - Membership advances to step 2 with `next_fire_at = now + 7 days`
5. Seven days later, step 2 fires:
   - Email **`post_sample_followup`** ("How did it feel?")
   - Membership status flips to `completed`

### What if the tracking is wrong?

Stop the membership (see §4). Then re-tag `samples_shipped`
manually if you want step 1 to re-fire — but tag-trigger will only
resume an existing membership, so for a clean re-run:

1. Stop the existing membership.
2. Remove and re-add the `samples_requested` tag — this creates a
   fresh membership starting at step 0.

---

## 3. Manually enrolling a contact (no tag needed)

If a contact's situation doesn't fit the trigger conditions but you
still want them in a sequence:

1. Open the contact drawer → **Flows** tab.
2. Scroll to **Add to flow** at the bottom.
3. Pick a flow from the dropdown → click **Add**.
4. The contact starts at step 0 of that flow on the next tick.

The dropdown only shows **active** flows the contact is **not
already in**. If you don't see the flow you want, it may be inactive
(check the `/flows` page → uncheck "Active only" filter to see it).

---

## 4. Pause / Resume / Stop — operator controls

All three actions are available from two surfaces:
- The **drawer Flows tab** (per contact)
- The **`/flows/:id` Members tab** (per flow, per row)

### Pause
**Use when:** "Hold this contact while I figure something out."

- Click **Pause** → confirmation dialog → OK.
- Membership status flips to `paused`. The scheduler tick **skips
  paused rows** so no further sends fire.
- The pause is **reversible**.

### Resume
**Use when:** "Ready to continue."

- Only available on `paused` memberships.
- Click **Resume** → membership flips back to `active` with
  `next_fire_at = now`. The next tick claims it and fires the
  current step.
- No confirmation dialog (resume is positive, not destructive).

### Stop
**Use when:** "This contact is done with this flow, irreversibly."

- Click **Stop** → confirmation dialog → OK (red button).
- Membership status flips to `stopped`. **Terminal — no recovery.**
- Re-adding the trigger tag creates a fresh membership starting at
  step 0.

### When transitions are blocked

The backend rejects illegal transitions with a 409 error and an
inline message:

| You tried | But the membership is | Result |
|---|---|---|
| Pause | already `completed`/`failed`/`stopped` | "Membership is not in a state that allows this action." |
| Resume | not `paused` | "Membership is not in a state that allows this action." |
| Stop | already `stopped`/`completed`/`failed` | Idempotent — no-op |

---

## 5. Reading the `/flows` list page

The list shows all flows in the system. After Phase 7.8, columns
are:

| Column | What it shows |
|---|---|
| **Status** | Active or Inactive (toggle in code today; flow editor lands in Phase 7.9). |
| **Name** | Flow name + description. |
| **Trigger** | `Manual` / `Lifecycle: <stage>` / `Tag: <tag>` — explains how contacts enter the flow. |
| **Channel** | Email / WhatsApp / Multi (multi = both). |
| **Steps** | Step count. |
| **Active** | Live members (active + waiting + paused). |
| **Created** | Relative timestamp. |

Click any row → navigate to the detail page.

**Default filter is "Active only".** Three legacy seed flows from
before Phase 7.7 are now `is_active=False` and hidden by this
filter; uncheck it to see them. They were the v1 cohort flows;
operator-edits to them since are preserved (we only deactivate the
ones still using the original seed descriptions).

---

## 6. Reading the `/flows/:id` detail page

Three tabs, plus the header + KPI cards.

### Header
Flow name + trigger pill + channel pill + step count + (if
inactive) Inactive pill.

### KPI cards
- **Active** — running on a timer
- **Waiting event** — parked, needs an operator action
- **Completed** — finished naturally
- **Failed** — 3 consecutive step failures, manually retry needed

(Paused/Stopped counts are visible on the Members tab via the
status filter dropdown.)

### Tab 1: Members (default)

Per-contact rows in this flow. Status filter at top defaults to
**Active**. Each row shows:

- Contact name + email
- Status pill
- Step (`Step N of M`)
- Next fire (relative time, or `—` for parked / completed)
- Started (relative time)
- Actions: Pause / Resume / Stop (whichever apply to the status)

Clicking a row opens the contact drawer (planned — not yet wired in
7.8.2; use the Contacts page to drill in for now).

### Tab 2: Steps

Read-only render of the flow's step JSON. Each step card shows:
- Channel pill(s) — one per channel the step fires on
- Email template slug
- WA template slug
- "Waits for: <event>" — for event-gated steps (no timer)
- "Delay: N days (immediate)" — for timer-gated steps
- Conditions (e.g. `email exists`, `consent_status in (opted_in, pending)`)

The flow editor lands in Phase 7.9 — for now, edits require code
changes to `services/database.py:_seed_default_flows` (or the
Sample-Dispatch definition).

### Tab 3: Step Runs

Flat audit log: every send attempt across the flow, sorted newest
first, filterable by `sent` / `failed` / `skipped`. Useful when a
step fails and you want "show me all failures last week."

Each row: when it fired, step index, channel, template, status,
error (truncated; full text on hover).

---

## 7. Reading the drawer **Flows** tab (per contact)

Three sections:

### Active flows
One card per membership in `active`/`waiting_event`/`paused`. Each
card has:
- Flow name + trigger pill + status pill
- Step progress bar
- Next fire / "Waiting for X event"
- Started timestamp
- Mark sample shipped (only when applicable — Sample Dispatch in
  `waiting_event` for `samples_shipped`)
- Pause / Resume (which one shows depends on status)
- Stop

### Past flows (collapsed by default)
Click `▸ Past flows (N)` to expand. Each row: flow name + status
pill + ended timestamp.

### Add to flow
Dropdown listing every active flow the contact is **not** already
in. Pick one + click **Add**. Errors render inline (e.g. "Already
enrolled in this flow.").

---

## 8. Common workflows

### "I want to start sending samples to this lead"
1. Contact drawer → Tags → add `samples_requested`.
2. Step 0 fires within 60 s (thank-you email + WA).
3. Prepare physical sample.
4. Drawer → Flows tab → Mark sample shipped → fill tracking.
5. Step 1 fires. Step 2 follow-up at T+7d.

### "Samples aren't ready, hold this contact"
- Drawer → Flows tab → Pause on the Sample Dispatch card. Resume
  later.

### "We can't fulfill — kill this flow"
- Drawer → Flows tab → Stop on the Sample Dispatch card. Membership
  is terminal. Adding the `samples_requested` tag again starts a
  fresh membership at step 0.

### "I want to enrol a whole batch of contacts"
- Not yet supported in 7.8. Per-contact "Add to flow" only. Bulk
  enrollment lands in Phase 7.10 (with a deliberate confirmation
  step to avoid the 5000-contact send-storm risk).

### "I want to create a new flow"
- Not yet supported in 7.8. Flow editor lands in Phase 7.9. For now,
  add a definition to `services/database.py` and redeploy.

---

## 9. Troubleshooting

### "I tagged the contact but no email fired"
- The scheduler tick runs every 60 seconds. Wait a minute.
- Check the contact's **Activity** tab — you should see
  `tag_added`, then `flow_assigned`, then `flow_step_sent` rows.
- If you see `flow_assigned` but no `flow_step_sent`, check the
  `/flows/:id` Step Runs tab for the contact — step 0 may have
  been **skipped** (e.g. `consent_status=opted_out`) or **failed**
  (e.g. Gmail token expired).

### "The Mark sample shipped button isn't showing"
- The button only appears when:
  - The contact is in `sample_dispatch` flow
  - Status is `waiting_event`
  - The current step's `trigger_event.value` is `samples_shipped`
- Check the **Flows** tab card's status pill — if it says `ACTIVE`
  the membership is in a different state and the button isn't
  applicable yet.

### "I clicked Pause and got an error"
- 409 means the membership isn't in `active`/`waiting_event`. If
  it's already paused, ignore the error. If it's terminal
  (`completed`/`failed`/`stopped`), the operation isn't valid.

### "A flow is showing as Failed"
- The membership hit 3 consecutive step failures. Check the Step
  Runs tab for the failure reason. Common causes:
  - WA template was rejected by Meta — re-submit from
    `/wa-templates`
  - Gmail token expired — refresh the Space secrets
  - Template slug typo in the flow definition
- After fixing the underlying issue, you can manually re-enroll the
  contact (Tags tab + re-add the trigger tag).

### "My changes to a flow definition aren't showing up"
- Flow definitions are seeded once. The Phase 7.7 seeder (`seed_phase7_flows`) is
  idempotent — it only inserts new flows; it never overwrites.
- If you edited `SAMPLE_DISPATCH_FLOW_DEF` in code and want the
  changes live, you need to update the existing DB row directly:
  ```sql
  UPDATE flows
     SET steps = '<new JSON>'::jsonb
   WHERE slug = 'sample_dispatch';
  ```
  The Phase 7.9 flow editor will make this an in-app operation.

---

## 10. Glossary

- **Flow** — the definition (name, trigger, list of steps).
- **Membership** — one contact's instance of a flow. Has a status
  and a current step index.
- **Step** — one entry in `flow.steps`. Fires email / WA / both
  when its turn arrives.
- **Trigger** — what creates a membership. Today: tag, lifecycle,
  or manual.
- **Trigger event** — what un-parks a `waiting_event` membership.
  Today: tag added.
- **Tick** — the scheduler heartbeat. Every 60 s, the engine claims
  due memberships and fires their current step.
- **Idempotency key** — `flowmem_<membership>_step_<idx>_<channel>`.
  The DB UNIQUE constraint blocks double-sends across crashes /
  restarts.

---

*Phase 7.8 — Day 5 deliverable. The flow editor (7.9), bulk
operations (7.10), and auto-tag jobs (7.10) are the next
increments.*
