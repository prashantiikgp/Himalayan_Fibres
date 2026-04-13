# Plan: Dashboard V2 — Home, Contacts, Inbox Refactor

## Context

The current dashboard works but the UI is confusing — pages overlap, flows are unclear, and there's no lifecycle management. This refactor focuses on three pages: Home (dashboard), Contacts (CRM), and Inbox (unified WhatsApp + Email conversations). All configuration driven by YAML.

## Key Additions

1. **Lifecycle stages** — New Lead → Contacted → Interested → Customer → Churned
2. **Combined Inbox** — WhatsApp + Email conversations in one page, per contact
3. **YAML-driven contact schema** — segments, tags, lifecycle, validation rules
4. **Home loads by default** — no blank screen on first load
5. **Clean, non-overlapping UI** — fixed column widths, proper spacing
6. **YAML-driven design system** — all CSS/component styles + page layouts in YAML, not Python

## Design Principle: YAML Everything

**No hardcoded styles or labels in Python.** Every visual element reads from YAML:

```
config/
├── theme/
│   ├── default.yml              # Colors, fonts, spacing, radii (existing)
│   └── components.yml           # Component-specific styles (NEW)
├── contacts/
│   └── schema.yml               # Contact fields, segments, tags, lifecycle (NEW)
├── pages/
│   ├── home.yml                 # Home page: KPI definitions, sections, labels (NEW)
│   ├── contacts.yml             # Contacts page: table columns, filter config (NEW)
│   ├── inbox.yml                # Inbox page: column config, channel options (NEW)
│   ├── campaigns.yml            # Campaigns page: form fields, labels (NEW)
│   ├── flows.yml                # Flows page: display config (NEW)
│   └── templates.yml            # Templates page: tab config (NEW)
├── dashboard/
│   ├── sidebar.yml              # Navigation items (existing)
│   └── dashboard.yml            # Title, default page (existing)
└── whatsapp/
    ├── settings.yml             # WA API config (existing)
    ├── templates.yml            # WA template registry (existing)
    └── messages.yml             # Quick replies (existing)
```

**Why:** When Prashant wants to add a new segment, change a card color, rename a button, or add a table column — he edits YAML, not Python. Design stays separate from logic.

---

## Config File: theme/components.yml (NEW)

```yaml
# Component-level styles — read by components/styles.py
# No hardcoded colors/sizes in Python files

components:
  kpi_card:
    background: "var(card_bg)"       # References theme/default.yml
    border_radius: "10px"
    padding: "14px 18px"
    value_font_size: "24px"
    value_font_weight: "700"
    label_font_size: "11px"
    label_color: "var(text_subtle)"
    label_transform: "uppercase"
    label_spacing: "0.5px"

  table:
    header_bg: "rgba(15,23,42,.95)"
    header_font_size: "10px"
    header_font_weight: "700"
    header_transform: "uppercase"
    header_padding: "8px 10px"
    cell_padding: "6px 10px"
    cell_font_size: "12px"
    row_border: "1px solid rgba(255,255,255,.04)"
    row_hover: "rgba(99,102,241,.04)"
    border_radius: "8px"
    max_height: "60vh"

  chat_bubble:
    inbound_bg: "rgba(99,102,241,.12)"
    outbound_bg: "var(card_bg)"
    border_radius: "12px"
    padding: "8px 12px"
    inbound_margin: "margin-right:60px"
    outbound_margin: "margin-left:60px"
    font_size: "12px"
    timestamp_size: "9px"

  badge:
    padding: "2px 8px"
    border_radius: "10px"
    font_size: "10px"
    font_weight: "600"

  section_card:
    background: "var(card_bg)"
    border_radius: "8px"
    padding: "12px 16px"
    accent_width: "4px"

  empty_state:
    padding: "40px"
    icon_size: "32px"
    font_size: "13px"

  nav_sidebar:
    background: "rgba(15,23,42,.45)"
    border: "1px solid rgba(255,255,255,.06)"
    border_radius: "12px"
    button_font_size: "13px"
    button_padding: "10px 14px"
    active_bg: "rgba(99,102,241,.12)"
    active_border: "3px solid #6366f1"
    inactive_color: "#94a3b8"
    active_color: "#e7eaf3"

  page_left_col:
    background: "rgba(15,23,42,.50)"
    border: "1px solid rgba(255,255,255,.06)"
    border_radius: "8px"
    padding: "10px"

  progress_bar:
    height: "8px"
    border_radius: "4px"
    background: "rgba(255,255,255,.06)"
```

