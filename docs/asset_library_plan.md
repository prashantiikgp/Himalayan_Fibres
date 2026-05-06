# WhatsApp Asset Library — Plan

**Owner:** Prashant · **Date:** 2026-05-06 · **Status:** Approved cleanup, ready to build

## Why

Today, when the team wants to attach an image to a WhatsApp template in the
Template Studio, they have to:

1. Open the Supabase web console.
2. Find the right file inside a deeply nested mirror of our Drive folder
   structure (4 inconsistent top-level prefixes: `Asset/`, `Product Images/`,
   `Farm Images/`, `field/`, with mixed casing, spaces, ampersands).
3. Hand-build a public URL, manually URL-encode the spaces.
4. Paste into the Studio's *Header asset URL* field.

This is slow, error-prone, and gates template creation behind Supabase access.
We need a self-serve **Asset Library** page inside the dashboard that lets the
team browse images by purpose (yarn / creative / village / etc.), see whether
each is WhatsApp-template-ready, and copy a one-click public URL.

## What's done already

A one-shot cleanup script ran against the `wa-template-images` bucket on
**2026-05-06**. The bucket is now 100% Meta-compliant for WhatsApp template
headers.

Cleanup actions, all reversible from `cleanup_backup_2026-05-06/` at repo root:

- Deleted **38** unprocessed phone photos under
  `Asset/Creating Images/Product Creative Images/Raw Images/`
- Deleted **2** empty-folder placeholders (`Untitled folder/`,
  `Serriy  Series/`).
- Compressed **3** Snow White JPGs (9 MB / 6 MB / 6 MB → 1.1 MB / 0.7 MB / 0.6 MB).
- Converted **9** webp → jpg and **1** webp → jpg in Hemp Display.
  - Burberry 3, Noor 3, ERB Special 2, Hemp Display 1.
- User manually replaced the 3 GIFs in `Nettle Yarn Fine/` with 4 JPEGs.

| Check | Before | After |
|---|---|---|
| Total files | 118 | **78** |
| > 5 MB (Meta rejects) | 10 | **0** |
| webp/gif (Meta rejects) | 15 | **0** |
| Raw phone photos | 38 | **0** |
| Empty placeholders | 3 | **0** |

Cleanup script lives at `scripts/cleanup_wa_template_images.py` and is
idempotent (safe to re-run; supports `--dry-run`).

## Bucket reference

- **Bucket:** `wa-template-images` (public, 78 objects)
- **URL pattern:**
  `https://yxlofrkkzjkxtbowyryj.supabase.co/storage/v1/object/public/wa-template-images/<path>`
  Path components must be URL-encoded with `urllib.parse.quote(path, safe="/")`
  because most paths contain spaces, ampersands, and other reserved chars.
- **Two adjacent buckets** that the page does NOT browse:
  - `wa-media` (3 files) — one-off legacy uploads, not in catalog.
  - `email-invoices` (private) — transactional, untouched.

## Goals

1. Team can find any image **by category in ≤3 clicks** (no Drive/Supabase trip).
2. Each image card carries a **WA-readiness badge** so the team knows up-front
   whether Meta will accept it as a template header.
3. **Copy URL** button puts a properly URL-encoded public link on clipboard.
   Pasting into the Template Studio's *Header asset URL* field "just works".
4. Adding a new image to the catalog later is **one YAML entry per file** — no
   page-code changes.

## Non-goals (this iteration)

- Uploading new images from the page. Uploads stay in
  `scripts/upload_template_images.py` for now (we can add a small upload UI
  in v2 once the read flow is proven).
- Renaming or restructuring the bucket itself. Bucket paths are kept as-is —
  the YAML decouples *display category* from *storage path*. Less risk, no
  broken external links.
- Editing the `wa-media` bucket or pulling from Drive directly.
- Cross-page wiring ("Send to Template Studio" auto-fill). Saved for v2.

