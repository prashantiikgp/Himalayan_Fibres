# Phase 6 — UX simplification plan

**Date:** 2026-05-05
**Goal:** Reduce per-page cognitive load. Channel-split Broadcasts + Templates. Add a HowToUse accordion to every page. Fix the contacts segment-filter bug surfaced during live use. Final acceptance: send a real intro template to the user's email + WhatsApp from the new pages.

---

## Step 1 — Fix segment filter bug (highest annoyance, 15 min)

`api_v2/routers/contacts.py:125-126` filters `Contact.customer_type == segment_id`. Segments are hashed ids (`3ec0ab03`); `customer_type` holds string values (`domestic_b2b`). They never match — selecting any segment returns 0 contacts.

**Fix.** Load the segment row, evaluate its `rules` via the already-imported `build_segment_query()` helper, intersect with the existing query.

```python
if segment and segment != "all":
    seg_row = db.query(Segment).filter(Segment.id == segment).first()
    if seg_row is None:
        return ContactListResponse(contacts=[], total=0, page=0, page_size=page_size, total_pages=1)
    seg_q, tag_filter = build_segment_query(db, seg_row.rules)
    member_ids = {c.id for c in seg_q.all()}
    if tag_filter:
        member_ids = {
            cid for cid in member_ids
            if (db.query(Contact).filter(Contact.id == cid).one().tags or [])
            and any(t in tag_filter for t in (db.query(Contact).filter(Contact.id == cid).one().tags or []))
        }
    q = q.filter(Contact.id.in_(member_ids)) if member_ids else q.filter(Contact.id == "__never_match__")
```

(Phase D Phase 1.3 column-narrowing kept; just adds an in-clause.)

**Test.** New pytest case — seed a contact matching `Carpet Exporters India`'s rules, query with that segment id, assert > 0 contacts returned.

---

## Step 2 — `<HowToUse>` accordion component + YAML schema (1 hour)

**Component.** `vite_dashboard/src/components/layout/HowToUse.tsx`. Renders a Radix `<Accordion>` (or native `<details>`) at the top of a page, collapsed by default. Inside: summary line + optional sectioned how-to list.

**Schema extension.** `vite_dashboard/src/schemas/_common.ts` adds `HowToUseSection`:
```ts
export const HowToUseSection = z.object({
  title: NonEmptyString,
  body: NonEmptyString,
}).strict();

export const HowToUse = z.object({
  summary: NonEmptyString,
  sections: z.array(HowToUseSection).default([]),
}).strict();
```

**Per-page YAML.** Add `how_to_use:` under `page:` in each page's YAML (`config/pages/<page>.yml`). Page schemas (`schemas/pages.ts`) accept the optional field.

**Page header pattern.** Replace `<h1>{title}</h1><p>{subtitle}</p>` with `<HowToUse cfg={cfg.page.how_to_use} />`. The summary line acts as the visible default; clicking expands to the step-by-step.

---

## Step 3 — Channel-split Broadcasts (2 hours)

**Routes.**
- `/wa-broadcasts` — WhatsApp only (Compose / History / Performance tabs). Channel toggle removed; channel locked to `whatsapp`.
- `/email-broadcasts` — Email only (Compose / History / Performance tabs). Channel toggle removed; channel locked to `email`.
- `/broadcasts` — redirect to `/wa-broadcasts` (back-compat for any bookmarks).

**Component re-use.** Keep ComposeTab / HistoryTab / PerformanceTab as-is, but pass `channel` as a prop instead of reading the toggle. Each parent page hardcodes one channel.

**HistoryTab.** Already filters by `channel=` query param. Hide the channel filter dropdown when called channel-locked.

**Sidebar.** Already has `broadcasts_wa` and `broadcasts_email` entries — change paths to the new routes.

---

## Step 4 — Email Templates page (NEW, 2 hours)

EmailTemplate rows exist in the DB; no UI today. Mirror the WA Templates studio shape:

