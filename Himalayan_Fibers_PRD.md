# Himalayan Fibers Growth Ops — Product Requirements Document (PRD)

**Version:** 1.0 (Draft)  
**Date:** 2026-01-15 (Asia/Kolkata)  
**Owner:** Prashant (Himalayan Fibers)  
**Scope:** Wix website operations + Email marketing automation (WhatsApp later)

---

## Executive Summary

Himalayan Fibers will implement a production-grade system that enables:

1) **Rapid website iteration on Wix** using **Wix MCP** (developer/ops tooling) to add pages, add products, publish blogs, improve SEO and performance, and maintain a consistent brand experience.

2) **Fully automated email marketing and lifecycle messaging** driven by **Wix commerce events (webhooks)** to send:
   - Transactional emails (welcome/thank-you, post-purchase education)
   - Scheduled campaigns (2 emails per week: 1 educational, 1 product/company update)
   - Segmented communications for global and local audiences

**Why this matters:**  
- The Wix site becomes a continuously improving storefront (better SEO, faster pages, more content, more products).  
- Email becomes a predictable growth channel with automation, segmentation, analytics, and compliance built-in.

**Recommended strategy:** Build two tracks with a shared backend:
- **Track A (Website Ops):** AI-assisted changes via Wix MCP to speed development and reduce manual effort.
- **Track B (Marketing Automation):** A stable, deployable automation service (webhooks → queue → email provider) to ensure reliability, deliverability, and observability.

---

## 1) Background & Context

Himalayan Fibers operates a Wix-based website and wants:
- Faster site improvements and content updates (products, pages, blog, gallery).
- Better performance and SEO to increase traffic and conversion.
- An automated email marketing system capable of weekly campaigns and order-triggered lifecycle messages.
- A future path to WhatsApp automation using the same campaign and segmentation foundation.

The system will be built to be **production-grade**, with:
- reliable webhook handling, idempotency, retries
- email deliverability best practices (authentication, suppression)
- compliant unsubscribe handling and consent logging
- observability (logs, metrics) and operator-friendly workflows

---

## 2) Goals

### 2.1 Website (Wix) Goals
- Add and maintain new pages:
  - Blog hub / resources
  - Gallery
  - “Why Himalayan Fibers”
  - Product/category landing pages
- Add and update products continuously:
  - metadata, images, variants, collections
  - SEO metadata and structured content
- Publish blogs continuously:
  - weekly blog publishing pipeline (draft → review → publish)
  - internal linking from blogs to products
- Improve SEO:
  - metadata hygiene, internal linking, content structure, canonical consistency
- Improve performance and purchase experience:
  - faster load times
  - reduced friction in checkout and payment UX
  - improved trust cues (policies, shipping, returns, contact)

### 2.2 Email Marketing Goals
- Automated transactional flows:
  - order created → welcome/thank-you email
  - post-purchase education email (delayed)
- Scheduled campaigns:
  - 2 emails per week:
    1) Educational content (science/material/process/case studies)
    2) Company/product update (new products, capabilities, offers)
- AI-assisted content generation with safety guardrails and human review.
- Segmentation by audience:
  - global vs local
  - producers vs buyers vs partners
  - interest tags (fiber type, use case, industry)

### 2.3 Future (Not MVP) Goals
- Add WhatsApp campaigns and automation after the email system is stable.

---

## 3) Non-Goals (MVP)

- No fully autonomous publishing without review/approval.
- No full WhatsApp integration in MVP (only architecture-ready).
- No migration away from Wix storefront (unless Wix constraints force later changes).

---

## 4) Personas & Users

1) **Owner/Admin (Prashant)**
   - wants a “control panel” to run campaigns, upload templates, manage products/pages fast

2) **Marketing Operator**
   - wants templates, segmentation, scheduling, analytics, approvals

3) **Developer/Automation Operator**
   - wants reliable systems: webhook verification, retries, idempotency, dashboards

4) **Customer**
   - receives timely, relevant emails
   - can unsubscribe easily
   - sees improved website experience and clear product information

---

## 5) Success Metrics (KPIs)

### Website KPIs
- Organic traffic growth (MoM)
- Conversion rate (sessions → purchases or inquiries)
- Product page engagement (time on page, scroll depth)
- Checkout completion rate
- Performance proxies (LCP/CLS/TTFB improvements; reduced heavy assets)

### Email KPIs
- Deliverability health: bounce rate, complaint rate
- Engagement: open rate, click rate
- List health: unsubscribe rate, growth rate
- Revenue attribution: revenue per send, conversion from email clicks
- Latency: time from order event to email send (target < 2 minutes)

---

## 6) Scope & Requirements

### 6.1 Track A — Wix Website Ops (via Wix MCP)

#### A1. Wix MCP Setup (Developer Tooling)
- Configure Wix MCP remote server endpoint in your AI coding environment.
- Store MCP config in repo (non-secret) with clear setup steps.

**Required MCP endpoint (keep in code block):**
```text
https://mcp.wix.com/mcp
```

Optional MCP run command:
```bash
npx -y @wix/mcp-remote https://mcp.wix.com/sse
```