---

## Config File: pages/home.yml (NEW)

```yaml
# Home page layout configuration
page:
  title: "Dashboard"
  auto_load: true

  kpi_rows:
    - cards:
        - id: emails_today
          label: "Emails Today"
          query: "emails_sent_today / 500"
          format: "{value} / 500"
          color_rule: "green if value < 400, amber if value < 480, red if value >= 480"
        - id: wa_today
          label: "WA Today"
          query: "wa_sent_today / 1000"
          format: "{value} / 1000"
        - id: total_contacts
          label: "Contacts"
          color: "primary"
        - id: wa_24h_window
          label: "24h Window"
          query: "contacts with last_wa_inbound_at within 24h"
          color_rule: "green if value > 0, muted if value == 0"

    - cards:
        - id: opted_in
          label: "Opted In"
          color: "success"
        - id: pending
          label: "Pending"
          color: "warning"
        - id: email_campaigns
          label: "Email Campaigns"
          color: "primary"
        - id: wa_campaigns
          label: "WA Campaigns"
          color: "success"

  sections:
    - id: lifecycle_breakdown
      title: "Lifecycle Breakdown"
      type: progress_bars

    - id: recent_activity
      title: "Recent Activity"
      type: feed
      limit: 20
      icons:
        email_sent: "✉"
        wa_sent: "💬"
        wa_received: "📩"
        contact_added: "📋"
        campaign_sent: "🚀"

    - id: getting_started
      title: "Getting Started"
      type: info_card
      steps:
        - "Contacts → add/import contacts"
        - "Email → pick template → send"
        - "Inbox → view/reply conversations"
        - "Flows → automate sequences"

    - id: system
      title: "System"
      type: info_card
```

---

## Config File: pages/contacts.yml (NEW)

```yaml
page:
  title: "Contacts"

  filters:
    - id: segment
      label: "Segment"
      type: dropdown
      source: "schema.segments"
      include_all: true
    - id: lifecycle
      label: "Lifecycle"
      type: dropdown
      source: "schema.lifecycle_stages"
      include_all: true
    - id: country
      label: "Country"
      type: dropdown
      source: "distinct(contacts.country)"
      include_all: true
    - id: channel
      label: "Channel"
      type: dropdown
      options: ["All", "Email Only", "WhatsApp Only", "Both"]

  table:
    page_size: 50
    columns:
      - field: name
        label: "Name"
        width: "18%"
        render: "name_with_company"
      - field: channels
        label: "Channel"
        width: "10%"
        render: "channel_badges"
      - field: lifecycle
        label: "Lifecycle"
        width: "10%"
        render: "lifecycle_badge"
      - field: email
        label: "Email"
        width: "25%"
        font: "monospace"
      - field: phone
        label: "Phone"
        width: "12%"
      - field: tags
        label: "Tags"
        width: "15%"
        render: "tag_pills"
      - field: segment
        label: "Segment"
        width: "10%"
        render: "segment_badge"

  add_contact:
    title: "Add New Contact"
    tabs: ["Single Contact", "Import CSV"]
    import_instructions: "CSV must have: email (required), first_name, last_name, phone, company"
```

---

## Config File: pages/inbox.yml (NEW)

