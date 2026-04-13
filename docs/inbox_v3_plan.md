# Plan: Separate WhatsApp & Email Inboxes

## Context

User wants two separate inbox pages instead of a combined one. Each inbox should match the respond.io/Chatwoot pattern: 3-column layout with conversation list, chat view, and contact profile. Only show active conversations (contacts who have actual message history).

## Reference

Screenshot: `Pages/3. Inbox/Inbox_screen_message.PNG` — respond.io WhatsApp inbox with:
- Left: Filter sidebar (All, Mine, Unassigned, lifecycle stages) + conversation list with avatars
- Center: Chat area with system events ("Conversation opened by you", "Contact added by you"), message bubbles with timestamps, 24h window warning, message input bar
- Right: Contact name + profile info

---

## Sidebar Update

```yaml
nav_items:
  - id: home
    label: "Home"
    icon: "🏠"

  - id: contacts
    label: "Contacts"
    icon: "📋"

  - id: wa_inbox
    label: "WhatsApp"
    icon: "💬"
    separator_before: true

  - id: email_inbox
    label: "Email"
    icon: "✉"

  - id: email_campaigns
    label: "Campaigns"
    icon: "📧"
    separator_before: true

  - id: flows
    label: "Flows"
    icon: "🔄"

  - id: templates_media
    label: "Templates"
    icon: "📄"
```

---

## Page: WhatsApp Inbox (pages/wa_inbox.py)

### Layout: 3 Columns

**Column 1 — Conversation List (250px)**

Top section:
- `gr.Textbox` — search conversations by contact name
- `gr.Dropdown` — filter: All, New Lead, Contacted, Interested, Customer

Conversation list (`gr.HTML`):
- **Only shows contacts with active WA conversations** (have WAChat + WAMessage records)
- Each entry: Avatar circle + Contact name + Last message preview + Timestamp + Unread badge
- Sorted by most recent message
- Click a name → use `gr.Dropdown` to select (same search-then-select pattern)

**Column 2 — Chat Area (flex)**

Header (`gr.HTML`):
- Contact name + phone number
- 24h window status indicator

System events + Messages (`gr.HTML`, scrollable):
- System events: "Contact added by you", "Conversation opened by you" — styled as centered gray text
- Date separators: "Today", "April 12, 2026"
- Inbound bubbles: left-aligned, colored background (indigo tint)
- Outbound bubbles: right-aligned, dark background
- Each bubble: text + timestamp + delivery status (✓ ✓✓)
- 24h window warning bar at bottom when window closed

Message input area:
- `gr.Textbox` — message input
- `gr.Dropdown` — template picker (for when window is closed)
- `gr.Button` — "Send" (text) + `gr.Button` — "Send Template"
- `gr.File` — image attachment

**Column 3 — Contact Profile (250px)**

Contact details (`gr.HTML`):
- Avatar + Name + Company
- Channels: WhatsApp badge
- Phone, Email, Country
- Lifecycle badge

Editable fields:
- `gr.Dropdown` — Lifecycle (saves on change)
- `gr.Textbox` — Tags (saves on change)

Activity log (`gr.HTML`):
- Timeline of all WA interactions for this contact

---

## Page: Email Inbox (pages/email_inbox.py)

### Layout: 3 Columns (same structure, email-specific content)

**Column 1 — Contact List (250px)**

- `gr.Textbox` — search
- `gr.Dropdown` — lifecycle filter
- Contact list: **Only contacts who have EmailSend records** (have been emailed)
- Each entry: Avatar + Name + Last email subject + Date + Status badge (sent/failed)

**Column 2 — Email Thread (flex)**

Header:
- Contact name + email address

Email list (`gr.HTML`, scrollable):
- Each email: Subject line, timestamp, status badge (SENT/FAILED)
- Email body preview (truncated, expandable)
- Newest first

Compose area:
- `gr.Dropdown` — template picker
- `gr.Textbox` — subject line
- `gr.Button` — "Send Email"

**Column 3 — Contact Profile (250px)**

Same structure as WhatsApp inbox profile panel.

---

## Page YAML Configs

### config/pages/wa_inbox.yml

```yaml
page:
  title: "WhatsApp Inbox"

  column_1:
    title: "Conversations"
    search_placeholder: "Search contacts..."
    empty_message: "No active WhatsApp conversations"
    filters:
      - id: lifecycle
        label: "Lifecycle"
        include_all: true

  column_2:
    system_events:
      contact_added: "Contact added by you"
      conversation_opened: "Conversation opened by you"
      conversation_closed: "Conversation closed by you"
      wa_api_connected: "New channel WhatsApp Cloud API added by you"
    window_warning:
      title: "WhatsApp's customer service window closed"
      detail: "WhatsApp doesn't allow sending messages after 24 hours since the last Contact reply. To continue, send an approved Message Template."
      button: "Send message template"
    message_input:
      placeholder: "Type a message..."

  column_3:
    title: "Contact details"
    sections: [channels, fields, lifecycle, tags, activity]
```

### config/pages/email_inbox.yml

```yaml
page:
  title: "Email Inbox"

  column_1:
    title: "Sent Emails"
    search_placeholder: "Search contacts..."
    empty_message: "No emails sent yet"
    filters:
      - id: lifecycle
        label: "Lifecycle"
        include_all: true

  column_2:
    compose:
      subject_placeholder: "Email subject..."
    empty_message: "Select a contact to view email history"

  column_3:
    title: "Contact details"
    sections: [channels, fields, lifecycle, tags, activity]
```

