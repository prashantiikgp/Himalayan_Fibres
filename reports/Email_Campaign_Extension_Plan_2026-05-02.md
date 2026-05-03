# Email Campaign Extension Plan
**Date:** 2026-05-02 (revised 2026-05-03 after self-review and design-system iteration; P0+P1 patches applied 2026-05-03)
**Author:** Claude Code session
**Scope:** `campaign/email_campaign/` — extension to new HTML templates, image system, blog variants, button standards, schema, mobile compatibility.

---

## 0. What's already shipped (state-of-disk)

This plan is now mid-execution. Sections marked with ✅ are done, 🟡 in flight, ⬜ not started.

### Standardized partials (✅ shipped, 14 total)

The middle-content partials each enforce dimensions / styling / accessibility so templates compose like Lego:

| Partial | Purpose | Notes |
|---|---|---|
| `heading.html` | H1 title | First element of every body |
| `paragraph.html` | Body paragraph (16px) | Used liberally |
| `hero_image.html` | 632×360 cropped hero | Object-fit cover; only used in product templates |
| `image_card.html` | Image-on-top card | For multi-category templates |
| `image_card_pair.html` ★ | 2 image_cards side-by-side (1+2 layout) | New for luxury-style multi-category |
| `image_split.html` ★ | Image-text 2-column row, image left or right | Editorial body block |
| `image_grid.html` ★ | 3 small product images side-by-side with captions + per-cell links | Variant strip |
| `info_card.html` | Card with title + body, no image | Spec / neutral block |
| `pull_quote.html` ★ | Italic accent quote with brand-gold left border | Editorial pacing |
| `stats_row.html` ★ | 3 large-number proof points | Sustainability / impact data |
| `cta_button.html` | Primary CTA (uppercase + auto-arrow) | Standardized 2026-05-03 |
| `whatsapp_help_button.html` | Secondary green CTA | Configurable label + prompt; padding bumped 12→14px to clear WCAG 44px tap target |
| `invoice_button.html` | Invoice-specific CTA | Transactional only |
| `proforma_stamp.html` | "PROFORMA" badge | Proforma invoice only |

★ = new this session.

### Three canonical templates (✅ shipped)

Each is a worked example of one of the three template types defined in `Email_Template_Standardization_2026-05-03.md`. Body-image counts verified against actual rendered HTML:

| Type | Canonical example | Body partials used | Body images | Product-page links |
|---|---|---|---|---|
| **Product** | `wool_focus.html` | image_split, pull_quote, image_grid | 5 | 5 |
| **Multi-category** | `yarn_categories_intro.html` | custom hero card + image_card_pair, per-card CTAs | 3 | 6 |
| **Campaign / blog** | `welcome_day_3_sustainability.html` | stats_row, image_split, pull_quote | 2 | 0 (story images, not product) |

(Full image counts including brand banner + 3 footer social icons: wool 9, yarn_categories 7, sustainability 6 — all under spam-filter risk thresholds even with `email_settings.yml` 5-image guideline interpreted as body-only.)

### System-wide changes (✅)

- Width: **640 → 680px** (research-backed, modern-safe; see §VII for the Outlook risk note)
- Hero image at top removed in favor of heading + lead (BLUF)
- Banner is locked: `banner_url` from `config/email/shared.yml` (brand "Whatsapp email Banner.jpg")
- Footer renders address (Gwalior) + phone (+91 8582952074) + email + social — all via shared config
- Every body image links to its Wix product page via `https://www.himalayanfibres.com/product-page/<slug>` (not the homepage)
- All buttons clear WCAG 44×44 tap target (see §V)
- Standardization doc shipped: `reports/Email_Template_Standardization_2026-05-03.md`

---

## I. Folder structure additions to `campaign/email_campaign/`

Already on disk (✅):
- `shared/company_templates/sustainability_field_story.yml`
- `shared/category_templates/{nettle_focus,wool_focus,hemp_focus}.yml`
- `shared/lifecycle_templates/{welcome,sample_invitation,winback_60d_silent}.yml`
- `shared/transactional_templates/{order_confirmation,proforma_invoice}.yml`
- `shared/product_templates/category/yarn_categories_intro.yml` ✅
- 4 segment campaigns under `existing_clients/`, `churned_clients/`, `potential_domestic/`, `international_email/`