## Proposed taxonomy (catalog) — 78 files mapped

The catalog is purpose-led, not folder-led. Yarns lead, fibres are demoted to
specs (per the standing yarn-first preference). Categories are flat under
groups; only one level of nesting in the UI to keep navigation snappy.

```
PRODUCTS
├─ Yarns
│   ├─ Nettle · Fine          (4 files)  Plant Based/1.2 Nettle Yarn/1.2.1 Nettle Yarn Fine/
│   ├─ Nettle · Thick         (4 files)  Plant Based/1.2 Nettle Yarn/1.2.2 Nettle Yarn Thick/
│   ├─ Nettle · White         (3 files)  Plant Based/1.2 Nettle Yarn/1.2.3 White Nettle/
│   ├─ Nettle · Special (ERB) (4 files)  Plant Based/1.2 Nettle Yarn/1.2.4 Special Nettle Yarn/
│   ├─ Hemp · Natural         (3 files)  Plant Based/2.2 Hemp Yarn/2.2.1 Natural Hemp Yarn/
│   ├─ Hemp · White           (2 files)  Plant Based/2.2 Hemp Yarn/2.2.2 White Hemp Yarn/
│   └─ Tibetan Wool           (3 files)  Animal Based/Tibetian Yarn/
├─ Blended Collections
│   ├─ Burberry               (4 files)  Nettle Wool Collection/Burberry Series/
│   ├─ Noor                   (3 files)  Nettle Wool Collection/Noor Series/
│   └─ Snow White             (4 files)  Nettle Wool Collection/Snow White Series/
└─ Fibres (specs only)
    ├─ Nettle Cottonised      (4 files)  Plant Based/1.1 Nettle Fibre/Cottonised Fibres/
    ├─ Nettle Degummed        (4 files)  Plant Based/1.1 Nettle Fibre/Degummed Fibre/
    ├─ Hemp Raw               (2 files)  Plant Based/2.1 Hemp Fibre/2.1.1 Raw Hemp Fibre/
    └─ Hemp Cottonised        (2 files)  Plant Based/2.1 Hemp Fibre/2.1.2 Hemp Cottonized/

CREATIVE & LIFESTYLE
├─ Hand Spinning              (5 files)  Asset/Creating Images/Hand Spinning/
├─ Styled Product             (2 files)  Asset/Creating Images/Product Creative Images/
└─ Village Life               (5 files)  Asset/Creating Images/Village Images/

FIELD & PROCESS
├─ Fibre Bundles & Drying     (6 files)  Asset/Fibre & Fields/
├─ Farm Process               (4 files)  Farm Images/
└─ Women at Work              (4 files)  field/

BRAND
├─ Logos                      (4 files)  Asset/Logo/
└─ Hero Banners               (2 files)  Asset/Hero Banner Image/
```

**Note on Seriry:** `Serriy  Series/` (note: double space, typo) folder is
empty after placeholder removal. Skipped in v1 — re-add as soon as Seriry
images are uploaded.

## Architecture

Four files. Follows the existing engine schema rule: every config goes through
a Pydantic model loaded by `loader/config_loader.py`.

### 1. `hf_dashboard/config/media/asset_catalog.yml`

Single source of truth. Seed once from the bucket listing; thereafter, adding
an image = one entry in this file plus the actual upload via
`scripts/upload_template_images.py`.

