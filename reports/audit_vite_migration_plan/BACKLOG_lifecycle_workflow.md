# Backlog — Lifecycle / follow-up workflow

**Added:** 2026-05-05
**Why this exists:** the v1 Gradio dashboard has the data model for tracking
contact replies / lifecycle moves (the `contact_interactions` table + `lifecycle`
column on `contacts`), but no UI to mark a contact as replied / interested /
converted, and no view of "who needs follow-up." Slice A (data simplification)
and Slice B1 (auto-log `email_sent` interactions on every campaign send) ship
in v1 *now*, populating the shared Supabase tables. The UI portion below is
deliberately deferred to v2 so we don't build throwaway Gradio code.

All three items below operate on data already in Supabase that v2 reads via
the existing v1 services (`services/database.py`, `services/interactions.py`,
`services/segments.py`). No DB schema changes required.

---

## B2 — Quick-action lifecycle buttons in the contact drawer

**Phase:** 1 (Contacts) — addition to the planned edit drawer commit
**v1 status:** intentionally not built (would be throwaway).
**Effort:** ~2 hrs end-to-end.

### Backend (`api_v2/routers/contacts.py`)

Add `POST /api/v2/contacts/{contact_id}/lifecycle`:

```python
class LifecycleUpdate(BaseModel):
    lifecycle: Literal["new_lead", "contacted", "interested", "customer", "churned"]
    note: str | None = None  # optional free-text reason

@router.post("/contacts/{contact_id}/lifecycle", response_model=ContactDetail)
async def set_lifecycle(contact_id: str, body: LifecycleUpdate, _auth: ...):
    with get_db() as db:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            raise HTTPException(404)
        old = contact.lifecycle
        contact.lifecycle = body.lifecycle
        log_interaction(
            db, contact_id=contact_id,
            kind=f"lifecycle_{body.lifecycle}",
            summary=f"{old} → {body.lifecycle}" + (f" — {body.note}" if body.note else ""),
            payload={"old": old, "new": body.lifecycle, "note": body.note},
            actor="user",
        )
        db.commit()
        return _build_contact_detail(db, contact)
```

### Frontend (`vite_dashboard/src/pages/contacts/components/ContactDrawer.tsx`)

Add a row of 4 buttons below the Profile tab header:

| Button | Sets lifecycle to | Use when |
|---|---|---|
| ✉️ Replied | `contacted` | Contact replied to a campaign (any reply, even a bounce-style "wrong person") |
| ⭐ Interested | `interested` | Reply expressed interest / asked for samples / asked questions |
| ✅ Converted | `customer` | Placed an order or signed |
| ❌ Not interested | `churned` | Explicit decline, unsubscribe, or "do not contact" |

Each click POSTs to the new endpoint, refetches contact detail, shows toast.

### Data flow this enables

`email_sent` interactions are now being written by v1 broadcasts (Slice B1).
Once these buttons exist:

1. Founder sends campaign from v1 → 50 contacts get `email_sent` rows
2. Replies arrive in Gmail → founder reads them → opens v2 contact drawer →
   clicks "Replied" or "Interested" → lifecycle bumps + interaction logged
3. The "Needs follow-up" filter (B3 below) surfaces all contacts in lifecycle
   `contacted` or `interested` so the founder knows where to spend attention next

---

## B3 — "Needs follow-up" filter chip on Contacts page

**Phase:** 1 (Contacts) — addition to `ContactsFilterBar.tsx`
**Effort:** ~30 min.

### Frontend

`vite_dashboard/src/pages/contacts/components/ContactsFilterBar.tsx` — add a
toggle chip "🔥 Needs follow-up" next to the existing Lifecycle dropdown.
When active, append `?lifecycle=contacted&lifecycle=interested` to the
contacts query.

### Backend

`GET /api/v2/contacts` already accepts `lifecycle` as a list query param
(see `api_v2/routers/contacts.py::list_contacts`). No backend change needed.

### Optional refinement

Sort the "Needs follow-up" results by *most recent `email_sent` interaction*
descending — surfaces the freshest sends first. Adds a join on
`contact_interactions` in the list query; defer until founder has used the
basic version for a week.

---

## C — "Send first N" control on Broadcasts page

**Phase:** 3 (Broadcasts)
**Effort:** ~1 hr (UI) + ~30 min (backend resolution change).

### Why

`api_v2/routers/contacts.py::list_contacts` already paginates. The Broadcast
page in v2 will reuse the same segment-resolution helpers from
`services/flows_engine.py`. Two small additions make batch sends ergonomic:

### UI additions to v2 Broadcasts page

- Number input: `Recipients: first [N]` (blank = all). Default placeholder = "all".
- Sort dropdown: `Country A→Z` / `Company A→Z` / `Recently added` / `Recently engaged`.
- Checkbox: `☐ Exclude already sent this template` — filters out anyone with an
  `email_sent` interaction whose `payload.template_slug` matches the chosen template.

### Backend addition

Either:
- Extend the existing segment resolution helper to accept `limit`, `sort`, and
  `exclude_template_slug` params; OR
- Resolve the segment to a list, then apply limit/sort/exclude in the broadcast
  router before kicking off the send.

The "exclude already sent" check is the killer feature — it makes batch
campaigns idempotent without requiring the user to maintain `batch_1` /
`batch_2` tags. The data is already there once Slice B1 lands in v1.

---

## Dependencies / sequencing

- **Slice A and B1 are v1 changes that ship now** — they don't block v2 work.
- **B2 + B3 land together** in Phase 1's edit-drawer commit (currently the
  "follow-up commit" mentioned in `api_v2/routers/contacts.py:6`).
- **C lands in Phase 3** when the Broadcasts page is built in v2.

No schema changes required for any of these — all data lives in tables that
exist today and that v1 is already populating.
