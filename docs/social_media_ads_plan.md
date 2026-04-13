# Plan: Instagram, Facebook & Ads Integration

## Context

Extend the Himalayan Fibers dashboard to manage social media posts (Instagram + Facebook) and Meta ads — all YAML-driven, same pattern as WhatsApp templates. This builds on the existing Meta Business API infrastructure (Facebook App, Business Account) already used for WhatsApp.

## Prerequisites (Prashant Must Do)

Before any code is written, these must be set up in Meta Business Suite:

### 1. Connect Facebook Page
- Go to https://business.facebook.com/settings → Pages → Add
- Connect the Himalayan Fibres Facebook page
- Get the Page ID and Page Access Token

### 2. Connect Instagram Business Account
- Meta Business Suite → Instagram Accounts → Add
- Instagram must be Business or Creator account (not personal)
- Link it to the Facebook Page
- Get the Instagram Business Account ID

### 3. Set Up Ad Account
- Meta Business Suite → Ad Accounts → Add
- Create new or connect existing
- Note the Ad Account ID (format: act_XXXXXXXXX)
- Add a payment method for ads

### 4. Update Facebook App Permissions
In your Facebook App (ID from .env WA_APP_ID), request these permissions:
- `pages_manage_posts` — publish to Facebook Page
- `pages_read_engagement` — read post performance
- `instagram_basic` — read Instagram profile
- `instagram_content_publish` — publish to Instagram
- `ads_management` — already granted ✅
- `ads_read` — already granted ✅
- `business_management` — already granted ✅

### 5. Generate New Token
After permissions are approved, generate a System User token with all permissions.
Add as HF Space secrets:
- `META_PAGE_ID` — Facebook Page ID
- `META_PAGE_TOKEN` — Page Access Token (long-lived)
- `INSTAGRAM_ACCOUNT_ID` — Instagram Business Account ID
- `META_AD_ACCOUNT_ID` — Ad Account ID (act_XXXX)

---

## Architecture

```
hf_dashboard/
├── config/
│   ├── social/
│   │   ├── posts.yml          # Post templates (IG + FB)
│   │   ├── stories.yml        # Story templates
│   │   ├── ads.yml            # Ad campaign definitions
│   │   └── audiences.yml      # Saved audiences for targeting
│   └── whatsapp/              # (existing)
├── services/
│   ├── social_publisher.py    # Publish posts to IG + FB via Graph API
│   ├── ads_manager.py         # Create/manage Meta ads via Marketing API
│   └── media_uploader.py      # Upload images/videos to Meta CDN
├── pages/
│   ├── social.py              # Social Media page (new)
│   └── ads.py                 # Ads Manager page (new)
└── scripts/
    ├── publish_post.py        # CLI: publish a post from YAML
    ├── create_ad.py           # CLI: create an ad campaign from YAML
    └── social_scheduler.py    # Cron: auto-publish scheduled posts
```

---

## YAML Schema: Posts

```yaml
# config/social/posts.yml
posts:

  # -- Product Showcase --
  nettle_yarn_showcase:
    platforms: [instagram, facebook]
    type: image
    image: media/products/nettle_yarn.jpg
    caption: |
      Premium Himalayan Stinging Nettle Yarn 🌿
      Sustainably sourced from 1200-2100m altitude.

      ✅ Naturally lustrous fiber
      ✅ EU sustainability certified
      ✅ Available in bulk for manufacturers

      DM us for samples and pricing.
    hashtags:
      - HimalayanFibres
      - NettleYarn
      - SustainableFashion
      - NaturalFibers
      - HandmadeTextiles
    schedule: "2026-04-15 10:00"  # Optional: schedule for later
    status: draft                  # draft | scheduled | published

  # -- Behind the Scenes --
  workshop_bts:
    platforms: [instagram, facebook]
    type: carousel
    images:
      - media/products/workshop_1.jpg
      - media/products/workshop_2.jpg
      - media/products/workshop_3.jpg
    caption: |
      From the Himalayas to your home 🏔️

      Our artisans hand-process every fiber at our workshop
      in Uttarakhand. No machines, no shortcuts.
    hashtags: [HimalayanFibres, Handmade, Artisan]
    status: draft

  # -- Reel --
  fiber_process_reel:
    platforms: [instagram]
    type: reel
    video: media/videos/fiber_processing.mp4
    caption: "Watch how we process raw nettle into premium yarn 🧶"
    hashtags: [HimalayanFibres, ProcessVideo, BehindTheScenes]
    status: draft
```

