# Plan D — Supabase Egress Reduction (v2)

**Status:** proposal, revised after self-review
**Deadline:** asap — HF Space is intermittently throttled by Supabase because of egress pressure
**Supabase project:** Free plan, `aws-1-ap-southeast-1.pooler.supabase.com:6543`, 5 GB outbound cap/month

## What changed from v1

Writing v1 I leaned on an audit report without verifying the claims. On review several of them turned out wrong or inflated. This version re-ranks offenders by actual code-confirmed impact, fixes two bad fix recommendations, adds a missing offender, and adds a measurement step so we can prove the fixes worked.

| v1 claim | v2 correction |
|---|---|
| "Contact has 45 columns" | Verified: **38 columns** |
| CSV download leaks "2-4 MB" of data per click | Still leaks but depends on download frequency — marked as conditional |
| Tag filter "1-2 MB/filter" — loads full rows | **Wrong.** Already uses `db.query(Contact.id, Contact.tags)` (column-tuple form) → only 2 columns come over the wire. Real waste is <30 KB, not 1-2 MB. Dropped from top list. |
| Lifecycle loop "100-150 KB/load" | **Wrong.** 5 count queries return 1 integer each — ~500 bytes/load total. Still worth fixing for code quality but not for egress. Moved to Phase 3. |
| Search keystroke "300-400 KB/keystroke" | **Inflated.** Query already has `.limit(20)` — actual waste is 20-40 KB/keystroke. Still meaningful cumulatively. |
| Fix: "debounce via Python timestamp gate" | **Bad fix.** Gradio has no native debounce; a Python gate leaves ghost UI states. **New fix:** switch `.change()` → `.submit()` — search fires on Enter. Standard chat pattern, zero new primitives. |
| Fix: "JSONB `@>` for tag filter" | **Dialect mismatch.** SQLite dev fallback doesn't support it. The current Python-side filter was a deliberate portability decision (see comment at `contacts.py:98`). Keep as-is. |
| **Missed offender:** `_build_table` pagination still ORM-full-rows | Every page render fetches `page_size=50` full 38-column Contact rows via `db.query(Contact).all()`. Not catastrophic per load, but this is the hottest path on the Contacts page and fires on every filter/search/page change. Added as new #3. |
| Effort: "Phase 1 = half a day" | **Optimistic.** Realistic is ~1 day for Phase 1 once HF↔Supabase flakiness is accounted for. |

## Ground truth (re-verified)

- **Contact table: 38 columns** — includes wide text fields (notes, address, response_notes, tags JSON)
- **943 contact rows**, 13 wa_templates, ~6 wa_messages (currently), 0 email_sends
- **Biggest hot paths** (by call frequency):
  - `wa_inbox.py::_get_active_conversations()` — fires on every Inbox page load + after each send
  - `contacts.py::_apply_reset()` / `_apply()` — fires on every filter change, search keystroke, or page nav
  - `home.py::_refresh()` — fires on Home page load
- **Not doing** (still): Pro upgrade, REST-API rewrite, Supavisor direct. See "Alternatives considered" below.

## Re-ranked offenders (v2)

Ranked by **verified** egress impact × call frequency.

### 1. WA Inbox N+1 on active conversations (biggest real win)
- **Where:** `hf_dashboard/pages/wa_inbox.py:38-65` — `_get_active_conversations()`
- **Pattern:** `db.query(WAMessage.contact_id).distinct().all()` then a Python loop that fires `db.query(Contact).filter(Contact.id == cid).first()` **and** `db.query(WAChat).filter(WAChat.contact_id == cid).first()` per contact id.
- **Call frequency:** every Inbox page load, every send (outbound refreshes the list).
- **Current cost:** 1 + 2N queries where N = active contacts. With 50 contacts that's 101 queries per load. Full Contact ORM rows come back each time (~38 cols × 50 rows = ~100 KB) + 50 full WAChat rows.
- **Fix:** single JOIN query with `with_entities` for only the columns the list item renders (name, company, avatar seed, `last_message_at`, `last_message_preview`, `unread_count`):
  ```python
  rows = (
      db.query(
          Contact.id, Contact.first_name, Contact.last_name, Contact.company,
          WAChat.last_message_at, WAChat.last_message_preview, WAChat.unread_count,
      )
      .join(WAChat, WAChat.contact_id == Contact.id)
      .filter(Contact.id.in_(db.query(WAMessage.contact_id).distinct()))
      .order_by(WAChat.last_message_at.desc())
      .all()
  )
  ```