```yaml
page:
  title: "Inbox"

  column_1:
    title: "Conversations"
    search_placeholder: "Search by name..."
    min_search_chars: 2
    contact_list:
      show_avatar: true
      show_last_message: true
      show_timestamp: true
      show_unread_badge: true
      sort_by: "last_activity"

  column_2:
    channels:
      - id: whatsapp
        label: "WhatsApp"
        icon: "💬"
      - id: email
        label: "Email"
        icon: "✉"
    message_input:
      placeholder: "Type a message..."
      show_attach: true
      show_template_picker: true
    window_warning:
      text: "WhatsApp's customer service window closed"
      detail: "WhatsApp doesn't allow sending messages after 24 hours since the last Contact reply. To continue, send an approved Message Template."

  column_3:
    title: "Contact Details"
    sections:
      - id: channels
        label: "Channels"
      - id: contact_fields
        label: "Contact Fields"
        fields: [phone, email, country]
      - id: lifecycle
        label: "Lifecycle"
        editable: true
      - id: segment
        label: "Segment"
        editable: true
      - id: tags
        label: "Tags"
        editable: true
      - id: activity_log
        label: "Activity Log"
        limit: 20
```

---

## Phase 1: Lifecycle + Contact Schema (YAML Config)

### New Config Files

**`config/contacts/schema.yml`** — defines contact fields, segments, tags, lifecycle

```yaml
contact_schema:
  segments:
    - id: potential_b2b
      label: "Potential B2B"
      color: "#6366f1"
      subtypes: [carpet_exporter, handicraft_exporter, textile_manufacturer]
    - id: existing_client
      label: "Existing Client"
      color: "#22c55e"
      subtypes: [vip, regular]
    - id: yarn_store
      label: "Yarn Store"
      color: "#f59e0b"
      subtypes: [retail_store, wholesale]
    - id: other
      label: "Other"
      color: "#64748b"
      subtypes: []

  lifecycle_stages:
    - id: new_lead
      label: "New Lead"
      color: "#6366f1"
      icon: "🔵"
    - id: contacted
      label: "Contacted"
      color: "#f59e0b"
      icon: "🟡"
    - id: interested
      label: "Interested"
      color: "#22c55e"
      icon: "🟢"
    - id: customer
      label: "Customer"
      color: "#14b8a6"
      icon: "⭐"
    - id: churned
      label: "Churned"
      color: "#ef4444"
      icon: "🔴"

  tags:
    predefined:
      - wool
      - hemp
      - nettle
      - yarn
      - carpet
      - silk
      - premium
      - samples_sent
      - samples_received
      - quoted
      - order_placed
    allow_custom: true

  fields:
    first_name:
      type: text
      required: true
      placeholder: "First name"
    last_name:
      type: text
      required: false
      placeholder: "Last name"
    phone:
      type: phone
      required: true
      prefix: "+91"
      placeholder: "10 digit mobile"
      validation: "^[0-9]{10}$"
    email:
      type: email
      required: false
      placeholder: "name@company.com"
    company:
      type: text
      required: false
      placeholder: "Company name"
    country:
      type: dropdown
      required: false
      default: "India"
      options: [India, US, UK, Canada, Australia, Germany, France, Nepal, Other]
```

### Database Changes

Add `lifecycle` column to Contact model:

```python
# services/models.py — Contact model
lifecycle = Column(String(32), default="new_lead")  # new_lead, contacted, interested, customer, churned
```

### Migration Script

One-time script to assign lifecycle to existing 941 contacts:

```python
# scripts/migrate_lifecycle.py
# pending + 0 emails sent → new_lead
# pending + emails sent > 0 → contacted
# opted_in → interested
# existing_client → customer
# opted_out → churned
```

### Lifecycle Seeding During CSV Import

In `services/database.py`, the `_seed_contacts()` function assigns lifecycle based on:

```python
# Auto-assign lifecycle during CSV seed
if customer_type == "existing_client":
    lifecycle = "customer"
elif consent_status == "opted_out":
    lifecycle = "churned"
elif consent_status == "opted_in":
    lifecycle = "interested"
elif int(total_emails_sent) > 0:
    lifecycle = "contacted"
else:
    lifecycle = "new_lead"
```

This ensures lifecycle is NEVER lost on DB recreate — it's computed from existing CSV data every time.

### Files to Create/Modify

| File | Action |
|------|--------|
| `config/contacts/schema.yml` | CREATE — contact schema definition |
| `services/models.py` | MODIFY — add `lifecycle` column |
| `services/database.py` | MODIFY — seed lifecycle from rules during CSV import |
| `services/contact_schema.py` | CREATE — load schema.yml, validate contacts |

