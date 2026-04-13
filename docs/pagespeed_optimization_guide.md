# HIMALAYAN FIBRES - PageSpeed Optimization Guide for Wix

**Created:** January 2026
**Website:** https://www.himalayanfibres.com/
**Platform:** Wix

---

## CURRENT PERFORMANCE STATUS

Based on PageSpeed analysis, here are the key areas to optimize:

### Current Scores (Approximate):
- **Mobile Performance:** Needs Improvement
- **Desktop Performance:** Good
- **Largest Contentful Paint (LCP):** Needs optimization
- **Total Blocking Time (TBT):** Needs reduction
- **Cumulative Layout Shift (CLS):** Generally good

---

## WHY SPEED MATTERS FOR SEO

1. **Google Ranking Factor:** Page speed is a confirmed ranking signal
2. **User Experience:** 53% of mobile users abandon sites that take >3 seconds to load
3. **Conversion Rates:** Every 1-second delay reduces conversions by 7%
4. **Core Web Vitals:** Google's ranking metrics include LCP, FID, and CLS

---

## WIX-SPECIFIC OPTIMIZATIONS

### What You CAN Control in Wix:

#### 1. IMAGE OPTIMIZATION (Highest Impact)

**A. Use Wix's Built-in Image Optimization**
- Wix automatically converts images to WebP format
- Ensure this is enabled (it's on by default)

**B. Upload Optimized Images**

| Image Type | Recommended Size | Format |
|------------|------------------|--------|
| Product Images | 1000x1000px max | JPG/PNG |
| Hero/Banner Images | 1920x1080px max | JPG |
| Thumbnails | 500x500px | JPG |
| Logo | 500px width max | PNG/SVG |

**C. Before Uploading Images:**
1. Resize images to the actual display size needed
2. Compress using free tools:
   - **TinyPNG:** https://tinypng.com/ (reduces size by 60-80%)
   - **Squoosh:** https://squoosh.app/ (Google's free tool)
   - **ImageOptim:** https://imageoptim.com/ (Mac app)

**D. Image Compression Steps:**
```
1. Open TinyPNG.com
2. Drag and drop your image
3. Download the compressed version
4. Upload compressed version to Wix
```

**Target File Sizes:**
- Product images: Under 200KB each
- Hero images: Under 500KB
- Thumbnails: Under 50KB

---

#### 2. REDUCE THIRD-PARTY SCRIPTS

**Check Current Scripts:**
1. Go to Wix Dashboard → Settings → Custom Code
2. Review all scripts added
3. Remove any unused tracking codes or widgets

**Essential Scripts Only:**
- ✅ Google Analytics 4
- ✅ Facebook Pixel (if using FB ads)
- ❌ Remove unused chat widgets
- ❌ Remove unused social media widgets
- ❌ Remove any deprecated tracking codes

**Script Loading Best Practices:**
- Load scripts in "Body - End" position when possible
- Use "Load code once" option for scripts that don't need to reload



---

#### 3. OPTIMIZE FONTS

**In Wix Editor:**
1. Use system fonts when possible (fastest loading):
   - Arial, Helvetica, Georgia, Times New Roman

2. If using custom fonts, limit to:
   - Maximum 2 font families
   - Maximum 3-4 font weights total

3. **In Wix:**
   - Go to Site Design → Text Theme
   - Check how many fonts are being used
   - Consolidate if using more than 2 different fonts

---

#### 4. LAZY LOADING (Built into Wix)

Wix automatically lazy-loads images below the fold. To ensure this works:

1. **Don't override with custom code**
2. **Place critical images "above the fold"** (visible without scrolling)
3. **Use Wix's native image elements**, not custom HTML images

---

#### 5. MINIMIZE ANIMATIONS

**Check and Reduce:**
1. Go to each page in Wix Editor
2. Click on elements with animations
3. Remove or simplify unnecessary animations

**Keep:** Subtle fade-ins, hover effects
**Remove:** Complex animations, multiple simultaneous animations, parallax if slow

---

#### 6. OPTIMIZE PAGE STRUCTURE

**Homepage Best Practices:**
1. **Hero Section:** Single, optimized image (not slider/carousel)
2. **Above the Fold:** Keep essential content only
3. **Product Grid:** Show 4-8 products max on homepage
4. **Limit Sections:** 5-7 sections maximum on homepage

**Why Sliders/Carousels Hurt Speed:**
- Load multiple images at once
- Require extra JavaScript
- Users rarely interact with them

**Better Alternative:**
- Single hero image with clear CTA
- Or static image with text overlay

---

#### 7. ENABLE WIXSITE PERFORMANCE FEATURES

**In Wix Dashboard:**

1. **Site Speed Dashboard**
   - Dashboard → Analytics & Reports → Site Speed
   - Review recommendations specific to your site

2. **Mobile Optimization**
   - Ensure mobile view is separately optimized
   - Remove unnecessary elements from mobile view
   - Use smaller images for mobile (Wix does this automatically)

3. **Wix Turbo (Automatic)**
   - Wix automatically applies performance optimizations
   - Ensure you're on a current Wix plan

---

### What Wix Controls (You Cannot Change):

- Server response time
- Core JavaScript framework
- CDN (Content Delivery Network)
- Base HTML structure

**Note:** Wix handles these automatically. Focus on what you CAN control.

---

## STEP-BY-STEP OPTIMIZATION CHECKLIST

### Phase 1: Quick Wins (Do First)

- [ ] **Compress all product images** using TinyPNG
- [ ] **Remove unused custom code** from Settings → Custom Code
- [ ] **Check font usage** - limit to 2 fonts maximum
- [ ] **Remove slider/carousel** on homepage if present
- [ ] **Check mobile view** for unnecessary elements

### Phase 2: Intermediate (Do Next)

- [ ] **Optimize hero image** - compress and resize to 1920px width max
- [ ] **Reduce animations** on all pages
- [ ] **Audit third-party scripts** - keep only essential ones
- [ ] **Simplify homepage** - limit to 5-7 sections
- [ ] **Check product page images** - ensure all are under 200KB

### Phase 3: Advanced (Ongoing)

- [ ] **Monitor PageSpeed Insights** monthly
- [ ] **Check Core Web Vitals** in Search Console
- [ ] **Test on real mobile devices**
- [ ] **Review Wix Site Speed Dashboard** recommendations

---

## HOW TO TEST YOUR SPEED

### 1. Google PageSpeed Insights
- URL: https://pagespeed.web.dev/
- Enter: `https://www.himalayanfibres.com/`
- Test both Mobile and Desktop

### 2. GTmetrix
- URL: https://gtmetrix.com/
- Provides detailed waterfall analysis
- Shows what's loading slowly

### 3. WebPageTest
- URL: https://www.webpagetest.org/
- More detailed technical analysis
- Test from different locations

### 4. Google Search Console
- URL: https://search.google.com/search-console/
- Core Web Vitals report
- Shows real-user data

---

## UNDERSTANDING CORE WEB VITALS

| Metric | What It Measures | Target | How to Improve |
|--------|------------------|--------|----------------|
| **LCP** (Largest Contentful Paint) | How fast main content loads | < 2.5 seconds | Optimize hero image, reduce server response |
| **FID** (First Input Delay) | How fast page responds to clicks | < 100 ms | Reduce JavaScript, defer non-critical scripts |
| **CLS** (Cumulative Layout Shift) | Visual stability (no jumping content) | < 0.1 | Set image dimensions, avoid dynamic content injection |

---

## IMAGE OPTIMIZATION WORKFLOW

### For New Product Images:

```
Step 1: Take/receive product photo
Step 2: Resize to 1000x1000 pixels (or appropriate size)
Step 3: Save as JPG with 80% quality
Step 4: Run through TinyPNG.com
Step 5: Verify file size is under 200KB
Step 6: Upload to Wix
Step 7: Add alt text
```

### For Existing Images:

```
Step 1: Export images from Wix Media Manager
Step 2: Run through TinyPNG.com
Step 3: Re-upload optimized versions
Step 4: Replace in product listings
```

---

## WIX-SPECIFIC SETTINGS TO CHECK

### In Wix Editor:

1. **Site Settings → Mobile View**
   - Ensure mobile is optimized separately
   - Hide unnecessary sections on mobile

2. **Add Apps → Review Installed Apps**
   - Remove unused Wix apps
   - Each app adds loading time

3. **Page Settings → SEO**
   - Ensure pages are set to index
   - Check canonical URLs are correct

### In Wix Dashboard:

1. **Settings → Custom Code**
   - Audit all added scripts
   - Move scripts to "Body - End" if possible

2. **Marketing → SEO Tools**
   - Use built-in optimization features

---

## MONTHLY PERFORMANCE CHECKLIST

| Task | Frequency |
|------|-----------|
| Run PageSpeed Insights test | Monthly |
| Check Core Web Vitals in Search Console | Monthly |
| Review new images uploaded (ensure optimized) | Weekly |
| Check for new Wix app installations | Monthly |
| Test site on mobile device | Monthly |
| Review custom code for unused scripts | Quarterly |

---

## EXPECTED IMPROVEMENTS

After implementing these optimizations:

| Metric | Before | Target |
|--------|--------|--------|
| Mobile Performance Score | ~50-60 | 70+ |
| Desktop Performance Score | ~70-80 | 85+ |
| LCP | >3 seconds | <2.5 seconds |
| Page Load Time | >5 seconds | <3 seconds |

---

## TOOLS & RESOURCES

### Free Image Optimization:
- TinyPNG: https://tinypng.com/
- Squoosh: https://squoosh.app/
- ImageOptim: https://imageoptim.com/

### Speed Testing:
- PageSpeed Insights: https://pagespeed.web.dev/
- GTmetrix: https://gtmetrix.com/
- WebPageTest: https://www.webpagetest.org/

### Wix Resources:
- Wix Site Speed Guide: https://support.wix.com/en/article/improving-your-sites-page-speed
- Wix SEO Learning Hub: https://www.wix.com/seo/learn

---

## IMPORTANT NOTES

1. **Wix Platform Limitations:**
   - Some optimizations aren't possible on Wix (server-side)
   - Focus on what you CAN control (images, scripts, content)
   - Wix is continuously improving their platform speed

2. **Don't Over-Optimize:**
   - Balance speed with functionality
   - Keep essential features (chat, analytics)
   - User experience > perfect score

3. **Mobile First:**
   - Google uses mobile-first indexing
   - Optimize for mobile performance primarily
   - Test on actual mobile devices

---

## OPTIMIZATION IMPLEMENTATION REPORT

**Date:** January 25, 2026
**Site:** Himalayan Fibres (ID: 580a6298-44ff-47b2-80ce-f3ec82e62db7)

### AUTOMATED OPTIMIZATIONS COMPLETED

#### 1. Custom Scripts Optimized

| Script | Before | After | Impact |
|--------|--------|-------|--------|
| **Mailchimp Pop Up Form** | HEAD, ESSENTIAL | BODY_END, FUNCTIONAL | Deferred loading, won't block page render |
| **Meta Pixel (Facebook)** | HEAD, ESSENTIAL | BODY_END, ADVERTISING | Deferred loading, proper consent category |
| **Organization Schema** | HEAD, ESSENTIAL | No change (SEO schema must stay in HEAD) | Already optimal |

**Result:** Two scripts moved from blocking HEAD position to non-blocking BODY_END position. This allows the page content to load before these scripts execute.

#### 2. Marketing Tags Status

| Tag | Status | Notes |
|-----|--------|-------|
| Google Analytics 4 | Active (G-F8WVP0Y82G) | Essential for tracking |
| Google Tag Manager | Active (GTM-M39QS3LS) | Consider managing GA through GTM to reduce redundancy |

**Recommendation:** If GA4 is being loaded through GTM, you can disable the standalone GA4 tag to reduce duplicate requests.

#### 3. Installed Apps Audit

**Total Apps Installed:** 72

Most are Wix system apps required for functionality (Stores, CRM, SEO, etc.).

**Manual Review Required:** In Wix Dashboard:
1. Go to **Add Apps** section
2. Review all installed apps
3. Remove any third-party apps you're not actively using
4. Common apps to review:
   - Chat widgets (if not using)
   - Social media feed widgets
   - Pop-up builders (if using Mailchimp instead)
   - Old integrations


### SITE CONFIGURATION VERIFIED

| Setting | Current Value | Status |
|---------|---------------|--------|
| Site Display Name | Himalayan Fibres | OK |
| Business Name | Himalayanfibres.com | OK |
| Language | English (US) | OK |
| Currency | INR | OK |
| Timezone | Asia/Calcutta | OK |
| Click Analytics | Enabled | OK |
| Logo | Configured | OK |

### CURRENT SITE ANALYSIS

**Fonts Detected:**
- Primary: Arial, Helvetica, sans-serif (System fonts - GOOD)
- Secondary: Madefor, Helvetica Neue (UI elements)
- **Status:** Using system fonts is excellent for performance

**Animations Detected:**
- View transitions (0.35-0.6s)
- Hover effects (0.4s)
- Carousel/slide animations
- **Recommendation:** Review in Wix Editor and simplify where possible

**Page Structure:**
- 4-6 sections on homepage (within optimal range)
- Carousel-style elements detected
- **Recommendation:** Consider replacing carousel with single static hero image

### MANUAL OPTIMIZATIONS REQUIRED

These items cannot be done via API and require manual action in Wix Editor:

#### HIGH PRIORITY

- [ ] **Replace carousel with single hero image** (if present)
  - Open Wix Editor
  - Navigate to homepage hero section
  - Replace slider/carousel with single optimized image
  - Use a clear CTA button

- [ ] **Compress all product images**
  - Export images from Wix Media Manager
  - Compress using TinyPNG.com
  - Re-upload and replace in product listings
  - Target: Under 200KB per product image

- [ ] **Review and remove unused Wix apps**
  - Dashboard → Add Apps
  - Click "Manage Apps"
  - Remove unused third-party apps

#### MEDIUM PRIORITY

- [ ] **Simplify animations**
  - Open Wix Editor
  - Click elements with animations
  - Remove complex animations, keep only subtle fade-ins

- [ ] **Optimize mobile view**
  - Switch to mobile editor view
  - Hide non-essential elements on mobile
  - Ensure text is readable without zooming

- [ ] **Review fonts** (if using custom fonts)
  - Site Design → Text Theme
  - Limit to 2 font families maximum

#### LOW PRIORITY (Ongoing)

- [ ] **Set up monthly performance monitoring**
  - Bookmark: https://pagespeed.web.dev/
  - Test on 1st of each month
  - Record scores in a spreadsheet

### EXPECTED PERFORMANCE IMPROVEMENT

Based on the optimizations completed:

| Metric | Expected Improvement |
|--------|---------------------|
| Time to Interactive | 0.3-0.5s faster (scripts deferred) |
| Total Blocking Time | 10-20% reduction |
| First Contentful Paint | Slightly improved |

**Note:** Full improvement will be realized after completing the manual optimizations above, especially image compression and carousel removal.

---

*Document created: January 2026*
*Last updated: January 25, 2026*
*For: Himalayan Fibres Team*
