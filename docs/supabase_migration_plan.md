# Supabase Migration Plan

**Owner:** Prashant · **Status:** Approved pending schema review · **Date:** 2026-04-13

## Why

Today the HF Spaces container has an **ephemeral filesystem**. Every redeploy,
idle timeout, or OOM wipes the SQLite file and re-seeds from
`data/contacts.csv` and `data/segments.csv`. Any contact the user adds via UI,
any field they edit through the new Phase 2a drawer, any new segment, any
inbound WA message handled mid-session — **all of it disappears on next start**.
This problem will get worse as Phase 2b adds segment CRUD, contact notes, and
an interactions timeline.

Supabase (managed Postgres, free tier: 500 MB) is the right destination:

- **Persistent** — tables survive container restarts unconditionally.
- **SQLAlchemy already speaks it** — swap is a URL change, not a rewrite.
- **Studio UI** at `supabase.com/dashboard/project/yxlofrkkzjkxtbowyryj` — user
  can view/edit tables directly without code.
- **Asia-Pacific region** — chosen to minimise latency from India.
- **Free tier covers 1000× the current data volume** (941 contacts, 11
  segments, ~thousands of WA messages expected).

## Target state

- **Single source of truth**: Supabase Postgres for all operational data
  (contacts, segments, campaigns, broadcasts, flows, WA conversations).
- **CSV files become seed-only**: `data/contacts.csv` and `data/segments.csv`
  only run on an empty DB. Once Supabase is seeded, they're never re-read.
- **Local dev keeps working**: if `DATABASE_URL` is unset, the dashboard falls
  back to local SQLite, unchanged. Devs don't need Supabase credentials to hack
  on the UI.
- **HF Spaces uses Supabase**: `DATABASE_URL` is a Space Secret; the container
  picks it up on boot.
- **Zero data loss during migration**: existing SQLite data on HF (which is
  empty on redeploy anyway) is ignored; Supabase gets seeded fresh from the
  CSVs, then all future writes land there permanently.

## Pre-flight checklist (already done in past sessions)

- [x] Supabase project created — `yxlofrkkzjkxtbowyryj`, Asia-Pacific region.
- [x] Database password saved in local `.env` (`SUPABASE_DB_PASSWORD`,
      publishable key, project URL).
- [x] `psycopg2-binary` installed locally; connection to Supabase tested
      from Python (`SELECT version()` returned PostgreSQL 17.6).
- [x] `services/config.py` reads `DATABASE_URL` env var (falls back to SQLite).
- [x] `services/database.py::get_engine()` picks Postgres when URL is set,
      SQLite otherwise. Includes `pool_pre_ping=True` so stale connections
      auto-reconnect.
- [x] `hf_dashboard/app.py` loads `.env` for local dev via `python-dotenv`.
- [x] `hf_dashboard/requirements.txt` has `psycopg2-binary` and `python-dotenv`.
- [x] Seeding is already idempotent: `ensure_db_ready()` checks
      `is_db_seeded()` before calling `seed_from_csv()` — no re-seed on boot.

**One remaining mechanical change before flip-the-switch:** `DATABASE_URL` is
currently *commented out* in the local `.env` so we develop against SQLite
while the Supabase schema is still being reviewed. Uncommenting is the switch.

## Schema decisions — what lives in Supabase

### Tables to create as-is (11 existing, no changes needed)

These all exist as SQLAlchemy models and will be created automatically on
first boot via `Base.metadata.create_all(engine)`:

| Table | Rows on first seed | What each row means |
|---|---|---|
| `contacts` | 941 (from CSV) | A person or business we can reach via email/WA. Lifecycle + tags + consent. |
| `segments` | 11 (from CSV) | A named saved filter over contacts. `rules` JSON determines membership. |
| `email_templates` | 7 | A reusable email template with subject + HTML body. |
| `campaigns` | 0 | A drafted or scheduled email campaign. User creates these via UI. |
| `email_sends` | 0 | One row per outbound email delivery attempt. Idempotency keyed. |
| `flows` | 3 | An automation sequence (B2B intro, welcome, WA welcome). |
| `flow_runs` | 0 | One active run of a flow for a given segment. |
| `broadcasts` | 0 | One-shot bulk send (email or WA) with status + totals. |
| `wa_chats` | 0 | Per-contact WhatsApp conversation state (24h window, unread). |
| `wa_messages` | 0 | Every inbound and outbound WhatsApp message. |
| `wa_templates` | 13 (synced) | Approved WA templates from Meta. |
| `product_media` | 0 | Uploaded images/files for WA media messages. |

