# Plan: YAML-Driven Blog & Story Publishing System for Wix

## Context

Prashant needs a simple, repeatable system to create blog posts and "Our Story" pages on the Himalayan Fibres Wix website (himalayanfibres.com). The site currently has no blog content, which hurts SEO. The system should follow the existing YAML config pattern, so Prashant fills in a YAML template with topic + key points + image paths, Claude AI-drafts the full content, Prashant reviews, then Claude publishes via the Wix MCP.

### User Decisions
- **Publishing**: Via Wix MCP (Claude reads YAML, uploads images, publishes posts directly)
- **Content creation**: AI drafts, Prashant reviews (Claude generates from topic + product data + brand voice)
- **Google Drive path**: `G:\My Drive\1. Media & Marketing` (Windows) = `/mnt/g/My Drive/1. Media & Marketing/` (WSL2)

---

## Part 1: Directory Structure

```
config/blog/
  _settings.yml              # Site ID, default author, GDrive base path, defaults
  _categories.yml            # Blog category definitions
  posts/                     # Blog post YAML files
    sustainability_story.yml
    nettle_fiber_guide.yml
    ...
  stories/                   # "Our Story" / brand narrative pages
    our_story.yml
    about_us.yml
    meet_our_artisans.yml
    ...
```

No new `app/blog/` Python module needed — publishing happens entirely through Claude + Wix MCP.

---

## Part 2: YAML Templates

### Blog Post Template (`config/blog/posts/<post_id>.yml`)

```yaml
# Blog Post: [Title]
# Usage: Fill in topic, key_points, and image paths. Claude generates full content.
# Then review the generated content sections and tell Claude to publish.

post:
  id: "sustainability_story"
  title: "From Himalayan Villages to Your Hands: Our Sustainability Story"
  slug: "our-sustainability-story"
  status: "draft"                     # draft | ready | published
  category: "storytelling"            # must match _categories.yml
  featured: false
  tags:
    - "sustainability"
    - "artisans"
    - "nettle"

seo:
  meta_title: ""                      # blank = auto-generated from title
  meta_description: ""                # blank = auto-generated from first paragraph
  focus_keyword: "sustainable himalayan fibers"

cover_image:
  local_file: "/mnt/g/My Drive/1. Media & Marketing/photos/sustainability_hero.jpg"
  alt: "Himalayan village artisans processing nettle fibers"

# ---- INPUT SECTION (Prashant fills this) ----
brief:
  topic: "Our sustainability practices and impact on Himalayan communities"
  key_points:
    - "75+ villages supported across Uttarakhand"
    - "200+ women artisans earning independent incomes"
    - "Zero-waste processing from raw fiber to finished product"
    - "Wild-harvested plants, no pesticides"
  tone: "warm, inspiring, factual"     # or use default from brand_kit
  target_audience: "eco-conscious crafters and B2B textile buyers"
  word_count: 800                      # approximate target
  product_refs:                        # auto-pull data from product configs
    - "special_nettle_yarn"
    - "natural_nettle_yarn"

# ---- CONTENT SECTION (Claude generates, Prashant reviews) ----
content:
  - type: heading
    level: 2
    text: ""

  - type: paragraph
    text: ""

  # ... Claude fills these in, Prashant reviews before publish

# ---- IMAGES (paths to local Google Drive files) ----
images:
  - local_file: "/mnt/g/My Drive/1. Media & Marketing/photos/village_artisans.jpg"
    alt: "Women artisans in a Himalayan village"
    insert_after: 1                    # insert after content block index 1

  - local_file: "/mnt/g/My Drive/1. Media & Marketing/photos/nettle_harvest.jpg"
    alt: "Wild nettle harvesting in the Himalayas"
    insert_after: 4

author:
  name: "Prashant Agrawal"
  role: "Founder"
```

### Key Design: `brief` Section
This is the simple input — Prashant fills just `topic`, `key_points`, `product_refs`, and image paths. Claude uses this + product data + brand voice to generate the full `content` blocks.

### "Our Story" Template (`config/blog/stories/our_story.yml`)
Same format as blog posts, with `featured: true` and `category: "storytelling"`. These get published as pinned blog posts that can be linked from site navigation.

### Categories (`config/blog/_categories.yml`)
```yaml
categories:
  - id: "storytelling"
    name: "Our Stories"
    description: "Brand narratives, artisan journeys, and the Himalayan Fibres story"
    slug: "our-stories"

  - id: "product_guides"
    name: "Product Guides"
    description: "Deep dives into our fibers, yarns, and collections"
    slug: "product-guides"

  - id: "sustainability"
    name: "Sustainability"
    description: "Environmental impact, ethical practices, and community development"
    slug: "sustainability"

  - id: "craft_tips"
    name: "Craft & Tips"
    description: "Working with natural Himalayan fibers - techniques and inspiration"
    slug: "craft-tips"

  - id: "behind_the_scenes"
    name: "Behind the Scenes"
    description: "Village life, production process, and the people behind our fibers"
    slug: "behind-the-scenes"

  - id: "news"
    name: "News & Updates"
    description: "Company news, trade shows, new products, and announcements"
    slug: "news"
```

### Settings (`config/blog/_settings.yml`)
```yaml
blog:
  wix_site_id: "580a6298-44ff-47b2-80ce-f3ec82e62db7"
  site_url: "https://www.himalayanfibres.com"

  default_author:
    name: "Prashant Agrawal"
    role: "Founder"

  default_tone: "warm, professional, sustainable-focused"

media:
  gdrive_base_path: "/mnt/g/My Drive/1. Media & Marketing"
  wix_upload_folder: "blog"
  supported_formats:
    - ".jpg"
    - ".jpeg"
    - ".png"
    - ".webp"

publishing:
  default_status: "draft"
  auto_seo: true
```

