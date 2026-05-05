# Plan B — WhatsApp Template Studio

> New feature. Execute after Plan A ships. Lets the user draft WhatsApp
> templates in the dashboard, upload header images/documents, submit to Meta
> for approval, and track status — without leaving the app.

## Context

Today templates live in two YAML files (`config/whatsapp/templates.yml`, `new_templates.yml`) and are submitted to Meta via a CLI tool (`scripts/submit_wa_templates.py`). Status checking is CLI-only. The `WATemplate` SQLAlchemy model (`hf_dashboard/services/models.py:231-242`) exists and **is already used** by the `app/whatsapp/` module (imported in `hf_dashboard/services/database.py:23` and referenced in `app/whatsapp/tasks.py`, `routes.py`, `models.py`, `schemas.py`, `config.py`). Any schema change must preserve those existing readers.

User requirements:

1. Draft templates in the dashboard with a visual editor
2. Upload header images (and PDFs for document templates) that get a persistent public URL the template can reference at submission time
3. Submit to Meta from the UI and see approval status roll in
4. Understand image size/format constraints and template-type options (TEXT header vs IMAGE header vs DOCUMENT header) without having to read Meta's docs

**Hard constraint:** Meta pre-approves every template. The dashboard cannot bypass that. What it *can* do is make authoring, submitting, and tracking dramatically less painful, and surface rejection reasons inline so you iterate faster.

## Reusable infrastructure (already in the repo)

- **`WATemplate` model** (`hf_dashboard/services/models.py:231`) — has `name`, `language`, `category`, `status`, `quality_score`, `components (JSON)`, `last_synced_at`. Extend with draft-specific columns **additively** so existing `app/whatsapp/` readers keep working.
- **`ProductMedia` model** (`hf_dashboard/services/models.py:266`) — `filename`, `filepath`, `caption`, `wa_media_id`, `uploaded_at`. Reuse for uploaded header assets; add a `public_url` column and a `kind` discriminator (`product` / `wa_header`) so catalog assets and template header assets don't get tangled when querying.
- **`WhatsAppSender.list_templates()`** (`hf_dashboard/services/wa_sender.py:213-225`) — GET from Meta, already works. Reuse for sync.
- **`WhatsAppSender.upload_media()`** (`hf_dashboard/services/wa_sender.py:176-192`) — pushes a file to Meta to get a `media_id`. Useful for runtime `send_template` calls, **not** for template headers (template submission needs a public HTTPS URL, not a media_id).
- **`scripts/submit_wa_templates.py`** — `_build_components` (lines 45-82) and `submit_template` (lines 85-104) already implement the exact Meta payload construction. **Extract `_build_components` into a shared helper** (e.g. `hf_dashboard/services/wa_template_builder.py`) and import it from both the CLI script and the new `WhatsAppSender.create_template()` method so the two call sites cannot drift.
- **`hf_dashboard/services/config.py` `media_path`** — already has a `MEDIA_PATH` setting pointing at `hf_dashboard/media/` for local uploads.
- **`hf_dashboard/app.py`** — already has the FastAPI instance (`fastapi_app`) and mounts Gradio at `/`, so adding a `/media/*` static route is a two-line change.

---

## B1. Local media store with public URLs

Header images (and header documents) must be reachable by Meta at template-submission time via HTTPS URL — not a local path, not a Meta media_id.

**Design.**
- Save uploaded files under `${MEDIA_PATH}/wa_headers/<uuid>_<slug>.<ext>`
- Mount `fastapi_app.mount("/media", StaticFiles(directory=...), name="media")` in `hf_dashboard/app.py` right after `fastapi_app = FastAPI(...)` (line 49)
- Public URL = `f"{settings.public_base_url}/media/wa_headers/<filename>"`
- Add `PUBLIC_BASE_URL` to `hf_dashboard/services/config.py` — defaults to `http://localhost:7860` for dev; production will be the HF Spaces HTTPS URL
- Persist `ProductMedia` row with `filepath` (local) and `public_url` (external) on upload

**⚠ Production requirement.** Meta will only pull from HTTPS URLs. On HF Spaces the Space URL is HTTPS so this works automatically. On localhost dev the user will need `ngrok` (or similar) since Meta can't reach `http://localhost:7860`. If `PUBLIC_BASE_URL` is not HTTPS, show a warning banner **and disable the "Submit to Meta" button** — otherwise Meta rejects the submission with a confusing error and the user has to dig to find the cause.

