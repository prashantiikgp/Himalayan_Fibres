# Contacts v2 — Plan

**Owner:** Prashant · **Date:** 2026-04-13 · **Status:** Approved, ready to build

## Why

The Contacts page is cramped, the Add Contact form clutters the page, pagination
is broken, and there is no visible link between contact tags and broadcast
audiences. Targeting customers for outreach requires opening the DB directly.
We will fix this in two phases so Phase 1 ships UI polish fast and Phase 2 does
the deeper data-model work.

## Data model distinction (authoritative)

This is the cleanliness model we agreed on. Follow it exactly.

- **Tags** = raw labels on a contact. Free-form. Multi-valued. Stored on the
  `Contact` row. Example tags: `wool`, `premium`, `samples_sent`, `quoted`.
  There is no hierarchy. You can create new tags at any time.
- **Segments** = named, saved filters over tags + contact fields. Stored as
  their own first-class objects in the DB. A segment is a *rule*, not a column
  on the contact. Example: *"Premium wool buyers in India"* = rule
  `tags contains wool AND tags contains premium AND country = India`.
- The existing `contact.customer_type` column (Potential B2B, Existing Client,
  etc.) becomes a **system segment** — a built-in, non-editable segment that
  filters on `customer_type`. Users can create additional **user segments** on
  top of tags + fields without touching the column.
- Broadcasts target **segments**, never raw tags. This forces the user to name
  and save an audience before sending to it, which makes "who am I mailing?"
  answerable at send time.

---

## Phase 1 — UI polish (ship first)

Goal: make the Contacts page readable and the Add Contact flow non-disruptive.
No schema changes. No Broadcasts changes.

### 1.1 Layout split

- Remove the current top `gr.Row` that puts Search + buttons above *both*
  columns. Move them into the right (table) column only.
- Left column: Segment / Lifecycle / Country / Channel dropdowns + KPI cards.
  Nothing else. Narrow it: `scale=1, min_width=200`.
- Right column: table section. Widen it: `scale=4`.
- Top of the right column, in one row:
  `[Search (scale=2)] [+ Add Contact (scale=1)] [Import (scale=1)]`
  all aligned. Search is compact. Buttons use `size="md"` (bump from `sm`).

### 1.2 Table sizing

- Drop `max-height: 60vh` from `table_scroll()` for the Contacts page.
- Make the right column a flex container (`display: flex; flex-direction: column`)
  with the table taking `flex: 1`. The shared row height is driven by the left
  column's natural height (filters + KPIs), so no magic pixel numbers.
- Keep the table header sticky.
- Reset `page` to 0 whenever a filter or search term changes, so pagination
  state doesn't point past the new total.

### 1.3 Missing placeholder

- In `_build_table`, show the literal string `Missing` (muted `#64748b`) for:
  - empty `email`
  - synthetic placeholder emails (any email containing `@placeholder.local` or
    starting with `wa_`)
  - empty `phone`
  - empty `company`
- Do **not** fall back to the company name or any other field. A missing field
  reads `Missing`, full stop.

### 1.4 Real pagination

- Replace the static `Page 1 of N` label with a working control. MVP layout:
  `[‹ Prev]  Page [ 3 ] of 19  [Next ›]`
- Implement with actual `gr.Button` components and a `gr.Number` for the page
  input — not HTML `onclick`, which Gradio cannot forward to Python without a
  custom JS bridge.
- A hidden `gr.State(0)` holds the current page index; Prev/Next and the
  number input all write to it and trigger `_apply` with the new page.
- Show a range indicator on the left: `Showing 51–100 of 941`. Compute as
  `start = page * page_size + 1`, `end = min((page + 1) * page_size, total)`.
- Numbered page buttons (`1 2 3 … 19`) are a nice-to-have — ship Prev/Next
  first, add numbered buttons in a follow-up if the team wants them.

### 1.5 Add Contact as a real modal overlay

This *is* possible in Gradio — my earlier claim was wrong. Approach:

- Wrap the existing `add_panel` contents in a `gr.Column(visible=False,
  elem_classes=["hf-modal"])`. The class is set **once at construction time**
  and never toggled at runtime — we only flip `visible`. When visible is
  False, Gradio removes the column from the DOM entirely and the overlay
  disappears. This avoids any `gr.update(elem_classes=...)` quirks.
- Add CSS in `shared/theme_css.py`:
  ```css
  .hf-modal {
      position: fixed !important;
      inset: 0 !important;
      background: rgba(0,0,0,.55) !important;
      z-index: 9999 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      padding: 20px !important;
  }
  .hf-modal > .block, .hf-modal .form {
      background: #0f172a !important;
      border: 1px solid rgba(255,255,255,.1) !important;
      border-radius: 12px !important;
      padding: 20px !important;
      max-width: 560px !important;
      width: 100% !important;
      max-height: 85vh !important;
      overflow-y: auto !important;
  }
  ```