---

## Part 3: Publishing Workflow (How It Works)

### Step-by-Step Flow
```
1. Prashant creates/copies a YAML file in config/blog/posts/
2. Fills in: brief.topic, brief.key_points, brief.product_refs, image paths
3. Tells Claude: "Generate content for config/blog/posts/sustainability_story.yml"
4. Claude:
   a. Reads the YAML brief
   b. Reads referenced product configs for data
   c. Reads brand_kit.yml for voice/tone
   d. Generates full content blocks and writes them into the YAML
5. Prashant reviews the content in the YAML file, makes edits
6. Prashant tells Claude: "Publish config/blog/posts/sustainability_story.yml"
7. Claude:
   a. Reads the finalized YAML
   b. Uploads cover image + inline images to Wix Media Manager
      - Step 1: CallWixSiteAPI -> POST /site-media/v1/files/generate-upload-url
      - Step 2: Bash -> curl -X PUT '<upload_url>' --data-binary @'<local_file>'
   c. Converts content blocks to Ricos JSON format
   d. Creates/publishes blog post via CallWixSiteAPI -> POST /blog/v3/draft-posts
   e. Updates YAML status to "published" + adds wix_post_url
8. Post is live at himalayanfibres.com/post/<slug>
```

### Image Upload Flow (Local File -> Wix)
Since images are local files (not URLs), we use the 2-step upload:
1. **MCP call**: Generate upload URL via `POST /site-media/v1/files/generate-upload-url`
2. **Bash curl**: Upload binary to the pre-signed URL
3. Returns a Wix media ID used in the blog post

---

## Part 4: How Blog Posts Appear on Wix

### Brand Identity — Automatic
- Blog posts **inherit the Wix site theme** (colors #232323/#c38513, Georgia fonts, styling)
- No custom CSS or design work needed — it matches the existing site
- Cover images display as hero banners
- Categories and tags create navigable archive pages

### URLs After Publishing
- Blog listing: `himalayanfibres.com/blog`
- Individual post: `himalayanfibres.com/post/our-sustainability-story`
- Category page: `himalayanfibres.com/blog/categories/our-stories`

### SEO Benefits (per post)
- Unique indexed page with proper URL slug
- Meta title + description (auto-generated or custom)
- Structured data / schema markup (Wix auto-generates)
- Open Graph tags for social sharing
- Internal linking via product references and related posts

### One-Time Setup (5 min in Wix Editor)
- Verify Blog app is in site navigation
- Optionally customize blog page layout (grid/list/posts per page)
- Done once — then everything is YAML + Claude

---

## Part 5: Content Creation Strategy (AI Drafts)

### For Each Post, Claude Uses:
1. **brief** section from the YAML (topic, key points, audience, word count)
2. **Product data** from `config/products/` (descriptions, features, USPs, benefits)
3. **Brand voice** from `config/brand/brand_kit.yml` (tone, keywords, words to avoid)
4. **Category context** to match appropriate depth and style

### Content Block Types
| Type | YAML | What Claude Generates |
|------|------|----------------------|
| `heading` | `level` + `text` | Section headings (H2, H3) |
| `paragraph` | `text` | Body paragraphs in brand voice |
| `image` | `local_file` + `alt` | Embedded image with alt text |
| `list` | `style` + `items` | Bullet or numbered lists |
| `quote` | `text` | Blockquotes |
| `product_highlight` | `product_id` | Auto-generated product showcase (name, description, image, features) pulled from product config |

### Suggested Initial Posts (Priority Order)
1. **Our Story** (stories/) — founding narrative, mission, vision
2. **About Himalayan Fibres** (stories/) — company overview, what we do, USPs
3. **The Nettle Fiber Journey** (posts/) — from wild plant to "Himalayan Silk" yarn
4. **Meet Our Artisans** (posts/) — women empowerment, village stories
5. **Why Choose Natural Fibers?** (posts/) — sustainability, synthetic comparison
6. **Hemp: The Versatile Wonder Fiber** (posts/) — product education
7. **Our Collections: Snow White Series** (posts/) — collection showcase

---

## Part 6: Google Drive Image Pipeline

### Path Mapping
- Windows: `G:\My Drive\1. Media & Marketing\`
- WSL2: `/mnt/g/My Drive/1. Media & Marketing/`

### Next Step
After building the YAML templates, I'll scan the Google Drive folder to:
1. Catalog available images (products, artisans, landscapes, process shots)
2. Suggest which images map to which blog posts
3. Pre-fill `local_file` paths in the YAML templates

---

## Part 7: Implementation Steps

### What I'll Build
1. **`config/blog/_settings.yml`** — blog settings with site ID, GDrive path, defaults
2. **`config/blog/_categories.yml`** — category definitions
3. **`config/blog/posts/_template.yml`** — blank template for new posts (copy & fill)
4. **`config/blog/stories/_template.yml`** — blank template for story pages
5. **First draft posts** — generate content for top priority posts using product data + brand voice

### What I Won't Build (Not Needed with MCP Approach)
- No `app/blog/` Python module
- No standalone publisher script
- No API key management
- Claude handles all Wix API calls via MCP

### Files to Create
- `config/blog/_settings.yml`
- `config/blog/_categories.yml`
- `config/blog/posts/_template.yml`
- `config/blog/stories/_template.yml`
- Initial post YAML files (content generated by Claude)

### Files to Modify
- `app/config_manager.py` — add blog config loading (optional, for listing/validation)

### Verification
1. Scan Google Drive folder to verify image access
2. Create first test post YAML with generated content
3. Upload test image to Wix Media Manager via MCP
4. Publish test post to Wix via MCP
5. Verify post at `himalayanfibres.com/post/<slug>` — check cover image, content, SEO, brand styling
