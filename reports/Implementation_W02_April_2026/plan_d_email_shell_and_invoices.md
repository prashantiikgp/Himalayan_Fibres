# Plan D — Email Templates (Locked Shell) + Drag-Drop Invoice Upload

## Context

Himalayan Fibres needs a small library of email templates for the customer journey, built on top of `main`. Current state:

- `hf_dashboard/services/email_sender.py` — Gmail API send, regex-based variable substitution. Works, but too primitive for `{% if invoice_url %}` guards.
- `hf_dashboard/services/models.py` — `Contact`, `Segment`, `EmailTemplate` (with `slug`/`html_content`/`subject_template`), `Campaign`, `EmailSend`. Everything we need except `EmailAttachment`.
- `hf_dashboard/pages/` — legacy `email_campaigns.py`, `email_inbox.py`, `templates_media.py` exist but will be replaced.

Founder's mental model, verbatim:
> "Keep the banner as well as the footer same, and fluctuate things in between — whether we inject the invoice, inject some images, or have some body text. I don't want to change my header image or the footer; they should always stay intact."

This maps cleanly to **locked top/bottom + flexible middle**. No MJML block engine. No Pydantic-validated block registry. Just HTML files + Jinja2 `{% include %}` + a tiny shared-settings YAML for branding variables.

### Locked decisions

- **Shell parts:** banner + social row + footer — each a Jinja2 partial, included by every template.
- **Shared branding vars** (banner URL, company address, phone, email, WhatsApp/IG/FB links, unsubscribe URL) live in one YAML file, substituted at render time. Change once, propagates everywhere.
- **Font/colors:** Amiri serif with Georgia fallback, text `#222`, body `#444`, accent `#2c3e50`, button `#232323`, footer bg `#f5f5f5`, link `#c38513`.
- **5 starter templates:** welcome, order_confirmation, order_shipped, order_delivered_feedback, operational_update.
- **Seed policy:** seed once on first boot; UI edits preserved after. `scripts/reseed_email_templates.py --force` for explicit resets.
- **Invoice bucket:** private Supabase `email-invoices`, 1-year signed URLs. `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in HF Space Secrets.
- **Invoice UI:** dropdown (recipient) + `gr.File` drop zone + attach button + status table. No per-row file inputs (Gradio limitation).
- **Delete legacy:** `email_campaigns.py`, `email_inbox.py`, `templates_media.py` get removed and replaced by `email_broadcast.py` + `email_analytics.py`.

---

## Architecture

```
hf_dashboard/templates/emails/
├── partials/
│   ├── banner.html           ← LOCKED (shared across all templates)
│   ├── social_row.html       ← LOCKED
│   ├── footer.html           ← LOCKED
│   └── middle/               ← Reusable building blocks for template bodies
│       ├── heading.html
│       ├── paragraph.html
│       ├── cta_button.html
│       ├── invoice_button.html   ← has {% if invoice_url %} baked in
│       ├── whatsapp_help_button.html
│       ├── info_card.html
│       └── hero_image.html
├── welcome.html
├── order_confirmation.html
├── order_shipped.html
├── order_delivered_feedback.html
└── operational_update.html

hf_dashboard/config/email/
├── shared.yml                ← branding vars (banner_url, address, etc.)
└── templates_seed/           ← one .meta.yml per template
    ├── welcome.meta.yml
    ├── order_confirmation.meta.yml
    ├── order_shipped.meta.yml
    ├── order_delivered_feedback.meta.yml
    └── operational_update.meta.yml
```

### Every template looks like

```html
{% include 'partials/banner.html' %}

<!-- MIDDLE: varies per template -->
{% include 'partials/middle/heading.html' with text='Thank you for your order!' emoji='🎉' %}
{% include 'partials/middle/paragraph.html' with body='Hello ' + first_name + ', ...' %}

<!-- raw HTML for order-specific content, pasted from founder's samples -->
<div style="...">...</div>

{% include 'partials/middle/invoice_button.html' %}
{% include 'partials/middle/whatsapp_help_button.html' %}
<!-- END MIDDLE -->