### New P0 tables to add *during* the migration (2 tables)

These are small, safe additions. Adding them now means the migration creates
them alongside the existing 11, so we never have to migrate twice.

**`contact_interactions`** — powers the Activity tab in the edit drawer.
Every significant contact event writes one row. Query by `contact_id` to
render a timeline.

```python
class ContactInteraction(Base):
    __tablename__ = "contact_interactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), ForeignKey("contacts.id"), index=True)
    kind = Column(String(32), nullable=False)
        # email_sent | email_opened | email_clicked |
        # wa_sent | wa_inbound | wa_read |
        # note_added | tag_added | tag_removed |
        # manual_edit | imported | segment_matched
    summary = Column(String(255), default="")
    payload = Column(JSONType, default=dict)  # kind-specific extras
    occurred_at = Column(DateTime, default=_utcnow, index=True)
    actor = Column(String(64), default="system")  # "system" | "user:<name>" | "webhook"
    created_at = Column(DateTime, default=_utcnow)
```

**`contact_notes`** — threaded notes replacing the single `contact.notes` text
field. The old field stays for migration compatibility but new notes go here.

```python
class ContactNote(Base):
    __tablename__ = "contact_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), ForeignKey("contacts.id"), index=True)
    body = Column(Text, nullable=False)
    author = Column(String(64), default="")
    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
```

### Deferred to Phase 3 (NOT part of this migration)

Listed here so we don't forget — but we're consciously not touching them now:

- `blog_posts`, `blog_categories` — consolidate `config/blog/*.yml`. Separate
  initiative, unrelated to contacts/broadcasts.
- `media_assets` — consolidate `config/media/*.yml`. Same.
- `tags` — canonical tag table (rename/merge/color). Nice-to-have; implicit
  tag inventory via `SELECT DISTINCT` already works.
- `users`, `audit_logs`, `consent_events` — only if multi-user or compliance
  becomes a requirement.
- Inbound email capture — requires a Gmail IMAP poller or webhook. No table
  today (only outbound via `email_sends`). User has not asked for this yet.

## The migration, step by step

Each step lists: **what changes**, **safety check**, **rollback**.

### Step 1 — Add the two P0 models to `services/models.py`

**Change:** append `ContactInteraction` and `ContactNote` classes (shown above)
to the existing models file. Add them to the import list in `services/database.py`.

**Safety check:** `python -c "from services.database import init_db; init_db()"`
against local SQLite should create both new tables without error and without
touching existing ones.

**Rollback:** revert the diff. SQLAlchemy create_all is additive by default —
no existing tables are dropped or altered.

### Step 2 — Audit seeding for idempotency

**Change:** verify each `_seed_*` function in `services/database.py` does the
right thing against a non-empty table:

- `_seed_contacts`: already checks `db.query(Contact).filter(email == x).first()`
  per row, so duplicate inserts are skipped. ✓ Idempotent.
- `_seed_segments`: uses `Segment(id=row_id)`; Postgres will raise on
  duplicate PK insert. ⚠ Needs a pre-check: `if db.query(Segment).filter(
  Segment.id == row.id).first(): continue`.
- `_seed_default_templates`: uses auto-increment `id`; on re-seed it would
  insert duplicates. ⚠ Needs a `slug` uniqueness check.
- `_seed_default_flows`: uses auto-increment `id`; same problem. ⚠ Needs a
  `name` uniqueness check.

But — `ensure_db_ready()` already gates on `is_db_seeded()` (which checks
contact count). So `seed_from_csv()` only runs once on a fresh DB. The only
way the above edge cases matter is if someone wipes `contacts` but leaves
other tables; that's not a real scenario.

**Decision:** leave seeding as-is. Do not add per-row idempotency checks —
premature hardening.

**Rollback:** n/a (no change).

### Step 3 — Uncomment `DATABASE_URL` in local `.env`

**Change:** uncomment the single line in `.env` that currently reads
`# DATABASE_URL=postgresql+psycopg2://...`. The credentials are already there.

