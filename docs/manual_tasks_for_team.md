# HIMALAYAN FIBRES - Manual Tasks for Team Implementation

**Created:** January 2026
**Website:** https://www.himalayanfibres.com/
**Platform:** Wix

---

## OVERVIEW

This document contains step-by-step instructions for manual tasks that need to be completed in the Wix Dashboard and external platforms. Each task includes exact text/content to add and where to add it.

---

## TASK 1: Submit XML Sitemap to Google Search Console

**Priority:** HIGH
**Time Required:** 15-20 minutes
**Impact:** Ensures all pages get indexed by Google

### Step-by-Step Instructions:

1. **Go to Google Search Console**
   - URL: https://search.google.com/search-console/
   - Sign in with the Google account associated with the website

2. **Add Property (if not already added)**
   - Click "Add Property"
   - Choose "URL prefix" method
   - Enter: `https://www.himalayanfibres.com/`
   - Verify ownership (Wix usually auto-verifies, or use HTML tag method)

3. **Submit Sitemap**
   - In the left sidebar, click "Sitemaps"
   - In the "Add a new sitemap" field, enter: `sitemap.xml`
   - Click "Submit"
   - The full URL will be: `https://www.himalayanfibres.com/sitemap.xml`

4. **Verify Submission**
   - Status should show "Success" or "Pending"
   - Check back in 24-48 hours to see indexed pages

### Screenshot Reference:
Look for the "Sitemaps" section in the left menu of Google Search Console.

---

## TASK 2: Submit to Bing Webmaster Tools

**Priority:** MEDIUM
**Time Required:** 15-20 minutes
**Impact:** Get indexed on Bing/Yahoo (10-15% of search traffic)

### Step-by-Step Instructions:

1. **Go to Bing Webmaster Tools**
   - URL: https://www.bing.com/webmasters/
   - Sign in with Microsoft account (or create one)

2. **Add Your Site**
   - Click "Add Site"
   - Enter: `https://www.himalayanfibres.com/`
   - Click "Add"

3. **Verify Ownership**
   - Choose "XML File" method OR
   - Choose "Meta Tag" method (add to Wix custom code)
   - For Meta Tag in Wix:
     - Go to Wix Dashboard → Settings → Custom Code
     - Add to `<head>` section
     - Paste the meta tag Bing provides

4. **Submit Sitemap**
   - After verification, go to "Sitemaps"
   - Enter: `https://www.himalayanfibres.com/sitemap.xml`
   - Click "Submit"

---

## TASK 3: Add Alt Text to Product Images

**Priority:** HIGH
**Time Required:** 30-45 minutes
**Impact:** Image search visibility + accessibility compliance

### Products Needing Alt Text:

The following 4 products need alt text added to their images:

#### Product 1: Snow White (Nettle Wool Blend Yarn)
**Location in Wix:** Store Products → Snow White → Edit Product → Media
**Alt Text to Add:**
```
Snow White handspun nettle wool blend yarn - sustainable eco-friendly yarn from Nepal, natural off-white color, soft texture for knitting and weaving
```

#### Product 2: Seriry (Grey Nettle Wool Yarn)
**Location in Wix:** Store Products → Seriry → Edit Product → Media
**Alt Text to Add:**
```
Seriry natural grey undyed nettle wool blend yarn - handspun sustainable yarn from Himalayan region, eco-friendly fiber for artisan textile projects
```

#### Product 3: Noor (Brown Nettle Wool Yarn)
**Location in Wix:** Store Products → Noor → Edit Product → Media
**Alt Text to Add:**
```
Noor brown organic nettle wool blend yarn - handspun sustainable plant fiber yarn from Nepal, natural earth tones for eco-conscious crafting
```

#### Product 4: Burberry (Beige Nettle Wool Yarn)
**Location in Wix:** Store Products → Burberry → Edit Product → Media
**Alt Text to Add:**
```
Burberry premium beige nettle wool blend yarn - luxury handspun sustainable fiber from Himalayas, natural color for high-end textile projects
```

### How to Add Alt Text in Wix:

1. Go to **Wix Dashboard**
2. Click **Store Products** in the left menu
3. Click on the product name to edit
4. Scroll to **Media** section
5. Click on each image
6. Find **Alt Text** field (may say "Image title" or "Alt text")
7. Paste the alt text from above
8. Click **Save**
9. Repeat for all images of that product

---

## TASK 4: Create About Page

**Priority:** HIGH
**Time Required:** 1-2 hours
**Impact:** Trust building + SEO + Brand storytelling

### Step-by-Step in Wix:

1. **Create New Page**
   - Go to Wix Editor
   - Click "Pages" in left menu
   - Click "+ Add Page"
   - Choose "Blank Page"
   - Name it: "About" or "About Us"
   - URL slug should be: `/about`

2. **Page Structure & Content:**

