# PLAN — Email Template Coverage & Standardization

> **Revision history**
> - **v3 (2026-05-06)** — locks in founder decisions and reflects two
>   discoveries that drastically simplify Phase C:
>   - **Founder decisions resolved (D1–D7):** D1 grandfather; **D2 = full
>     rewrite all 11 to founder-warm + yarn-first highest-quality voice**;
>     D3 proforma = HTML body + uploaded PDF attachment via existing
>     `email_attachments` table; D4 price list = Drive-hosted PDF, location
>     forthcoming from founder; D5 seasonal = manual broadcast; D6 Phase D
>     deferred; D7 keep `abandoned_cart_recovery` on disk.
>   - **Discovery 1 — `email_attachments` table already exists**
>     (`hf_dashboard/services/models.py:188`). Per-recipient PDFs are
>     uploaded to Supabase Storage bucket `email-invoices`, a 1-year signed
>     URL is generated, and `build_send_variables`
>     (`services/email_personalization.py:96`) injects `{{ invoice_url }}`
>     into the template at send time. **Email never carries actual MIME
>     attachments** — PDFs are downloadable links. Phase C's MIMEMultipart
>     rebuild is therefore unnecessary; we extend the existing pattern with
>     a new `kind` value (`price_list`) and a parallel `{{ price_list_url }}`
>     variable.
>   - **Discovery 2 — Supabase bucket `wa-template-images` is public** and
>     contains a full image library (hand-spinning, fibre & fields, village,
>     hero banners, product photos by category). Templates can use direct
>     public URLs — no signed-URL refresh, no Drive integration needed for
>     images. Drive is only used for the price-list PDF (founder-uploaded
>     once per quarter, then mirrored to Supabase `email-invoices` per send).
>   - **`order_in_production` framing corrected:** "we are preparing your
>     order, picking from bundles, packaging" — NOT "on the loom." Yarn,
>     not fabric.
>   - **Brand kit consumed from `hf_dashboard/config/email/shared.yml`** —
>     banner, colors, fonts, social links, copyright already centralized.
> - **v2 (2026-05-06)** — addresses 11 review findings on v1:
>   - Phase A rebuilt around the actual on-disk variable surface (most "orphans" are fully static or have style-only vars, not richly templated as v1 assumed).
>   - Category-enum migration tabulated (Section 2.2) with one-to-one mapping for every existing seeded slug.
>   - **D6 flipped:** schema additions (Phase 0) ship *before* the flow engine, so flows can read `flow` / `flow_step` metadata. Index regeneration (Phase D) stays deferrable.
>   - **D1 firmed:** grandfathered slugs are explicit in the migration table; new slugs follow the convention. Both styles co-exist permanently — accepted, documented.
>   - Idempotency-key collision (same-day re-send of a corrected price list) called out in Phase C with attachment-hash inclusion.
>   - Phase C: feature-flagged sender rollout, MIME sniffing via `python-magic`, Pydantic-layer attachment validation, `EmailSend` audit-trail columns, Drive read-scope as a *verification* step (not an assumption).
>   - Per-phase test plan added (Section 7).
>   - "Do nothing" baseline added (Section 0).
>   - `transactional_price_list_share` slug shortened to `price_list_share`.
>   - Phase A.5 (voice rewrites) numbered in §8 sequencing.
> - **v1 (2026-05-06)** — initial draft (this file's first commit).

> **Scope:** content + registry layer for email templates. Closes the gaps in
> the Sample Dispatch flow, Order/Purchase flow, and Campaign categories that
> the founder named on 2026-05-06. Standardizes the meta layer to mirror the
> WhatsApp registry pattern and adds first-class attachment support so price
> lists / proformas can ride a template instead of being one-off ad-hoc sends.
>
> **Non-scope:**
> - Flow orchestration (the engine that *chains* these templates step-by-step
>   on a per-contact timer): see `PLAN_flows.md`.
> - Studio / Broadcast / Single-send UI changes: see `PLAN_email.md`.
> - WhatsApp template additions: see `PLAN_whatsapp.md`.
> - Seasonal-send automation (no scheduler concept of "fire on Diwali"); these
>   stay manual broadcasts in v1.

---

## Section 0 — "Do nothing" baseline

If we ship none of this:

- Founder hand-attaches PDFs to every price-list send (no template path).
- Sample Dispatch flow can't be productized — three of five steps either
  don't exist or aren't picker-discoverable. The founder has to remember the
  cadence and trigger each step manually.
- Order Lifecycle flow has a 7-21 day silence between
  `order_confirmation` and `order_shipped` because `order_in_production`
  doesn't exist. B2B leads have already escalated by email about this.
- The 11 on-disk-but-unseeded templates (product/story/seasonal) are dead
  code — they exist in the repo but the picker can't see them, so they're
  never sent. Authoring effort already paid, value zero.
- Phase 7 flow engine (`PLAN_flows.md`) lands but has nothing to chain
  beyond the 6 currently seeded templates.

This plan is the precondition for that flow engine being useful.

---

## Section 1 — Audit (current state, verified 2026-05-06)

### 1.1 Sample Dispatch flow (founder named 4 stages)

| Stage | Template | On-disk? | Seeded? | Variable surface (actual) |
|---|---|---|---|---|
| 0. Thanks-for-interest | `sample_request_received` | ✅ | ✅ | `first_name`, `fibre_requested?`, `book_call_link?` |
| 1. **Swatch preparation** | — | ❌ | ❌ | needs authoring |
| 2. Dispatch | `sample_shipped` | ✅ | ✅ | `first_name`, `courier_name`, `tracking_id`, … |
| 3. **Price list share (image + PDF)** | — | ❌ | ❌ | needs authoring + attachment infra |
| 4. T+7 follow-up | `post_sample_followup` | ✅ | ✅ | `first_name`, `fibre_sent`, `sample_dispatched_at?`, `proforma_link?`, `book_call_link?` |
| Entry CTA | `sample_invitation` | ✅ static | ❌ | **no per-recipient vars in HTML today** |

### 1.2 Order / Purchase flow (founder named 5 stages)

| Stage | Template | On-disk? | Seeded? | Variable surface |
|---|---|---|---|---|
| 0. Thanks-for-purchasing | `order_confirmation` | ✅ | ✅ | full set (`order_number`, `items_html`, …) |
| 1. **In-production** | — | ❌ | ❌ | needs authoring |
| 2. Invoice / Proforma | `proforma_invoice` | ✅ partial | ❌ | **only style + total/subtotal/shipping_estimate; no `first_name`, no `proforma_number`** |
| 3. Dispatch | `order_shipped` | ✅ | ✅ | full set |
| 4. Feedback | `order_delivered_feedback` | ✅ | ✅ | `first_name` |

### 1.3 Campaign templates (founder named 3 buckets) — variable audit

| Slug | On-disk? | Seeded? | Per-recipient vars in HTML today |
|---|---|---|---|
| `hemp_focus` / `wool_focus` / `nettle_focus` / `collections_focus` | ✅ | ❌ | **none — fully static** |
| `yarn_categories_intro` | ✅ | ❌ | none (only loop-locals + style) |
| `blog_founder_letter` | ✅ | ❌ | `quarter` only |
| `blog_process_deep_dive` | ✅ | ❌ | none |
| `blog_field_origin_story` | ✅ | ❌ | `region_name` only |
| `blog_customer_case_study` | ✅ | ❌ | `customer_name` only |
| `diwali_greetings` | ✅ | ❌ | none (only `_year` macro) |
| `harvest_announcement` / `year_end_recap` | ✅ | ❌ | none |
| `abandoned_cart_recovery` | ✅ | ❌ | `total` only |
| `operational_update` | ✅ | ✅ | `first_name`, `update_title`, `update_body_html`, … |
| `b2b_introduction` | ✅ | ✅ | `company_name` |
| `welcome` / `welcome_day_3_sustainability` / `onboarding_day_14_first_order` | ✅ | ✅ | `first_name` |
| `winback_60d_silent` | ✅ | ✅ | `first_name`, `last_engaged_at?` |

**Critical implication:** the v1 plan assumed seeding the orphans was a 30-min meta-file write. False. **11 of 12 orphan templates have no `{{ first_name }}` in their HTML today** — they're broadcast-style static copy. Seeding them as-is means "everyone gets the exact same body, no warm greeting." The founder's voice rules
(`feedback_template_voice_english.md`, `feedback_yarn_first_emphasis.md`)
require at minimum a `Hello {first_name},` opening. So most orphans need an
HTML edit to add personalization *and* a meta file. Phase A is split
accordingly (§3).

### 1.4 Registry-layer gaps (unchanged from v1)

1. **No central index file.** WA has `config/whatsapp/templates.yml`. Email
   has 12 scattered `.meta.yml` files plus 12 `.html` files with no meta.
2. **Inconsistent `category` values.** Current set: `transactional`,
   `nurture`, `campaign`, `announcement` — no enum, no namespacing for
   sample / order / story / seasonal.
3. **No attachment field in meta.** `SeedTemplateMeta`
   (`hf_dashboard/services/template_seed.py:52-62`) has no `attachments`.
4. **No attachment support in the sender.**
   `EmailSender.send_email` (`hf_dashboard/services/email_sender.py:179-193`)
   builds `MIMEMultipart("alternative")` — text + html only.
5. **`EmailSend` row carries no attachment audit trail.** Required for
   "did we send the right price list to lead X?" reconstruction.
6. **Drive PDF support is unverified.** No Drive client found in the email
   side; blog Drive integration is referenced in memory but not grepped in
   `hf_dashboard/services/`. Phase C must verify scope before depending on
   it.

---

## Section 2 — Target state

### 2.1 Naming convention (codified, applies to NEW templates only)

Slugs: `{flow_or_kind}_{stage_or_subject}` lowercase snake_case.

| Prefix | Meaning |
|---|---|
| `sample_` | Sample Dispatch flow stages |
| `order_` | Order / Purchase Lifecycle flow stages |
| `welcome_` / `onboarding_` | Welcome flow stages |
| `campaign_product_` | Per-fibre / per-category education |
| `campaign_story_` | "How we work" / behind the scenes |
| `campaign_seasonal_` | Time-of-year sends |
| `campaign_general_` | One-off announcements / news |
| `cold_` | Cold-outreach entry templates |
| `winback_` | Re-engagement |
| `transactional_` | Standalone transactional (non-flow) |

**Decision logged:** existing slugs that don't match the convention
(`hemp_focus`, `b2b_introduction`, `diwali_greetings`, `abandoned_cart_recovery`,
the four `blog_*`, `welcome_day_3_sustainability`, `onboarding_day_14_first_order`,
`yarn_categories_intro`, `winback_60d_silent`) are **grandfathered** —
no rename, no DB migration. The convention applies only to the 3 new
authored templates and any future additions. Two styles co-exist; the
`category` field provides the discoverability wrapper that the slug pattern
otherwise would.

### 2.2 `category` enum migration (every seeded file mapped)

```python
EmailCategory = Literal[
    "transactional",       # invoice / proforma / shipping notice
    "sample_flow",         # any step of Sample Dispatch
    "order_flow",          # any step of Order Lifecycle
    "welcome_flow",        # any step of B2B Welcome
    "campaign_product",    # fibre / category education
    "campaign_story",      # founder / process / origin / case
    "campaign_seasonal",   # Diwali, harvest, year-end
    "campaign_general",    # ad-hoc announcements
    "cold_outreach",       # first-touch
    "winback",             # re-engagement
]
```

**Migration table (every currently-seeded slug):**

| Slug | Current category | New category | Action |
|---|---|---|---|
| `welcome` | `nurture` | `welcome_flow` | edit meta file |
| `welcome_day_3_sustainability` | (not seeded yet) | `welcome_flow` | new meta file |
| `onboarding_day_14_first_order` | `nurture` (per repo) | `welcome_flow` | edit meta file |
| `b2b_introduction` | `campaign` | `cold_outreach` | edit meta file |
| `order_confirmation` | `transactional` | `order_flow` | edit meta file |
| `order_shipped` | `transactional` | `order_flow` | edit meta file |
| `order_delivered_feedback` | `transactional` | `order_flow` | edit meta file |
| `sample_request_received` | `transactional` | `sample_flow` | edit meta file |
| `sample_shipped` | `transactional` | `sample_flow` | edit meta file |
| `post_sample_followup` | `transactional` | `sample_flow` | edit meta file |
| `winback_60d_silent` | (per repo) | `winback` | confirm/edit |
| `operational_update` | `announcement` | `campaign_general` | edit meta file |

12 currently-seeded files; all need a one-line `category:` change as part of
**Phase 0** (schema tightening). No migration script required — these are
YAML files in the repo, not DB rows.

> **Note on DB rows:** the live `EmailTemplate.category` column is populated
> by `seed_email_templates(...)` from the YAML on every boot (or on `--force`
> reseed). Updating the YAML and reseeding propagates the new categories.
> No SQL migration needed because the column is a free-form `String`, not a
> Postgres `ENUM`.

### 2.3 Meta schema additions (Phase 0) — slimmed in v3

Add to `SeedTemplateMeta`:

```python
class SeedTemplateMeta(BaseModel):
    # existing fields …
    flow: str | None = None                      # "sample" | "order" | "welcome" | None
    flow_step: int | None = None                 # 0-indexed step within flow
    expected_attachments: list[Literal["invoice", "price_list"]] = Field(default_factory=list)
    category: EmailCategory                      # tightened from `str` to `Literal`
```

**No `TemplateAttachmentSpec` class.** v2 was over-designed — we don't
need `source`, `max_size_mb`, MIME-sniff metadata at the template level
because attachments are decoupled (uploaded via UI, stored in Supabase,
linked via `email_attachments` table). The template just declares which
**kinds** of `email_attachments` it expects to find variables for. UI
uses this to show "this template expects a price-list PDF — attach one?"
prompt.

**Rationale for `flow` / `flow_step` on meta:** the flow engine reads
template meta when it builds a `Flow` definition — tagging makes the editor
suggest templates in the correct order. It's metadata, not enforcement.

### 2.4 `EmailSend` audit trail (v2 plan dropped in v3)

The v2 plan added `attachment_filename` / `_size_bytes` / `_sha256` to
`email_sends`. **Dropped in v3** — `email_attachments` already carries
`file_name`, `size_bytes`, and the storage path is reconstructable from
`storage_bucket` + `storage_path`. The audit trail is the join of
`email_sends.campaign_id + .contact_id` against `email_attachments`. No
new columns, no migration.

### 2.5 Central registry (`config/email/templates.yml`) — Phase D, deferred

Generated by `scripts/regen_email_template_index.py` walking
`templates_seed/*.meta.yml`. Per-template `.meta.yml` files remain the
source of truth (the seeder reads them); the index is a read-only
human + flow-editor convenience. CI test diffs the regenerator output
against the committed index to prevent drift.

---

## Section 3 — Phase A: orphan triage + targeted seeding

Effort revised from v1 estimate of 0.5 day to **1.5–2 days** based on the
1.3 audit.

### Phase A.0 — verify on-disk-only inventory (10 min)

`grep -L 'meta.yml' hf_dashboard/templates/emails/*.html` cross-referenced
with `ls hf_dashboard/config/email/templates_seed/` confirms the orphan
list. (Done as part of this plan; reproduce as the Phase A first step
to catch any drift.)

### Phase A.1 — seed the 4 templates that already have usable variable surface

These can ship as `.meta.yml` files alone; their HTML doesn't need editing
for v1.

| Slug | New category | Required vars (per HTML) | Optional vars | Subject template |
|---|---|---|---|---|
| `proforma_invoice` | `transactional` | `subtotal`, `total_due`, `shipping_estimate` | `valid_until`, `notes` | "Proforma for your records" |
| `blog_founder_letter` | `campaign_story` | `quarter` | `featured_image_url` | "A quarterly note from {{ quarter }}" |
| `blog_field_origin_story` | `campaign_story` | `region_name` | `featured_image_url` | "From the slopes of {{ region_name }}" |
| `blog_customer_case_study` | `campaign_story` | `customer_name` | `featured_image_url` | "How {{ customer_name }} uses our yarn" |

Files to CREATE (4):
- `hf_dashboard/config/email/templates_seed/proforma_invoice.meta.yml`
- `hf_dashboard/config/email/templates_seed/blog_founder_letter.meta.yml`
- `hf_dashboard/config/email/templates_seed/blog_field_origin_story.meta.yml`
- `hf_dashboard/config/email/templates_seed/blog_customer_case_study.meta.yml`

Caveat: these templates lack `first_name` greeting, so they read as
broadcast-grade not founder-warm. Acceptable for v1 (founder-on-demand
sends, not flow-fired). Personalization upgrade tracked as a follow-up,
not blocking.

### Phase A.2 — voice + personalization upgrade for the 8 fully-static templates

| Slug | Current state | Decision needed (D2) |
|---|---|---|
| `sample_invitation` | static | **Edit:** add `first_name`, soften CTA. Cold-outreach entry must read warm. |
| `hemp_focus`, `wool_focus`, `nettle_focus`, `collections_focus` | static, fibre-led | **Spot-check vs Yarn-First:** if body still leads with fibre over finished yarn (likely, per slug name), rewrite the lead. Add `first_name`. |
| `yarn_categories_intro` | static | **Edit:** add `first_name`, optional `hero_image_url`. |
| `blog_process_deep_dive` | static | **Edit:** add `first_name`. Body voice already in editorial form per the seeded `post_sample_followup` style; spot-check. |
| `harvest_announcement` | static | **Edit:** add `first_name`, `harvest_year`, `availability_date`. Seasonal but data-bearing. |
| `year_end_recap` | static | **Edit:** add `first_name`, `recap_body_html` (founder writes per-year body). |
| `diwali_greetings` | static | **Edit:** add `first_name`. Stays single-paragraph short. |
| `abandoned_cart_recovery` | static, only `total` var | **Defer:** no cart system today. Skip seeding entirely until that flow exists. |

Per-template effort: ~30 min (HTML edit to add 1-3 vars + voice spot-check
+ meta file). Total for the 8: ~4 hours.

Files to CREATE / MODIFY:
- 7 `.meta.yml` files (skipping `abandoned_cart_recovery`).
- 7 `.html` edits to add personalization variables.

### Phase A.3 — author the 3 new campaign templates (no current HTML)

The v1 plan listed 6 new campaign meta files for templates that don't
exist on disk. After audit, only these need authoring (the rest are
covered by A.2 above):

| Slug | Category | Why |
|---|---|---|
| `cold_b2b_sample_offer` | `cold_outreach` | distinct from `b2b_introduction`; leads with sample CTA, not company intro |
| (no others — A.2 covers product/story/seasonal) | | |

Actually, on review: **defer this to a future plan.** Current `b2b_introduction` + the upgraded `sample_invitation` (A.2) already cover the cold-outreach surface. Adding more cold templates is a content decision, not a system gap. Removed from scope.

### Phase A — acceptance criteria

- All 11 modified/new meta files validate against the tightened
  `SeedTemplateMeta` schema (Phase 0 ships first).
- `python scripts/seed_email_templates.py --force` runs without warnings.
- Studio template picker (`/email-templates`) lists 19 active templates
  (12 existing + 4 from A.1 + 7 from A.2; -1 `abandoned_cart_recovery`).
- Each modified template renders successfully via
  `render_template_by_slug(slug, example_vars)` with the example values
  declared in its meta.

---

## Section 4 — Phase B: author the 3 missing Tier-1 templates

The three flow stages with no template anywhere. Each author session
follows the workflow detailed in §6.

### B.1 `sample_swatch_preparation` (Sample flow, step 1)

- File: `hf_dashboard/templates/emails/sample_swatch_preparation.html`
- Meta: `hf_dashboard/config/email/templates_seed/sample_swatch_preparation.meta.yml`
- `category: sample_flow`, `flow: sample`, `flow_step: 1`
- Required vars: `first_name`, `fibre_requested`
- Optional vars: `expected_dispatch_date`, `prep_image_url`, `book_call_link`
- Subject: `"We're hand-picking your {{ fibre_requested }} swatches, {{ first_name }}"`
- Voice: `founder_warm` (mirrors `sample_request_received.html` exactly)

### B.2 `price_list_share` (manual / Sample flow, step 4)

- File: `hf_dashboard/templates/emails/price_list_share.html`
- Meta: `hf_dashboard/config/email/templates_seed/price_list_share.meta.yml`
- `category: transactional`, `flow: null`
- `expected_attachments: ["price_list"]`
- Required vars: `first_name`
- Optional vars: `valid_until`, `notes`, `book_call_link`
- **Variable injected by Phase C:** `{{ price_list_url }}` (signed URL
  to the per-recipient PDF). Template body renders a "Download price list"
  CTA button pointing to this URL. Hero image still pulled from
  `wa-template-images` bucket so the email is visual without the click.
- Subject: `"Our current yarn price list, {{ first_name }}"`
- **Depends on Phase C** (price_list kind in `build_send_variables` +
  `attach_current_price_list` helper).

### B.3 `order_in_production` (Order flow, step 1)

> **Framing rule (founder, 2026-05-06):** these are yarns, not fabrics.
> Never say "on the loom." Use "we're packaging your order, picking from
> the bundles, getting it ready." Generic warm check-in, not detailed.

- File: `hf_dashboard/templates/emails/order_in_production.html`
- Meta: `hf_dashboard/config/email/templates_seed/order_in_production.meta.yml`
- `category: order_flow`, `flow: order`, `flow_step: 1`
- Required vars: `first_name`, `order_number`
- Optional vars: `expected_dispatch_date`
- Subject: `"Your order {{ order_number }} is being prepared, {{ first_name }}"`
- Body: 3-block structure. Hero image (e.g. "Men Packing Bundles" from
  `wa-template-images`) → warm two-paragraph note that we're picking
  from bundles and packing → "looking forward to your feedback once it
  lands." No detailed updates per send (founder explicitly does NOT want
  this to be data-bearing).