{% include 'partials/social_row.html' %}
{% include 'partials/footer.html' %}
```

### How render-time works

At send time (inside `_fire_campaign` / `_do_send` loop):

1. `attachments = load_campaign_attachments(db, campaign_id)` — one query, dict keyed by contact_id.
2. For each contact:
   - `vars = build_send_variables(contact, attachments, shared_config)` — merges contact fields, `invoice_url` (from attachment if present, empty string if not), and all `shared.yml` keys.
   - `html = render_template_by_slug(template.slug, vars)` — Jinja2 env with `FileSystemLoader(templates/emails/)` resolves the slug → template file → includes → renders with vars.
   - `sender.send_email(contact.email, rendered_subject, html)`.

Empty `invoice_url` → `invoice_button.html`'s `{% if invoice_url %}` guard hides the button silently. Recipients without an upload see a clean email; recipients with an upload see a button linking to the signed Supabase URL.

---

## Phase A — Partials, templates, seed loader, Jinja2 upgrade

**Goal:** 5 templates seeded into `email_templates` table, renderable from the sender. Zero UI changes, zero DB schema changes. Verifiable by seeding into local SQLite + eyeballing rendered HTML.

### A.1 Shared settings layer

- **`hf_dashboard/config/email/shared.yml`** — branding variables:
  ```yaml
  banner_url: "https://yxlofrkkzjkxtbowyryj.supabase.co/storage/v1/object/sign/wa-media/Whatsapp%20email%20Banner.jpg?token=..."
  banner_alt: "Himalayan Fibres"
  company_name: "Himalayan Fibres"
  address: "S.K. Complex, Khurje Wala Mohalla, Daulat Ganj, Lashkar, Gwalior 474001"
  company_email: "info@himalayanfibres.com"
  company_phone: "+91 8582952074"
  whatsapp_url: "https://wa.me/918582952074"
  instagram_url: "https://www.instagram.com/himalayan_fibres/"
  facebook_url: "https://www.facebook.com/Himalayanfibres"
  privacy_url: "https://www.himalayanfibres.com/privacy-policy"
  terms_url: "https://www.himalayanfibres.com/terms-conditions"
  refund_url: "https://www.himalayanfibres.com/refund-cancellation"
  unsubscribe_mailto: "info@himalayanfibres.com?subject=Unsubscribe"
  copyright_line: "© 2025 Himalayan Fibres. All rights reserved."
  ```

- **`hf_dashboard/services/email_shared_config.py`** — Pydantic loader:
  - `SharedEmailConfig(BaseModel)` with all fields from above, validated.
  - `load_shared_config() -> dict` — lru-cached reader.
  - Follows repo convention "every engine loads YAML through Pydantic".

### A.2 Partials

Create `hf_dashboard/templates/emails/partials/`:

- **`banner.html`** — full-width `<img src="{{ banner_url }}" ...>` inside a `<table>` row. Width 640–800px to match founder's samples.
- **`social_row.html`** — 3-icon row (WhatsApp/IG/FB), 32px icons, centered.
- **`footer.html`** — bg `#f5f5f5`, address, email, phone, policy links, unsubscribe, copyright. Pulls all strings from shared vars.

Create `hf_dashboard/templates/emails/partials/middle/`:

