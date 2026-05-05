# Email Infrastructure Redesign — Three-Part Plan

> **Status:** Reviewed and corrected. Three load-bearing factual errors from the v1 draft have been fixed (missing model columns, wrong FastAPI mount, sequential-id metric forgery). See "Risks & assumptions" at the bottom for everything that remains uncertain.

## Context

The current email surface in `hf_dashboard/` is built on patterns that don't match how the user actually wants to work:

- **Email Inbox** (`pages/email_inbox.py`) mirrors the WhatsApp inbox layout (left list of contacts, middle thread, right tools), but emails are long, threaded, and already viewable in Gmail. The inbox page is mostly a duplicate of Gmail with worse UX.
- **Email Campaigns** (`pages/email_campaigns.py`) is a stepper with a user-entered subject line, a manual "send to me" textbox, no live audience filtering, and no scheduling. It does not match the cleaner two-column WhatsApp broadcast at `pages/broadcasts.py`.
- **Templates**: WhatsApp templates are YAML-driven and validated via Pydantic. Email templates currently come from CloudHQ HTML imports stored as raw `EmailTemplate.html_content`. There is no in-dashboard way to create or edit a template.
- **Analytics**: `Contact` has `last_email_opened_at` but `EmailSend` and `Campaign` do **not** have any open/click/bounce columns yet (verified in `hf_dashboard/services/models.py:123-157`). Gmail API returns delivery confirmation only.

**Goal of this redesign:**
1. Replace the email inbox with an **analytics page** showing opens, clicks, sends, scheduled campaigns — driven by tracking pixels and click rewriting we add to the dashboard's FastAPI app.
2. Refactor the email broadcast page to mirror the WhatsApp two-column pattern (audience filters left, template preview right), with the subject line driven by the template (not user-entered) and **scheduled send** support.
3. Add **two independent template-creation pages**: a "Paste HTML" studio and an "MJML Blocks" studio — both write to `email_templates`, either can be removed cleanly without affecting the other.
4. Reorganize the sidebar into **WhatsApp** and **Email** channel groups so navigation stops jumping around.

Decisions locked in with the user:
- Tracking: real open pixel + click rewriting, **no** Gmail reply polling.
- Scheduling: real scheduled send, extending the existing 30-min background thread.
- Template editors: paste-HTML and MJML blocks, on **two separate pages**, independently removable.

---

## Phase 0 — Pre-flight checks (do this FIRST, before writing any code)

These verify two assumptions that, if wrong, force a plan change. Both are ~5 minutes.

### 0.1 Verify `mjml` Python package actually compiles MJML

The `mjml==0.12.0` PyPI package wraps the Node `mjml` CLI via subprocess — it does **not** bundle a Python compiler. If Node isn't installed in the runtime environment (HF Spaces or local), Page 3b will throw `FileNotFoundError` on first compile.

```bash
python -c "import mjml; print(mjml.mjml_to_html('<mjml><mj-body><mj-text>hi</mj-text></mj-body></mjml>'))"
```

- ✅ If it prints HTML → proceed with the plan as written.
- ❌ If it errors with "node not found" or similar → switch to `mrml` (pure-Rust port, `pip install mrml`, no Node dependency). Update `requirements.txt` and `services/mjml_compiler.py` to import `mrml` instead. Same compile contract, no other changes.

### 0.2 Add `beautifulsoup4` to requirements

The HTML walker for click-link rewriting is fragile with regex (multi-line tags, quoted attributes, `<base href>`). `bs4` is not currently in `requirements.txt`. Add it:

```
beautifulsoup4==4.12.3
```

This is a hard dependency for Part 1 and Part 3a (HTML validation on save).

---

## Part 1 — Email Analytics Page (replaces Email Inbox)

### Intent
Replace the Gmail-lookalike inbox with a campaign-centric analytics view: which campaigns went out, who opened them, who clicked, what's scheduled.

### 1.1 Schema additions (the v1 plan was wrong here — these columns do NOT exist yet)

**`hf_dashboard/services/models.py`:**

