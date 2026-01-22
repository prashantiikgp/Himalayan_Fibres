# API & Tools Setup Guide - Himalayan Fibres

## Overview

This guide walks you through setting up all the APIs and tools needed for comprehensive SEO, performance monitoring, and digital presence management.

**Total Setup Time**: ~2-3 hours for all phases
**Prerequisites**:
- Google account (preferably the one used for your business)
- Access to your Wix site admin
- Meta Business account (you already have this - Facebook Pixel is installed)

---

## PHASE 1: Google Foundation

### 1.1 Google Cloud Project Setup (Required for ALL Google APIs)

Before using any Google API, you need a Google Cloud Project. This is a one-time setup that all Google APIs will share.

#### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Click the project dropdown (top left, next to "Google Cloud")
4. Click **"New Project"**
5. Enter project details:
   - **Project name**: `himalayan-fibres-seo` (or your preferred name)
   - **Organization**: Leave as default
   - **Location**: Leave as default
6. Click **"Create"**
7. Wait for project creation (takes ~30 seconds)
8. Select your new project from the dropdown

#### Step 2: Enable Billing (Required but you won't be charged for basic usage)

> **Note**: Most Google APIs have generous free tiers. You need billing enabled but won't be charged for normal SEO monitoring usage.

1. In Google Cloud Console, go to **Navigation Menu (☰) → Billing**
2. Click **"Link a billing account"**
3. If you don't have one, click **"Create billing account"**
4. Follow the prompts to add a payment method
5. Set up **Budget Alerts** (recommended):
   - Go to **Billing → Budgets & alerts**
   - Create a budget of $10/month with email alerts
   - This protects you from unexpected charges

---

### 1.2 Google Search Console Setup

Google Search Console is FREE and essential for SEO monitoring.

#### Step 1: Verify Site Ownership