#### A2. Website Information Architecture (IA) Updates
- Navigation updates and page creation:
  - Blog hub / Resources page
  - Gallery page
  - “Why Himalayan Fibers” page
  - Product category pages
- Mobile-first layout checks and navigation consistency.

#### A3. Product Operations
- Product CRUD workflow:
  - create new products with mandatory fields
  - set images, variants, pricing, inventory rules (as applicable)
  - assign categories/collections
  - fill SEO metadata consistently
- Bulk or batch operations (where possible).

#### A4. Blog Operations
- Blog pipeline:
  - generate draft → review → publish
  - internal linking checklist:
    - link to relevant products
    - include FAQ section for SEO
  - tags/categories for retrieval and navigation

#### A5. SEO Improvements
- Page titles, meta descriptions, canonical patterns
- Internal linking structure from:
  - Blog hub → articles → product pages
  - Product pages → related products → educational content
- Content structure guidelines:
  - clear headers, consistent terminology
  - avoid unsupported health/medical claims

#### A6. Performance Improvements (Practical)
- reduce heavy image payloads, enforce compression and responsive images
- minimize page bloat (apps, heavy widgets)
- improve “first meaningful interaction” on key pages (home, product, checkout)

---

### 6.2 Track B — Email Marketing Automation System

#### B1. Core Capabilities
- Contact management:
  - CSV import
  - manual add/edit
  - consent status and consent source
- Segmentation engine:
  - rule-based segments (tags, geography, activity)
- Template store:
  - HTML template storage + variable schema
  - linting/validation (missing variables, required footer)
- Campaign creation:
  - pick segment + template + subject + content blocks
  - schedule send + approve
- Transactional automation:
  - order created → welcome/thank-you email
  - post-purchase education email (delayed)

#### B2. Trigger Events (Wix)
- Receive Wix order events via webhooks.
- Verify authenticity (JWT verification where applicable).
- Enforce idempotency and retry safety (no duplicate sends).

#### B3. Provider Integration (ESP)
- Use a production ESP (SendGrid / Amazon SES / Mailgun).
- Required:
  - suppression list support
  - bounce/complaint handling
  - webhooks for delivery events (optional in MVP but recommended)

#### B4. Scheduling
- Weekly schedule: two campaigns per week.
- Rate limiting and safe batching (avoid provider throttles).
- Human approval gate before send.

---

### 6.3 AI Content Generation (Guardrailed)

#### C1. Content Types
- Email copy:
  - subject, preview text, body sections
- Blog drafts:
  - title, outline, content, FAQ, internal links suggestions

#### C2. Safety Guardrails
- No unverified “medical” or “cure” claims.
- Scientific claims must be:
  - conservative
  - supported by sources (store references internally)
- Human review required for outgoing campaigns.

#### C3. Brand Voice
- Maintain consistent tone:
  - professional, informative
  - credible, minimal hype
  - clear CTA (request samples, view catalog, contact sales)

---

## 7) Non-Functional Requirements

### 7.1 Reliability
- Webhook handling:
  - idempotency per event (event_id + payload hash)
  - safe retries with exponential backoff
  - dead-letter queue for failed jobs

### 7.2 Security
- Secrets management (env + secret store)
- Webhook verification and request signing validation
- Least privilege API tokens
- Audit logs for admin actions

### 7.3 Deliverability
- SPF/DKIM/DMARC configured for sending domain
- Suppression lists enforced
- Unsubscribe link always present for campaigns

### 7.4 Compliance
- Consent logging (opt-in source, timestamp)
- Unsubscribe compliance
- Data deletion workflow (GDPR-style “forget” requests)

### 7.5 Observability
- Structured logs (request_id, event_id, campaign_id, contact_id)
- Metrics:
  - webhook received/processed
  - jobs succeeded/failed
  - sends delivered/bounced/complained
- Alerting thresholds (e.g., spike in failures)

---

## 8) Architecture (Recommended)

### Components
1) **API service**
   - Receives Wix webhooks
   - Admin endpoints for templates/contacts/campaigns
2) **Queue/Worker**
   - Processes send jobs and scheduled campaigns
3) **Database**
   - Contacts, templates, campaigns, sends, webhook_events, orders snapshots
4) **ESP connector**
   - provider interface so you can swap SendGrid/SES later
5) **Wix integration**
   - webhook subscriptions and event validation
6) **Optional content generator**
   - runs drafts and stores them for review

### Why not run automation “through MCP”?
MCP is ideal for development and operations assistance, but always-on automation should be a stable service with predictable deployment, monitoring, and retries.

---

## 9) Data Model (Minimum)

### Tables
- `contacts`
  - id, email, name, country, tags, consent_status, consent_source, created_at
- `segments`
  - id, name, rules_json, created_at
- `templates`
  - id, name, html, required_vars_json, category, created_at
- `campaigns`
  - id, name, segment_id, template_id, subject, schedule_at, status, created_at
- `email_sends`
  - id, campaign_id, contact_id, provider_message_id, status, timestamps
- `webhook_events`
  - id, source, event_type, event_id, payload_hash, received_at, processed_at