**Additions still pending:**
```
shared/
  ├── category_templates/       +1 collections_focus.yml (sidecar only — HTML pending)
  ├── product_templates/        +6 (mirrors WA), with subfolders:
  │   ├── category/   ✅ yarn_categories_intro
  │   ├── plant/      ⬜ nettle_yarn_fine, hemp_yarn_natural
  │   ├── animal/     ⬜ tibetan_wool_yarn
  │   └── blend/      ⬜ burberry_blend, noor_blend
  ├── lifecycle_templates/      +1 sidecar for welcome_day_3_sustainability.yml ⬜
  │                              +3 engagement: post_sample, onboarding, abandoned_cart ⬜
  ├── seasonal_templates/       NEW — Diwali (P1, hard date Oct 2026), year-end, harvest
  └── blog_templates/           NEW — 4 additional blog variants (see §III)
```

---

## II. Templates to build (priority-ordered, 22 total)

### Phase 0.5 — Sidecar backfill (P0, schema alignment)

Existing sidecars predate the new schema. They have `required_variables` but no `optional_variables`. Refactoring HTMLs without backfilling means YAML drifts further from reality.

| # | YAML to backfill | Reason |
|---|---|---|
| pre-1 | `welcome.yml` | Add `optional_variables` |
| pre-2 | `winback_60d_silent.yml` | Add `optional_variables` |
| pre-3 | `sample_invitation.yml` | Add `optional_variables` |
| pre-4 | `proforma_invoice.yml` | Add `optional_variables` |
| pre-5 | `order_confirmation.yml` | Add `optional_variables` |
| pre-6 | `sustainability_field_story.yml` | Add `optional_variables` |
| pre-7 | `nettle_focus.yml` | Will be re-written when nettle_focus.html is refactored |
| pre-8 | `hemp_focus.yml` | Will be re-written when hemp_focus.html is refactored |

### Phase 1 — Category deep-dives (P0, 4 templates)

| # | Template | Status |
|---|---|---|
| 1 | `wool_focus.html` | ✅ shipped (canonical product) |
| 2 | `hemp_focus.html` | 🟡 exists but old spec-table layout; needs editorial refactor — **post-refactor, hemp_focus.yml needs new optional_variables** |
| 3 | `nettle_focus.html` | 🟡 same — yaml needs alignment after refactor |
| 4 | `collections_focus.html` | ⬜ not started; sidecar also missing |

### Phase 2 — Product / SKU + multi-category (P1, 6 templates)

(Renamed from "Product / SKU spotlights" since `yarn_categories_intro` is multi-category, not SKU.)

| # | Template | Type | Catalog SKU reference | Status |
|---|---|---|---|---|
| 5 | `product/category/yarn_categories_intro.html` | multi-category | educational primer | ✅ shipped (canonical multi-category) |
| 6 | `product/plant/nettle_yarn_fine.html` | SKU | `ys9qh6g0zt` (₹625) | ⬜ |
| 7 | `product/plant/hemp_yarn_natural.html` | SKU | `otgmx28zqr` (₹275) | ⬜ |
| 8 | `product/animal/tibetan_wool_yarn.html` | SKU | `wte1jvygze` (₹375) | ⬜ |
| 9 | `product/blend/burberry_blend.html` | SKU | `hf_burberry_series` (₹1200) | ⬜ |
| 10 | `product/blend/noor_blend.html` | SKU | `hf_noor_series` (₹1100) | ⬜ |

### Phase 3 — Blog / campaign variants (P1, 4 NEW templates + 1 already-shipped canonical)