```
[HERO SECTION]
Heading: Our Story - Preserving Himalayan Traditions
Subheading: From the peaks of Nepal to your creative hands

[MAIN CONTENT - Section 1: Our Mission]
Heading: Who We Are

Content:
Himalayan Fibres is a sustainable fiber company dedicated to preserving
ancient Himalayan textile traditions while supporting local artisan
communities. Based in India, we source the finest natural plant fibers
directly from the Himalayan region of Nepal, bringing you authentic,
eco-friendly materials for your textile projects.

[Section 2: Our Fibers]
Heading: What Makes Our Fibers Special

Content:
We specialize in:
• Himalayan Stinging Nettle Fiber - Wild-harvested from high-altitude regions
• Premium Hemp Fiber - Sustainably grown in the Himalayan foothills
• Natural Wool Blends - Ethically sourced from Tibetan sheep

Every fiber we sell is:
✓ Sustainably and ethically sourced
✓ Hand-processed using traditional methods
✓ Chemical-free and naturally dyed (where applicable)
✓ Supporting fair wages for local artisans

[Section 3: Our Process]
Heading: From Forest to Fiber

Content:
Our fibers journey from remote Himalayan villages to your doorstep:

1. Wild Harvesting - Nettle plants are carefully harvested by hand during
   the optimal season
2. Traditional Processing - Fibers are extracted using age-old techniques
   passed down through generations
3. Hand Spinning - Skilled artisans spin the fibers into beautiful yarns
4. Quality Control - Each batch is inspected for consistency and quality
5. Direct to You - We ship worldwide, bringing Himalayan craftsmanship
   to creators everywhere

[Section 4: Our Impact]
Heading: Sustainability & Community

Content:
By choosing Himalayan Fibres, you're supporting:
• Rural employment in remote Himalayan villages
• Preservation of traditional textile knowledge
• Sustainable, chemical-free farming practices
• Women artisans and their families

[CONTACT SECTION]
Heading: Get in Touch

Content:
Have questions about our fibers or want to discuss wholesale orders?

Email: himalayanfibres@gmail.com
Phone/WhatsApp: +91 9582321281
Address: D1 101, Amrapali Sapphire, Sector 45, Noida, UP 201301

[Add "Contact Us" button linking to contact page]
```

3. **SEO Settings for About Page:**
   - Click "Page SEO" in Wix
   - Meta Title: `About Himalayan Fibres | Sustainable Natural Fiber Supplier from Nepal`
   - Meta Description: `Learn about Himalayan Fibres - your source for sustainable nettle fiber, hemp yarn, and natural plant fibers from Nepal. Supporting artisan communities since [year].`

4. **Add to Navigation:**
   - Go to Site Menu settings
   - Add "About" between "Shop" and "Contact"

---

## TASK 5: Optimize URL Slugs (If Possible in Wix)

**Priority:** MEDIUM
**Time Required:** 30 minutes
**Impact:** Cleaner URLs improve SEO

### Current URLs to Optimize:

| Current URL | Ideal URL |
|-------------|-----------|
| `/product-page/himalayan-stinging-nettle-plant-fibre` | `/himalayan-nettle-fiber` |
| `/product-page/special-stinging-nettle-yarn` | `/fine-nettle-yarn` |
| `/product-page/white-himalayan-hemp-yarn` | `/himalayan-hemp-yarn` |

### How to Change in Wix:

1. Go to **Store Products**
2. Click on product
3. Look for **SEO** or **URL** settings
4. Edit the URL slug
5. **Note:** Wix may add `/product-page/` prefix automatically - this is a Wix limitation

**Important:** If you change URLs, Wix should create automatic redirects. Verify old URLs redirect properly.

---

## TASK 6: Add Structured Data / Schema Markup

**Priority:** HIGH
**Time Required:** 1 hour
**Impact:** Rich snippets in Google search results

### Organization Schema (ALREADY ADDED)
✅ **Completed via API** - Organization Schema has been added to the site.

### Product Schema (Per Product)

For each product page, add this schema. In Wix:

1. Go to **Wix Editor**
2. Click on a **Product Page**
3. Click **Add** → **Embed** → **Custom Embeds** → **Embed a Site**
4. Choose **Custom Code**
5. Paste the schema code below (customize for each product)

**Example for Himalayan Nettle Fiber:**
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Himalayan Stinging Nettle Plant Fibre",
  "description": "Premium wild-harvested Himalayan nettle fiber, sustainably sourced from Nepal. Perfect for eco-friendly textile projects, handspinning, and natural fiber crafts.",
  "brand": {
    "@type": "Brand",
    "name": "Himalayan Fibres"
  },
  "offers": {
    "@type": "Offer",
    "priceCurrency": "INR",
    "price": "1500",
    "availability": "https://schema.org/InStock",
    "seller": {
      "@type": "Organization",
      "name": "Himalayan Fibres"
    }
  },
  "material": "Natural Himalayan Nettle Fiber",
  "manufacturer": {
    "@type": "Organization",
    "name": "Himalayan Fibres"
  }
}
</script>
```

**Customize for each product:**
- Change `name` to product name
- Change `description` to product description
- Change `price` to actual price
- Update `material` as appropriate

---

## TASK 7: Add FAQ Schema to Product Pages

**Priority:** MEDIUM
**Time Required:** 2 hours
**Impact:** FAQ rich results in Google

### Sample FAQ Content for Products:

**For Nettle Fiber Product:**

Add these FAQs to the product page AND as schema:

```
Q: What is Himalayan nettle fiber?
A: Himalayan nettle fiber comes from the stinging nettle plant (Girardinia diversifolia) that grows wild in the high-altitude regions of Nepal. It's a sustainable, biodegradable fiber known for its durability and natural antimicrobial properties.