- `orders`
  - order_id, contact_email, items_json, value, currency, created_at

---

## 10) Milestones & Phases

### Phase 0 — Foundations
- Pick ESP + configure domain authentication (SPF/DKIM/DMARC)
- Repo scaffold + CI + env management
- Webhook receiver skeleton + verification + idempotency
- One HTML template stored + rendering validated

### Phase 1 — MVP
- Order created → welcome email automation
- Minimal admin tooling:
  - add templates
  - import contacts
  - create basic segments
- Basic logs + retry behavior

### Phase 2 — Campaign System
- Scheduled campaigns with approval gate
- Segment sends and analytics
- Delivery event handling (optional but recommended)

### Phase 3 — Content Engine + Blog Automation
- AI drafts (email + blog) stored for review
- Publish blogs to Wix + internal linking checklist

### Phase 4 — WhatsApp
- Implement WhatsApp opt-in flows + templates + scheduling using same segments.

---

## 11) Risks & Mitigations

- **Duplicate webhooks → duplicate emails**
  - idempotency on event_id + payload hash; store processed events
- **Deliverability issues**
  - enforce domain authentication, warm-up, suppression lists
- **Over-automation content risk**
  - mandatory human approval gate for campaigns
- **API/credential drift**
  - token refresh strategy + alerting on auth failures

---

## 12) Open Questions (Decisions Needed)

1) Which ESP should be the default (SendGrid vs SES vs Mailgun)?
2) Do we need a lightweight admin UI now, or is CLI + database/admin endpoints enough for MVP?
3) Content review workflow:
   - email drafts stored in DB and reviewed in UI, or reviewed in Git/Markdown first?
4) Target segments definition:
   - exact fields for “global vs local” and “producer vs buyer” classification

---

# Appendix A — Cloud Code Implementation Prompt (Wix MCP)

Paste this prompt into your Cloud Code agent:

```text
You are my implementation agent for “Himalayan Fibers Growth Ops”.

Goal: Use Wix MCP to implement website improvements + prepare hooks for marketing automation.

Do this in order:
1) Discover current site structure: pages, blog status, store catalog structure, checkout flow notes.
2) Propose a site IA update: add Blog hub + Gallery + Education/Resources + Why Himalayan Fibers.
3) Implement the pages and navigation updates in Wix (mobile + desktop).
4) Create a repeatable workflow for adding products: required fields, SEO fields, collections, images.
5) Create a blog publishing workflow: draft → review → publish → internal links to products.
6) Output:
   - A checklist of all changes made
   - A rollback plan
   - A “next actions” list for Phase 0 marketing (webhooks + welcome email)
Use Wix MCP tools to search docs and call Wix site APIs where needed.
```

---

# Appendix B — Codex Setup Prompt (Repo Scaffold)

Paste this prompt into Codex (or your coding agent):

```text
Create a production-grade monorepo for “himalayan-fibers-growth-ops”.

Tech:
- Node.js (>=20), TypeScript
- API: Fastify
- DB: Postgres (Prisma)
- Queue: Redis + BullMQ
- Email: SendGrid connector (provider interface so we can swap later)

Apps:
1) apps/api
   - POST /webhooks/wix/ecom/order-created
     - Verify Wix event authenticity (JWT verification if applicable)
     - Enforce idempotency on event id + payload hash
     - Store order snapshot + webhook event record
     - Enqueue “send_welcome_email” job
   - Minimal admin endpoints:
     - CRUD templates (HTML + variables)
     - CRUD contacts + segments
     - Create campaign + schedule

2) apps/worker
   - BullMQ processor:
     - send_welcome_email: render HTML template, send via provider, store result
     - scheduled_campaign_send: send to segment contacts with rate limiting

Packages:
- packages/core
  - Template renderer (handle {{var}}), validation (missing vars, unsubscribe footer)
  - Common types (OrderCreatedEvent, Contact, Template, Campaign)
- packages/connectors
  - email/sendgrid (send, suppressions)
  - wix/webhooks (verify, parse payload)

Infra:
- docker-compose.yml for postgres + redis
- .env.example
- Prisma schema + migrations
- Structured logging (pino) + request IDs
- Basic unit tests for:
  - webhook verification + idempotency
  - template rendering + validation
  - email provider adapter (mocked)

Output all files and include a README with local dev commands.
```

---

# Appendix C — Operational Checklists

## C1. Website Release Checklist
- [ ] Mobile layout verified on key pages (Home, Product, Cart/Checkout)
- [ ] Navigation links correct
- [ ] SEO fields filled (title, description) for new pages/products
- [ ] Images optimized and responsive
- [ ] Blog post has internal links to products + FAQ section
- [ ] Contact and policy pages visible (shipping/returns/terms)

## C2. Email Campaign Checklist
- [ ] Subject + preview text reviewed
- [ ] Unsubscribe footer present (campaigns)
- [ ] All template variables present
- [ ] Links validated
- [ ] Segment reviewed (sample recipients)
- [ ] Send time verified (Asia/Kolkata)
- [ ] Suppression/unsubscribe list enforced