### Phase B — acceptance criteria

- Each renders with example vars (per-template render test added).
- `price_list_share` blocks send when `price_list_pdf` attachment missing
  (422 from `POST /api/v2/email/test-sends`).
- All 3 visible in Studio picker filtered to their category.
- Voice spot-check by the founder before merging (manual gate).

---

## Section 5 — Phase C: extend existing signed-URL attachment pattern

**Major v3 simplification.** The `email_attachments` table + Supabase
Storage `email-invoices` bucket + `{{ invoice_url }}` template variable
ALREADY ship invoice PDFs end-to-end. Email body carries a download link,
not a MIME attachment. We extend the same pattern for price lists.

### C.1 Extend `email_attachments.kind` enum

Today `kind` is a free-form `String(32)` defaulting to `'invoice'`. Add a
second supported value: `'price_list'`. No DDL change needed (column is
free-form). Add a Python `Literal["invoice", "price_list"]` alias on the
ORM layer for type safety.

### C.2 Extend `build_send_variables` to expose `price_list_url`

`hf_dashboard/services/email_personalization.py:96` currently does:

```python
base["invoice_url"] = att.signed_url if (att and att.kind == "invoice") else ""
```

Generalize to walk all attachments for the campaign+contact, exposing one
template variable per kind:

```python
attachments_by_kind = {att.kind: att for att in attachments_for_contact}
base["invoice_url"]    = attachments_by_kind.get("invoice", _empty).signed_url or ""
base["price_list_url"] = attachments_by_kind.get("price_list", _empty).signed_url or ""
```

