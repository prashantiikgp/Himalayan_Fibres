# Plan D — Supabase Egress Reduction

**Status:** proposal
**Deadline:** asap — we're burning through the free-tier 5 GB/month cap
**Trigger:** HF Space → Supabase `aws-1-ap-southeast-1.pooler.supabase.com:6543` TCP-timing out every 5–15 minutes because Supabase throttles over-egress projects at the network layer. Each Space restart gives us a fresh egress IP that works briefly until it's throttled again.

## Ground truth

- Project is on **Supabase Free plan** (confirmed via Billing → Usage screenshot 2026-04-14 17:14)
- Free plan gives **5 GB outbound egress / month**
- The egress chart for the current billing period (11 Apr → 11 May) is **red** with tall bars on both observed days — the project is on track to blow past the cap
- Code-side investigation (audit by Explore agent, 2026-04-14) identified 10 query patterns that waste egress, several of them severe (N+1s, unbounded `.all()`, over-fetching wide Contact rows)

## Not doing

- **Not upgrading to Pro.** User call: data volume doesn't justify $25/mo. We fix the leaks instead.
- **Not rewriting to Supabase REST API.** Too invasive for the return.
- **Not running a local-cache shadow DB.** Overkill; no hot-reload story.

## Top-10 offenders (ranked by estimated egress impact)

| # | File:line | Pattern | Trigger | Est. egress | Fix |
|---|---|---|---|---|---|
| 1 | `contacts.py:993` | `db.query(Contact).all()` | Click "Download CSV" | **~2–4 MB / click** (all 947 rows × 45 cols) | Use `db.query(Contact).with_entities(col1, col2, ...)` with the 8-10 columns the CSV actually needs. Keep row count but drop column width. |
| 2 | `wa_inbox.py:45-65` | N+1 on active conversations: distinct `WAMessage.contact_id` → loop → `Contact.filter(id).first()` + `WAChat.filter(contact_id).first()` | Every Inbox page load | **~1–2 MB / load** (50 contacts × full row × 2 queries) | Single JOIN: `db.query(Contact, WAChat).join(WAChat, WAChat.contact_id == Contact.id).filter(Contact.id.in_(sub))`. Select only the columns used to render the list item (name, company, avatar, chat preview, ts, unread). |
| 3 | `contacts.py:112` | Tag filter loads ALL contacts' `(id, tags)` into Python then filters in-process | Every tag dropdown change | **~1–2 MB / filter** | Push the tag filter into SQL: `WHERE tags @> '["tag"]'::jsonb` (Postgres JSONB contains op) or pre-compute a tag→contact_id map once per process. |
| 4 | `email_inbox.py:31-32` | Subquery + join over ALL `EmailSend` rows without `.limit()` | Every Email inbox page load | **~1–2 MB / load** | Limit the subquery to the 50 most-recent senders. `row_number() OVER (PARTITION BY contact_id ORDER BY created_at DESC)`. |
| 5 | `wa_inbox.py:80, 358` | Search-box `.change()` fires `Contact.filter(wa_id).all()` per keystroke, no debounce | Every character typed | **~300–400 KB / keystroke** | Add 400 ms debounce on the search handler. Limit result to `.limit(20)`. Cache the "all wa_id contacts" set for 60s in-process. |
| 6 | `home.py:157-161` | Two `limit(20)` queries on `EmailSend` + `WAMessage` for the activity feed | Every Home page refresh | **~200–300 KB / refresh** | Combine into a single UNION query; wrap in a 5-min `ttl_cache`. |
| 7 | `contacts.py:730-733` | Four separate `.count()` calls (total / opted_in / pending / wa_ready) fire on every filter change | Every filter interaction | **~100–150 KB / interaction** | Single query using `func.count(Case(...))` with four conditional aggregates. Also 30s `ttl_cache` keyed on the filter dict. |
| 8 | `home.py:129-130` | Loop over lifecycle stages calling `Contact.filter(lifecycle=stage).count()` — 5–6 separate queries | Every Home page load | **~100–150 KB / load** | Single `group_by(lifecycle)` query. Cache 60s. |
| 9 | `broadcast_history.py:108` | `db.query(Broadcast).all()` with no limit | Every page render | **~50–100 KB** | Add `.limit(50).order_by(created_at.desc())`. |
| 10 | Segment list in `broadcasts.py:314` + everywhere | `Segment.filter(is_active).all()` re-queried per render | Every Broadcasts page render + filter change | **~20–30 queries / page** | `@lru_cache(maxsize=1)` on a module-level `get_active_segments()` helper with 5-min TTL. |

### Background thread

`app.py::_flow_automation_loop` runs every 30 min. Per cycle it issues ~1 + N + N queries where N is the active-FlowRun count. Not urgent but should be batched into one JOIN query (Flow + FlowRun) when we pick up Plan D.

## Shared utilities to build once and reuse

1. **`hf_dashboard/services/ttl_cache.py`** — small TTL cache decorator (60s / 5min variants) since Python `lru_cache` has no expiry.
2. **`hf_dashboard/services/query_helpers.py`** — common column-set constants (`CONTACT_LIST_COLS`, `CONTACT_CSV_COLS`, `WA_CHAT_LIST_COLS`) and a `with_entities()` factory. Stops every page from reinventing column lists.
3. **`hf_dashboard/shared/debounce.py`** — a small helper for debouncing Gradio `.change()` handlers (maybe just a timestamp-gate at the start of the handler; Gradio doesn't have native debounce but we can discard calls that fire within the window).

## Staging plan

### Phase 1 — quick wins (half a day, ~60% of the savings)
- [ ] Fix offender #2: replace wa_inbox N+1 with JOIN (single biggest single win)
- [ ] Fix offender #1: CSV download column selection
- [ ] Fix offender #5: debounce wa_inbox search + limit + cache
- [ ] Fix offender #7: combine 4 counts into 1 query

### Phase 2 — structural (half a day, ~30% more)
- [ ] Build `ttl_cache` + `query_helpers` utilities
- [ ] Fix offenders #3, #6, #8, #10 using the new utilities
- [ ] Fix offender #9 (trivial `.limit()` add)

### Phase 3 — nice-to-haves
- [ ] Fix offender #4 (email inbox subquery)
- [ ] Batch background-thread queries
- [ ] Add an egress-observability page that reads Supabase's egress metric via their management API so we can see the number in the dashboard itself

## Expected savings

If Phase 1 + Phase 2 ship:
- WA Inbox interactions: **~30 MB → ~5 MB / month** (–83%)
- Contacts page filter+search: **~50 MB → ~5 MB / month** (–90%)
- Home page refreshes: **~18 MB → ~3 MB / month** (–83%)
- CSV exports: **~16 MB → ~8 MB / month** (–50%)
- **Total: ~100+ MB saved per month**, comfortably keeps us under the 5 GB free-tier cap.

## Rollback plan

All changes are additive-safe (adding `.limit()`, swapping `all()` for `with_entities()`, adding caches). A single `git revert` of each commit restores the old behavior. We should ship each offender fix in its own commit for surgical rollback.

## Decision points for the user

1. **Phase order**: ship Phase 1 first and measure egress for 48h before starting Phase 2? Or bundle both?
2. **Egress observability page**: worth the extra scope, or park it and watch the Supabase dashboard manually?
3. **Search debounce UX**: 400 ms is the sweet spot for typing, but a 500 ms debounce feels a touch laggy. Preference?