- Button handlers: `+ Add Contact` → `gr.update(visible=True)`;
  `Cancel` and successful `_save` → `gr.update(visible=False)`.
- Do the same pattern for the Import panel.
- Acceptance: clicking `+ Add Contact` opens a centered card over the page
  content with a dimmed backdrop; the table behind is still visible; the page
  does not scroll to the bottom.

### 1.6 Legend under the contacts table

Goal: when a user looks at the Contacts table, they should be able to answer
"what is a segment? what is a tag? what is a customer type?" without leaving
the page. Today none of this is explained anywhere in the UI.

- Render a collapsible legend as a single `gr.HTML` block **directly below**
  the table footer (before the Add Contact / Import panels).
- Use `<details><summary>Legend — Segments, Tags & Customer Types</summary>…`
  so it starts collapsed and doesn't eat vertical space. User clicks once to
  expand.
- Inside, three side-by-side columns (`display: flex; gap: 16px`):

  **Customer Types** — the fixed system values from `schema.yml.segments`
  (`Potential B2B`, `Existing Client`, `Yarn Store`, `Other`). Each rendered
  as its colored pill (reuse `badge()` helper) followed by a one-line
  description.
  > *"A contact's primary business relationship category. Set when the
  > contact is created and rarely changes."*

  **Segments** — one-line explanation:
  > *"Named saved filters over tags and fields. Broadcasts target segments,
  > not raw tags. In Phase 1 the system segments (same as Customer Types
  > above) are the only segments. In Phase 2 you'll be able to create your
  > own — e.g. 'Premium wool buyers in India'."*

  **Tags** — one-line explanation, then the predefined tag list from
  `schema.yml.tags.predefined` rendered as small pills:
  > *"Raw, free-form labels you attach to any contact. A contact can have
  > many tags. Custom tags are allowed. Predefined tags:"* `wool` `hemp`
  > `nettle` `yarn` `carpet` `silk` `premium` `samples_sent` `samples_received`
  > `quoted` `order_placed`.

- **Zero hardcoding.** The legend builder function
  (`_build_legend()` in `pages/contacts.py`) reads from
  `services/contact_schema.py` only — same source as the filter dropdowns.
- Phase 2 extension: once user segments exist, the Segments column of the
  legend lists them with their member counts, not just the system ones.

### Phase 1 acceptance checklist

- [ ] Search + Add + Import sit on one row above the table only.
- [ ] Left filter column is visibly narrower than before.
- [ ] Table columns have breathing room; no horizontal cramping at 1366px.
- [ ] Table fills vertical space to the bottom of the KPI cards.
- [ ] Every empty / synthetic field in the table reads `Missing`.
- [ ] Pagination row has working Prev / page numbers / Next.
- [ ] `+ Add Contact` opens a centered modal over a dim backdrop.
- [ ] Collapsible legend under the table explains Customer Types, Segments,
      and Tags, driven entirely from `schema.yml`.
- [ ] Filter / search changes reset pagination to page 0.
- [ ] Tested in a real browser on HF Spaces, not just local.

---

## Phase 2 — Segments, inline edit, broadcast linkage

Goal: make the Contacts table editable in place, turn segments into named saved
filters, and wire them into Broadcasts so targeting is obvious at send time.

### Pre-flight findings (2026-04-13)

Ran the pre-flight grep + reads before writing code. The plan below is a
revision of the original Phase 2 — **most of the data layer already exists**.

- `services/models.py` already has a `Segment` table with
  `id, name, description, rules (JSON), is_active, created_at`. No new table
  needed.
- `contacts.notes` column already exists on the Contact model. No migration
  needed.
- `contacts.tags` is already a JSON list column.
- `services/broadcast_engine.py::get_segment_contacts()` is an existing rule
  evaluator that handles `customer_type`, `customer_subtype`, `geography`.
- `data/segments.csv` seeds 8 segments at DB init time via
  `services/database.py::_seed_segments()`. All 8 use the flat-dict rule shape
  `{field: [values]}` ANDed across fields — simpler than the nested AND/OR
  grammar I originally proposed. **Adopt the existing shape.**
- `pages/broadcasts.py` already loads segments from the DB and has a whole
  audience-breakdown flow (`get_audience_breakdown`, `apply_filters`). Its
  segment picker is a `gr.Dropdown` populated from a helper — the integration
  is a *polish* job, not a rewrite.