(Naming clarified: the existing `welcome_day_3_sustainability.html` IS the Variant-1 canonical. We don't duplicate it as `blog_sustainability_story.html`. Future variants are new files.)

| # | Variant | File | Angle |
|---|---|---|---|
| — | Variant 1 (canonical, shipped) | `welcome_day_3_sustainability.html` ✅ | Sustainability story / why behind the brand |
| 11 | Variant 2 | `blog_field_origin_story.html` ⬜ | Specific region / harvest behind-the-scenes |
| 12 | Variant 3 | `blog_founder_letter.html` ⬜ | Long-form quarterly founder voice, no pitch |
| 13 | Variant 4 | `blog_customer_case_study.html` ⬜ | B2B success story / social proof |
| 14 | Variant 5 | `blog_process_deep_dive.html` ⬜ | How the fibre becomes yarn |

### Phase 4 — Engagement lifecycle (P1, 3 templates)

| # | Template | Trigger |
|---|---|---|
| 15 | `post_sample_followup.html` | 5–7 days after sample dispatch |
| 16 | `onboarding_day_14_first_order.html` | Soft first-order nudge |
| 17 | `abandoned_cart_recovery.html` | Quotation request abandoned |

### Phase 5 — Seasonal (1 P1 with hard date + 2 P2)

| # | Template | Timing | Priority |
|---|---|---|---|
| 18 | `diwali_greetings.html` | **Diwali = 8 Nov 2026 — must ship by 15 Oct** | **P1 (HARD DATE)** |
| 19 | `new_year_recap.html` | Year-end story | P2 |
| 20 | `harvest_announcement.html` | Per fibre batch arrival | P2 |

### Phase 6 — Inventory fix (P0)

| # | Item | Notes |
|---|---|---|
| 21 | `shared/lifecycle_templates/welcome_day_3_sustainability.yml` | Sidecar for the already-shipped HTML |

**Total: 22 deliverables** across 8 phase buckets (counting Phase 0.5 backfills as 8 separate entries against the 14 trackable templates / sidecars). Median per HTML template ≈ 85 lines based on shipped reference.

---

## III. Five blog variants — extension of the campaign / blog type

The campaign/blog type covers any long-form editorial email — story-led, lower product-pitch, higher engagement-with-cause. Five variants give us coverage of every common blog topic without ad-hoc designs.

Each variant **reuses the canonical campaign/blog skeleton** (heading → lead → stats_row → image_split → pull_quote → image_split → close → CTAs) but with different defaults baked into the shared variables.

### Variant 1 — Sustainability Story ✅ (canonical: `welcome_day_3_sustainability.html`)

| | |
|---|---|
| **When to use** | Welcome series Day 3, eco-curious prospects, recurring monthly cadence |
| **Hook** | "0 pesticides, 1,200m altitude, 120+ artisan partner homes" |
| **Imagery** | Field-artisan shots from `/assets/` |
| **Voice angle** | Why the source matters, less the product |
| **Primary CTA** | "See how it's made" → blog post |
| **Secondary CTA** | "Browse the yarn catalog" |
| **Per-send vars** | `first_name`, 3× `stat_*_value/label`, 2× `story_*_image_url/title/body/link`, `quote_text/attribution`, `blog_link`, `catalog_link` |

### Variant 2 — Field / Origin Story ⬜ `blog_field_origin_story.html`

| | |
|---|---|
| **When to use** | Region-specific or harvest-specific drop, quarterly cadence |
| **Hook** | "We just got back from a week in Almora — here's what we saw" |
| **Imagery** | A specific trip — 3-4 photos from one field visit |
| **Voice angle** | Photojournalism, location is the protagonist |
| **Primary CTA** | "See more from the field" → blog gallery |
| **Per-send vars** | `region_name`, `trip_date`, `lead_paragraph`, 4× story image_split, optional contributor name |

### Variant 3 — Founder Letter ⬜ `blog_founder_letter.html`

| | |
|---|---|
| **When to use** | Quarterly, milestone moments, year-end reflection |
| **Hook** | "It's been a year. Here's what we learned." |
| **Imagery** | Sparse — 1 brand-banner-style photo, 1 personal artisan/team shot |
| **Voice angle** | Personal, reflective, no product pitch at all |
| **Primary CTA** | "Read the full letter" → blog OR no CTA at all |
| **Per-send vars** | `quarter` (e.g. "Q4 2026"), `letter_title`, multi-paragraph body, optional pull_quote |

### Variant 4 — Customer Case Study ⬜ `blog_customer_case_study.html`

| | |
|---|---|
| **When to use** | Quarterly social proof, B2B prospect mid-funnel |
| **Hook** | "How Mahesh's atelier in Bhadohi switched from imported wool" |
| **Imagery** | 2-3 photos of the customer's workshop / finished products |
| **Voice angle** | Third-person narrative + customer pull quote |
| **Primary CTA** | "Read the full case study" → blog |
| **Secondary CTA** | "Request a sample" |
| **Per-send vars** | `customer_name`, `customer_business`, `customer_quote`, 3× context paragraphs, before/after stats |

### Variant 5 — Process Deep-Dive ⬜ `blog_process_deep_dive.html`

| | |
|---|---|
| **When to use** | Educational moments, GOTS-style certification news, "how it's made" stories |
| **Hook** | "12 steps from a wild plant to a yarn ball" |
| **Imagery** | Numbered process steps — 5-7 small images in sequence |
| **Voice angle** | Instructional but conversational |
| **Primary CTA** | "Watch the process video" → YouTube link, OR "See the full breakdown" → blog |
| **Per-send vars** | `process_title`, `step_count`, multiple `image_grid` rows for steps |

### Common blog-variant variables

Every blog template ships with these standardized overrideable variables:

```
first_name*           recipient first name
heading_text          main H1
lead_paragraph        BLUF opening
stats_row             3-cell impact data (optional, hide if not passed)
story1 / story2       image_split blocks (image, title, body, link)
quote_text + attr     pull_quote (optional)
primary_cta_label     "See how it's made" / "Read full story" / etc.
primary_cta_link      blog or YouTube URL
secondary_cta_label   "Browse catalog" / "Request a sample" (optional)
secondary_cta_link    URL (optional)
```

This keeps the 5 variants a single template family — same skeleton, different copy + imagery + CTAs.

---

## IV. Button standardization (NEW — 2026-05-03)

All buttons across all templates now follow a consistent format:

### Primary CTA (`cta_button` partial)

```
Solid dark background (color_button_bg = #232323)
Uppercase text, 14px, letter-spacing 1.2px
Auto-appended " →" arrow
14px vertical padding, 32px horizontal padding
Rounded 4px corners
Font weight 700
Tap target ≥ 45px (clears WCAG 44px mobile minimum)
```

Optional `width='full'` arg for block-style. Optional `bg` and `text_color` overrides for festive variants (e.g. gold for Diwali).

### Tertiary card CTA (inline in `yarn_categories_intro` cards)

```
Outlined / ghost button (transparent bg, brand-gold border + text)
Uppercase 11px, letter-spacing 1px
Auto-appended " →" arrow
8px vertical, 14px horizontal padding
Rounded 3px corners
```

Used for "Explore Nettle →", "Explore Hemp →", etc. inside cards. Note: at 11px font with gold (#c38513) on white, contrast is borderline AA — use only for tertiary in-card CTAs, never for the primary action.

### Secondary CTA (`whatsapp_help_button` partial)

```
WhatsApp green (#25d366) background
White text, font weight 600
Configurable label (default "Message us on WhatsApp")
Configurable prompt (pre-fills WhatsApp message)
14px vertical, 24px horizontal padding (clears WCAG 44px)
13px font, letter-spacing 0.5px
```

### Every CTA is dynamic per send

Every button across every template exposes its label and URL as a per-send variable so a campaign can override them without editing HTML:

| Template | Configurable buttons |
|---|---|
| `wool_focus` | `catalog_link` (primary), WhatsApp prompt (secondary) |
| `yarn_categories_intro` | `featured_cta_label`, `pair_left_cta_label`, `pair_right_cta_label` (cards), `catalog_link` (primary), WhatsApp prompt (secondary) |
| `welcome_day_3_sustainability` | `blog_link` + `catalog_link` (two primaries), WhatsApp prompt |
| Future blog variants | `primary_cta_label` + `primary_cta_link`, `secondary_cta_label` + `secondary_cta_link` |

---

## V. Mobile compatibility

All templates designed mobile-first; verified responsive:

| Element | Desktop (680px) | Mobile (~375px) | How |
|---|---|---|---|
| Outer container | 680px max-width, centered | Fluid 100% (down to 320px min) | `width="680" style="max-width:680px"` + percentage cells |
| Banner | 680×natural | Scales to 100% width | `width="680" style="width:100%"` |
| Hero image | 632×360 cropped | Scales 100% (height stays 360px) | `width="632" height="360" style="width:100%;max-width:632px;object-fit:cover"` |
| `image_split` | 300+text side-by-side | Reflows to stacked (image-on-top) on phones | TD width attrs + modern client reflow |
| `image_card_pair` | 308+308 paired | Stacks to 1-up | Same |
| `image_grid` | 3 cells of 200px | Reflows to 3-up (Apple Mail/Gmail) or stacked (Outlook iOS) | Same |
| `stats_row` | 3 cells side-by-side | Stays 3-up at 320px+ (cells narrow but readable) | Same |
| `cta_button` | Hugs content centered | Same; ≥45px tap target | Padding-based sizing |
| `whatsapp_help_button` | Hugs content centered | Same; padding now 14px (was 12), clears WCAG 44px | Padding-based sizing |

**Outlook desktop (Word renderer)** keeps side-by-side everywhere. **Apple Mail / Gmail mobile / iOS Outlook** reflow tables to stacked on narrow viewports — the standard fluid-hybrid behavior, no media queries needed.

**Tap targets:** all buttons cleared WCAG 44×44 tap area as of 2026-05-03 (WhatsApp button padding bumped from 12px to 14px to clear minimum).

**Body text:** 14-16px throughout — readable without zooming on iPhone SE (smallest common viewport).

---

## V.1 Accessibility (NEW)

| Concern | Status | Notes |
|---|---|---|
| Tap targets ≥ 44×44 | ✅ verified post-2026-05-03 patch | All button partials cleared |
| Alt text on images | 🟡 partial — `image_card`, `image_split`, `image_grid` accept alt; defaults to title or caption | Audit pass needed: every per-send image variable should have a per-send alt variable too |
| Color contrast | 🟡 brand-gold (#c38513) on white passes AA at 14px+ but fails at 11px (the card-CTA tertiary size); fine for tertiary use, never use 11px gold for body text | |
| Screen reader semantics | ✅ all decorative tables marked `role="presentation"` | |
| Keyboard navigation | ✅ all CTAs are `<a>` elements, focusable | |

## V.2 Regression testing

When any partial changes, all 13 templates inherit. Testing approach:
1. Smoke-render every template with default context (script TBD: `scripts/smoke_render_emails.py`)
2. Compare rendered byte size to baseline (drift > 10% triggers visual review)
3. Track per-template rendered char count in template sidecar metadata

## V.3 Deploy cadence

Templates land on disk locally but don't reach the live HF Space until `python scripts/deploy_hf.py` runs. Convention:
- **Per-phase batched** — deploy at the end of each Phase, not per-template
- **Hotfixes** — deploy immediately for partial-level fixes that affect multiple templates (e.g. the WhatsApp button padding bump)

## V.4 Backward compatibility (variable renames)

When a template adds a new `optional_variables` key, defaults handle missing values — no breakage.

When a template **renames or removes** a variable, existing campaign-yaml references break silently. Process:
1. Search all `campaign/email_campaign/*/campaigns.yml` for the old variable name
2. If used: update those references in the same commit
3. Add a deprecation note in the sidecar's `description` for one cycle before removing

---

## VI. Image system

| Layer | Source | Bucket / location |
|---|---|---|
| Brand banner | Drive → Supabase | `wa-media/Whatsapp email Banner.jpg` (signed URL, expires 2027) |
| Product images (yarn / fibre / blends) | Drive → compressed → Supabase | `wa-template-images/category/*.jpg` |
| Field / artisan / story images | `/assets/` → compressed → Supabase | `wa-template-images/field/*.jpg` |

All Supabase URLs use object-fit:cover via the standardized partials so a tall webp doesn't blow up the layout.

**Available image inventory** (verified against Supabase manifest 2026-05-03):
- 3 nettle: `nettle1`, `nettle-thick-yarn`, `nettle-white-yarn`  *(nettle2/nettle3 deleted earlier this session)*
- 3 hemp: `hemp1`, `hemp-natural-yarn`, `hemp-white-yarn`
- 4 wool: `wool1`, `wool2`, `wool3`, `wool-millspun`
- 3 collections: `burberry`, `burberry-detail`, `noor`
- 3 field artisan: `field-artisan1`, `field-artisan2`, `field-artisan3`

**Total: 16 production images** ready to use. Manifest at `campaign/_image_manifest.yml`.

---

## VII. Width decision (research-backed)

Bumped from 640 → 680px on 2026-05-03. Sources:
- [Beefree Email Template Size Guide](https://beefree.io/hub/html-email-creation/email-template-size) — 600-680px modern-safe
- [Tabular](https://tabular.email/blog/email-template-size-width-and-height) — practitioner consensus 600-640px universal, 680 modern-only
- [Designmodo 2026 Trends](https://designmodo.com/email-design-trends/) — wider feels less cramped at desktop

Outlook desktop fallback via explicit `width="680"` HTML attr survives Word-renderer.

**Risk note:** If audience analytics show >5% Outlook desktop opens with bad rendering (compressed columns, banner not fitting), revert to 640px container. Initial bet: B2B India audience uses primarily Gmail + Apple Mail mobile, so 680 should be fine. Monitor first 5 sends.

---

## VIII. Schema work

Currently on disk (✅ pre-existing for WhatsApp): `hf_dashboard/engines/campaign_schemas.py` with `WhatsAppTemplate`, `Campaign`, `CampaignFile`. Email side has no Pydantic schema yet.

**Pending (P0 prerequisite to broadcast wiring):**

```python
class EmailTemplate(BaseModel):
    name: str
    tier: Literal["company", "category", "product", "lifecycle", "transactional", "seasonal", "blog"]
    voice: str
    subject: str
    preview_text: str = ""
    html_template_file: str
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    hero_image: Optional[str] = None
    alternates: list[str] = Field(default_factory=list)
    target_segments: list[Segment] = Field(default_factory=list)
    status: Literal["READY", "PLANNED", "RETIRED"] = "READY"
    description: str = ""
```

Plus extend `validate_campaigns.py` to walk `campaign/email_campaign/`.

---

## IX. Variable contracts (per-send validation)

Each template's sidecar YAML declares `required_variables` (must be passed) and `optional_variables` (have defaults). The broadcast page should pre-validate sends against these.

Standardized across all templates:
- `first_name` (required)
- All button labels + links (optional, with defaults)
- All image URLs (optional, with defaults pointing to Supabase bucket)
- All copy fields (optional, with defaults baked into the HTML template)

**Backward-compatibility rule:** Variable removal or rename requires a campaign-yaml audit first; see §V.4.

---

## X. Out of scope (with explicit ticket flags)

- A/B testing framework (subject lines, hero images, CTA labels) → ticket TBD
- ESP / sender deliverability (SendGrid / Resend / Postmark) — needed before going beyond ~300 sends/day → Phase 7 future blocker
- GDPR / unsubscribe verification — assumed handled by `footer.html`; verify per template inherits footer
- Engagement metric definitions (open rate, CTR, click maps) — partially in `email_analytics.py`
- Email Template Studio dashboard page (mirror of `wa_template_studio.py`) — separate ticket

---

## XI. Summary table — at-a-glance

| Phase | Templates | Effort (est lines HTML) | Status |
|---|---|---|---|
| Standardized partials (14) | — | ~700 across all partials | ✅ shipped |
| Phase 0.5 — Sidecar backfill | 8 sidecars | ~80 (10 per yaml) | ⬜ |
| Phase 1 — Category | 4 (3 deep-dives + collections) | wool ✅, hemp/nettle/collections ⬜ | 🟡 1/4 |
| Phase 2 — Product/multi-cat | 6 (1 multi-cat + 5 SKU) | yarn_categories_intro ✅; rest ⬜ | 🟡 1/6 |
| **Phase 3 — Blog (5 variants)** | sustainability ✅ + 4 new files | ~360 (4 × 90) | 🟡 1/5 |
| Phase 4 — Lifecycle | 3 engagement | ~270 (3 × 90) | ⬜ |
| Phase 5 — Seasonal | Diwali (P1, hard date) + 2 P2 | ~270 | ⬜ |
| Phase 6 — Inventory fix | 1 sidecar YAML | minimal | ⬜ |

---

## XII. Recommended next moves (sequenced by dependency)

1. **Phase 6 — `welcome_day_3_sustainability.yml` sidecar.** 5 minutes. Unblocks campaign-yaml references. Do first.
2. **Phase 0.5 — Backfill old sidecars** (`welcome.yml`, `winback_60d_silent.yml`, `sample_invitation.yml`, `proforma_invoice.yml`, `order_confirmation.yml`, `sustainability_field_story.yml`) with `optional_variables` fields. ~30 min total.
3. **Phase 1 refactor — `hemp_focus.html` + `nettle_focus.html`** to match wool_focus editorial pattern. Update their YAMLs in the same commit (so sidecars don't drift). ~180 lines HTML + 2 YAML rewrites.
4. **Phase 3 blog variants — 4 new files** (`field_origin_story`, `founder_letter`, `customer_case_study`, `process_deep_dive`). All reuse the canonical sustainability skeleton. ~360 lines HTML + 4 sidecars.
5. **Phase 4 lifecycle templates** (`post_sample_followup`, `onboarding_day_14`, `abandoned_cart_recovery`).
6. **Diwali template** (P1, hard date 15 Oct ship).
7. **Phase 1 collections_focus.html** (last category).
8. **Phase 2 SKU spotlights** (5 product templates).

---

## Revisions log

- **2026-05-02:** Initial plan with 16 templates.
- **2026-05-03 (early):** Self-review applied — Phase 0 added, schema/wiring promoted to P0, Diwali promoted to P1, 17 templates total.
- **2026-05-03 (late):** Major revision after design-system iteration:
  - 5 new partials shipped (`image_split`, `image_grid`, `pull_quote`, `image_card_pair`, `stats_row`)
  - 3 canonical templates shipped (`wool_focus`, `yarn_categories_intro`, `welcome_day_3_sustainability`)
  - Width 640 → 680px (research-backed)
  - Hero-at-top removed; BLUF heading + content-first
  - Buttons standardized: uppercase, auto-arrow, configurable labels + links
  - Per-card CTAs in multi-category templates ("Explore Nettle →" etc.)
  - WhatsApp button label/prompt now configurable per template
  - 5-variant Blog/Campaign type defined (§III) — sustainability ✅, 4 more planned
  - Mobile compatibility section added (§V)
  - Image inventory section added (§VI)
  - Total deliverables: 22 (was 17)
- **2026-05-03 (P0+P1 patches):** Self-review v3 applied:
  - Body-image counts in §0 corrected (3 / 2 / 5 — was 4 / 3 / 5)
  - WhatsApp button padding bumped 12→14px to clear WCAG 44px tap target (real code change, not just doc)
  - §III Variant 1 naming clarified: `welcome_day_3_sustainability.html` IS the canonical, not a future `blog_sustainability_story.html`
  - §VI image inventory updated (3 nettle, was claimed as 4 — `nettle2`/`nettle3` deleted earlier session)
  - Phase 2 renamed "Product / SKU + multi-category" — `yarn_categories_intro` is multi-category, not SKU
  - §III Variant 1 added Per-send vars row (was missing)
  - §XII recommended next moves resequenced by dependency (sidecar backfill first, refactor second, new builds third)
  - Phase 0.5 added — backfill 8 old sidecars to new schema
  - §V.1 Accessibility added — alt-text contract, contrast notes, semantics
  - §V.2 Regression testing approach added
  - §V.3 Deploy cadence rule added (per-phase batched)
  - §V.4 Backward-compat rule for variable renames added
  - §VII Outlook risk note added
  - Total deliverables: 22 (8 sidecar backfills, 14 templates)