```python
class Campaign(Base):
    # existing columns: scheduled_at, sent_at, total_recipients, total_sent, total_failed, ...
    # ADD:
    total_opened    = Column(Integer, default=0)
    total_clicked   = Column(Integer, default=0)
    total_bounced   = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    audience_snapshot = Column(JSONType, nullable=True)  # for scheduled sends, see Part 2

class EmailSend(Base):
    # existing columns: status, idempotency_key, error_message, sent_at, created_at, ...
    # ADD:
    tracking_token = Column(String(32), unique=True, nullable=True,
                            default=lambda: secrets.token_urlsafe(16))
    delivered_at   = Column(DateTime, nullable=True)
    opened_at      = Column(DateTime, nullable=True)   # first open
    clicked_at     = Column(DateTime, nullable=True)   # first click
    bounced_at     = Column(DateTime, nullable=True)
    open_count     = Column(Integer, default=0)        # every open
    click_count    = Column(Integer, default=0)        # every click
```

**`hf_dashboard/services/database.py`** — add an idempotent `_add_column_if_missing` helper used during `init_db()` bootstrap. SQLite's `ALTER TABLE ADD COLUMN` raises on a duplicate column, so we need the guard:

```python
def _add_column_if_missing(engine, table: str, column: str, ddl: str) -> None:
    cols = {row[1] for row in engine.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        engine.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
```

Call it once per new column on bootstrap. Backfill `tracking_token` for existing `EmailSend` rows in the same step (`UPDATE email_sends SET tracking_token = ... WHERE tracking_token IS NULL`, generated per row in Python).

> **Tech debt note:** `alembic==1.13.1` is already in `requirements.txt` but is not wired up to the dashboard SQLite database. Bootstrap ALTERs are pragmatic for now; introduce alembic migrations once schema churn settles.

### 1.2 Tracking infrastructure — routes mounted on the **dashboard** FastAPI app

The actually-running FastAPI app is `hf_dashboard/app.py:49` (`fastapi_app = FastAPI(title="Himalayan Fibers Dashboard")`). The separate `app/` directory is a parallel backend that the dashboard process does not run — putting tracking routes there leaves them unreachable. Routes go in the dashboard.

**New file: `hf_dashboard/api/email_tracking.py`** — exports an `APIRouter`:

- `GET /track/open/{token}.png`
  - Looks up `EmailSend` by `tracking_token`. 404 silently if not found (return PNG anyway, never break the email render).
  - Sets `EmailSend.opened_at = utcnow()` if null. Increments `EmailSend.open_count`.
  - On the **first** open only: increments `Campaign.total_opened`, increments `Contact.total_emails_opened`, sets `Contact.last_email_opened_at`, logs `email_opened` interaction via `services/interactions.py`.
  - Returns the bytes of a 1×1 transparent PNG with `Content-Type: image/png`, `Cache-Control: no-store`.
- `GET /track/click/{token}/{link_index}`
  - Looks up the original URL stored at send time in a new `EmailLink` table (see below) — **no `?u=` query param**. This eliminates the open-redirect vulnerability entirely.
  - Sets `EmailSend.clicked_at` if null. Increments `EmailSend.click_count`.
  - On the **first** click only: increments `Campaign.total_clicked`, increments `Contact.total_emails_clicked`, sets `Contact.last_email_clicked_at`, logs `email_clicked` interaction.
  - Returns `RedirectResponse(url, status_code=302)`.

**New model `EmailLink`** in `services/models.py`:

```python
class EmailLink(Base):
    __tablename__ = "email_links"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    send_id     = Column(Integer, ForeignKey("email_sends.id"), nullable=False, index=True)
    link_index  = Column(Integer, nullable=False)   # 0, 1, 2... per send
    target_url  = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("send_id", "link_index"),)
```

This is the only safe way to do click tracking without an open redirect.

**Wire the router** in `hf_dashboard/app.py`:

```python
from api.email_tracking import router as tracking_router
fastapi_app.include_router(tracking_router)
```

**New `email_clicked` interaction kind** in `services/interactions.py` — add it next to the existing `email_opened` (which the audit confirmed is already declared but currently unused).

### 1.3 Sender modifications — `hf_dashboard/services/email_sender.py`

Add `_inject_tracking(html: str, send_id: int, tracking_token: str, base_url: str) -> str`:

1. Parse HTML with `bs4` (`BeautifulSoup(html, "html.parser")`).
2. Walk every `<a href="...">`. Skip `mailto:`, `tel:`, anchors (`#`), and hrefs already pointing at our tracking domain. For each remaining link:
   - Insert an `EmailLink(send_id=..., link_index=i, target_url=original)` row.
   - Replace the `href` with `f"{base_url}/track/click/{tracking_token}/{i}"`.
3. Append the open pixel just before `</body>` (or at end of document if `</body>` is missing): `<img src="{base_url}/track/open/{tracking_token}.png" width="1" height="1" alt="" style="display:block">`.
4. Return `str(soup)`.