## YAML Schema: Ads

```yaml
# config/social/ads.yml
campaigns:

  # -- B2B Lead Generation --
  b2b_carpet_exporters:
    objective: LEAD_GENERATION
    status: PAUSED                    # PAUSED | ACTIVE
    budget:
      type: daily                     # daily | lifetime
      amount: 500                     # INR per day
      duration_days: 30
    audience:
      countries: [IN]
      cities: [Bhadohi, Mirzapur, Varanasi, Agra, Jaipur]
      age_min: 25
      age_max: 60
      interests:
        - carpet manufacturing
        - textile exports
        - handloom industry
      exclude_interests:
        - competitor brands
    creative:
      format: single_image
      image: media/ads/b2b_banner.jpg
      headline: "Premium Himalayan Fibers for Your Carpets"
      description: "Direct from source. Sustainably sourced. EU certified."
      cta: LEARN_MORE
      url: "https://www.himalayanfibres.com"
    tracking:
      pixel_id: ""                    # Meta Pixel ID for conversion tracking
      conversion_event: Lead

  # -- International Yarn Store Awareness --
  yarn_store_awareness:
    objective: REACH
    status: PAUSED
    budget:
      type: daily
      amount: 1000
      duration_days: 14
    audience:
      countries: [US, GB, CA, AU]
      interests:
        - yarn stores
        - knitting
        - crochet
        - fiber arts
      age_min: 30
      age_max: 65
      gender: all
    creative:
      format: carousel
      images:
        - media/ads/nettle_yarn.jpg
        - media/ads/hemp_yarn.jpg
        - media/ads/wool_blend.jpg
      headlines:
        - "Himalayan Nettle Yarn"
        - "Organic Hemp Yarn"
        - "Tibetan Wool Blend"
      description: "Premium natural fibers, direct from the Himalayas"
      cta: SHOP_NOW
      url: "https://www.himalayanfibres.com/shop"

## YAML Schema: Audiences

```yaml
# config/social/audiences.yml
audiences:

  indian_carpet_manufacturers:
    name: "Indian Carpet Manufacturers"
    countries: [IN]
    cities: [Bhadohi, Mirzapur, Varanasi, Agra, Jaipur, Panipat]
    age_min: 25
    age_max: 60
    interests:
      - carpet manufacturing
      - textile exports
      - handloom weaving

  international_yarn_enthusiasts:
    name: "International Yarn Stores & Crafters"
    countries: [US, GB, CA, AU, DE, FR]
    age_min: 25
    age_max: 65
    interests:
      - yarn
      - knitting
      - crochet
      - fiber arts
      - textile crafts

  eco_conscious_buyers:
    name: "Eco-Conscious Textile Buyers"
    countries: [US, GB, DE, FR, NL, SE]
    age_min: 28
    age_max: 55
    interests:
      - sustainable fashion
      - organic textiles
      - eco-friendly products
      - fair trade