- **Est. savings:** ~100 KB → ~8 KB per load. With ~50 Inbox loads/day = **~5 MB/day saved** (~150 MB/month).
- **Effort:** ~45 min (function rewrite + manual chat-list QA).

### 2. Contacts page table pagination fetches full rows
- **Where:** `hf_dashboard/pages/contacts.py:72, 124` — `_build_table` uses `q = db.query(Contact)` then `q.order_by().offset().limit(page_size).all()`. page_size defaults to 50.
- **Pattern:** paginated but ORM-full. Each render returns 50 × 38-col Contact rows. Most of the wide columns (notes, address, response_notes) are not rendered in the table.
- **Call frequency:** every filter/search/segment/lifecycle/channel/tag change, every page click. On an active user session this is the hottest read in the app.
- **Current cost:** ~100 KB per render × N renders per session.
- **Fix:** switch `_build_table` to a `with_entities` query that selects only the columns actually used by the row renderer. Look at the `cfg["table"]["columns"]` YAML to figure out which. Likely 10-12 columns instead of 38 → ~2/3 reduction per render.
- **Est. savings:** ~30-50 KB per render saved × dozens of renders per session = **~5-15 MB/day saved**.
- **Effort:** ~1 hour (need to audit the table renderer to map YAML column ids → Contact attributes, then swap the query).

### 3. Contacts CSV download over-fetch
- **Where:** `hf_dashboard/pages/contacts.py:993` — `db.query(Contact).all()` returns full ORM rows, then a dict-comp picks out 9 columns.
- **Current cost:** ~3-5 MB per click (947 rows × 38 cols). Uncertainty is which columns are wide — a few thousand-char `notes` fields blow this up.
- **Call frequency:** unknown — *open question for the user: how often do you click Download?* Twice a month = 10 MB/month savings max. Twice a week = 40 MB/month savings.
- **Fix:** one-line `with_entities(Contact.email, Contact.first_name, ...)` for the 9 used columns.
- **Est. savings:** ~2-4 MB per click. Effective monthly savings depend on usage.
- **Effort:** ~10 min.

### 4. WA Inbox search on every keystroke
- **Where:** `hf_dashboard/pages/wa_inbox.py:68-98` `_search_all_contacts()` + wiring at `.change()` handlers.
- **Pattern:** fires on **every character typed** in the Start-New-Conversation search box. Has `.limit(20)` already (good), but returns full ORM Contact rows and has no debounce.
- **Current cost:** ~20-40 KB × characters typed. A 20-char search = 400-800 KB. Users type multiple searches per session.
- **Fix (do both):**
  - **Switch from `.change()` to `.submit()`** — search fires when the user presses Enter, not per keystroke. One-line change in the `.change` → `.submit` call. Native Gradio, no new primitives.
  - **Add `with_entities`** for only the columns the dropdown needs (id, first_name, last_name, company).
- **Est. savings:** ~20-40 KB per character × typical typing = **~5 MB/month saved** at moderate use.
- **Effort:** ~15 min.

### 5. Home activity feed — two big `.limit(20)` queries per refresh
- **Where:** `hf_dashboard/pages/home.py:157-163` — `EmailSend.limit(20).all()` + `WAMessage.limit(20).all()` on every Home page load.
- **Current cost:** modest but stacks up. Home page loads every nav-to-home hit.
- **Fix:**
  - Combine into a single UNION-style query (or just two `with_entities` calls selecting only `contact_id, subject/text, created_at, direction`).
  - Wrap the result in a 60-second `ttl_cache` keyed on the current minute.
- **Est. savings:** ~2-3 MB/month.
- **Effort:** ~30 min.

### 6. Home page 4-way contact counts fire every refresh
- **Where:** `hf_dashboard/pages/home.py` + `contacts.py:730-733` — same pattern in both places: four separate `.count()` calls (total / opted_in / pending / wa_ready).
- **Current cost:** Count queries return tiny integers, so per-query egress is trivial. But it's **four round-trips** instead of one, which wastes connection time more than bytes.
- **Fix:** single aggregated query:
  ```python
  row = db.query(
      func.count().label("total"),
      func.sum(case((Contact.consent_status == "opted_in", 1), else_=0)).label("opted_in"),
      func.sum(case((Contact.consent_status == "pending", 1), else_=0)).label("pending"),
      func.sum(case((Contact.wa_id.isnot(None), 1), else_=0)).label("wa_ready"),
  ).one()
  ```
- **Est. savings:** egress-wise negligible. Latency-wise good (1 RTT instead of 4).
- **Effort:** ~20 min. **This is a latency/UX fix, not an egress fix.** Do it in Phase 2 but don't count it against the egress budget.