Q: How is nettle fiber processed?
A: Our nettle fiber is hand-processed using traditional methods. The plants are harvested, retted (soaked to loosen fibers), dried, and then the fibers are extracted by hand. This chemical-free process preserves the fiber's natural qualities.

Q: What can I make with nettle fiber?
A: Nettle fiber is versatile and can be used for handspinning into yarn, weaving, knitting, crochet, paper making, and blending with other fibers. It's particularly valued for its silk-like sheen and strength.

Q: Is nettle fiber sustainable?
A: Yes! Nettle is one of the most sustainable fibers available. It grows wild without pesticides or fertilizers, requires minimal water, and the entire plant is used (fibers for textiles, leaves for food/medicine).

Q: What is the minimum order quantity?
A: Please contact us for wholesale/bulk order quantities. For samples, you can order directly from our shop.
```

**FAQ Schema Code:**
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is Himalayan nettle fiber?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Himalayan nettle fiber comes from the stinging nettle plant (Girardinia diversifolia) that grows wild in the high-altitude regions of Nepal. It's a sustainable, biodegradable fiber known for its durability and natural antimicrobial properties."
      }
    },
    {
      "@type": "Question",
      "name": "How is nettle fiber processed?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Our nettle fiber is hand-processed using traditional methods. The plants are harvested, retted (soaked to loosen fibers), dried, and then the fibers are extracted by hand. This chemical-free process preserves the fiber's natural qualities."
      }
    },
    {
      "@type": "Question",
      "name": "Is nettle fiber sustainable?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes! Nettle is one of the most sustainable fibers available. It grows wild without pesticides or fertilizers, requires minimal water, and the entire plant is used."
      }
    }
  ]
}
</script>
```

---

## TASK 8: Set Up Google Analytics 4 (If Not Done)

**Priority:** HIGH
**Time Required:** 30 minutes
**Impact:** Track visitor behavior and conversions

### Steps:

1. **Create GA4 Property**
   - Go to https://analytics.google.com/
   - Click "Admin" (gear icon)
   - Click "Create Property"
   - Enter: "Himalayan Fibres Website"
   - Set timezone and currency (INR)
   - Get the Measurement ID (starts with G-)

2. **Add to Wix**
   - Go to Wix Dashboard
   - Settings → Marketing Integrations OR
   - Settings → Custom Code
   - Add the GA4 code to `<head>` section:

```html
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

3. **Set Up Ecommerce Tracking**
   - Wix may have built-in GA4 integration
   - Check: Dashboard → Marketing & SEO → Marketing Integrations → Google Analytics

---

## TASK 9: Verify and Monitor Search Console

**Priority:** ONGOING
**Frequency:** Weekly

### Weekly Checklist:

1. **Check Index Coverage**
   - Look for any pages with errors
   - Note any pages excluded from indexing

2. **Review Performance**
   - Check which queries bring traffic
   - Note average position for target keywords

3. **Check for Issues**
   - Mobile usability issues
   - Core Web Vitals problems
   - Security issues

4. **Target Keywords to Monitor:**
   - "himalayan nettle fiber"
   - "himalayan hemp yarn"
   - "nettle fiber supplier india"
   - "sustainable plant fiber"
   - "nettle yarn wholesale"

---

## TASK 10: Create Blog Section (Future)

**Priority:** MEDIUM (Phase 3)
**Time Required:** 2-3 hours initial setup

### Blog Post Ideas (To Write Later):

1. "What is Himalayan Nettle Fiber? Complete Guide"
2. "Hemp vs Cotton vs Nettle: Sustainability Comparison"
3. "How Himalayan Nettle is Harvested and Processed"
4. "Benefits of Natural Plant Fibers for Textiles"

---

## QUICK REFERENCE: Priority Order

| Priority | Task | Time |
|----------|------|------|
| 1 | Submit sitemap to Google Search Console | 15 min |
| 2 | Add alt text to 4 product images | 30 min |
| 3 | Create About page | 1-2 hours |
| 4 | Set up Google Analytics 4 | 30 min |
| 5 | Submit to Bing Webmaster Tools | 15 min |
| 6 | Add Product Schema to product pages | 1 hour |
| 7 | Add FAQ content and schema | 2 hours |

---

## CHECKLIST

- [ ] Sitemap submitted to Google Search Console
- [ ] Sitemap submitted to Bing Webmaster Tools
- [ ] Alt text added to Snow White product images
- [ ] Alt text added to Seriry product images
- [ ] Alt text added to Noor product images
- [ ] Alt text added to Burberry product images
- [ ] About page created and published
- [ ] About page added to navigation menu
- [ ] Google Analytics 4 set up and verified
- [ ] Product Schema added to all products
- [ ] FAQ Schema added to main products

---

*Document created: January 2026*
*For: Himalayan Fibres Team*