This makes the template variable surface predictable — every template can
reference `{{ price_list_url }}` and gets an empty string when no
price-list PDF is attached for that contact (graceful fallback in the
template body via `{% if price_list_url %}`).

### C.3 Founder-uploaded "current price list" PDF (Drive → Supabase mirror)

The price-list PDF that the founder will upload to Drive is the canonical
document; per send, we **mirror it to Supabase Storage** so each contact
gets a dedicated `email_attachments` row. This keeps the existing
"per-recipient signed URL" pattern; switching to a single shared URL would
break the audit trail and make link expiry painful.

New helper `services/email_price_list.py::attach_current_price_list(
campaign_id, contact_ids
)`:

1. Read the canonical price-list PDF location from a new
   `config/email/shared.yml::shared.price_list_pdf_url` field (founder-
   maintained — points to Drive download URL or just a local
   `data/current_price_list.pdf` file in v1).
2. For each `contact_id`, upload the same bytes to
   `email-invoices/price_lists/{campaign_id}/{contact_id}.pdf` via the
   existing `supabase_storage.upload_file()`.
3. Insert one `EmailAttachment` row per contact with
   `kind='price_list'`, `file_name='Current Price List.pdf'`, the
   returned signed URL, content type, size.

For single-contact sends (Phase 7.1), the same helper runs once before
the send fires.