**Backend** (`api_v2/routers/email_templates.py`).
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/email/templates` | List, filterable by `is_active`, `email_type`, `category`, search |
| GET | `/api/v2/email/templates/{id}` | Full record incl. `html_content` |
| POST | `/api/v2/email/templates` | Create |
| POST | `/api/v2/email/templates/{id}/save` | Save (in-place; emails don't have Meta-style immutability) |
| DELETE | `/api/v2/email/templates/{id}` | Delete |

**Frontend** (`vite_dashboard/src/pages/email-templates/`).
- `EmailTemplatesPage` — left list, right editor.
- `EmailTemplateEditor` — name, slug, subject_template, html_content (textarea or simple iframe preview), email_type, category, is_active.
- No phone preview (no equivalent), but render a basic HTML preview iframe.

---

## Step 5 — Add HowToUse content to every page (30 min)

YAML stub per page. Below are the summaries; each will get 2-4 sections of detail.

| Page | Summary line |
|---|---|
| Home | "Daily snapshot: who's in your DB, what's been sent today, what's queued." |
| Contacts | "Browse and edit every contact. Filter by segment, lifecycle, channel; import a CSV; mark a status." |
| WA Inbox | "Active WhatsApp conversations within the 24h window. Reply directly or send a template to reopen one." |
| WA Broadcasts | "Send an approved WhatsApp template to a segment. WA broadcasts fire immediately." |
| WA Templates | "Author + submit + sync WhatsApp templates with Meta. Approved templates can't be edited; saving creates a clone." |
| Email Broadcasts | "Send an email template to a segment, or schedule for later. Email queues in the background — track progress on the Compose page." |
| Email Templates | "Author and edit email templates. Saved templates are immediately usable in Email Broadcasts." |
| Flows | "Multi-step automated sequences (read-only for now). Each row shows its recent runs." |

---

## Step 6 — Verification: send real intro template (NEW)

After the redesign deploys, send the existing intro template through the new pages to confirm everything works end-to-end. **Real Meta + SMTP calls** — only fire after explicit user go-ahead.

### 6a. Email — `/email-broadcasts` Individual mode → `b2b_introduction` → `prashant.mine@gmail.com`

1. Open `/email-broadcasts`, Compose tab.
2. (If Individual mode lands as part of this phase) pick contact by name OR enter direct email `prashant.mine@gmail.com`.
3. Pick template `b2b_introduction`.
4. Click Send Now → type SEND in confirm dialog → Send.
5. Verify the email lands in your gmail inbox.

If individual-mode isn't available in /email-broadcasts yet (current Compose is segment-only), seed a one-row segment OR add the contact to a small test segment first.

### 6b. WhatsApp — `/wa-broadcasts` → template send to `918582952074`

1. Confirm a Contact row exists with `wa_id=918582952074`. Add via `/contacts` if not.
2. Make a single-member segment "Test — Prashant WA" with rule `tags: ["test:prashant"]` and tag the contact.
3. Open `/wa-broadcasts`, Compose tab.
4. Pick segment Test — Prashant WA → pick template `b2b_fiber_intro` (or `sample_request_thanks`) → Send Now → confirm.
5. Verify the message lands on your WhatsApp.

### 6c. Tear-down

After delivery confirmed, remove the test tag (or leave it — it's annotative).

---

## Sequencing + commit boundaries

| Commit | Step |
|---|---|
| `fix(contacts): segment filter actually evaluates rules` | Step 1 |
| `feat(layout): HowToUse accordion + YAML schema` | Step 2 |
| `refactor(broadcasts): channel-split into /wa-broadcasts + /email-broadcasts` | Step 3 |
| `feat(email-templates): list + editor + CRUD endpoints` | Step 4 |
| `docs(pages): HowToUse content for all 7 pages` | Step 5 |
| `verify: send live intro template to prashant.mine@gmail.com + 918582952074` | Step 6 (no code change; just human-driven via Playwright) |

Each commit is independent + deployable. ~6 hours total.

---

## Out of scope for this plan

- Email Inbox (no inbound email infrastructure today; revisit if SMTP-receive is added).
- Sentry-driven UX feedback collection (different project).
- Visual regression Storybook setup (per STANDARDS §8) — orthogonal.