**Helper file:** new `hf_dashboard/services/media_store.py` with:
- `save_upload(file, subdir="wa_headers") -> ProductMedia`
- `get_public_url(media) -> str`
- `delete_upload(media_id)` (for cleaning up rejected templates)

---

## B2. Extend `WATemplate` additively (non-breaking)

### Audit findings (2026-04-14)

There are **two parallel `WATemplate` ORM classes** both mapped to the `wa_templates` table, on different SQLAlchemy `Base`s:

1. **`hf_dashboard/services/models.py:231`** — the one deployed on HF Spaces. `hf_dashboard/Dockerfile` runs `uvicorn app:app`, which calls `init_db()` → `Base.metadata.create_all()` using `hf_dashboard`'s own Base. This is the live production schema today.
2. **`app/whatsapp/models.py:149`** — the richer model (Mapped[]-style, JSONB, unique constraint on `(name, language)`, FK relationship from `WAMessage.wa_template_id`) used by the separate `main.py` FastAPI backend. Alembic is configured (`alembic/env.py` → `app.db.session.Base`) but `alembic/versions/` is **empty** — no migrations have ever run. This app is not deployed to HF Spaces.

**Implication.** Both models must receive the same additive columns so whichever app touches the shared Postgres DB sees a consistent schema. The HF Space is the critical path; `app/whatsapp/` is maintained in parallel for forward-compatibility.

**Query sites that need an `is_draft=False` filter:**
- **`app/whatsapp/routes.py:274`** — the `GET /templates` list endpoint. Must hide drafts from consumers. ✅ add filter.
- `app/whatsapp/routes.py:315` — sync upsert keyed on `(name, language)`. Safe without a filter: incoming Meta rows match existing drafts only if the user literally submitted that draft, in which case the draft should be promoted to `is_draft=False` anyway. Add a comment noting this.
- `app/whatsapp/tasks.py:227` — Celery variant of the same upsert. Same reasoning.
- `hf_dashboard/services/database.py:23` — import only, no query. No change.
- `hf_dashboard/services/models.py` — no readers outside the new Template Studio page we're about to write.

**Step 2 — Add draft-specific fields (all nullable or with defaults so existing rows stay valid):**

```python
# Added to hf_dashboard/services/models.py::WATemplate
is_draft = Column(Boolean, nullable=False, default=False, server_default="0")
body_text = Column(Text, nullable=False, default="", server_default="")
header_format = Column(String(20), nullable=True)  # TEXT / IMAGE / VIDEO / DOCUMENT / None
header_asset_url = Column(String(512), nullable=True)
header_text = Column(String(60), nullable=True)
footer_text = Column(String(60), nullable=True)
buttons = Column(JSONType, nullable=False, default=list)
variables = Column(JSONType, nullable=False, default=list)
rejection_reason = Column(Text, nullable=False, default="", server_default="")
submitted_at = Column(DateTime, nullable=True)
meta_template_id = Column(String(64), nullable=True)
```

Note `is_draft` defaults to `False` (not `True`) so any row inserted by the existing `app/whatsapp/` code path is automatically treated as a non-draft synced template — matching today's behavior. The Studio explicitly sets `is_draft=True` when creating a new draft.

**One row per `(name, language)` pair.**
- `is_draft=True` → user is still editing, not submitted to Meta
- `is_draft=False` + `status=PENDING|APPROVED|REJECTED` → submitted, status reflects Meta's latest known state
- On successful Meta submission set `is_draft=False`, store the response `id` into `meta_template_id`, and stamp `submitted_at`

**Step 3 — Migration (mandatory, not optional).** `ensure_db_ready` uses `create_all` which does NOT ALTER existing tables, so new columns will silently be missing on an already-deployed DB and every `WATemplate` query will error at runtime. Options:

1. **One-shot migration script** (`scripts/migrate_wa_template_draft_fields.py`) that runs `ALTER TABLE wa_templates ADD COLUMN ...` for each new column, idempotent (check `PRAGMA table_info` / `information_schema.columns` first). Run once on HF Spaces before the first deploy of this feature. **Default choice — simplest, no new dependency.**
2. Introduce Alembic. Overkill for a single migration; defer unless we already need it elsewhere.