### C.4 UI/API plumbing (mostly already in place)

- The Broadcast Compose page already has a drag-drop invoice upload
  control. Phase 7.2a (per `PLAN_email.md`) extends it. A "Price list"
  toggle in that UI surfaces a single button — "Attach current price list
  to this broadcast" — which calls `attach_current_price_list(...)`
  for every recipient. No per-recipient drag-drop needed for price lists
  (it's the same PDF for everyone).
- Single-contact send (Phase 7.1) gets the same toggle.

This is **out of this plan's scope** — flagged here as a follow-up that
`PLAN_email.md` should pick up. This plan only:
1. Extends the `kind` enum (C.1).
2. Extends `build_send_variables` (C.2).
3. Adds the price-list helper (C.3).

The UI toggle ships in `PLAN_email.md` Phase 7.2a follow-up.

### Phase C — acceptance criteria

- `email_attachments` rows with `kind='price_list'` round-trip correctly
  (insert via helper, read by `build_send_variables`, signed URL valid).
- Template body referencing `{{ price_list_url }}` renders the URL when
  attachment present, empty string when absent.
- Existing invoice flow untouched — `kind='invoice'` continues to work.
- No MIME-pipeline change. No feature flag needed.

---

## Section 6 — Template authoring workflow (used by A.2 and B)

Per template:

1. Copy `hf_dashboard/templates/emails/sample_request_received.html` as
   the skeleton (`{% extends 'layout/base.html' %}` + the
   `partials/middle/*` imports).
2. Replace heading + body blocks with the voice draft. Voice rules:
   - `Hello <strong>{{ first_name }}</strong>,` greeting line.
   - "Quick note —" or equivalent warm opening.
   - 3-4 bullets, each `<strong>label:</strong> body` separated by
     `<br>`.
   - Soft no-pressure close.
   - Sign-off: `— Prashant<br>Founder, Himalayan Fibres` (font color
     `#888`, size `13px` per existing partial style).
   - Yarn-First: lead with finished yarn, fibre demoted to specs.
   - English only (per `feedback_template_voice_english.md`).
3. Pick image URL from `config/media/catalog.yml`. Match thematically
   (workshop / loom / dye-pot for production; sample-pack for swatch
   prep).
4. Write `.meta.yml` with category, flow, flow_step, required + optional
   vars, example values for each.
5. Render-test by deploying to HF Space (per `CLAUDE.md`: never run
   locally) and using Playwright MCP to fire `/email-send` to founder's
   address. Iterate on rendered output.
6. Founder voice approval before merge (manual gate).

---

## Section 7 — Test plan per phase

| Phase | Test | Location |
|---|---|---|
| 0 (schema) | `test_seed_meta_validates_all_files.py` — load every `.meta.yml`, assert `SeedTemplateMeta(**raw)` succeeds | `tests/services/` |
| 0 (schema) | `test_category_enum_exhaustive.py` — assert every seeded `.meta.yml` uses a value from `EmailCategory` Literal | `tests/services/` |
| A | `test_template_renders_with_examples.py` — for each seeded template, render with the example vars from its meta, assert no Jinja `UndefinedError` | `tests/services/` |
| B | `test_new_templates_render.py` — same as A but specifically for `sample_swatch_preparation`, `price_list_share`, `order_in_production` | `tests/services/` |
| C | `test_attachment_resolver.py` — round-trip each `source` (upload, url, mock-drive, media_catalog), MIME-sniff rejection cases | `tests/services/` |
| C | `test_email_sender_attachments.py` — multipart MIME structure assertion, plain-send unaffected when flag off | `tests/services/` |
| C | `test_idempotency_attachment_aware.py` — same bytes dedup, different bytes distinct, no-attachment unchanged | `tests/services/` |
| C | `test_email_send_audit_columns.py` — sender writes filename/size/sha256 correctly, NULL for no-attachment | `tests/services/` |
| D | `test_template_index_consistency.py` — re-run regenerator, assert no diff against committed `templates.yml` | `tests/scripts/` |

---

## Section 8 — Sequencing

```
Phase 0  (schema additions: TemplateAttachmentSpec, flow/flow_step,
          EmailCategory Literal, category migration of 12 seeded files,
          email_sends audit columns)
   │
   ├──> Phase A.1  (seed 4 partial-var templates)
   │
   ├──> Phase A.2  (HTML+meta edits for 7 static templates)
   │       │
   │       └──> Phase A.5  (Yarn-First voice rewrite for any product/story
   │                        templates that fail spot-check, conditional)
   │
   ├──> Phase B.1  (author sample_swatch_preparation)
   ├──> Phase B.3  (author order_in_production)
   │
   ├──> Phase C    (attachment support, feature-flagged off)
   │       │
   │       ├──> deploy with flag off, smoke-test plain sends
   │       ├──> flip flag on, deploy
   │       │
   │       └──> Phase B.2  (author price_list_share, depends on C)
   │
   └──> Phase D    (central registry index + CI consistency test)
                   (deferrable; ships when convenient)
```

**Estimated effort, generous (v3 revised):**

- Phase 0: 0.5 day (slim — only flow/flow_step/expected_attachments + 12 category edits)
- Phase A.1: 0.5 day (4 partial-var templates)
- Phase A.2 + A.5: 2 days (FULL rewrite of all 11 static templates per founder D2)
- Phase B.1 (`sample_swatch_preparation`): 0.5 day
- Phase B.3 (`order_in_production`): 0.5 day
- Phase C (slim): 0.5 day (kind enum + price_list_url variable + Supabase mirror helper)
- Phase B.2 (`price_list_share`): 0.5 day
- Phase D: 0.5 day (deferrable)

**Total:** ~5 days end-to-end with D shipped; ~4.5 days with D deferred.

The big v3 deltas vs v2: Phase C dropped from 1.5d to 0.5d (no
MIMEMultipart rebuild); Phase A.2+A.5 grew from 1d to 2d (founder asked
for full rewrites, not spot-check).

---

## Section 9 — Decisions (resolved by founder, 2026-05-06)

| ID | Decision | Resolution |
|---|---|---|
| **D1** | Rename existing slugs to the new convention, or grandfather? | **Grandfather** — both styles co-exist permanently. New slugs follow convention. |
| **D2** | Voice rewrite scope for the 11 static templates? | **Full rewrite all 11** to founder-warm + yarn-first highest quality. Magazine-style for campaigns (hero banner + body + features + social + footer); personalized warmer voice for sample/order flow. |
| **D3** | `proforma_invoice` — HTML template, PDF attachment, or both? | **HTML body + uploaded PDF attachment.** Body mentions products bought; PDF is the formal stamped copy. Wired via existing `email_attachments` `kind='invoice'`. |
| **D4** | `price_list_share` — Drive or per-send upload? | **Drive-hosted canonical PDF** that the founder maintains; mirror to Supabase per send so each contact gets a per-recipient signed URL. Founder will share the Drive location separately. |
| **D5** | Seasonal templates — manual or scheduled? | **Manual broadcast only in v1.** |
| **D6** | Phase D (central registry index) — when? | **Deferred.** Schema additions (Phase 0) ship before flow engine; index regeneration is the polish that ships when convenient. |
| **D7** | Delete `abandoned_cart_recovery`? | **Keep on disk, do not seed.** No cart system today; harmless to leave. |
| **D8** *(new)* | Catalog integration (link to WA-style catalog instead of website)? | **Out of this plan's scope.** Founder flagged as separate work. Templates link to website for now. |
| **D9** *(new)* | Image source for hero banners and product photos? | **Public Supabase bucket `wa-template-images`** — direct public URLs, no signed-URL refresh needed. |

---

## Section 10 — Out-of-scope dependencies

- **Flow orchestration** — `PLAN_flows.md`. This plan provides the
  templates flow consumes. Flow engine reads `flow` / `flow_step` from
  meta (Phase 0).
- **Studio / Broadcast UI changes** for new categories or attachment
  inputs — `PLAN_email.md`. The category-filter chips and
  attachment-upload control are added there once this plan's schema lands.
- **WhatsApp template parity** — `PLAN_whatsapp.md`.
- **Drive PDF integration** — gated on Phase C.1 verification; if blog
  Drive scope is image-only, a separate scope-uplift commit is needed
  before `price_list_share` can use `source: drive`.

---

## Section 11 — Verification

Per `CLAUDE.md` and the founder preference (memory:
`reference_hf_space.md`): no local runs.

1. `git commit` per phase.
2. `python scripts/deploy_hf.py`.
3. Wait for Space to report **Running**.
4. Drive the live URL with Playwright MCP per the per-phase acceptance
   criteria above.
5. For Phase C, deploy *twice*: once with `EMAIL_ATTACHMENTS_ENABLED=false`
   (regression check on plain sends), then with `=true` (attachment
   smoke test).