**Skip injection entirely** if `EMAIL_TRACKING_BASE_URL` env var is unset (so local dev still works). Log a `WARN` once at startup if it's missing in production.

**`EmailSender.send_email()` flow change:**
- Today: page handlers create the `EmailSend` row, then call `EmailSender.send_email()`.
- New: `EmailSender.send_email()` itself takes the `db` session, creates the `EmailSend` row first (so it has an `id` and a `tracking_token`), calls `_inject_tracking()`, then sends, then updates the row's status.
- Page handlers in `email_campaigns.py` (and the broadcast engine's `send_broadcast()` email branch at `broadcast_engine.py:256`) get a small refactor to drop their manual `EmailSend` insert and let the sender own it.

### 1.4 New env vars
- `EMAIL_TRACKING_BASE_URL` — the public URL the dashboard is reachable at (HF Spaces URL or ngrok in dev). No trailing slash.
- `OPERATOR_EMAIL` — used by Part 2's "Test to me" button. No fallback to `settings.smtp_user` because `EmailSender` uses Gmail API, not SMTP, and `smtp_user` may not be populated.

### 1.5 Analytics page — `hf_dashboard/pages/email_analytics.py` (new file, replaces `email_inbox.py`)

**Layout** — two-column, mirrors the WhatsApp broadcast scale ratios:

```
┌─────────────────────┬────────────────────────────────┐
│ scale=1, min=300    │ scale=3, min=600               │
│                     │                                │
│ KPI cards (top)     │ Selected campaign detail:      │
│  • Total sent (30d) │  ┌──────────────────────────┐  │
│  • Avg open rate    │  │ Campaign name + status   │  │
│  • Avg click rate   │  │ Subject • template • seg │  │
│  • Scheduled queue  │  └──────────────────────────┘  │
│                     │                                │
│ Tabs:               │  Metric tiles (5):             │
│  [ Sent ]           │   Sent | Delivered | Opened | │
│  [ Scheduled ]      │   Clicked | Bounced/Failed    │
│  [ Drafts ]         │                                │
│                     │  Recipient table:              │
│ Campaign list       │   Name • Email • Status •      │
│ (radio, like        │   Sent at • Opened at •        │
│  wa_inbox conv list)│   Clicked at • Open count      │
└─────────────────────┴────────────────────────────────┘
```

**Data sources** (after schema additions land):
- Campaign list: `Campaign` table, ordered by `sent_at DESC NULLS LAST, scheduled_at DESC, created_at DESC`. Filter by status per tab.
- KPI cards: aggregate from `Campaign` rows in last 30 days (`total_sent`, `total_opened`, `total_clicked`).
- Recipient table: `EmailSend` rows for the selected campaign joined to `Contact`.

**Reuse**: KPI rendering helpers from `pages/broadcasts.py` (`_render_audience_kpis`, section-header HTML), conversation-list radio styling from `wa_inbox.py`, table renderer from `components/`.

**Actions on selected campaign**:
- "View HTML" → opens compiled HTML in an iframe inside a hidden `gr.Group` toggled on click.
- "Cancel scheduled" → only on scheduled campaigns; flips `status` from `scheduled` → `cancelled`. Worker (Part 2) skips anything not `scheduled`.
- "Resend to failures" → re-queues just the failed `EmailSend` rows. **Idempotency note:** the current sender uses `sha256(campaign_id:contact_id:date)` as the idempotency key, which would silently dedupe a same-day retry. Append `:retry{N}` (using `EmailSend.id` count for that contact+campaign) to the key on resend so the new send isn't blocked.

**Files**:
- New: `hf_dashboard/pages/email_analytics.py`
- New: `hf_dashboard/api/__init__.py`, `hf_dashboard/api/email_tracking.py`
- New: `hf_dashboard/config/pages/email_analytics.yml` (labels, KPI definitions — match the YAML-config pattern from `wa_inbox.yml`)
- Delete (after nav swap): `hf_dashboard/pages/email_inbox.py`

---

## Part 2 — Email Broadcast Refactor (mirrors WhatsApp broadcast)

### Intent
Make the email broadcast page feel identical to `pages/broadcasts.py` (WhatsApp): a left column for audience selection, a right column for template preview + actions. Subject line comes from the template, not the user. Add scheduled send.

### Layout — two columns, same scale ratios as WhatsApp broadcast

```
┌──────────────────────────┬────────────────────────────────┐
│ scale=2, min=380         │ scale=3, min=540               │
│                          │                                │
│ 🎯 Audience              │ 💰 Cost / Volume KPIs (4)      │
│  Segment dropdown        │  Recipients | Est. send time   │
│  Country (multi)         │  Template • Subject preview    │
│  Lifecycle (multi)       │                                │
│  Consent (multi)         │ 👁️ Preview                     │
│  Tags (multi)            │  Radio: [Template] [Rendered]  │
│  Limit slider            │  ┌──────────────────────────┐  │
│  Audience KPIs HTML      │  │ Iframe preview of HTML   │  │
│                          │  │ (compiled MJML or pasted │  │
│ ✏️ Message               │  │  HTML, vars substituted) │  │
│  Template dropdown       │  └──────────────────────────┘  │
│                          │                                │
│ ⏰ Schedule              │ Actions:                       │
│  ○ Send now              │  [Test to me] [Send / Schedule]│
│  ○ Schedule for later    │  Result HTML                   │
│    Date | Time (gr.DateTime)│                             │
└──────────────────────────┴────────────────────────────────┘
```

> **Gradio version:** `gr.DateTime` is available — verified Gradio 6.12.0 is installed. No fallback needed.

### Key changes vs current `email_campaigns.py`

1. **Subject is template-driven, not user-entered.** Drop the `subject_input` Textbox. Display the resolved subject as part of the preview. Template-change handler pulls `EmailTemplate.subject_template` and renders it with the same Jinja2 path the broadcast send uses.
2. **Audience picker reuses the WhatsApp pattern.** Copy the audience block from `pages/broadcasts.py:38-91` verbatim. Wire change handlers identically; reuse `services/broadcast_engine.py`'s `BroadcastFilters`, `apply_filters`, `count_eligible_contacts`, `get_unique_*` helpers — `send_broadcast()` already routes on `channel == "email"` (verified at `broadcast_engine.py:256` and uses `EmailSender` at line 463), so no engine changes needed for the send path.
3. **"Test to me" uses `OPERATOR_EMAIL` env var** (added in Part 1.4). No free-text email field. Match WhatsApp's test pattern (sends to operator number from config).
4. **Preview is an iframe** (`<iframe srcdoc="...">`), not a `<pre>` of HTML source. Two preview modes via the same Radio pattern as `broadcasts.py:114-120`: "Template view" (raw with {{vars}} visible) and "Rendered view" (vars substituted using a sample contact from the filtered audience).
5. **Schedule support** — see below.

### Scheduling implementation

**UI**: Radio (`Send now` / `Schedule for later`) + a `gr.DateTime` for the picked time, IST assumed and converted to UTC before save. DateTime hidden when "Send now" selected.

**Send handler logic**:
- "Send now": call existing `broadcast_engine.send_broadcast(channel="email", ...)`. Same as today.
- "Schedule for later":
  - Insert `Campaign` row with `status="scheduled"`, `scheduled_at=<picked datetime UTC>`, `template_slug` set, and `audience_snapshot=<BroadcastFilters as JSON>`.
  - Return immediately with "Scheduled for {time IST}" message.

**Snapshot column**: `Campaign.audience_snapshot` (already added in Part 1.1). Stores `BroadcastFilters` dict so the worker can re-resolve the audience at fire time (filters re-evaluate against the live contact table — this is intentional; it means a contact who unsubscribes between schedule and send is correctly excluded).

**Worker**: extend the background thread in `hf_dashboard/app.py:99-115` (currently runs `check_pending_steps()` for flows every 30 min). Add a sibling call in a new helper `services/campaign_scheduler.py`:

```python
def check_due_campaigns(db) -> int:
    due = db.query(Campaign).filter(
        Campaign.status == "scheduled",
        Campaign.scheduled_at <= datetime.utcnow(),
    ).all()
    fired = 0
    for c in due:
        c.status = "sending"
        db.commit()
        try:
            filters = BroadcastFilters(**json.loads(c.audience_snapshot))
            send_broadcast(db, channel="email", campaign_id=c.id, filters=filters,
                           template_slug=c.template_slug)
            c.status = "sent"
            c.sent_at = datetime.utcnow()
            fired += 1
        except Exception:
            c.status = "failed"
            logger.exception("scheduled campaign %s failed", c.id)
        db.commit()
    return fired
```

The 30-min cadence means a 9:00 schedule may fire as late as 9:30 — document this in the UI ("Sends within 30 minutes of selected time").

**Concurrency note:** The `status="sending"` flip is the lock, which is **only safe because there is exactly one background thread**. If you ever run `check_due_campaigns()` from a CLI script in parallel, or scale to multiple workers, two of them can both read `status="scheduled"` before either writes `"sending"`. Acceptable for now — document the single-worker assumption. When scaling, replace the read-then-write with a `UPDATE campaigns SET status='sending' WHERE id=:id AND status='scheduled'` and check `rowcount == 1`.

**Cancel scheduled**: a button on the analytics page (Part 1) flips `status` from `scheduled` → `cancelled`. Worker filter (`status == 'scheduled'`) naturally skips cancelled rows.

### Files
- Modify (then rename in Phase 7): `hf_dashboard/pages/email_campaigns.py` — full rewrite to match the layout above. Keep filename through Phase 2-6 to minimize churn; rename to `email_broadcast.py` only as part of the navigation reorg in Phase 7.
- New: `hf_dashboard/services/campaign_scheduler.py`
- Modify: `hf_dashboard/app.py` — call `check_due_campaigns()` in the background loop alongside `check_pending_steps()`.
- Reuse (no changes needed beyond Part 1's sender refactor): `services/broadcast_engine.py`, `services/segments.py`, `services/email_sender.py`.

---

## Part 3 — Email Template Creation (two independent pages)

### Intent
Stop depending on CloudHQ for template creation. Provide two separate, self-contained ways to author templates inside the dashboard. Either page can be deleted without affecting the other or anything else.

Both pages write to the same `email_templates` table. Broadcast / analytics flows don't care which page produced a template — they only read `EmailTemplate.html_content` and `subject_template`.

### Schema additions

```python
class EmailTemplate(Base):
    # existing: id, name, slug, subject_template, html_content, email_type,
    #           required_variables, category, is_active, created_at
    # ADD:
    preview_text = Column(String(255), nullable=True)
    mjml_source  = Column(Text, nullable=True)  # null = template was created via Page 3a
```

Bootstrapped via the same `_add_column_if_missing` helper from Part 1.

### Page 3a — "Email Template Studio (HTML)"

**File**: `hf_dashboard/pages/email_template_html.py`

**Layout** — two columns:

```
┌─────────────────────────────┬────────────────────────────┐
│ scale=2, min=400            │ scale=3, min=600           │
│                             │                            │
│ Template list (radio)       │ Iframe live preview        │
│  + "New template" button    │   (re-renders on HTML      │
│                             │    textarea blur)          │
│ ── Editing ──               │                            │
│  Name (textbox)             │  Device toggle:            │
│  Slug (textbox, auto)       │   [💻 Desktop] [📱 Mobile] │
│  Subject template (textbox) │                            │
│  Preview text (textbox)     │  Variables detected:       │
│  Category dropdown          │   • {{first_name}}         │
│                             │   • {{company_name}}       │
│  HTML source                │                            │
│  (gr.Code lang='html')      │  [Save] [Send test to me]  │
│                             │                            │
│  Insert variable: dropdown  │                            │
└─────────────────────────────┴────────────────────────────┘
```

**Behavior**:
- Paste any HTML (CloudHQ export, Claude-generated, hand-written). On save, re-detect variables via `services/email_renderer.py:extract_variables()` and store in `EmailTemplate.required_variables`.
- Live preview: re-render iframe `srcdoc` from textarea contents on `change` event.
- "Send test to me" sends to `OPERATOR_EMAIL` with sample vars via `EmailSender.send_email()`.
- Save validates HTML is parseable (`BeautifulSoup(html, "html.parser")` — it tolerates malformed HTML but we surface unclosed-tag warnings inline).
- New templates default to `is_active=True`, `email_type="campaign"`, `mjml_source=None`.

### Page 3b — "Email Template Studio (MJML Blocks)"

**File**: `hf_dashboard/pages/email_template_mjml.py`

**Why MJML**: MJML is a markup language designed for emails — write block tags, compile to the table-soup HTML that renders correctly across Gmail, Outlook, Apple Mail. Closest "give non-developers safe email building" without a JS WYSIWYG editor. **Phase 0 verifies the compiler actually works in our runtime** before we commit to this page.

**Block library** (Phase 1, ship with these 6):
1. **Header** — logo image URL, background color
2. **Hero image** — image URL, alt text, link URL (optional)
3. **Text block** — heading, body
4. **Button** — label, URL, color
5. **Divider** — color, padding
6. **Footer** — company name, address, unsubscribe link (auto-injected)

Each block is a Pydantic model. The full template is a list of block dicts stored as JSON in `EmailTemplate.mjml_source`.

**Layout** — three columns:

```
┌─────────────┬──────────────────────┬────────────────────┐
│ scale=1     │ scale=2              │ scale=2            │
│             │                      │                    │
│ Template    │ Block list (re-      │ Iframe live        │
│ list        │ ordered via up/down  │ preview            │
│             │ buttons since Gradio │                    │
│ + New       │ has no native DnD)   │ Device toggle      │
│             │                      │                    │
│ ── Meta ──  │ ┌─[Header]──────┬─┐  │                    │
│ Name        │ │ Logo: ___     │↑│  │                    │
│ Slug        │ │ BG:   #fff    │↓│  │                    │
│ Subject     │ │               │✕│  │                    │
│ Preview txt │ └───────────────┴─┘  │                    │
│             │ ┌─[Text]────────┬─┐  │                    │
│             │ │ Heading: ___  │↑│  │                    │
│             │ │ Body: _______ │↓│  │                    │
│             │ └───────────────┴─┘  │                    │
│             │                      │                    │
│             │ + Add block ▼        │ [Save]             │
│             │                      │ [Send test to me]  │
└─────────────┴──────────────────────┴────────────────────┘
```

**Compile pipeline** (`hf_dashboard/services/mjml_compiler.py`):
1. Walk the block list → build an MJML document string from a Jinja2 template per block type (block templates live in `hf_dashboard/templates/mjml_blocks/*.mjml`).
2. Pass the MJML string to the compiler chosen in Phase 0 (`mjml` Python wrapper or `mrml`) → returns HTML.
3. Run through `premailer` (already in `requirements.txt`) → inlines CSS so Gmail respects styles.
4. Cache the compiled HTML in `EmailTemplate.html_content`.

**Broadcast/analytics never touch MJML** — they always read `html_content`. MJML is just the source-of-truth for editing on Page 3b.

**Save flow**: serialize block list to JSON → `EmailTemplate.mjml_source`, compile → `EmailTemplate.html_content`. Same row, two fields.

**Independence guarantee**: Page 3b only touches `mjml_source` and reads/writes `html_content`. Page 3a only touches `html_content`. Deleting either page (and its file) leaves the other fully functional. Page 3b's template list filters `WHERE mjml_source IS NOT NULL` so HTML-only templates never appear.

### Files
- New: `hf_dashboard/pages/email_template_html.py`
- New: `hf_dashboard/pages/email_template_mjml.py`
- New: `hf_dashboard/services/mjml_compiler.py`
- New: `hf_dashboard/templates/mjml_blocks/{header,hero,text,button,divider,footer}.mjml`
- Reuse: `services/email_renderer.py` for variable extraction, `services/email_sender.py` for test sends.

---

## Navigation Reorganization

`hf_dashboard/config/dashboard/sidebar.yml` is a flat list with `separator_before` markers. The navigation engine renders nav items in order with separators between groups. Channel groups are expressed via separators + a new optional `section_label` field — small, contained engine change.

**New sidebar order**:

```yaml
nav_items:
  - { id: home,     label: "Home",     icon: "🏠" }
  - { id: contacts, label: "Contacts", icon: "📋" }

  # ── WhatsApp ──
  - { id: wa_inbox,         label: "Inbox",     icon: "💬", separator_before: true, section_label: "WhatsApp" }
  - { id: broadcasts,       label: "Broadcast", icon: "📢" }
  - { id: wa_templates,     label: "Templates", icon: "📄" }   # split out from templates_media

  # ── Email ──
  - { id: email_analytics,    label: "Analytics", icon: "📊", separator_before: true, section_label: "Email" }
  - { id: email_broadcast,    label: "Broadcast", icon: "📧" }   # renamed from email_campaigns
  - { id: email_template_html,label: "Templates (HTML)",  icon: "📝" }
  - { id: email_template_mjml,label: "Templates (Blocks)", icon: "🧱" }

  # ── Other ──
  - { id: flows,             label: "Flows",   icon: "🔄", separator_before: true }
  - { id: broadcast_history, label: "History", icon: "📜" }
```

**Engine change**: Add optional `section_label` rendering in `engines/navigation_engine.py` — if present on a nav item, render a small header above it ("WhatsApp", "Email"). ~10 lines of HTML in the sidebar build loop.

**Templates page split**: `pages/templates_media.py` currently renders WhatsApp + Email + Media via a Radio toggle. Split into:
- `pages/wa_templates.py` — just the WhatsApp section (the YAML-driven `_build_wa_template_list`)
- The Email tab is replaced entirely by Pages 3a and 3b.
- The Media tab — keep as `pages/media_library.py` if used, or drop if empty.

**Rename**: `pages/email_campaigns.py` → `pages/email_broadcast.py`. Update `_resolve_page_module()` in `engines/navigation_engine.py` (or just update the `id` mapping in `sidebar.yml`).

---

## Critical files (full picture)

### New
- `hf_dashboard/pages/email_analytics.py`
- `hf_dashboard/pages/email_broadcast.py` (renamed from `email_campaigns.py` in Phase 7)
- `hf_dashboard/pages/email_template_html.py`
- `hf_dashboard/pages/email_template_mjml.py`
- `hf_dashboard/pages/wa_templates.py`
- `hf_dashboard/api/__init__.py`
- `hf_dashboard/api/email_tracking.py`
- `hf_dashboard/services/campaign_scheduler.py`
- `hf_dashboard/services/mjml_compiler.py`
- `hf_dashboard/templates/mjml_blocks/*.mjml`
- `hf_dashboard/config/pages/email_analytics.yml`
- `hf_dashboard/config/pages/email_broadcast.yml`

### Modified
- `requirements.txt` — add `beautifulsoup4==4.12.3` (and `mrml` if Phase 0 sends us there)
- `hf_dashboard/services/models.py` — `Campaign.{total_opened,total_clicked,total_bounced,total_delivered,audience_snapshot}`, `EmailSend.{tracking_token,delivered_at,opened_at,clicked_at,bounced_at,open_count,click_count}`, `EmailTemplate.{mjml_source,preview_text}`, new `EmailLink` model
- `hf_dashboard/services/database.py` — `_add_column_if_missing` helper + bootstrap calls + `tracking_token` backfill
- `hf_dashboard/services/email_sender.py` — `_inject_tracking()`, take responsibility for creating `EmailSend` rows + `EmailLink` rows
- `hf_dashboard/services/interactions.py` — add `email_clicked` interaction kind alongside `email_opened`
- `hf_dashboard/services/broadcast_engine.py` — minor refactor of email branch (line 256+) to drop manual `EmailSend` insert (sender now owns it)
- `hf_dashboard/app.py` — `include_router(tracking_router)`; extend background thread to call `check_due_campaigns`
- `hf_dashboard/engines/navigation_engine.py` — render `section_label` when present; updated page-id resolver for renamed broadcast page
- `hf_dashboard/config/dashboard/sidebar.yml` — new order + section labels

### Deleted
- `hf_dashboard/pages/email_inbox.py` (after Phase 2)
- `hf_dashboard/pages/templates_media.py` (after split in Phase 7)

---

## Phasing (suggested order to keep PRs reviewable)

0. **Pre-flight checks** (above): verify `mjml` compiles, add `beautifulsoup4` to requirements.
1. **Schema + tracking foundation**: model columns (Part 1.1), `_add_column_if_missing` helper, `EmailLink` model, `email_tracking` router, `_inject_tracking()` in sender, sender takes ownership of `EmailSend` row creation, `email_clicked` interaction kind. No UI yet. Verify by sending a test email and watching DB get updated when the open pixel loads.
2. **Email Analytics page** (Part 1.5): build the page reading from now-populated tracking fields. Delete `email_inbox.py` once analytics is wired in nav.
3. **Email Broadcast refactor — send-now only** (Part 2 minus scheduling): rewrite layout, audience picker, template-driven subject, test-to-me. File still named `email_campaigns.py` at this stage.
4. **Scheduling** (Part 2 cont.): `audience_snapshot` (already added in Phase 1), `campaign_scheduler.py`, background thread wiring, schedule UI radio + `gr.DateTime`, cancel-scheduled action on analytics page.
5. **HTML template page** (Part 3a): standalone, doesn't depend on MJML.
6. **MJML template page** (Part 3b): block library, compiler, MJML-source column wiring. Skip this phase entirely if Phase 0 said MJML is unavailable and we haven't switched to `mrml` yet.
7. **Navigation reorg + rename**: split `templates_media.py`, rename `email_campaigns.py` → `email_broadcast.py`, update `sidebar.yml`, add `section_label` rendering. Bundled together because the rename and the section labels both touch the nav surface, and doing them once minimizes churn.

---

## Verification

**Phase 0**:
- `python -c "import mjml; print(mjml.mjml_to_html('<mjml><mj-body><mj-text>hi</mj-text></mj-body></mjml>'))"` returns valid HTML.
- `python -c "import bs4; print(bs4.__version__)"` returns 4.12.x.

**Tracking pipeline (Phase 1)**:
1. Set `EMAIL_TRACKING_BASE_URL` to ngrok or HF Spaces URL.
2. Send a test email via the existing `email_campaigns.py` "Send test" path (still alive in Phase 1).
3. Inspect DB: `EmailSend.tracking_token` populated, `EmailLink` rows created for every `<a>` in the email.
4. Open the email in Gmail. Confirm `EmailSend.opened_at` populates and `open_count == 1`. Open it again — `opened_at` unchanged, `open_count == 2`.
5. Click a link in the email. Confirm browser redirects correctly to the original URL AND `EmailSend.clicked_at` populates.
6. Check `Contact.total_emails_opened` incremented (only once, on first open).
7. Check `email_opened` and `email_clicked` rows appear in `contact_interactions`.
8. Hit `/track/open/nonsense.png` → returns a PNG, no error, no DB write.

**Analytics page (Phase 2)**:
1. Sent campaign appears in "Sent" tab with correct totals.
2. Open rate updates as test recipients open the email.
3. Scheduled campaign appears in "Scheduled" tab with cancel action working (Phase 4).
4. KPI cards show last-30-day aggregates.
5. "Resend to failures" on a campaign with failed sends actually re-sends them (idempotency suffix working).

**Broadcast refactor (Phase 3)**:
1. Open new email broadcast page. Audience filters update KPIs live as you change them.
2. Pick template — subject preview shows resolved `tpl.subject_template`, no editable subject field anywhere.
3. "Test to me" sends one email to `OPERATOR_EMAIL`.
4. "Send Broadcast" creates a `Campaign` row with `status=sent` after immediate send.

**Scheduling (Phase 4)**:
1. "Schedule for later" with a future time creates a `Campaign` row with `status=scheduled` and `audience_snapshot` populated.
2. Wait for the next 30-min tick (or manually call `check_due_campaigns(db)` from a Python REPL) — verify it sends and flips to `sent`.
3. Schedule another, then click "Cancel scheduled" on analytics page — status flips to `cancelled`, never fires.

**Template pages (Phases 5-6)**:
1. HTML page: paste a CloudHQ export, see live preview, save, appear in broadcast page's template dropdown.
2. MJML page: add Header + Text + Button blocks, save, see compiled HTML render in iframe and match what's stored in `html_content`, appear in same dropdown.
3. Delete `email_template_mjml.py` — confirm HTML page and broadcast still work. Restore. Delete `email_template_html.py` — confirm MJML page and broadcast still work.

**Navigation (Phase 7)**:
1. Sidebar shows "WhatsApp" header above WhatsApp items, "Email" header above Email items.
2. Clicking each nav item navigates correctly.
3. No regressions on existing pages.

---

## Risks & assumptions

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | `mjml==0.12.0` requires Node.js installed in the runtime. | Phase 0 verification; fall back to `mrml` (pure Rust, no Node) if it fails. |
| 2 | Tracking pixels are blocked by Apple Mail Privacy Protection and many corporate firewalls. | Industry-standard limitation; document that open rates are under-counted by ~20-30%. Click rates are not affected. |
| 3 | Single background-thread assumption for `check_due_campaigns`. | Documented in code; replace with `UPDATE ... WHERE status='scheduled'` rowcount-checked update if scaling to multiple workers. |
| 4 | 30-min worker tick means a 9:00 schedule may fire at 9:30. | Document in UI ("sends within 30 min of selected time"); reduce tick if tighter SLA needed. |
| 5 | SQLite `ALTER TABLE ADD COLUMN` bootstraps are not real migrations — risk of drift between dev and prod. | `_add_column_if_missing` helper guards against duplicate-column errors; introduce alembic (already in requirements) once schema churn slows. |
| 6 | `EmailLink` table will grow large (1 row per `<a>` per send × every recipient). | Index on `send_id`; consider `link_index`-only retention (archive `target_url` after 90 days) if it becomes a problem. |
| 7 | HF Spaces public URL changes between Spaces restarts could break tracking pixels in already-sent emails. | Use a custom domain pointing at HF Spaces, or accept that tracking only works for emails sent under the current URL. |
| 8 | `EmailSender` Gmail-API path may rate-limit on broadcast sends. | Existing 3-second delay between sends in `email_campaigns.py` — preserve in the refactored broadcast handler. |