- **`heading.html`** — `<h2 style="text-align:center;font-size:22px;font-weight:bold;color:#222;margin:24px 20px 10px;font-family:'Amiri',serif;">{{ emoji }} {{ text }}</h2>`
- **`paragraph.html`** — `<p style="font-size:16px;color:#444;margin:10px 24px 20px;font-family:'Amiri',serif;">{{ body | safe }}</p>` (using `| safe` so Jinja2 doesn't escape inline HTML like `<strong>`).
- **`cta_button.html`** — `{{ label }}` → `{{ url }}`, fields: `label`, `url`, optional `bg_color` (default `#232323`), `text_color` (default `#ffffff`).
- **`invoice_button.html`** — wraps `cta_button` usage in `{% if invoice_url %}{% endif %}`. Label defaults `🧾 Download Invoice (PDF)`.
- **`whatsapp_help_button.html`** — small green button linking to `whatsapp_url`.
- **`info_card.html`** — boxed note, fields: `title`, `body`, `bg_color` (default `#f5f5f5`), `border_color` (default `#c38513`).
- **`hero_image.html`** — for mid-email image injections. Fields: `url`, `alt`.

### A.3 Five seed templates

Create `hf_dashboard/templates/emails/`:

- **`welcome.html`** — banner → heading → intro paragraph → 3 fibre-story info_cards → shop CTA → social → footer.
- **`order_confirmation.html`** — banner → heading ("Thank you for your order") → greeting → lifted HTML order summary from founder's sample → invoice_button → whatsapp_help_button → social → footer.
- **`order_shipped.html`** — banner → heading → shipment details (lifted HTML from founder's sample) → track CTA → invoice_button → social → footer.
- **`order_delivered_feedback.html`** — banner → heading → paragraph → info_card ("How was it?") → review CTA → social → footer.
- **`operational_update.html`** — banner → heading → 4 letter-style paragraphs → generic CTA → social → footer. Mirrors founder's "Payment Gateway Activated" sample.

Each template file has a companion `hf_dashboard/config/email/templates_seed/<slug>.meta.yml`:
```yaml
slug: order_confirmation
name: "Order Confirmation"
category: transactional
subject_template: "Order confirmed — thank you, {{ first_name }}!"
is_active: true
```

### A.4 Upgrade `email_sender.render_template` to Jinja2

`hf_dashboard/services/email_sender.py::render_template` is currently regex-based (`email_sender.py:153`). Swap it to use a module-level Jinja2 `Environment(loader=FileSystemLoader(templates/emails))` with `autoescape=False` (we're rendering HTML for email bodies, not user content).

Keep the public signature `render_template(template_content: str, variables: dict) -> str` so existing callers don't break — render the passed-in string via `env.from_string(template_content).render(**variables)`. Add a new helper `render_template_by_slug(slug: str, variables: dict) -> str` for the new path where the DB-stored HTML references partials.

**Critical:** the DB `EmailTemplate.html_content` will store the full rendered-by-file version (with `{% include %}` resolved into the partials' HTML) NOT the raw file text. Rationale: the editor page (future) and sender both read from DB; if DB stored the raw includes, every send would re-resolve file I/O. We compile includes to concrete HTML once at seed time.

So seed time flow: read `.html` file from disk → `env.from_string(file_content).render(**shared_config)` → store result in `html_content`. At send time: render that stored string with per-recipient vars (`first_name`, `invoice_url`, etc.).

This means shared-config changes require a reseed (or a boot hook that re-renders templates if the shared.yml mtime is newer). For v1, reseed via the script. Document it.

### A.5 Template seed loader

- **`hf_dashboard/services/template_seed.py`**:
  - `SeedMeta(BaseModel)`: slug, name, category, subject_template, is_active.
  - `seed_email_templates(db, *, force=False)`:
    1. Glob `hf_dashboard/config/email/templates_seed/*.meta.yml`.
    2. For each: validate as `SeedMeta`, find the matching `templates/emails/<slug>.html`, read it.
    3. Render the file with shared config vars → get the concrete HTML (partials inlined, branding filled in, per-recipient placeholders like `{{ first_name }}` left untouched since they're not in shared config).
    4. If `force=True` OR no row exists with this slug: upsert into `email_templates` table.
  - If seed loader finds a `.meta.yml` without a matching `.html` or vice-versa: log warning, skip.

### A.6 Wire seed into `ensure_db_ready`

`hf_dashboard/services/database.py::ensure_db_ready` — after `create_all`, call `seed_email_templates(db)`. Idempotent.

### A.7 Reseed script

`scripts/reseed_email_templates.py`: CLI wrapper → `seed_email_templates(db, force=True)`.

### Phase A verify

Without the Space — I can run a smoke test script locally via `python -c "..."` that:
1. Calls `seed_email_templates(session, force=True)` against a temp SQLite.
2. Queries the 5 templates.
3. Calls `render_template(html, {'first_name':'Alisha','invoice_url':'https://example.com/i.pdf'})` on `order_confirmation`.
4. Asserts the output contains the banner URL, 'Alisha', 'https://example.com/i.pdf', and the footer address.

Per `CLAUDE.md`: **no local app runs**. A Python smoke script is allowed; it's not launching the dashboard. Full Playwright verify happens at Phase C.

---

## Phase B — EmailAttachment + Supabase helper + personalization

**Goal:** data layer for invoices. No UI yet.

### B.1 `EmailAttachment` model

`hf_dashboard/services/models.py`:

```python
class EmailAttachment(Base):
    __tablename__ = "email_attachments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    contact_id = Column(String(64), ForeignKey("contacts.id"), nullable=False, index=True)
    kind = Column(String(32), default="invoice")
    file_name = Column(String(255), default="")
    storage_bucket = Column(String(64), default="email-invoices")
    storage_path = Column(String(512), default="")
    signed_url = Column(String(1024), default="")
    content_type = Column(String(64), default="application/pdf")
    size_bytes = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=_utcnow)
    __table_args__ = (UniqueConstraint("campaign_id", "contact_id", "kind"),)
```

New table — `create_all` auto-creates on next boot. No migration.

### B.2 Supabase helper

`hf_dashboard/services/supabase_storage.py`:

```python
def ensure_bucket(bucket: str, public: bool = False) -> None
def upload_file(bucket: str, path: str, file_bytes: bytes, content_type: str) -> str  # returns signed URL
def create_signed_url(bucket: str, path: str, expires_in: int = 31_536_000) -> str
def delete_file(bucket: str, path: str) -> None
```

Package: `storage3` (lighter than full `supabase` SDK). Add to `requirements.txt`.

Env vars (HF Space Secrets, **manual step for founder**):
- `SUPABASE_URL` = `https://yxlofrkkzjkxtbowyryj.supabase.co`
- `SUPABASE_SERVICE_KEY` = service_role key

Bucket `email-invoices` auto-created on first `upload_file` call.

### B.3 Personalization helper

`hf_dashboard/services/email_personalization.py`:

```python
def load_campaign_attachments(db, campaign_id: int) -> dict[str, EmailAttachment]:
    """One query, keyed by contact_id."""

def build_send_variables(contact, attachments: dict, shared_config: dict) -> dict:
    return {
        **shared_config,                    # banner_url, address, etc.
        "first_name": contact.first_name or "there",
        "last_name": contact.last_name or "",
        "name": (...).strip() or "there",
        "company_name": contact.company or "",
        "email": contact.email,
        "invoice_url": (att.signed_url if (att := attachments.get(contact.id)) else ""),
    }
```

### Phase B verify

Python smoke test:
1. Create a dummy `EmailAttachment` row for a test contact + campaign.
2. `vars = build_send_variables(contact, attachments, shared_config)` → assert `invoice_url` populated.
3. Render `order_confirmation` with those vars → assert `Download Invoice` button HTML present.
4. Drop the attachment, re-render → assert button HTML NOT present (hidden by `{% if %}`).

---

## Phase C — Broadcast + Analytics pages + legacy cleanup

**Goal:** founder can select template, select segment, drag-drop invoices per recipient, send, and see results.

### C.1 New `email_broadcast.py`

`hf_dashboard/pages/email_broadcast.py` + `hf_dashboard/config/pages/email_broadcast.yml`.

Layout (Gradio):
```
Row:
  Left column (scale=1):
    Dropdown: Segment
    Dropdown: Template
    Textbox (readonly): subject preview
    Accordion: "📎 Invoice attachments" (collapsed by default)
      Dropdown: Recipient (populated when segment resolved)
      File: Invoice PDF (type=binary)
      Button: Attach
      Dataframe: Recipient | Email | Invoice status
      Button: Remove attachment
    Button: Send Now
    Button: Schedule...
  Right column (scale=2):
    HTML: preview iframe (renders selected template with sample vars)
```

Handlers use the personalization helper + Gmail API sender. Draft campaign created lazily on first attach (see plan §B flow).

### C.2 New `email_analytics.py`

Per the earlier design that was already working — KPI strip, tab list (Sent/Scheduled/Drafts), recipient table on the right. Reads from `Campaign` + `EmailSend` tables directly. Keep config in `hf_dashboard/config/pages/email_analytics.yml`.

### C.3 Delete legacy pages

Remove from disk AND `hf_dashboard/config/dashboard/sidebar.yml`:
- `hf_dashboard/pages/email_campaigns.py`
- `hf_dashboard/pages/email_inbox.py`
- `hf_dashboard/pages/templates_media.py`

Add sidebar entries for `email_broadcast` and `email_analytics`.

### Phase C verify (Playwright on live HF Space)

1. Commit Phase C → `python scripts/deploy_hf.py` → wait for Running.
2. Navigate to `https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/`.
3. Email Broadcast page loads.
4. Select segment with 2 test recipients.
5. Select `order_confirmation` template → preview shows banner + sample content + footer.
6. Open attachments accordion → recipient dropdown populated → select recipient 1 → drag-drop a sample PDF → click Attach → dataframe shows `✓ filename.pdf`.
7. Click Send Now → success toast, 2 sends recorded.
8. Open founder's inbox:
   - Recipient 1: Download Invoice button visible, href = Supabase signed URL, HTTP 200 returns PDF.
   - Recipient 2: Download Invoice button hidden (no attachment).
9. Navigate to Email Analytics → new campaign visible → click → recipient table shows both as `sent`.
10. Negative: remove attachment for recipient 1, re-send, verify button now hidden in their email.

---

## Critical files

### Create
- `hf_dashboard/config/email/shared.yml`
- `hf_dashboard/config/email/templates_seed/welcome.meta.yml`
- `hf_dashboard/config/email/templates_seed/order_confirmation.meta.yml`
- `hf_dashboard/config/email/templates_seed/order_shipped.meta.yml`
- `hf_dashboard/config/email/templates_seed/order_delivered_feedback.meta.yml`
- `hf_dashboard/config/email/templates_seed/operational_update.meta.yml`
- `hf_dashboard/templates/emails/partials/banner.html`
- `hf_dashboard/templates/emails/partials/social_row.html`
- `hf_dashboard/templates/emails/partials/footer.html`
- `hf_dashboard/templates/emails/partials/middle/heading.html`
- `hf_dashboard/templates/emails/partials/middle/paragraph.html`
- `hf_dashboard/templates/emails/partials/middle/cta_button.html`
- `hf_dashboard/templates/emails/partials/middle/invoice_button.html`
- `hf_dashboard/templates/emails/partials/middle/whatsapp_help_button.html`
- `hf_dashboard/templates/emails/partials/middle/info_card.html`
- `hf_dashboard/templates/emails/partials/middle/hero_image.html`
- `hf_dashboard/templates/emails/welcome.html`
- `hf_dashboard/templates/emails/order_confirmation.html`
- `hf_dashboard/templates/emails/order_shipped.html`
- `hf_dashboard/templates/emails/order_delivered_feedback.html`
- `hf_dashboard/templates/emails/operational_update.html`
- `hf_dashboard/services/email_shared_config.py`
- `hf_dashboard/services/template_seed.py`
- `hf_dashboard/services/supabase_storage.py`
- `hf_dashboard/services/email_personalization.py`
- `hf_dashboard/pages/email_broadcast.py`
- `hf_dashboard/pages/email_analytics.py`
- `hf_dashboard/config/pages/email_broadcast.yml`
- `hf_dashboard/config/pages/email_analytics.yml`
- `scripts/reseed_email_templates.py`

### Modify
- `hf_dashboard/services/email_sender.py` — upgrade `render_template` to Jinja2, add `render_template_by_slug` helper
- `hf_dashboard/services/models.py` — add `EmailAttachment`
- `hf_dashboard/services/database.py` — call `seed_email_templates` in `ensure_db_ready`
- `hf_dashboard/config/dashboard/sidebar.yml` — remove legacy entries, add broadcast/analytics
- `requirements.txt` — add `Jinja2` (already transitively via Gradio, but pin explicitly), `storage3`

### Delete
- `hf_dashboard/pages/email_campaigns.py`
- `hf_dashboard/pages/email_inbox.py`
- `hf_dashboard/pages/templates_media.py`

---

## Verification strategy

- **Phase A:** Python smoke script (`python -c "..."`) against temp SQLite. No Space deploy yet — templates aren't hooked into the UI.
- **Phase B:** Python smoke script verifying attachment lookup + Jinja2 `{% if invoice_url %}` guard.
- **Phase C:** Full Playwright MCP against live HF Space after `python scripts/deploy_hf.py`.

Per `CLAUDE.md`: never run the app locally. All end-to-end verification happens on HF after deploy.

---

## Open items (deferred, not blocking v1)

1. **Shared-config change propagation** — v1 requires reseed after editing `shared.yml`. v2 could auto-reseed on boot if shared.yml mtime > max template row mtime. 15-line change, deferred.
2. **Banner signed URL rotation** — token expires 2027. Before then, flip file to public or reseed.
3. **Bulk invoice upload** (ZIP → filename matching) — v2, not needed for small batches.
4. **Template editor UI** — v2. For now, editing templates = editing files. Founder asks me to change copy → I edit file → reseed → deploy.
5. **Scheduled-send worker** — if we need it, resurrect the pattern from the lost engine. For v1, "Send Now" is enough.