```yaml
# Asset catalog for the WhatsApp template image library.
# bucket + url_pattern apply to every entry; per-image `path` is the
# bucket-relative key.
bucket: wa-template-images
url_pattern: "https://yxlofrkkzjkxtbowyryj.supabase.co/storage/v1/object/public/{bucket}/{path}"

groups:
  products:
    label: "Products"
    icon: "📦"
    categories:
      yarns_nettle_fine:
        label: "Nettle Yarn — Fine"
        parent: "Yarns"
        items:
          - path: "Product Images/Plant Based/1.2 Nettle Yarn/1.2.1 Nettle Yarn Fine/1.jpg"
            display_name: "Fine — 1"
            tags: ["nettle", "yarn", "fine", "natural"]
            best_for: ["whatsapp_header", "email_inline", "product_card"]
          # ... three more
      yarns_nettle_thick:
        label: "Nettle Yarn — Thick"
        parent: "Yarns"
        items: [...]
      # ... and so on for all 22 categories
  creative:
    label: "Creative & Lifestyle"
    icon: "🎨"
    categories:
      hand_spinning:
        label: "Hand Spinning"
        items: [...]
      # ...
  field:
    label: "Field & Process"
    icon: "🏞️"
    categories: {...}
  brand:
    label: "Brand"
    icon: "🏷️"
    categories: {...}
```

The seed is generated by a small one-off helper
(`scripts/seed_asset_catalog.py`) that lists the bucket, applies the
prefix-to-category rules from this plan, and emits the YAML. After seeding,
the script is dead — humans edit the YAML by hand.

### 2. `hf_dashboard/engines/asset_catalog_schemas.py`

```python
from pydantic import BaseModel, Field

class AssetItem(BaseModel):
    path: str
    display_name: str
    tags: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)

class AssetCategory(BaseModel):
    label: str
    parent: str | None = None
    items: list[AssetItem]

class AssetGroup(BaseModel):
    label: str
    icon: str
    categories: dict[str, AssetCategory]

class AssetCatalogConfig(BaseModel):
    bucket: str
    url_pattern: str
    groups: dict[str, AssetGroup]
```

Loaded once at import time via `loader.config_loader.load_config(...)`.

### 3. `hf_dashboard/services/asset_catalog.py`

Pure logic, no Gradio:

```python
def public_url(path: str) -> str:
    """Build a properly URL-encoded public URL for a bucket key."""

def wa_status(path: str, size_bytes: int, mime: str) -> Literal["ready","heavy","wrong_format","too_big"]:
    """🟢 ready (jpg/png ≤500 KB), 🟡 heavy (jpg/png 0.5–5 MB),
       🔴 wrong_format, ⚫ too_big (>5 MB)."""

def list_categories() -> list[CategoryView]:
    """Return groups + categories for sidebar/radio rendering."""

def list_items(category_id: str, *, search: str = "") -> list[ItemView]:
    """Return items in a category, filtered by case-insensitive search across
    display_name + tags."""
```

Image size + MIME come from a one-time HEAD against each public URL on first
load, cached via the existing `services.ttl_cache` (TTL 1 day — bucket is
relatively stable). On cache miss the page still renders, just without size
badges; they fill in async.

### 4. `hf_dashboard/pages/asset_browser.py`