---

## Phase 2: Home Page Refactor

### Requirements
- Loads with data by default (no blank screen)
- Two rows of KPI cards (8 total)
- Lifecycle breakdown with progress bars
- Recent activity feed (both channels)
- Getting Started + System info

### KPI Cards (Row 1)
| Card | Value | Color Logic |
|------|-------|-------------|
| Emails Today | `12 / 500` | Green if < 400, amber if < 100, red if 0 |
| WhatsApp Today | `5 / 1000` | Same |
| Total Contacts | `941` | Primary |
| 24h Window | `3` | Green if > 0, muted if 0 |

### KPI Cards (Row 2)
| Card | Value | Color Logic |
|------|-------|-------------|
| Opted In | `127` | Green |
| Pending | `814` | Amber |
| Email Campaigns | `4` | Primary |
| WA Campaigns | `2` | Green |

### Lifecycle Breakdown
- Horizontal progress bars showing distribution
- Each stage: colored bar + label + count + percentage
- Clickable — links to Contacts page filtered by that lifecycle

### Recent Activity Feed
- Last 20 actions across both channels
- Format: `timestamp  icon  description`
- Icons: ✉ email sent, 💬 WA sent, 📩 WA received, 📋 contact added, 🚀 campaign sent

### Auto-Load Fix
- In `navigation_engine.py`, after building the Blocks, add:
  ```python
  # Trigger home page data load on initial page visit
  if "home" in page_wirings:
      home_wiring = page_wirings["home"]
      app.load(fn=home_wiring["update_fn"], outputs=home_wiring["outputs"])
  ```
- This calls the home page's `update_fn()` when the app first loads, so KPI cards show data immediately without clicking Home button

### Files to Modify

| File | Change |
|------|--------|
| `pages/home.py` | REWRITE — new dashboard layout |
| `engines/navigation_engine.py` | MODIFY — auto-load default page data on startup |

---

## Phase 3: Contacts Page Refactor

### Layout: Two Columns

**Left Column (250px fixed):**
- `gr.Dropdown` — Segment filter: All, Potential B2B (504), Yarn Store (310), Existing Client (127)
  - Choices populated dynamically with counts from DB
  - `.change()` event filters the table
- `gr.Dropdown` — Lifecycle filter: All, New Lead (612), Contacted (198), Interested (76), Customer (45), Churned (10)
  - Choices populated dynamically with counts
  - `.change()` event filters the table
- `gr.Dropdown` — Country filter: All, India, US, UK, etc.
- `gr.Dropdown` — Channel filter: All, Email Only, WhatsApp Only, Both
- KPI cards (gr.HTML) below filters showing:
  - Total contacts, Opted In, Pending, WA Ready

**Right Column (flex):**
- Top bar: `gr.Textbox` search + [+ Add Contact] `gr.Button` + [Import] `gr.Button`
- Contact table (`gr.HTML`, scrollable, sticky header):
  - Columns: Name+Company | Channel badges | Lifecycle badge | Email | Phone | Tags
  - Fixed column widths via `<colgroup>`
  - Row hover highlight
- Pagination footer: "1-50 of 941 | Page 1 of 19"

**All filter dropdowns wire `.change()` to a single `_apply_filters()` function that rebuilds the table.**

### Add Contact Overlay

When [+ Add Contact] is clicked:
- Overlay panel appears (or slides from right)
- Two tabs: [Single Contact] [Import CSV]
- Single Contact form fields loaded from `config/contacts/schema.yml`:
  - First Name*, Last Name, Phone* (+91 prefix), Email, Company, Country dropdown
  - Segment: radio buttons (B2B, Yarn Store, Existing Client, Other)
  - Lifecycle: dropdown (New Lead, Contacted, etc.)
  - Tags: multi-select from predefined + custom input
- Validation: phone must be 10 digits, email must have @
- On save: table auto-refreshes, new contact visible

### Import CSV Tab
- File upload area
- Instructions: "CSV must have columns: email (required), first_name, last_name, phone, company"
- On upload: shows preview (first 5 rows)
- [Confirm Import] button
- Result: "Imported 50, skipped 3 (duplicates)"