1. Go to [Google Search Console](https://search.google.com/search-console)
2. Click **"Add property"**
3. Choose **"URL prefix"** method
4. Enter your full website URL: `https://www.himalayanfibres.com` (replace with your actual URL)
5. Click **"Continue"**

#### Step 2: Verification Methods (Choose ONE)

**Option A: HTML Tag (Easiest for Wix)**
1. Copy the meta tag provided (looks like: `<meta name="google-site-verification" content="xxxxx" />`)
2. In Wix:
   - Go to **Dashboard → Settings → Custom Code**
   - Or **Marketing & SEO → SEO Tools → Site Verification**
   - Add the meta tag to the `<head>` section
3. Return to Search Console and click **"Verify"**

**Option B: DNS Verification (More reliable)**
1. Copy the TXT record provided
2. Go to your domain registrar (where you bought your domain)
3. Add a DNS TXT record with the value provided
4. Wait 5-10 minutes, then click **"Verify"**

#### Step 3: Submit Your Sitemap

1. In Search Console, go to **Sitemaps** (left sidebar)
2. Enter your sitemap URL: `sitemap.xml`
   - Wix auto-generates this at: `https://yoursite.com/sitemap.xml`
3. Click **"Submit"**
4. Status should change to "Success" within a few hours

#### Step 4: Enable Search Console API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (`himalayan-fibres-seo`)
3. Go to **Navigation Menu (☰) → APIs & Services → Library**
4. Search for **"Google Search Console API"**
5. Click on it, then click **"Enable"**

#### Step 5: Create API Credentials

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials"** → **"OAuth client ID"**
3. If prompted, configure OAuth consent screen first:
   - User Type: **External**
   - App name: `Himalayan Fibres SEO Tools`
   - User support email: Your email
   - Developer contact: Your email
   - Click **"Save and Continue"** through all steps
4. Back to Credentials → **"+ Create Credentials"** → **"OAuth client ID"**
5. Application type: **Desktop app** (for local scripts) or **Web application** (for server)
6. Name: `Search Console Client`
7. Click **"Create"**
8. **Download the JSON file** - save it securely as `google_credentials.json`

#### Step 6: Create Service Account (Alternative - for automated scripts)

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials"** → **"Service account"**
3. Enter details:
   - Name: `seo-monitoring-service`
   - ID: auto-generated
4. Click **"Create and Continue"**
5. Role: **Basic → Viewer** (or skip)
6. Click **"Done"**
7. Click on the service account you created
8. Go to **"Keys"** tab → **"Add Key"** → **"Create new key"**
9. Choose **JSON** format
10. Download and save securely as `service_account.json`
11. **Add this service account to Search Console**:
    - Go to [Search Console](https://search.google.com/search-console)
    - Click **Settings** (gear icon) → **Users and permissions**
    - Click **"Add user"**
    - Enter the service account email (found in your JSON file)
    - Permission: **Full**

#### Search Console API - What You Can Do

| Endpoint | Purpose |
|----------|---------|
| `searchAnalytics.query` | Get search performance data (clicks, impressions, keywords) |
| `sitemaps.list` | List all submitted sitemaps |
| `sitemaps.submit` | Submit a new sitemap |
| `urlInspection.index.inspect` | Check if a URL is indexed |

**API Documentation**: https://developers.google.com/webmaster-tools/v1/api_reference_index

---

### 1.3 Google PageSpeed Insights API

This API is simpler - you only need an API key, no OAuth.

#### Step 1: Enable the API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Go to **APIs & Services → Library**
4. Search for **"PageSpeed Insights API"**   # AIzaSyARZbM69LdQbocvNc_k694hX-S3o7LqNi4
5. Click **"Enable"**

#### Step 2: Create API Key

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials"** → **"API key"**
3. Copy the API key that appears
4. **Restrict the key** (recommended):
   - Click on the API key name
   - Under "API restrictions", select **"Restrict key"**
   - Choose only **"PageSpeed Insights API"**
   - Click **"Save"**

#### Step 3: Test Your API Key

You can test immediately in your browser:

```
https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://yoursite.com&key=YOUR_API_KEY
```
https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://himalayanfibres.com&key=AIzaSyARZbM69LdQbocvNc_k694hX-S3o7LqNi4
Replace `yoursite.com` with your actual site and `YOUR_API_KEY` with your key.

#### PageSpeed API - What You Get

| Metric | Description |
|--------|-------------|
| Performance Score | 0-100 overall score |
| First Contentful Paint (FCP) | Time to first content |
| Largest Contentful Paint (LCP) | Time to largest element |
| Cumulative Layout Shift (CLS) | Visual stability |
| Time to Interactive (TTI) | When page becomes interactive |
| Speed Index | How quickly content is visible |

**API Documentation**: https://developers.google.com/speed/docs/insights/v5/get-started

---

### 1.4 Google Indexing API (For faster indexing)

This API lets you notify Google immediately when you publish new content.

#### Step 1: Enable the API

1. Go to **APIs & Services → Library**
2. Search for **"Indexing API"** (or "Web Search Indexing API")
3. Click **"Enable"**

#### Step 2: Use Your Service Account

The service account you created for Search Console works here too.

1. Make sure your service account has been added to Search Console (Step 1.2.6)
2. Use the same `service_account.json` file

#### Step 3: How to Use

```python
# Example: Notify Google of a new/updated URL
POST https://indexing.googleapis.com/v3/urlNotifications:publish
{
  "url": "https://yoursite.com/new-blog-post",
  "type": "URL_UPDATED"  # or "URL_DELETED"
}
```

**Limits**: 200 requests per day (free tier)

**API Documentation**: https://developers.google.com/search/apis/indexing-api/v3/quickstart

---

### 1.5 Bing Webmaster Tools (For Microsoft AI - Copilot, Bing Chat)

#### Step 1: Sign Up

1. Go to [Bing Webmaster Tools](https://www.bing.com/webmasters)
2. Sign in with Microsoft account (or create one)
3. Click **"Add a site"**

#### Step 2: Import from Google (Easiest)

1. Choose **"Import from Google Search Console"**
2. Sign in to your Google account
3. Select your site
4. Bing will automatically verify and import settings

#### Step 3: Alternative - Manual Verification

1. Enter your site URL
2. Choose verification method:
   - **XML file**: Download and upload to your site root
   - **Meta tag**: Add to your site's `<head>`
   - **CNAME**: Add DNS record

#### Step 4: Submit Sitemap

1. Go to **Sitemaps** in Bing Webmaster
2. Submit your sitemap URL: `https://yoursite.com/sitemap.xml`

#### Bing Webmaster API

1. Go to **Settings → API Access**
2. Generate an API key
3. Use for programmatic access

**API Documentation**: https://docs.microsoft.com/en-us/bingwebmaster/

---

## PHASE 2: Analytics & Tracking

### 2.1 Google Analytics 4 Setup

#### Step 1: Create GA4 Property

1. Go to [Google Analytics](https://analytics.google.com/)
2. Click **Admin** (gear icon)
3. Click **"Create Property"**
4. Enter:
   - Property name: `Himalayan Fibres`
   - Reporting time zone: Your timezone
   - Currency: Your currency
5. Click **"Next"**
6. Select your business details and objectives
7. Click **"Create"**

#### Step 2: Set Up Data Stream

1. Choose **"Web"** platform
2. Enter your website URL and stream name
3. Click **"Create stream"**
4. Copy the **Measurement ID** (starts with `G-`)

#### Step 3: Add to Wix

1. In Wix Dashboard, go to **Marketing & SEO → Marketing Integrations**
2. Find **Google Analytics**
3. Click **"Connect"**
4. Enter your Measurement ID (`G-XXXXXXX`)
5. Save

#### Step 4: Enable GA4 API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. **APIs & Services → Library**
3. Search for **"Google Analytics Data API"**
4. Click **"Enable"**

#### Step 5: Link to Search Console

1. In GA4, go to **Admin → Product Links → Search Console Links**
2. Click **"Link"**
3. Select your Search Console property
4. Complete the linking

#### GA4 API - What You Can Do

| Endpoint | Purpose |
|----------|---------|
| `runReport` | Get traffic, user, and conversion data |
| `runRealtimeReport` | See current active users |
| `getMetadata` | List available dimensions and metrics |

**API Documentation**: https://developers.google.com/analytics/devguides/reporting/data/v1

---

### 2.2 Meta Conversions API (Enhance Your Existing Pixel)

You already have Meta Pixel installed. The Conversions API sends events server-side for better accuracy.

#### Step 1: Access Events Manager

1. Go to [Meta Events Manager](https://business.facebook.com/events_manager)
2. Select your Pixel
3. Click **"Settings"**

#### Step 2: Generate Access Token

1. Scroll to **"Conversions API"** section
2. Click **"Generate access token"**
3. Copy and save the token securely

#### Step 3: Get Your Pixel ID

1. In Events Manager, your Pixel ID is shown at the top
2. It's a number like: `123456789012345`

#### Step 4: API Endpoint

```
POST https://graph.facebook.com/v18.0/{PIXEL_ID}/events?access_token={ACCESS_TOKEN}
```

#### What to Send

Track these e-commerce events:
- `PageView` - Every page visit
- `ViewContent` - Product page views
- `AddToCart` - Cart additions
- `InitiateCheckout` - Checkout started
- `Purchase` - Completed orders

**API Documentation**: https://developers.facebook.com/docs/marketing-api/conversions-api

---

### 2.3 Meta Open Graph Tags (Improve Social Sharing)

Open Graph tags control how your pages appear when shared on Facebook, LinkedIn, WhatsApp, etc.

#### Required Tags for Each Page

```html
<!-- Basic OG Tags -->
<meta property="og:title" content="Himalayan Nettle Fiber | Sustainable Plant Textiles">
<meta property="og:description" content="Premium hand-processed nettle fiber from the Himalayas. Sustainable, durable, and eco-friendly.">
<meta property="og:image" content="https://yoursite.com/images/og-image.jpg">
<meta property="og:url" content="https://yoursite.com/page-url">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Himalayan Fibres">

<!-- For Products -->
<meta property="og:type" content="product">
<meta property="product:price:amount" content="99.00">
<meta property="product:price:currency" content="USD">

<!-- Twitter Cards -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Your Title">
<meta name="twitter:description" content="Your Description">
<meta name="twitter:image" content="https://yoursite.com/images/twitter-image.jpg">
```

#### Adding to Wix

**For Site-Wide Tags:**
1. Go to **Dashboard → Settings → Custom Code**
2. Click **"+ Add Custom Code"**
3. Paste your OG meta tags
4. Place in: **Head**
5. Apply to: **All pages** or specific pages

**For Product Pages (Dynamic):**
- Wix automatically generates some OG tags for products
- You can customize via **SEO Settings** on each product

#### Test Your OG Tags

- [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/)
- [Twitter Card Validator](https://cards-dev.twitter.com/validator)
- [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/)

---

## PHASE 3: E-commerce & Shopping

### 3.1 Google Merchant Center

Google Merchant Center lets your products appear in Google Shopping.

#### Step 1: Create Account

1. Go to [Google Merchant Center](https://merchants.google.com/)
2. Sign in with your Google account
3. Enter business information:
   - Business name: `Himalayan Fibres`
   - Country: Your country
   - Timezone
4. Accept terms and create account

#### Step 2: Verify and Claim Website

1. Go to **Settings → Business Information → Website**
2. Enter your website URL
3. Choose verification method:
   - **HTML tag** (easiest for Wix)
   - **Google Analytics** (if already linked)
   - **Google Tag Manager**
4. Complete verification

#### Step 3: Set Up Product Feed

**Option A: Manual Upload**
1. Create a spreadsheet with your products
2. Required fields:
   - `id` - Unique product ID
   - `title` - Product name
   - `description` - Product description
   - `link` - Product page URL
   - `image_link` - Product image URL
   - `price` - Price with currency
   - `availability` - in stock/out of stock
3. Upload as Google Sheets or CSV

**Option B: Wix Integration**
1. In Wix, go to **Marketing & SEO → Marketing Integrations**
2. Look for **Google Merchant Center** integration
3. Connect and sync products automatically

#### Step 4: Content API (For Automation)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **"Content API for Shopping"**
3. Use your service account for authentication

**API Documentation**: https://developers.google.com/shopping-content/guides/quickstart

---

### 3.2 Meta Commerce Manager (Facebook/Instagram Shops)

#### Step 1: Access Commerce Manager

1. Go to [Meta Commerce Manager](https://business.facebook.com/commerce)
2. Click **"Get Started"** or **"Add Shop"**

#### Step 2: Connect Your Catalog

**Option A: Manual Catalog**
1. Create a new catalog
2. Add products manually or via spreadsheet

**Option B: Connect Wix Store**
1. In Wix, go to **Marketing & SEO → Marketing Integrations**
2. Find **Facebook & Instagram** integration
3. Connect your accounts
4. Sync your product catalog

#### Step 3: Set Up Shop

1. Choose checkout method:
   - **Checkout on website** (recommended) - Users buy on your Wix site
   - **Checkout on Facebook/Instagram** (US only)
2. Configure shipping and returns
3. Submit for review

---

## PHASE 4: Advanced Tools

### 4.1 Schema Markup (Structured Data)

Schema markup helps search engines AND AI understand your content.

#### Product Schema (For Product Pages)

```json
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Himalayan Stinging Nettle Plant Fibre",
  "image": "https://yoursite.com/images/nettle-fiber.jpg",
  "description": "Premium hand-processed nettle fiber from the Himalayas...",
  "brand": {
    "@type": "Brand",
    "name": "Himalayan Fibres"
  },
  "offers": {
    "@type": "Offer",
    "price": "45.00",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock",
    "url": "https://yoursite.com/product/nettle-fiber"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.8",
    "reviewCount": "24"
  }
}
```

#### Organization Schema (For Homepage)

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Himalayan Fibres",
  "url": "https://yoursite.com",
  "logo": "https://yoursite.com/logo.png",
  "description": "Premium sustainable fibers from the Himalayas",
  "address": {
    "@type": "PostalAddress",
    "addressLocality": "Your City",
    "addressCountry": "IN"
  },
  "contactPoint": {
    "@type": "ContactPoint",
    "telephone": "+91-XXXXXXXXXX",
    "contactType": "sales"
  },
  "sameAs": [
    "https://www.facebook.com/himalayanfibres",
    "https://www.instagram.com/himalayanfibres"
  ]
}
```

#### FAQ Schema (For FAQ Page)

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is Himalayan nettle fiber?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Himalayan nettle fiber is a sustainable plant-based textile material harvested from the Giant Himalayan Nettle (Girardinia diversifolia) found at high altitudes..."
      }
    },
    {
      "@type": "Question",
      "name": "Is nettle fiber sustainable?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes, nettle fiber is highly sustainable. It requires no pesticides, minimal water, and the plant regenerates annually..."
      }
    }
  ]
}
```

#### Adding Schema to Wix

1. Go to **Dashboard → Settings → Custom Code**
2. Click **"+ Add Custom Code"**
3. Add your schema in a `<script type="application/ld+json">` tag
4. Place in: **Head** or **Body - End**
5. Apply to specific pages

#### Validate Your Schema

- [Google Rich Results Test](https://search.google.com/test/rich-results)
- [Schema.org Validator](https://validator.schema.org/)

---

### 4.2 Security Headers Check

Use these free tools to audit security:

| Tool | URL | What It Checks |
|------|-----|----------------|
| Security Headers | https://securityheaders.com | HTTP security headers |
| SSL Labs | https://www.ssllabs.com/ssltest/ | SSL/TLS configuration |
| Mozilla Observatory | https://observatory.mozilla.org | Overall security grade |

---

## Summary: Your API Credentials Checklist

After completing this guide, you should have:

### Google (All in one Cloud Project)
| Credential | File/Value | Used For |
|------------|------------|----------|
| OAuth Client ID | `google_credentials.json` | Interactive scripts |
| Service Account | `service_account.json` | Automated scripts |
| API Key | String (save securely) | PageSpeed Insights |

### Google Services Enabled
- [ ] Search Console API
- [ ] PageSpeed Insights API
- [ ] Indexing API
- [ ] Analytics Data API
- [ ] Content API for Shopping

### Bing
| Credential | Value |
|------------|-------|
| API Key | From Bing Webmaster Tools |

### Meta
| Credential | Value |
|------------|-------|
| Pixel ID | Your existing pixel |
| Conversions API Token | Generated in Events Manager |

---

## Next Steps After Setup

Once all APIs are set up, we can:

1. **Audit current SEO status** via Search Console API
2. **Run performance tests** via PageSpeed Insights
3. **Optimize meta titles/descriptions** via Wix MCP
4. **Submit sitemap** and monitor indexing
5. **Add schema markup** to all pages
6. **Set up automated monitoring** scripts

---

## Need Help?

If you get stuck on any step:
1. Check the linked documentation
2. Google the specific error message
3. Ask me - I can help troubleshoot

---

*Document created: January 2026*
*For: Himalayan Fibres Website Optimization Project*
