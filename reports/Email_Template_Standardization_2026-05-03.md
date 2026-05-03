# Email Template Standardization
**Date:** 2026-05-03
**Status:** ACTIVE — applies to all new + existing email templates

This document is the single source of truth for how email templates are
structured. Changes to the rules in §I require a separate decision; new
templates must follow these rules without exception.

---

## I. Locked elements (never change per template)

| Element | File | Rule |
|---|---|---|
| **Outer container** | `layout/base.html` | 640px max-width, white background, single shell |
| **Banner (top)** | `partials/banner.html` | Brand banner image only. **Never** show a product image here. `banner_url` always points to the brand banner |
| **Footer (bottom)** | `partials/footer.html` | Logo, social, unsubscribe, contact. Locked structure |
| **Social row** | `partials/social_row.html` | Above the footer. Locked |

A template only changes the `{% block content %}` section between banner and social row. Header and footer stay the same in every email — that's what makes them feel like "Himalayan Fibres" mail.

---

## II. Three standardized template types

### Type 1 — **Product** template

Single SKU or single category spotlight. Used for product-focused emails like `nettle_yarn_fine.html`, `burberry_blend.html`, category focus templates (`hemp_focus`, `wool_focus`).

**Body structure:**
```
heading              — title with optional emoji
hero_image           — 640×360 cropped block (NEW: enforced dimensions)
paragraph            — greet
paragraph            — narrative (1-2 sentences)
inline spec table    — Forms / Origin / Properties / MOQ / Lead time
paragraph            — differentiator line
paragraph            — sample CTA setup
paragraph            — sign-off "— Prashant"
cta_button           — optional ("View catalog")
whatsapp_help_button — fallback contact
```

### Type 2 — **Multi-category** template

Multiple subjects in one email. Used for overview emails like `welcome.html`, an "all 3 fibre families" intro, the existing welcome card layout.

**Body structure:**
```
heading              — title
paragraph            — greet + intro (1-2 sentences)
image_card × 2-3     — image-on-top + title + body (NEW partial)
paragraph            — closing
cta_button           — primary CTA
whatsapp_help_button — fallback contact
```

The `welcome.html` template already follows this pattern using `info_card`
(text-only). Use `image_card` (NEW) when each subject benefits from imagery.

### Type 3 — **Campaign / blog / info** template

Long-form article style. Used for sustainability stories, founder letters,
seasonal greetings, harvest announcements.

**Body structure:**
```
heading              — article title
hero_image           — 640×360 cropped (magazine-style)
paragraph × 3-5      — article body
optional pull-quote  — italic, accent-color border-left
paragraph            — sign-off
cta_button           — soft CTA (optional)
whatsapp_help_button — fallback contact
```

`welcome_day_3_sustainability.html` already follows this pattern.

---

## III. Standardized partials inventory

| Partial | Type | Output | When to use |
|---|---|---|---|
| `heading` | text | H1-style title | First element in `block content` |
| `paragraph` | text | Body paragraph, 14-16px, 24px x-padding | Narrative copy |
| `hero_image` | image | **640×360 cropped, 24px x-padding, object-fit:cover** | Hero shot in product / campaign templates |
| `image_card` | image+text | Card with image-on-top (200×592 cropped) + title + body | Multi-category template subjects |
| `info_card` | text | Card with title + body, no image | Multi-category text-only OR spec card |
| `cta_button` | button | Primary CTA, brand-color background | One per email, near the bottom |
| `invoice_button` | button | Specific to invoice / proforma flows | Transactional templates only |
| `whatsapp_help_button` | button | "Reply on WhatsApp" fallback | Every customer-facing template |
| `proforma_stamp` | badge | "PROFORMA" diagonal badge | Proforma invoice only |

---

## IV. Image dimension contract

All image partials enforce fixed dimensions via `width="..." height="..."` HTML attrs (Outlook fallback) + `object-fit: cover` (modern clients crop). No template should ever embed a raw `<img>` with `height: auto`.

| Block | Output dimensions | Aspect | Inset padding |
|---|---|---|---|
| `partials/banner.html` | 640 × natural | full bleed, 0 inset | 0 |
| `hero_image` (default) | 640 × 360 (cropped) | 16:9 | 24px L/R |
| `hero_image` (height=400) | 640 × 400 (cropped) | tighter | 24px L/R |
| `image_card` (default) | 592 × 200 (cropped) inside card | 3:1 panel | 24px L/R |

**Why fixed dimensions matter:**
- Source images vary wildly: 600×400 webp, 4032×3024 phone shot, 1024×1024 square. Without enforcement, each renders at its own size and the email feels chaotic.
- Outlook desktop strips most CSS — only the HTML width/height attrs survive. Without them, Outlook renders huge.
- Modern clients (Apple Mail, Gmail web) crop with `object-fit: cover` — same image, same size in every email.

---

## V. Banner contract

`banner_url` is **always** the brand banner. It comes from
`build_send_variables` in `email_personalization.py` (or wherever the
sender wires defaults). Templates do not override it.

If a template needs an additional product/lifestyle image, it goes in the
**body** via `hero_image` or `image_card` — never as the banner.

The brand banner asset should be roughly 640 × 240 (or 640 × 200) — narrow
ribbon, logo + tagline. Larger product imagery in the banner slot creates
the duplication problem we hit with `wool_focus.html` v1.

---

## VI. What changed (2026-05-03)

| Change | Affected files | Reason |
|---|---|---|
| `hero_image.html` enforces 640×360 + object-fit:cover | hero_image.html | Was rendering full-bleed at natural aspect (could be 1000+ px tall) — looked broken |
| New `image_card.html` partial | NEW: image_card.html | Multi-category templates need image cards; previously had to inline raw HTML |
| Documented banner contract | this doc | Caught duplication bug on wool_focus preview where banner_url was overridden with a product image |
| Documented 3 template types | this doc | New templates must pick a type — ad-hoc structures are no longer allowed |

**Migration:** existing `welcome`, `order_confirmation`, `order_shipped`,
`order_delivered_feedback`, `operational_update`, `proforma_invoice`,
`sample_invitation`, `winback_60d_silent`, `welcome_day_3_sustainability`,
`hemp_focus`, `wool_focus`, `nettle_focus` — all conform to one of the 3
types, no rewrites needed beyond the hero_image partial fix.

---

## VII. New-template checklist

Before committing a new email template:

- [ ] Picks one of: **product / multi-category / campaign**
- [ ] Extends `layout/base.html`
- [ ] Has `{% block content %}` only — no banner/footer overrides
- [ ] Uses standardized partials (hero_image, image_card, info_card, paragraph, etc.)
- [ ] Hero image (if any) calls `hero_image` macro with default 360px height (or explicit height arg)
- [ ] Renders cleanly at 640px desktop AND ~375px mobile (verify with the dashboard's Mobile preview toggle)
- [ ] Has a sidecar YAML in `campaign/email_campaign/shared/<tier>_templates/<name>.yml`
- [ ] Sidecar declares: `name`, `tier`, `voice`, `subject`, `preview_text`, `html_template_file`, `required_variables`, `target_segments`, `status`
- [ ] Smoke-tested via Jinja render with realistic context (no broken vars)
- [ ] Banner URL is the brand banner (not overridden with product imagery)