### Files to Create/Modify

| File | Action |
|------|--------|
| `pages/contacts.py` | REWRITE — two-column with segment sidebar |
| `services/contact_schema.py` | CREATE — load YAML schema, validate, provide choices |
| `config/contacts/schema.yml` | CREATE (Phase 1) |

---

## Phase 4: Inbox Page (Combined WhatsApp + Email)

### Rename
- Sidebar: "WhatsApp" → "Inbox"
- Page file: keep `pages/whatsapp.py` but rename display to "Inbox"
- Or create `pages/inbox.py` and remove `pages/whatsapp.py`

### Layout: Three Columns

**Column 1 — Contact List + Filters (250px)**
- `gr.Textbox` — search contacts by name (live DB query on each keystroke)
  - When user types 2+ chars, populates the contact dropdown below
- `gr.Dropdown` — contact selector (populated from search results)
  - `.change()` loads conversation + profile in columns 2 + 3
- `gr.Dropdown` — lifecycle filter: All, New Lead, Contacted, etc.
- Chat list below (`gr.HTML`) — visual display of recent conversations
  - Avatar + Name + last message preview + timestamp
  - Unread badge
  - This is display-only — actual selection via the dropdown above
- `gr.Button` — 🔄 Refresh

**Column 2 — Conversation Center (flex)**
- Contact header (`gr.HTML`) — name + phone/email + 24h window status
- `gr.Dropdown` — Channel: "WhatsApp" or "Email"
  - `.change()` swaps conversation content between WA and Email view
- Conversation content (`gr.HTML`) — renders based on selected channel:

  **When channel = WhatsApp:**
  - Date separators ("April 12, 2026")
  - Chat bubbles (inbound left, outbound right)
  - Timestamps + delivery status (✓ ✓✓)
  - 24h window indicator bar

  **When channel = Email:**
  - Sent email cards: Subject, To, timestamp, status badge (SENT)
  - Email body preview (truncated)
  - Phase 1: sent emails only (from EmailSend table)
  - Phase 2: Gmail API read for received emails

- Message input area:
  - `gr.Textbox` — type message (for WhatsApp text reply)
  - `gr.File` — attach image
  - `gr.Dropdown` — template selector (for WA templates or email templates)
  - `gr.Button` — "Send Template" + `gr.Button` — "Send"

**Column 3 — Contact Profile (250px)**
- Contact info (`gr.HTML`) — avatar, name, company, channels, phone, email, country
- `gr.Dropdown` — Lifecycle (change saves immediately via `.change()`)
- `gr.Dropdown` — Segment (change saves immediately)
- `gr.Textbox` — Tags (comma-separated, saves on change)
- Activity log (`gr.HTML`) — built from EmailSend + WAMessage tables:
  - Merged, sorted by date
  - "Apr 12 — WA message received"
  - "Apr 12 — Email campaign sent"
  - "Apr 11 — Contact created"

### Key Interactions

1. **Search contact** → type name in search → dropdown populates → select
2. **Select contact** → dropdown `.change()` loads conversation + profile
3. **Switch channel** → channel dropdown `.change()` swaps WA ↔ Email view
4. **Send WhatsApp** → type message → Send (checks 24h window) OR pick template → Send Template
5. **Send Email** → pick email template from dropdown → Send Template (via Gmail API)
6. **Change lifecycle** → dropdown `.change()` saves immediately
7. **Change segment** → dropdown `.change()` saves immediately
8. **Edit tags** → textbox `.change()` saves comma-separated tags
9. **Refresh** → button reloads all three columns

### Files to Create/Modify

| File | Action |
|------|--------|
| `pages/inbox.py` | CREATE — new combined inbox page |
| `pages/whatsapp.py` | DELETE — replaced by inbox.py |
| `config/dashboard/sidebar.yml` | MODIFY — rename "WhatsApp" to "Inbox" |
| `engines/navigation_engine.py` | MODIFY — update page module reference |

---

## Phase 5: Sidebar Config Update