**What the grammar is missing:** `tags`, `lifecycle`, `country`, and
`consent_status` — none of them are honoured by the current evaluator. We'll
extend it to cover those while keeping the existing flat-dict shape.

### Revised Phase 2 work items

- **2.1 Extend rule evaluator** (no schema changes). Add a new
  `services/segments.py` module that wraps `broadcast_engine.get_segment_contacts`
  and adds support for `tags`, `lifecycle`, `country`, `consent_status` rule
  keys. Export bulk helpers: `get_contact_segments_map(db)` and
  `count_segment_members(db, segment)`.
- **2.2 Tag inventory helper**. Add `get_all_tags_from_contacts(db)` that runs
  a single `SELECT DISTINCT` over the JSON tags column. No new table.
- **2.3 Segments column on the contacts table**. Precompute
  `{contact_id: [segment_ids]}` once per render (one query per segment),
  then look up per row. Render matching segments as pills (cap at 2 + `+N`).
  Column is added to `config/pages/contacts.yml`.
- **2.4 Inline edit drawer** (details in 2.5 below) — unchanged.
- **2.5 Segment manager** — unchanged but smaller in scope because the DB
  table already exists and seeding already works.
- **2.6 Broadcasts polish** — change the segment dropdown to show
  `{name} — {count} contacts` and add a 5-row sample preview. The rest of
  broadcasts.py stays as-is.

*Effort revised down*: Phase 2 now ≈ 2 sessions instead of 3–4, because the
data layer (table, migration, most of the evaluator) is already done.

### 2.1 DB schema changes

Add two new models in `hf_dashboard/services/models.py` (and an Alembic
migration under `alembic/versions/`).