Gradio page. Layout:

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  🖼️  Asset Library — copy a URL, paste into Template Studio header field              │
│  🔎 Search [ ___________ ]   ☐ Show only WA-ready                                     │
├────────────────────────┬─────────────────────────────────────────────────────────────┤
│  📦 Products           │   Products › Yarns › Nettle Yarn — Thick   (4 images)       │
│   ▾ Yarns              │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│      · Nettle Fine (4) │  │  [thumb]     │  │  [thumb]     │  │  [thumb]     │       │
│      · Nettle Thick(4) │  │  Thick · 1   │  │  Thick · 2   │  │  Thick · 3   │       │
│      · Nettle White(3) │  │  198 KB jpg  │  │  240 KB jpg  │  │   91 KB jpg  │       │
│      · …               │  │  🟢 WA ready │  │  🟢 WA ready │  │  🟢 WA ready │       │
│   ▸ Blended            │  │ [📋 Copy URL]│  │ [📋 Copy URL]│  │ [📋 Copy URL]│       │
│   ▸ Fibres             │  └──────────────┘  └──────────────┘  └──────────────┘       │
│  🎨 Creative           │                                                              │
│  🏞️ Field & Process    │   URL preview:                                               │
│  🏷️ Brand              │   https://….co/storage/v1/object/public/wa-template-images/  │
│                        │   Product%20Images/Plant%20Based/1.2%20Nettle%20Yarn/...     │
└────────────────────────┴─────────────────────────────────────────────────────────────┘
```

- **Left rail:** group accordions, each expanding to a list of categories with
  file counts. Selecting a category swaps the right-pane gallery.
- **Right pane:** 3-column grid of cards. Each card renders the actual image
  (loaded directly from Supabase public URL — no proxy needed). Below the
  image: name, size + mime, status pill, copy-URL button. Clicking copy
  shows a transient "Copied!" toast and writes the canonical URL to the
  clipboard via Gradio's `gr.HTML` + tiny `<script>` (or
  `gradio.copy_to_clipboard` if available — Gradio 4 has no native helper, so
  a 5-line JS hook is fine here).
- **Status pill rules:**
  - 🟢 **WA ready** — jpeg/png AND ≤500 KB (instant header use)
  - 🟡 **Heavy** — jpeg/png AND 500 KB–5 MB (works, slow load)
  - 🔴 **Wrong format** — webp/gif (Meta rejects). Should never appear after
    cleanup, but the badge is kept defensively.
  - ⚫ **Too big** — >5 MB (Meta rejects). Same — defensive.
- **Search box** (top right): case-insensitive substring match on
  `display_name` + `tags`. Acts on the currently-selected category, with a
  "search across all categories" toggle. Default: search current category
  only, so the rail position stays meaningful.
- **"Show only WA-ready" checkbox:** filters out 🟡 / 🔴 / ⚫ cards. Default:
  off, since some 🟡 files are still legitimate to send (just larger). The
  team can flip on when they want a "safe set".

### 5. `hf_dashboard/config/dashboard/sidebar.yml`

Add one nav entry, between Template Studio and the rest:

```yaml
- id: asset_browser
  label: "Asset Library"
  icon: "\U0001F5BC️"   # 🖼️