**Safety check:**
```
cd hf_dashboard && python -c "
import os; from dotenv import load_dotenv; load_dotenv('../.env')
from services.database import get_engine, init_db, ensure_db_ready
eng = get_engine()  # should print 'DB engine: Postgres (...)'
ensure_db_ready()   # should print 'seeding from CSV...' then 'seeded N contacts'
from services.models import Contact
from services.database import get_db
db = get_db()
print('contact count on Supabase:', db.query(Contact).count())
db.close()
"
```
Expected: creates 13 tables on Supabase, seeds 941 contacts + 11 segments + 7
templates + 3 flows + 13 WA templates, prints `941`.

**Verify in Supabase Studio:**
1. Open `https://supabase.com/dashboard/project/yxlofrkkzjkxtbowyryj`
2. Table Editor → Sidebar shows 13 tables.
3. `contacts` table has 941 rows.
4. `segments` table has 11 rows with `rules` JSON visible.

**Rollback:** re-comment the line. Local dev falls back to SQLite. Supabase
tables remain (harmless).

### Step 4 — Start the app locally against Supabase + smoke-test persistence

**Change:** `python app.py`, open `localhost:7860`, go to Contacts page, add
a new contact via the Add Contact modal, then restart the app (`Ctrl+C`, rerun).

**Safety check:** the new contact should still be present after restart. If
the contact disappears, something is pointed at SQLite, not Supabase.

**Also test:**
- Click Edit on an existing row, change a field, Save → field updates in table
  immediately.
- Restart app → edited field persists.
- Open Supabase Studio → `contacts` table shows the edit.

**Rollback:** stop app, re-comment `DATABASE_URL`, restart. Local SQLite
resumes with its own (unchanged) data.

### Step 5 — Set `DATABASE_URL` as a HF Space Secret

**Change:** add `DATABASE_URL` to the HF Space settings. Option A (CLI):
```
hf repo-files update-secret Prashantiitkgp08/himalayan-fibers-dashboard \
    DATABASE_URL 'postgresql+psycopg2://postgres:yQcrar5ZfmRutCAu@db.yxlofrkkzjkxtbowyryj.supabase.co:5432/postgres?sslmode=require'
```
Option B (UI): go to
`https://huggingface.co/spaces/Prashantiitkgp08/himalayan-fibers-dashboard/settings`
→ *Variables and secrets* → *New secret* → name `DATABASE_URL`, paste the URL.

**Safety check:** Space redeploys automatically when a secret is added. Watch
the build log for:
```
DB engine: Postgres (postgresql+psycopg2://postgres:***@db.yxlofrkkzjkxtbowyryj.supabase.co:5432/postgres?sslmode=require)
Database already seeded (N contacts)
```
The "already seeded" message confirms the app is reading from the *same*
Supabase DB we seeded in Step 4 — no duplicate seed.