```python
class Segment(Base):
    __tablename__ = "segments"
    id = Column(String, primary_key=True)         # slug, e.g. "premium-wool-in"
    name = Column(String, nullable=False)         # display name
    description = Column(String, nullable=True)
    kind = Column(String, nullable=False)         # "system" | "user"
    rule = Column(JSON, nullable=False)           # see rule schema below
    color = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

System segments (`potential_b2b`, `existing_client`, `yarn_store`, `other`) are
seeded on first run from `config/contacts/schema.yml`. Their `rule` is
`{"field": "customer_type", "op": "eq", "value": "<id>"}`. They are non-editable
in the UI but targetable like any other segment.

No changes to `Contact` table. Tags stay where they are.

### 2.2 Segment rule schema

A rule is a tree of conditions. Minimum viable grammar:

```json
{
  "op": "and",
  "conditions": [
    {"field": "tags", "op": "contains", "value": "wool"},
    {"field": "tags", "op": "contains", "value": "premium"},
    {"field": "country", "op": "eq", "value": "India"},
    {"field": "lifecycle", "op": "in", "value": ["interested", "customer"]}
  ]
}
```

Supported ops: `and`, `or`, `eq`, `neq`, `in`, `contains`, `not_contains`,
`is_null`, `is_not_null`. Fields: `tags`, `country`, `lifecycle`,
`customer_type`, `consent_status`, `company`.

Implement the evaluator as a pure function
`services/segments.py::build_query(db_session, rule) -> Query` that translates
the rule into a SQLAlchemy query. Write unit tests first — one per op.

### 2.3 Contacts table — show segment + tags clearly

- Add a `Segments` column showing pills for every segment the contact matches,
  capped at 2 pills + `+N`.
- **Performance:** do not evaluate rules row-by-row. Instead, before rendering
  a page, run one query per segment (`build_query(db, rule)`) to get its
  matching contact IDs, then build a dict
  `{contact_id: [segment_id, ...]}` and look up by ID when rendering cells.
  Cost is `O(segments)` SQL queries per render, not `O(contacts × segments)`.
- Cache this dict per request; invalidate on any segment create/edit/delete
  or contact edit.
- Keep the `Tags` column; improve wrap behavior so it doesn't truncate silently.

### 2.3a Tag inventory (how the tag picker is populated)

- **Source of truth for which tags exist** = the union of
  `schema.yml.tags.predefined` (seed values) and `SELECT DISTINCT unnest(tags)`
  over the `contacts.tags` JSON column (user-created tags).
- **No new `tags` table.** Creating a tag means typing it into the drawer
  picker and saving the contact — it exists because at least one contact has
  it. If the last contact with a tag is untagged, the tag naturally disappears
  from the picker. That is the intended behavior.
- SQLite JSON column handling: use `json_each()` in the DISTINCT query,
  wrapped in a helper `services/contact_schema.py::get_all_tags(db)`.

### 2.4 Inline edit drawer

- Clicking any table row opens a right-hand drawer (similar modal approach to
  Phase 1 but anchored right, width ~480px).
- Drawer has tabs:
  - **Profile** — edit name, email, phone, company, country, lifecycle.
  - **Tags & Segments** — multi-select tags (predefined + create-new), list of
    matching segments (read-only — segments are rules, not direct assignments).
  - **Notes** — free text, stored on the Contact row (`notes TEXT` — new column).
  - **Activity** — read-only timeline stub for Phase 2; fill later.
- Save writes back to DB and re-renders the table. Cancel discards.

### 2.5 Segment manager page (or modal)

- New entry in the left nav: **Segments** (or a `Manage segments…` button on
  the Contacts filter panel — decide during build).
- Lists all segments with: name, kind, member count (live), last updated.
- Create / edit / delete user segments. System segments are view-only.
- The editor is a rule builder: stack of condition rows with field / op / value
  pickers, AND/OR toggle at the top. Live preview of matching contacts.

### 2.6 Broadcasts integration

**Pre-flight (do this before writing any code for 2.6):** read
`hf_dashboard/pages/broadcasts.py` end-to-end and document the current segment
picker — what it binds to, what audience it computes, what it displays on
send. The design below assumes a straightforward replacement; if the current
picker is deeply coupled to `customer_type`, the migration plan may need a
compat shim.

- Replace the current segment picker in Broadcasts (`pages/broadcasts.py`) with
  a dropdown sourced from the `segments` table. Each option shows
  `{name} — {member_count} contacts`.
- On selection, show a preview card: member count, a sample of 5 contacts
  (name + company), and a `View all` link opening the drawer with the full list.
- The "who am I sending to?" question must be answerable without leaving
  the page.

### Phase 2 acceptance checklist

- [ ] `segments` table exists, migrated, seeded with system segments.
- [ ] `services/segments.py` evaluator handles all listed ops, unit-tested.
- [ ] Contacts table shows a Segments column with live-matched pills.
- [ ] Clicking a row opens a tabbed edit drawer; edits persist.
- [ ] Users can create a new tag from the drawer and it immediately appears in
      segment rule builders.
- [ ] Segment manager page can create / edit / delete user segments with live
      member count.
- [ ] Broadcasts page targets segments (not raw tags) and shows member count +
      preview before send.

---

---

## Risks

- **Modal on small viewports.** `position: fixed` + `max-width: 560px` works
  on desktop but can overflow on narrow screens. Test at 1024px and 768px;
  add a mobile fallback (`width: 95%; max-height: 95vh`) if needed.
- **Pagination desync on filter change.** Easy to forget; the Phase 1.2 note
  to reset page to 0 on any filter/search event must actually be wired into
  `_apply`, not just in the spec.
- **Alembic migrations.** The Phase 2 schema changes (`segments` table,
  `contacts.notes` column) must ship as proper Alembic revisions under
  `alembic/versions/`, not raw DDL against the live DB. The repo already uses
  Alembic — follow the existing revision naming style.
- **Segment rule evaluation divergence.** The Python-side `build_query`
  evaluator and the UI-side rule builder must agree on supported ops and
  field types. Keep the op list in one place (a constant in
  `services/segments.py`) and import it from the UI.
- **Migration of existing `customer_type` usage.** Any code that currently
  filters on `customer_type` directly (Broadcasts, campaign targeting, etc.)
  must switch to segment-based targeting in Phase 2 — or keep working
  unchanged because system segments wrap the same column. Grep for
  `customer_type` before starting Phase 2.

## Effort estimates

- **Phase 1:** ~1 focused session (layout + modal + Missing + pagination +
  legend). No schema changes, no tests beyond manual browser check.
- **Phase 2:** ~3–4 sessions.
  - Session 1: Alembic migration + `Segment` model + `services/segments.py`
    evaluator with unit tests.
  - Session 2: Contacts table segment column + inline edit drawer.
  - Session 3: Segment manager page with rule builder + live preview.
  - Session 4: Broadcasts integration + end-to-end smoke test.

## Out of scope (for both phases)

- No changes to the Contact import CSV format.
- No bulk-edit in Phase 2 (single-row edit only — bulk is Phase 3 if needed).
- No scheduled / auto-refreshing segments — member count is computed on read.
- No sharing segments across workspaces — single-tenant app.

## Open questions

- Should `notes` on a contact be a single field or a threaded note log? Phase 2
  will start with single field; revisit if the team wants history.
- Does the segment rule builder need a raw-JSON escape hatch for power users?
  Default: yes, hidden behind an "Advanced" toggle.