The migration script must be run **before** the new code is deployed, otherwise the app will crash on startup when SQLAlchemy tries to load a column that doesn't exist in the DB.

**Step 4 — Verify the audit.** After migration, run a smoke test of `app/whatsapp/` template-dependent flows (send a known approved template to a test recipient) to confirm nothing regressed.

---

## B3. `WhatsAppSender.create_template()` and sync

Port `scripts/submit_wa_templates.py::_build_components` and `submit_template` into `hf_dashboard/services/wa_sender.py` as instance methods:

```python
def create_template(
    self, name: str, category: str, language: str, components: list[dict],
) -> tuple[bool, dict | None, str | None]:
    """POST /{waba_id}/message_templates — submit a template for approval."""
    if not self.waba_id:
        return False, None, "WA_WABA_ID not set"
    url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
    payload = {"name": name, "language": language, "category": category, "components": components}
    try:
        r = httpx.post(url, headers=self._headers(), json=payload, timeout=self._timeout)
        if r.status_code // 100 == 2:
            return True, r.json(), None
        return False, None, f"{r.status_code}: {r.text}"
    except Exception as e:
        return False, None, str(e)
```

Also add:

- `delete_template(name)` → `DELETE /{waba_id}/message_templates?name=...`
- `sync_templates_from_meta(db)` → calls `list_templates()` (existing), upserts `WATemplate` rows with `status`, `quality_score`, `last_synced_at`, `is_draft=False`. Add `fields=rejected_reason` to the query params to surface rejection reasons for failed submissions. **Verify the field name against the Graph API version in use** (`WhatsAppSender.api_version`) — older versions return it under a different key; if `rejected_reason` is empty after a REJECTED sync, fall back to reading it from the template status webhook payload.

---

## B4. New page `pages/wa_template_studio.py`

Three-column layout mirroring other dashboard pages:

```
┌─ Left (scale=1) ──┐┌─ Center (scale=3) ──────┐┌─ Right (scale=1) ─┐
│ + New Draft       ││ Editor form              ││ Live WA preview   │
│ ──── Drafts ────  ││  Name     [_______]      ││ [WhatsApp-styled  │
│  • welcome_v2     ││  Category [MARKETING ▼]  ││  phone mockup of  │
│  • b2b_intro      ││  Language [en_US ▼]      ││  the rendered     │
│ ──── Submitted ── ││  Header   [IMAGE ▼]      ││  template]        │
│ 🟡 pending_review ││    [Upload image…]       ││                   │
│ 🟢 approved_intro ││    Preview: <img>        ││  Image guidance:  │
│ 🔴 rejected_promo ││  Body     [textarea]     ││   • Max 5 MB      │
│ ──── Synced ───── ││    {{1}} {{customer}}    ││   • 1200×628 rec. │
│  [🔄 Sync Meta]   ││  Footer   [_______]      ││   • JPG/PNG only  │
│                   ││  Buttons  [+ add]        ││  Document: PDF    │
│                   ││  [Save Draft] [Submit]   ││   up to 100 MB    │
└───────────────────┘└──────────────────────────┘└───────────────────┘
```

**Form behavior.**
- **Header format dropdown**: NONE / TEXT / IMAGE / VIDEO / DOCUMENT. This directly answers the user's question about "different specific templates for images vs PDFs" — it's one template type with a header-format flag, not separate templates. Picking IMAGE shows an image uploader; picking DOCUMENT shows a PDF uploader.
- **Image upload widget** (visible when format=IMAGE): `gr.File(file_types=[".jpg", ".jpeg", ".png"])` → on change, call `media_store.save_upload(file, "wa_headers")`, display the `public_url` and inline preview
- **Document upload** (format=DOCUMENT): `gr.File(file_types=[".pdf"])` — same flow
- **Body text**: textarea with live variable detection (`{{1}}`, `{{customer_name}}`). Variables list below auto-populates with example fields
- **Buttons**: repeater with type (URL / QUICK_REPLY / PHONE_NUMBER) + fields
- **Save Draft** button: upsert `WATemplate` with `is_draft=True`
- **Submit to Meta** button: build components via the same logic as `scripts/submit_wa_templates.py::_build_components`, call `WhatsAppSender.create_template()`, flip `is_draft=False`, show success/error inline
- **Sync from Meta**: calls `sync_templates_from_meta(db)`; refreshes the left-column list with fresh status badges