---

## Key Differences from Current Inbox

| Current | New |
|---------|-----|
| One combined inbox page | Two separate pages (WA + Email) |
| Shows ALL contacts with wa_id | Only shows contacts with ACTIVE conversations |
| No system events | Shows "Contact added", "Conversation opened" events |
| Channel dropdown to switch | Each page is dedicated to one channel |
| Complex, confusing | Simple, focused |

---

## Active Conversations Logic

**WhatsApp Inbox shows a contact if:**
- They have at least 1 WAMessage record (sent or received)
- OR they have a WAChat record with messages

**Email Inbox shows a contact if:**
- They have at least 1 EmailSend record (email was sent to them)

This means:
- Newly added contacts DON'T appear in inboxes until you message them
- Contacts page is where you find contacts
- Inbox pages are where you manage ongoing conversations

---

## System Events

System events appear as centered gray text in the conversation, like:
```
─────── Today ───────
        Contact added by you
        Conversation opened by you
        New channel WhatsApp Cloud API added by you

    ┌──────────────────────────────┐
    │ Hello World                  │
    │ Welcome and congratulations! │
    │ This message demonstrates... │
    └──────────────────────────────┘
                          WhatsApp Business Platform sample message

─── WhatsApp Cloud API · no: 918582952074 ───

⚠ WhatsApp's customer service window closed
  WhatsApp doesn't allow sending messages after 24 hours...
  [Send message template]
```

These events are generated from:
- Contact created_at → "Contact added by you"
- First WAMessage sent → "Conversation opened by you"
- WAChat created → "New channel WhatsApp Cloud API added by you"

---

## Review Gaps — Addressed

### Gap 1: Shared Profile Component (MEDIUM)
Both pages need the same contact profile panel. Extract into reusable component.

**Fix:** Create `components/contact_profile.py` with `render_profile(db, contact_id)`.
Returns HTML for: avatar, name, company, channels, phone/email/country fields, lifecycle badge, tags.
Used by both `wa_inbox.py` and `email_inbox.py` — no code duplication.

### Gap 2: Shared Conversation List Component (MEDIUM)
Both pages have similar Column 1 (avatar + name + preview + timestamp).

**Fix:** Create `components/conversation_list.py` with:
- `render_wa_conversations(db)` — contacts with WAMessage records, sorted by last message
- `render_email_conversations(db)` — contacts with EmailSend records, sorted by last sent
- Shared avatar + name + preview rendering logic

### Gap 3: System Events — No Database Table (LOW)
System events like "Conversation opened" are inferred, not stored.

**Fix V1:** Only show events that can be inferred from existing data:
- `contact.created_at` → "Contact added by you"
- First WAMessage with direction="out" → "Conversation opened by you"
- WAChat.created_at → "New channel WhatsApp Cloud API added"
- Skip "closed" and "assigned" — add in future when we build conversation state management

### Gap 4: Email Compose Reuses Existing Send Logic (LOW)
Already solved. `EmailSender.send_email()` handles everything. Compose handler calls it directly and creates EmailSend record.

### Gap 5: Refresh Button on Both Pages (LOW)
**Fix:** Add `gr.Button("🔄 Refresh")` to top bar of both pages. Wired to reload conversation list + current conversation + profile.

### Gap 6: Email Inbox Search Queries All Contacts (LOW)
**Fix:** Email inbox search queries ALL contacts with email (not just those with EmailSend records). This allows starting a new email conversation with any contact from the inbox page itself.

### Gap 7: WhatsApp Inbox Already Has Chat List Logic (LOW)
Already solved. Existing `_build_chat_list()` pattern handles the JOIN between Contact + WAChat.

---

## Implementation Steps (Updated)

| Step | What |
|------|------|
| 1 | Create `components/contact_profile.py` — shared profile renderer |
| 2 | Create `components/conversation_list.py` — shared conversation list renderer |
| 3 | Create `config/pages/wa_inbox.yml` |
| 4 | Create `config/pages/email_inbox.yml` |
| 5 | Create `pages/wa_inbox.py` — WhatsApp inbox with 3 columns, refresh button, system events |
| 6 | Create `pages/email_inbox.py` — Email inbox with 3 columns, compose, search all contacts |
| 7 | Delete `pages/inbox.py` (the combined one) |
| 8 | Update `config/dashboard/sidebar.yml` — add wa_inbox + email_inbox, remove inbox |
| 9 | Push to HF Spaces |
| 10 | Playwright verify both inbox pages |

---

## Files Summary (Updated)

| File | Action |
|------|--------|
| `components/contact_profile.py` | CREATE — shared profile panel renderer |
| `components/conversation_list.py` | CREATE — shared conversation list renderer |
| `config/pages/wa_inbox.yml` | CREATE — WhatsApp inbox page config |
| `config/pages/email_inbox.yml` | CREATE — Email inbox page config |
| `pages/wa_inbox.py` | CREATE — full WhatsApp inbox page |
| `pages/email_inbox.py` | CREATE — full Email inbox page |
| `pages/inbox.py` | DELETE — replaced by wa_inbox + email_inbox |
| `config/dashboard/sidebar.yml` | UPDATE — add wa_inbox + email_inbox, remove inbox |