**Rollback:** delete the secret. Space falls back to SQLite on next redeploy
(and loses ephemeral data again, but that's already the current state).

### Step 6 — Deploy the two new models to HF Spaces

**Change:** push `services/models.py` and `services/database.py` (with the
ContactInteraction and ContactNote imports added) to the Space.

**Safety check:** on Space rebuild, `create_all()` creates the two new tables
alongside the existing ones. No existing tables are touched.

**Rollback:** revert the commit. The two new tables remain in Supabase
(harmless; empty). We can drop them via Supabase Studio if desired.

### Step 7 — Smoke-test on the deployed Space

**Change:** hit the deployed URL. Add a contact, edit a contact, close the
browser, come back in 10 minutes, verify the changes are still there.

**Safety check:** refresh and confirm data survived. Also check Supabase
Studio directly — it's the authoritative view.

**Rollback:** remove the `DATABASE_URL` secret.

## Execution notes (2026-04-13)

Migration executed end-to-end. The direct-connection URL
(`db.<ref>.supabase.co:5432`) **failed on HF Spaces with `Network is
unreachable`** — Supabase free tier resolves that hostname to IPv6 only, and
HF Spaces containers don't have IPv6 connectivity.

**Fix applied**: switched both the local `.env` and the HF Space
`DATABASE_URL` secret to the Supabase **session pooler**:

```
postgresql+psycopg2://postgres.yxlofrkkzjkxtbowyryj:<password>@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres
```

Key differences from the direct URL:
- **Host**: `aws-1-ap-southeast-1.pooler.supabase.com` (Singapore pooler). The
  specific subdomain is `aws-1-` for this project — not `aws-0-`, which we
  tried first. Different projects land on different poolers.
- **Username**: `postgres.<project-ref>`, not plain `postgres`.
- **Port**: `5432` for session pooler (stable connections, ORM-friendly) or
  `6543` for transaction pooler (close after each txn, incompatible with
  SQLAlchemy's pool_pre_ping pattern). We use `5432`.
- **No `?sslmode=require`**: the pooler enforces SSL automatically.

**Anyone debugging future region changes** can rerun the same "try each
region" loop I used — connect with `connect_timeout: 8` and catch
`OperationalError` per candidate; the one that reaches the pooler with
`"Tenant or user not found"` is a wrong region, and the one that returns
`(postgres, postgres)` from `SELECT current_user` is the right region.

**Persistence verified end-to-end**: inserted a marker row via local Python,
opened the live HF URL, searched for it, saw it show up in the table — both
the local process and the deployed container read from the same Supabase DB.

## Risks and unknowns

- **Password URL encoding**: `yQcrar5ZfmRutCAu` is alphanumeric, no encoding
  needed. If we regenerate the password and it has `@/:` characters, we must
  URL-encode them. Non-issue today.
- **SSL mode**: the URL uses `?sslmode=require`. Supabase enforces SSL on the
  pooler and direct ports. Tested locally — works.
- **Connection pooling**: using SQLAlchemy's `pool_size=5, max_overflow=5`
  against Supabase direct port (not the pooler). For <100 concurrent users
  this is fine. If we hit "remaining connection slots reserved" errors, switch
  to the Supabase connection pooler URL (`aws-0-ap-south-1.pooler.supabase.com`
  port `6543`) in the secret, no code change needed.
- **Seeding race on cold-start redeploys**: HF Spaces may boot two containers
  briefly during a redeploy. If both call `seed_from_csv()` simultaneously on
  a fresh DB, we could get duplicate key errors. Mitigation: rely on
  `is_db_seeded()` gate which runs a count query before inserting. If both
  containers see count=0, both try to insert, one gets a unique-violation and
  logs it. Non-fatal. Acceptable for the first run only.
- **Tags column JSON shape in Postgres**: SQLAlchemy's `JSONType` TypeDecorator
  stores lists as JSON-encoded strings. Postgres `JSONB` would be more
  efficient but requires code changes. Today's shape works on both backends;
  we can optimise later.
- **Accidentally nuking data**: the plan never calls `DROP TABLE` or
  `create_all(engine, drop_existing=True)`. `create_all()` is purely additive.
- **`contact.notes` vs `contact_notes`**: for a while both exist. The old
  field keeps whatever single note is on it today. New notes go into the new
  table. Reading logic in the drawer should prefer the new table but fall
  back to the old field if the new table is empty for that contact. Phase 2b
  work.

## Effort estimate

- **Steps 1–4 (local)**: ~45 min. Most time is writing the models + smoke
  testing.
- **Step 5 (HF secret)**: ~5 min.
- **Steps 6–7 (deploy + verify)**: ~15 min including HF rebuild time.

**Total: ~1 session**, one focused hour of work.

## What this does NOT do

- Does not migrate existing Phase 2a features — they already work unchanged.
- Does not change the UI. Segments column, Tags filter, Edit drawer all
  continue to work; they just write to a different DB.
- Does not add Activity tab UI — that's Phase 2b, on top of the new
  `contact_interactions` table.
- Does not delete any CSV files — they stay as seeds.
- Does not migrate blog/media YAML files — separate Phase 3 initiative.

## After this lands

Phase 2b picks up with:
1. Activity tab in the drawer, reading from `contact_interactions`.
2. Notes tab converted to threaded notes via `contact_notes`.
3. Every edit/add/tag-change writes one interaction row so the timeline
   builds organically over time.
4. Backfill interactions from `email_sends` + `wa_messages` for historical
   context on existing contacts.

Then Phase 2c:
1. Segment manager page (create/edit/delete user segments with rule builder).
2. Broadcasts page polish (segment dropdown shows member count + sample).