```yaml
# config/dashboard/sidebar.yml
sidebar:
  nav_items:
    - id: home
      label: "Home"
      icon: "\U0001F3E0"

    - id: contacts
      label: "Contacts"
      icon: "\U0001F4CB"

    - id: inbox
      label: "Inbox"
      icon: "\U0001F4E8"
      separator_before: true

    - id: email_campaigns
      label: "Campaigns"
      icon: "\U00002709"

    - id: flows
      label: "Flows"
      icon: "\U0001F504"
      separator_before: true

    - id: templates_media
      label: "Templates"
      icon: "\U0001F4C4"
```

---

## Implementation Order

| Step | What | Depends On |
|------|------|------------|
| 1 | Create `config/contacts/schema.yml` | — |
| 2 | Add `lifecycle` to Contact model in `services/models.py` | — |
| 3 | Update `services/database.py` — seed lifecycle from CSV data rules | Steps 1, 2 |
| 4 | Create `services/contact_schema.py` (YAML loader + validator) | Step 1 |
| 5 | Create `config/theme/components.yml` — component styles | — |
| 6 | Update `components/styles.py` — read from components.yml | Step 5 |
| 7 | Create all page YAMLs: `config/pages/{home,contacts,inbox,campaigns,flows,templates}.yml` | — |
| 8 | Rewrite `pages/home.py` — reads from pages/home.yml | Steps 3, 5, 7 |
| 9 | Fix `engines/navigation_engine.py` — auto-load home on startup | Step 8 |
| 10 | Rewrite `pages/contacts.py` — reads from pages/contacts.yml + schema.yml | Steps 3, 4, 7 |
| 11 | Create `pages/inbox.py` — reads from pages/inbox.yml | Steps 3, 4, 7 |
| 12 | Update `config/dashboard/sidebar.yml` — rename WhatsApp to Inbox | Step 11 |
| 13 | Delete `pages/whatsapp.py` | Step 11 |
| 14 | Push to HF Spaces | All |
| 15 | Playwright verify all pages + screenshots | Step 14 |

---

## New Files Summary

| File | Purpose |
|------|---------|
| `config/contacts/schema.yml` | Contact fields, segments, lifecycle, tags, validation |
| `config/theme/components.yml` | KPI card, table, bubble, badge, sidebar styles |
| `config/pages/home.yml` | KPI definitions, sections, activity icons |
| `config/pages/contacts.yml` | Filters, table columns, add form config |
| `config/pages/inbox.yml` | 3-column config, channel options, profile sections |
| `config/pages/campaigns.yml` | Form fields, step labels |
| `config/pages/flows.yml` | Flow display config |
| `config/pages/templates.yml` | Channel tabs, preview config |
| `services/contact_schema.py` | YAML loader + validator for contact schema |
| `pages/inbox.py` | Combined WA + Email inbox page |

---

## Verification Checklist

### Home Page
- [ ] Loads with data by default (no click needed)
- [ ] 8 KPI cards showing correct numbers
- [ ] Lifecycle breakdown with progress bars
- [ ] Recent activity feed shows both channels
- [ ] Getting Started + System sections

### Contacts Page
- [ ] Left sidebar: segments clickable with counts
- [ ] Left sidebar: lifecycle clickable with counts
- [ ] Table: proper columns with fixed widths, no overlap
- [ ] Search filters table instantly
- [ ] Click segment → table filters
- [ ] [+ Add Contact] → overlay form appears
- [ ] Form validates phone (10 digits) and email (has @)
- [ ] Segment radio + Lifecycle dropdown + Tags in form
- [ ] Save → table refreshes with new contact
- [ ] Import CSV works
- [ ] Download CSV works

### Inbox Page
- [ ] Three-column layout renders correctly
- [ ] Contact list shows avatars + names + last message preview
- [ ] Click contact → conversation loads
- [ ] WhatsApp tab: chat bubbles with timestamps
- [ ] Email tab: sent emails listed
- [ ] 24h window indicator shows correctly
- [ ] Send text message works (within 24h)
- [ ] Send template works (anytime)
- [ ] Profile panel: lifecycle dropdown saves
- [ ] Profile panel: tags editable
- [ ] Refresh button reloads data
- [ ] Activity log shows timeline