**Left column categories** (derived from `WATemplate` rows):
- Drafts — `is_draft=True`
- Submitted — `is_draft=False AND status=PENDING`
- Approved — `status=APPROVED`
- Rejected — `status=REJECTED` (show rejection reason on hover)

---

## B5. Image & document guidance (shown in right panel)

Pull from a new `hf_dashboard/config/whatsapp/media_guidelines.yml`:

```yaml
header_image:
  formats: [JPG, PNG]
  max_size_mb: 5
  recommended: "1200x628 px (WhatsApp crops to 1.91:1)"
  tips:
    - "Use product-on-white or lifestyle shots, not text screenshots"
    - "Keep key content in the center — edges may be cropped"
    - "Avoid heavy text overlays (Meta may reject)"
header_video:
  formats: [MP4, 3GPP]
  max_size_mb: 16
header_document:
  formats: [PDF]
  max_size_mb: 100
  tips:
    - "Keep filenames short and descriptive — they're visible to the recipient"
```

Rendered as a collapsible help block in the right column so the rules are discoverable without crowding the form.

---

## B6. Wiring into existing navigation

- Add `wa_template_studio` entry to `hf_dashboard/config/dashboard/sidebar.yml` near the existing `"Templates"` item (line 41)
- Default: **new standalone "Template Studio" sidebar item** (easier to discover, mirrors the pattern used by WA Inbox). Alternative: a tab inside the existing Templates & Media page. Will confirm with the user before committing.

---

## Files touched

**New:**
- `hf_dashboard/pages/wa_template_studio.py`
- `hf_dashboard/services/media_store.py`
- `hf_dashboard/services/wa_template_builder.py` — shared `_build_components` helper imported by both the CLI script and `WhatsAppSender.create_template()`
- `hf_dashboard/config/whatsapp/media_guidelines.yml`
- `scripts/migrate_wa_template_draft_fields.py` — idempotent ALTER script for the new `WATemplate` columns

**Modified:**
- `hf_dashboard/services/models.py` — additive fields on `WATemplate` + `public_url` and `kind` on `ProductMedia`
- `hf_dashboard/services/wa_sender.py` — add `create_template`, `delete_template`, `sync_templates_from_meta`
- `hf_dashboard/services/config.py` — add `PUBLIC_BASE_URL` setting
- `hf_dashboard/app.py` — mount `/media` StaticFiles
- `hf_dashboard/config/dashboard/sidebar.yml` — register the new page
- `scripts/submit_wa_templates.py` — import `_build_components` from the new shared helper instead of defining it locally
- `app/whatsapp/` existing `WATemplate` queries — add `is_draft=False` filter where drafts should not be visible

## End-to-end verification

1. Open Template Studio → click "+ New Draft" → fill in `name = test_template_01`, category MARKETING, language en_US, header IMAGE
2. Upload a 1200×628 JPG → preview renders in right column, public URL appears
3. Type body "Hello {{1}}, welcome to Himalayan Fibres" → variable list shows `{{1}}` with an example field
4. Click Save Draft → row appears under "Drafts" in left column, `WATemplate` row exists in DB with `is_draft=True`
5. Click Submit to Meta → Meta returns `id` and `status=PENDING` → row moves to "Submitted" with 🟡 badge
6. Wait (typically 24–48h), then click 🔄 Sync Meta → status updates to `APPROVED` 🟢 (or `REJECTED` 🔴 with reason)
7. Go to WhatsApp Inbox → send the approved template to a test contact → message delivered with header image
8. Image is served correctly at `${PUBLIC_BASE_URL}/media/wa_headers/<filename>` and Meta's CDN cached the header

## User decisions (locked in)

- **Meta submission** path: submit directly from the dashboard (reuse `scripts/submit_wa_templates.py` logic inside `WhatsAppSender.create_template`)
- **Image hosting** path: local `/media` route on the dashboard via FastAPI `StaticFiles`. `PUBLIC_BASE_URL` env var drives the external URL; production = HF Spaces HTTPS URL, localhost dev needs ngrok

## Remaining decisions to confirm before execution

- **Nav placement**: standalone "Template Studio" sidebar item (default) vs a tab inside the existing Templates page