```

## Acceptance criteria

A reviewer should be able to verify all of these on the live HF Space after
deploy:

1. Sidebar shows **Asset Library** between Template Studio and the next item.
2. Default landing category is **Products › Yarns › Nettle Fine**.
3. All 78 files appear in some category. Run
   `SELECT count(*) FROM storage.objects WHERE bucket_id = 'wa-template-images';`
   and compare to the sum of items across the catalog YAML.
4. Every visible card image renders (no broken images). Implies URL encoding
   is correct.
5. Clicking *Copy URL* on a Nettle Thick card and pasting into Template
   Studio's *Header asset URL* field shows the image in the live preview
   panel.
6. The 4 Nettle Yarn Fine entries point at `1.jpg` … `4.jpg` (the files
   Prashant uploaded after the GIF removal), not the old `.gif` paths.
7. Search "noor" with category="Products › Blended → Noor" returns 3 cards.
8. Toggling "Show only WA-ready" hides the 4 cards currently in the 🟡 Heavy
   bucket: Hand Spinning main (3.0 MB), Hand Spinning 4 (2.7 MB), Hand
   Spinning 5 (2.0 MB), and Village Cose_house_view (4.0 MB). (See future
   work for compressing those.)

## Out-of-bucket links to update later

Two existing surfaces still hard-code old `.webp` URLs that no longer exist:

- `campaign/_image_manifest.yml` — search for `.webp` entries and rewrite to
  `.jpg`. Same paths, just extension swap.
- Any submitted Meta WA template that referenced the old webp/gif URLs.
  Header asset is immutable for approved templates; check
  `wa_templates` rows where `header_asset_url LIKE '%.webp'` or `LIKE '%.gif'`
  and decide per-row: edit (only allowed for drafts), or supersede with a
  v2 template using a `.jpg` URL.

```sql
-- Find templates that still reference dead URLs
SELECT id, name, status, header_asset_url
FROM wa_templates
WHERE header_asset_url LIKE '%.webp' OR header_asset_url LIKE '%.gif';
```

## Future work (deliberately deferred)

1. **Upload from the page.** Drop a file → Pillow compress → Supabase upload →
   YAML auto-append. Saves the team a CLI trip. Wait for v1 traction first.
2. **"Send to Template Studio" cross-page button.** Pre-fills
   `header_asset_url_input` and switches tabs. Needs a small wiring change in
   `pages/wa_template_studio.py` to accept a route param or shared
   `gr.State`.
3. **Compress the 4 remaining 🟡 Heavy creative shots** (Hand Spinning 3.0 MB
   / 2.7 MB / 2.0 MB, Village 4.0 MB). Same recipe as the Snow White pass.
4. **Seriry Series.** Empty after placeholder cleanup. Re-populate when
   Seriry product photography lands.
5. **Asset usage tracker.** Record which `wa_templates.header_asset_url`
   each catalog item has been used in, surface it on the card so the team
   can see "this image has been sent in 4 campaigns."
6. **Variant suggestions.** Render an "alternatives" rail beside each card
   pulling from the same category — encourages reuse over duplication.

## Build steps (in order)

1. **Seed YAML.** Run `scripts/seed_asset_catalog.py` (one-shot, generates
   `hf_dashboard/config/media/asset_catalog.yml` from the bucket). Hand-review
   tags/best_for and tighten display names where the auto-derivation is ugly.
2. **Schemas + service.** Add `engines/asset_catalog_schemas.py` and
   `services/asset_catalog.py`. Unit-test:
   - `public_url("Hand Spinning/Hand_spinning_3.jpg")` produces the encoded URL
     and a HEAD on it returns 200.
   - `wa_status` correctly classifies a 600 KB jpg as 🟡.
3. **Page.** Add `pages/asset_browser.py` matching the layout above.
4. **Sidebar.** Add the nav entry.
5. **Local sanity-check (skip if you trust the build).** This codebase's
   policy is to never run the app locally; deploy + Playwright is the
   verification path.
6. **Deploy.** `python scripts/deploy_hf.py`. Wait for the Space to report
   *Running*.
7. **Playwright verification.** Drive the live URL through every acceptance
   criterion above, headless. Hand off only when all green.

## Risks

- **Public URLs are long and ugly when copied into emails / chat.** That's
  fine for the Template Studio (programmatic) but may bite if someone copies
  a URL into a customer chat thread. Acceptable risk — the cards do not
  encourage that use.
- **Meta image-cache divergence.** Meta caches the header image at template
  approval time; replacing the file in Supabase later does NOT update what
  Meta sends. This was already true and is not changed by this work; future
  work item #5 (usage tracker) makes the impact visible.
- **Service-key in the dashboard.** `services/supabase_storage.py` already
  uses the service-role key for invoice uploads and is a documented
  server-only secret. The Asset Library does not need the service key for
  reads — public URLs go through Supabase's public CDN — so we should NOT
  add new code paths that fetch through the service key from the page.

## File-by-file change list

```
NEW   docs/asset_library_plan.md                                 (this file)
NEW   scripts/cleanup_wa_template_images.py                      (already shipped)
NEW   scripts/seed_asset_catalog.py                              (one-shot YAML seed)
NEW   hf_dashboard/config/media/asset_catalog.yml                (catalog SoT)
NEW   hf_dashboard/engines/asset_catalog_schemas.py              (Pydantic)
NEW   hf_dashboard/services/asset_catalog.py                     (URL + status logic)
NEW   hf_dashboard/pages/asset_browser.py                        (Gradio page)
EDIT  hf_dashboard/config/dashboard/sidebar.yml                  (+1 nav entry)
```

No edits to existing pages, no edits to the bucket layout, no schema
migrations.