### 7. Segment list re-queried on every render
- **Where:** `hf_dashboard/pages/broadcasts.py:314` and similar — `db.query(Segment).filter(Segment.is_active).all()`.
- **Call frequency:** every page render + every filter change.
- **Fix:** `@ttl_cache(300)` wrapper on a module-level `get_active_segments()` helper. 5-min TTL is fine — segments rarely change.
- **Est. savings:** ~1-2 MB/month (depends on segment count and render frequency).
- **Effort:** ~15 min + the shared `ttl_cache` utility (see Phase 2 utilities).

### 8. Email Inbox subquery fetches all EmailSend rows
- **Where:** `hf_dashboard/pages/email_inbox.py:31-32` — subquery + join without `.limit()`.
- **Current cost:** EmailSend is currently empty (0 rows), so zero impact today — but this will blow up the second we start sending email campaigns.
- **Fix:** add `.limit(50)` to the subquery and paginate.
- **Est. savings:** ~0 today, potentially ~5-10 MB/month post-email-launch.
- **Effort:** ~20 min. Fix it before shipping email campaigns, not today.

### Not in v2's top list (things I dropped from v1)

- **Tag filter** — already uses column-tuple form, egress is tiny. Keep as-is.
- **Lifecycle loop on Home** — 5 count queries = ~500 bytes total egress. Still ugly code, but a Phase 3 code-quality fix.
- **Background flow loop** — fires every 30 min = 48 cycles/day. Each cycle issues 1 + 2N queries where N = active flow runs (currently 0). Zero impact today. Revisit when flows go active.

## Measurement first (NEW in v2)

We can't claim success without baseline numbers. Before touching any offender:

1. Add a SQLAlchemy event listener in `hf_dashboard/services/database.py`:
   ```python
   from sqlalchemy import event

   @event.listens_for(_engine, "after_cursor_execute")
   def _track(conn, cursor, statement, parameters, context, executemany):
       # Estimate bytes returned: sum(len(str(v)) for row in cursor.fetchall() ... )
       # Store in a daily rolling file: egress_log_YYYYMMDD.json
       ...
   ```
   Logs to `hf_dashboard/data/egress_log_YYYY-MM-DD.json` per day with `{query_fingerprint: {calls: N, rows: M, bytes_estimate: K}}`. Small overhead, persisted across Space restarts via the Space's `/data` volume.

2. Deploy, let it run for **24 hours of normal use**, fetch the log.

3. Rank the top 10 queries by actual bytes pulled. **Compare with Plan D's ranking.** Any surprises in the top 10 get bumped up the priority list.

4. Only then ship Phase 1 fixes.

5. After each phase, snapshot the log to see the actual reduction.

This is ~30 min of work to set up. Without it we're fixing by guesswork.

## Phases (revised effort)

### Phase 0 — measurement (~30 min + 24h passive)
- [ ] Add `after_cursor_execute` logger to `services/database.py`
- [ ] Deploy
- [ ] Let 24h elapse with normal dashboard usage
- [ ] Pull the log and verify the ranking below

### Phase 1 — top offenders (~1 day of focused work, including deploy+verify cycles)
- [ ] #1 WA Inbox N+1 → single JOIN with `with_entities`
- [ ] #2 Contacts table pagination → `with_entities` with UI-only columns
- [ ] #3 CSV download → `with_entities` for 9 used columns
- [ ] #4 Search `.change()` → `.submit()` + `with_entities`
- [ ] Re-measure with the Phase-0 logger. Verify **50%+ egress drop** before moving on.

### Phase 2 — structural + caching (~1 day)
- [ ] Build `hf_dashboard/services/ttl_cache.py` — thread-safe TTL dict cache (Gradio runs handlers in threads, plain `lru_cache` needs wrapping)
- [ ] Build `hf_dashboard/services/query_helpers.py` — `CONTACT_LIST_COLS`, `CONTACT_CSV_COLS`, `WA_CHAT_LIST_COLS` constants
- [ ] #5 Home activity feed → single query + 60s `ttl_cache`
- [ ] #6 Home 4-way counts → single aggregated query (latency win, not egress)
- [ ] #7 Segment list → `@ttl_cache(300)`
- [ ] Re-measure. Verify additional reduction.

### Phase 3 — nice-to-haves
- [ ] #8 Email inbox `.limit(50)` — required before email campaigns ship
- [ ] Background flow loop batching — required if flows go active
- [ ] Move the lifecycle loop to a single `group_by(lifecycle)` query — code cleanup
- [ ] (Optional) In-dashboard egress meter page reading from the Phase-0 logger