```

---

## Dashboard Pages

### Page: Social Media (📸)

Layout: Same two-column pattern as other pages.

**Left column:**
- Platform filter (All / Instagram / Facebook)
- Post type filter (Image / Carousel / Reel / Story)
- Status filter (Draft / Scheduled / Published)

**Right column:**
- Post list with thumbnail, caption preview, platform badges, status
- "Create Post" button → form with:
  - Platform checkboxes (Instagram ☑ Facebook ☑)
  - Image/video upload
  - Caption textarea
  - Hashtag input
  - Schedule date/time (optional)
  - "Publish Now" or "Schedule" button
- Published posts history with engagement stats (likes, comments, shares)

### Page: Ads Manager (📊)

**Left column:**
- Campaign status filter (Active / Paused / All)
- Budget summary KPI cards (total spend, reach, leads)

**Right column:**
- Campaign list with name, status, budget, spend, reach, leads
- "Create Campaign" from YAML dropdown
- "Activate / Pause" buttons
- Performance metrics per campaign (impressions, clicks, CTR, CPC, conversions)

---

## Implementation Steps

### Phase 1: Social Media Publishing (1-2 days)

1. **services/social_publisher.py** — Meta Graph API client
   - `publish_to_facebook(page_id, message, image_url)` — POST to /{page_id}/feed
   - `publish_to_instagram(ig_account_id, image_url, caption)` — POST to /{ig_id}/media → /{ig_id}/media_publish
   - `schedule_post(post_id, timestamp)` — schedule for later
   - `get_post_insights(post_id)` — likes, comments, shares, reach

2. **services/media_uploader.py** — Upload images to Meta CDN
   - `upload_image(filepath)` → returns hosted URL
   - Instagram requires a publicly accessible URL for images

3. **config/social/posts.yml** — Post definitions (YAML)

4. **scripts/publish_post.py** — CLI to publish from YAML
   - `python scripts/publish_post.py nettle_yarn_showcase` — publish one post
   - `python scripts/publish_post.py --schedule` — publish all scheduled posts due now

5. **pages/social.py** — Dashboard page for viewing/publishing

### Phase 2: Ads Manager (2-3 days)

1. **services/ads_manager.py** — Meta Marketing API client
   - `create_campaign(name, objective, budget, status)` — creates campaign
   - `create_ad_set(campaign_id, audience, budget)` — creates targeting
   - `create_ad(ad_set_id, creative)` — creates the actual ad
   - `get_campaign_insights(campaign_id)` — impressions, clicks, spend, conversions
   - `pause_campaign(campaign_id)` / `activate_campaign(campaign_id)`

2. **config/social/ads.yml** — Campaign definitions (YAML)
3. **config/social/audiences.yml** — Saved audience definitions

4. **scripts/create_ad.py** — CLI to create campaigns from YAML
   - `python scripts/create_ad.py b2b_carpet_exporters` — create one campaign
   - `python scripts/create_ad.py --status` — check all campaign statuses

5. **pages/ads.py** — Dashboard page for viewing/managing ads

### Phase 3: Automation & Analytics (1-2 days)

1. **scripts/social_scheduler.py** — Cron job to auto-publish scheduled posts
2. **Background thread** in app.py for scheduled publishing
3. **Analytics section** — aggregate metrics across all posts and campaigns
4. **Content calendar view** — see what's scheduled for the week/month

---

## API Endpoints Used

### Facebook Page Publishing
```
POST https://graph.facebook.com/v21.0/{page_id}/photos
  - message: caption text
  - url: image URL (or upload source)

POST https://graph.facebook.com/v21.0/{page_id}/feed
  - message: text post
  - link: URL to share
```

### Instagram Publishing (2-step process)
```
Step 1: Create media container
POST https://graph.facebook.com/v21.0/{ig_user_id}/media
  - image_url: publicly accessible image URL
  - caption: post caption with hashtags

Step 2: Publish
POST https://graph.facebook.com/v21.0/{ig_user_id}/media_publish
  - creation_id: container ID from step 1
```

### Meta Ads (Marketing API)
```
Create Campaign:
POST https://graph.facebook.com/v21.0/act_{ad_account_id}/campaigns
  - name, objective, status, special_ad_categories

Create Ad Set (targeting):
POST https://graph.facebook.com/v21.0/act_{ad_account_id}/adsets
  - campaign_id, targeting, budget, billing_event

Create Ad Creative:
POST https://graph.facebook.com/v21.0/act_{ad_account_id}/adcreatives
  - name, object_story_spec (image, headline, description, CTA)

Create Ad:
POST https://graph.facebook.com/v21.0/act_{ad_account_id}/ads
  - adset_id, creative_id, status
```

---

## Secrets Needed (HF Spaces)

| Secret | Description |
|--------|-------------|
| `META_PAGE_ID` | Facebook Page ID |
| `META_PAGE_TOKEN` | Long-lived Page Access Token |
| `INSTAGRAM_ACCOUNT_ID` | Instagram Business Account ID |
| `META_AD_ACCOUNT_ID` | Ad Account ID (act_XXXX format) |
| `META_PIXEL_ID` | Meta Pixel for conversion tracking (optional) |

---

## Priority Order

1. **First:** Prashant connects FB Page + Instagram + Ad Account in Meta Business Suite
2. **Second:** I build social media publishing (posts to IG + FB)
3. **Third:** I build ads manager (create/manage campaigns)
4. **Fourth:** Automation + analytics

---

## Cost Estimates

- **Social media posting:** Free (organic posts)
- **Meta Ads:** You control the budget (minimum ₹40/day per campaign)
- **API usage:** Free (Meta Graph API has no per-call charges)
- **HF Spaces hosting:** Free tier (already running)