## Shared utilities (Phase 2)

### `hf_dashboard/services/ttl_cache.py`
```python
import threading, time
from functools import wraps

def ttl_cache(seconds: int):
    """Thread-safe TTL cache decorator. Gradio runs handlers in threads
    so plain functools.lru_cache is fine but offers no expiry."""
    def deco(fn):
        store = {}
        lock = threading.Lock()
        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                if key in store:
                    expires, value = store[key]
                    if expires > now:
                        return value
                value = fn(*args, **kwargs)
                store[key] = (now + seconds, value)
                return value
        return wrapped
    return deco
```

### `hf_dashboard/services/query_helpers.py`
Just column-tuple constants so every page doesn't reinvent them:
```python
from services.models import Contact, WAChat, WAMessage, EmailSend

CONTACT_LIST_COLS = (
    Contact.id, Contact.first_name, Contact.last_name, Contact.company,
    Contact.country, Contact.lifecycle, Contact.consent_status,
    Contact.wa_id, Contact.updated_at,
)
CONTACT_CSV_COLS = (
    Contact.email, Contact.first_name, Contact.last_name, Contact.company,
    Contact.phone, Contact.country, Contact.lifecycle,
    Contact.consent_status, Contact.wa_id,
)
WA_CHAT_LIST_COLS = (
    Contact.id, Contact.first_name, Contact.last_name, Contact.company,
    WAChat.last_message_at, WAChat.last_message_preview, WAChat.unread_count,
)
```

## Alternatives considered (instead of reducing egress)

In order of user-friendliness:

### A. Pro plan — $25/month, $300/year
- Removes the free-tier egress cap
- Zero code changes
- Predictable baseline
- **Tradeoff:** $300/year vs my engineering time. At any sane hourly rate, Pro is cheaper than the ~8-12 hours of work across Phase 1 + Phase 2. User has decided against this — we're not doing it, but it's worth restating that the financial math favors it.

### B. Region move — Supabase project from `ap-southeast-1` to a US region
- HF Spaces egress mostly lands in US. Cross-region TCP to Singapore adds RTT and may be part of the intermittent throttling.
- Supabase free tier only lets you pick region at project creation. Migrating means creating a new project and copying data over.
- **Effort:** 1-2 hours for a `pg_dump` + restore, plus re-wiring `DATABASE_URL` and redeploying.
- **Might fix the connectivity issue entirely.** Doesn't reduce egress volume, but eliminates the throttling symptom we keep seeing.
- Worth investigating *before* Plan D if we think the issue is routing, not volume.

### C. SQLite read-replica on the HF Space
- Run a local SQLite file on the Space's `/data` persistent volume.
- Periodic `pg_dump`-and-import from Supabase (every hour or on first page load per day).
- All dashboard reads hit SQLite (zero egress). Writes still go to Supabase.
- **Effort:** 2-3 days. Substantial — needs a sync script, failure-recovery logic, schema drift handling.
- **Payoff:** uncaps reads entirely. Worth it if Plan D phases 1+2 aren't enough.

### D. Supabase REST API (PostgREST) instead of direct DB
- Supabase ships an auto-generated REST endpoint at `https://<project>.supabase.co/rest/v1/...`
- Goes through Supabase's edge CDN which has different connection handling than the pooler.
- **Effort:** multiple days. Every ORM query has to be rewritten to HTTP calls. No SQLAlchemy session → no transactions across queries.
- **Probably not worth it.** Listed for completeness.

## Decision points

1. **Measurement first?** Or skip Phase 0 and ship Phase 1 blind? Phase 0 is 30 min of setup + 24 h wait. Default: yes, measure.
2. **Phase 1 all at once, or one offender per deploy?** One per deploy is more surgical (easier rollback) but 4× the HF rebuild time. All-at-once is faster but harder to blame a regression. Default: bundle into 1 commit, 1 deploy.
3. **Phase 2 utility ordering:** build `ttl_cache` first and then convert callers, or convert callers first and extract shared utility later? Default: extract utility first to avoid two refactor passes.
4. **Region move (Alternative B):** worth investigating before Plan D? If the Supabase region swap fixes the connectivity issue, we might not need Plan D at all — though reducing egress is still good hygiene for the free tier. Default: do Plan D regardless; investigate the region question in parallel if you have the patience to recreate the project.

## Rollback

Every fix ships as an independent commit touching a single function. `git revert <sha>` restores the prior behavior without affecting other fixes. Phase-0 measurement hook is additive (event listener) so it's always safe to leave on — even in production.
