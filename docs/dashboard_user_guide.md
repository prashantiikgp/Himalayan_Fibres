# Himalayan Fibers Dashboard — User Guide

**Dashboard URL:** https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space

---

## What is this dashboard?

Think of it like a control room for talking to your customers. You have **two phones** — one for email and one for WhatsApp. This dashboard lets you:

1. **See all your contacts** (like a big address book)
2. **Send emails** to many people at once (campaigns)
3. **Send WhatsApp messages** to people
4. **Set up automatic follow-ups** (flows — like a robot that sends emails on a schedule)
5. **See your email templates** (pre-written emails you can reuse)

The dashboard has **6 pages** — click the buttons on the left sidebar to switch between them.

---

## Page 1: Home (🏠)

This is your **dashboard homepage**. It shows you:

- **Emails Today: 0 / 500** — You can send up to 500 emails per day (Gmail limit). This counter shows how many you've used.
- **Total Contacts: 941** — How many people are in your address book
- **Opted In: 0** — How many people said "yes, send me emails" (right now everyone is "pending" because they were imported from Mailchimp)
- **WA Reachable: 681** — How many contacts have phone numbers for WhatsApp

### Quick Actions
- **Test SMTP** — Click this to check if your email connection is working. If it says ✅ Connected, you're good to send emails.
- **Test WA API** — Click this to check if your WhatsApp connection is working.

---

## Page 2: Contacts (📋)

This is your **address book**. All 941 contacts are here.

### How to find a contact

1. **Search box** — Type a name, email, or company name. The table filters instantly.
2. **Consent dropdown** — Filter by "Opted In", "Pending", or "Opted Out"
3. **Type dropdown** — Filter by business type: "potential_b2b" (new leads), "existing_client" (current customers), "yarn_store" (US/UK retailers)
4. **Country dropdown** — Filter by India, US, UK, etc.
5. **Segment dropdown** — Filter by pre-built groups like "All Existing Clients" or "Carpet Exporters - India"

### Understanding the table columns

| Column | What it means |
|--------|--------------|
| **Name** | Contact person's name |
| **Email** | Their email address |
| **Company** | Their company name |
| **Type** | carpet_exporter, retail_store, textile_manufacturer, etc. |
| **Country** | Where they're based |
| **Consent** | "pending" = haven't said yes yet, "opted_in" = said yes, "opted_out" = said no |
| **Ch** | Channels: ✉ = has email, 💬 = has WhatsApp |

### How to opt someone in (so you can email them)

Right now, all 941 contacts are "pending." Before you can send them campaigns, you need to opt them in:

1. In the **Consent** section on the left, type the contact's email (e.g. `info@overseascarpets.com`)
2. Click **Opt In**
3. You'll see a green message: "info@overseascarpets.com → opted_in"
4. Now this contact can receive campaigns!

> **Important:** Only send emails to people who have given you permission. "Opt In" means they agreed to receive emails from you.

### How to import new contacts

1. Scroll down to **Import / Export** section
2. Click **"Click to upload or drop files"**
3. Select a CSV or Excel file with columns: `email`, `first_name`, `last_name`, `company`, `phone`, `country`
4. The system will import them, skipping any duplicates
5. You'll see: "Imported 50, skipped 3 (duplicates/invalid)"

### How to download your contacts

1. Click **Download CSV**
2. A CSV file with all your contacts will download

---

## Page 3: Email Campaigns (✉)

This is where you **create and send bulk emails**.

### Step-by-step: How to send a bulk email campaign

#### Step 1: Create a campaign

1. Go to the **Email** page (click ✉ Email in the sidebar)
2. Find the **"Create New Campaign"** section
3. Fill in:
   - **Campaign Name:** Give it a name like "B2B Spring Outreach"
   - **Subject Line:** What people see in their inbox, e.g. "Premium Himalayan Fibers for {{company_name}}"
     - `{{company_name}}` gets replaced with each contact's company name automatically!
   - **Template:** Pick a pre-written email template from the dropdown:
     - `b2b_introduction` — Introduces Himalayan Fibers to carpet exporters
     - `sustainability` — About EU/US sustainability standards
     - `tariff_advantage` — About beating import tariffs with domestic sourcing
     - `welcome_production` — Welcome email
   - **Segment:** Pick who should receive it:
     - `all_opted_in` — Everyone who opted in
     - Or pick a specific segment from the dropdown
4. Click **Create Draft**
5. You'll see: "Campaign 'B2B Spring Outreach' created as draft"

#### Step 2: Send the campaign

1. In the **"Send Campaign"** section, select your campaign from the dropdown
2. Click **Preview Send**
3. You'll see a yellow/red box showing:
   - How many people will receive it (e.g. "Recipients: 127 contacts")
   - How many emails you have left today (e.g. "Daily limit remaining: 488")
4. **Check the checkbox** that says "I confirm sending to the recipients above"
5. Click **Confirm & Send Now**
6. The system starts sending — one email every 3 seconds (to avoid Gmail blocking)
7. When done, you'll see: "Sent: 124 | Failed: 3 | Total: 127"

> **How fast?** About 20 emails per minute. A campaign to 500 contacts takes ~25 minutes.

### What the KPI cards mean

| Card | Meaning |
|------|---------|
| **Campaigns** | Total number of campaigns created |
| **Sent** | How many campaigns have been fully sent |
| **Drafts** | How many are waiting to be sent |
| **Limit Left** | How many more emails you can send today (out of 500) |

---

## Page 4: Flows & Automations (🔄)

Flows are like **automatic email robots**. You set them up once, and they send a sequence of emails over days.

### Pre-built flows

The system comes with 3 flows ready to use:

**1. B2B Introduction Flow (Email, 3 steps)**
- Day 0: Sends the B2B Introduction email
- Day 3: Sends the Sustainability Compliance email
- Day 7: Sends the Tariff Advantage email

**2. Welcome & Nurture Flow (Email, 2 steps)**
- Day 0: Sends Welcome email
- Day 5: Sends product showcase email

**3. WhatsApp Welcome Flow (WhatsApp, 2 steps)**
- Day 0: Sends welcome_message template via WhatsApp
- Day 3: Sends snow_white product showcase template

### How to start a flow

1. Go to **Flows** page (click 🔄 in sidebar)
2. Select a flow from the **Flow** dropdown (e.g. "B2B Introduction Flow")
3. You'll see the step-by-step visualization showing what gets sent and when
4. Select a **Segment** — this is who should enter the flow
5. Set the **Start Date**
6. Click **Start Flow**
7. Step 1 sends immediately. Step 2 sends automatically after 3 days. Step 3 after 7 days.

> **How does the automation work?** A background process checks every 30 minutes for flow steps that are due. When it finds one, it sends the emails automatically.

---

## Page 5: WhatsApp (💬)

This is your **WhatsApp control center**.

### How to send a WhatsApp message to a contact

There are **two ways** to message someone on WhatsApp:

#### Way 1: Send a Template Message (works anytime)

Template messages are pre-approved by Meta/WhatsApp. You can send these to anyone, even if they haven't messaged you first.

1. Go to **WhatsApp** page
2. In the **Quick Send** section on the left:
   - Select a **Template** (e.g. "hello_world", "welcome_message", "snow_white")
   - Select a **Contact** from the dropdown (shows name + phone number)
3. Click **Send Template**
4. The message goes out via WhatsApp!

Available templates:
| Template | What it does |
|----------|-------------|
| `hello_world` | Simple test message |
| `welcome_message` | Welcome with product intro + website link |
| `order_confirmation` | Confirm an order with details |
| `payment_confirmation` | Acknowledge payment |
| `order_tracking` | Share shipping tracking info |
| `thank_you_note` | Post-purchase thank you |
| `snow_white` | Snow White yarn product showcase |
| `interactive_whatsap_buttons_new` | Catalog browsing button |

#### Way 2: Send a Text Reply (only within 24 hours)

WhatsApp has a rule: you can only send free-text messages if the contact messaged you in the last 24 hours. Otherwise, you must use a template.

1. In the **Reply** section on the right:
   - Type your message in the text box
   - Click **Send**
2. If you're **outside the 24-hour window**, you'll see a red warning: "Outside 24h window — use a template message instead."

#### How to send a product image via WhatsApp

1. In the **Send Image** section:
   - Upload a JPG/PNG image
   - Select the contact to send to
2. Click **Send Image via WA**
3. The image gets uploaded to Meta's servers and sent to the contact

### How to run a WhatsApp bulk campaign

Just like email campaigns, but for WhatsApp:

1. In the **WA Bulk Campaign** section at the bottom:
   - Select a **Template** (e.g. "welcome_message")
   - Select a **Segment** (which group of contacts)
2. Click **Send WA Campaign**
3. The system sends the template to every contact in the segment who has a WhatsApp number

---

## Page 6: Templates & Media (📄)

This is where you **preview and manage your email templates** and see your WhatsApp templates.

### Viewing email templates

1. Make sure **Email** is selected in the Channel radio buttons
2. Select a template from the **Template** dropdown
3. You'll see:
   - A **table** of all 7 email templates with their names, slugs, types (CAMPAIGN/TRANSACTIONAL), and subject lines
   - A **live preview** of the selected template showing exactly how the email will look

### Viewing WhatsApp templates

1. Click **WhatsApp** in the Channel radio buttons
2. You'll see all 9 Meta-approved WhatsApp templates with their categories, use cases, and variable counts

### Uploading a new email template

1. In the **Upload** section on the left, click the upload area
2. Select an HTML file (you can create these with CloudHQ or write them yourself)
3. The template gets added to your library

### Sending a test email

Before sending a campaign, you can test how a template looks in someone's inbox:

1. In the **Test Send** section:
   - Type your email address (e.g. your personal email)
   - Make sure a template is selected
2. Click **Send Preview**
3. Check your inbox — you'll see exactly what your contacts will receive

---

## Common Workflows

### "I want to send my first email campaign"

1. **Contacts page** → Opt in some contacts (type their email, click "Opt In")
2. **Email page** → Create a campaign (pick name, subject, template, segment)
3. **Email page** → Preview Send → Check the box → Confirm & Send

### "I want to set up a week-long email sequence"

1. **Flows page** → Select "B2B Introduction Flow"
2. Pick a segment (e.g. "Carpet Exporters - India")
3. Click "Start Flow"
4. Day 0: Introduction email sends immediately
5. Day 3: Sustainability email sends automatically
6. Day 7: Tariff advantage email sends automatically

### "I want to send a WhatsApp message to a new lead"

1. **WhatsApp page** → Quick Send section
2. Template: "welcome_message"
3. Contact: Select the person
4. Click "Send Template"

### "I want to import a new list of contacts"

1. **Contacts page** → Scroll to Import / Export
2. Upload your CSV/Excel file
3. Check the import count
4. Go opt in the new contacts you want to email

---

## Important Rules to Remember

1. **500 emails per day** — Gmail's limit. The dashboard tracks this for you.
2. **Opt in before emailing** — Only send to contacts with consent_status = "opted_in"
3. **WhatsApp 24-hour rule** — Free text messages only within 24h of their last message. Template messages work anytime.
4. **3-second delay between emails** — The system automatically spaces out sends to avoid Gmail blocking your account.
5. **No duplicate sends** — The system uses idempotency keys to prevent sending the same campaign email twice to the same person.

---

## Setting Up Secrets (for Prashant / admin)

To make email and WhatsApp actually work, set these secrets in Hugging Face Spaces settings:

1. Go to https://huggingface.co/spaces/Prashantiitkgp08/himalayan-fibers-dashboard/settings
2. Under **Repository secrets**, add:

| Secret Name | What to put |
|------------|-------------|
| `SMTP_USER` | `info@himalayanfibre.com` |
| `SMTP_PASSWORD` | Your Gmail App Password (16 characters from Google Account → App Passwords) |
| `WA_TOKEN` | Your Meta WhatsApp API Bearer token |
| `WA_PHONE_NUMBER_ID` | `814283648426112` |
| `WA_WABA_ID` | `2138990753291314` |
| `APP_PASSWORD` | A password to protect the dashboard (optional — leave empty for no login) |

3. After adding secrets, the Space will restart and pick them up.

### How to get a Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Other (Custom name)"
3. Type "Himalayan Fibers Dashboard"
4. Click "Generate"
5. Copy the 16-character password — that's your `SMTP_PASSWORD`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Test SMTP" shows ❌ | Check SMTP_PASSWORD secret is set correctly |
| "Test WA API" shows ❌ | Check WA_TOKEN secret — Meta tokens expire, you may need a new one |
| Emails not sending | Make sure contacts are "opted_in" (not "pending") |
| WhatsApp says "outside 24h window" | Use a template message instead of text |
| Contact table empty | Wait 30 seconds — the database seeds on first load |
| Dashboard shows login page | Enter the APP_PASSWORD you set in secrets |
| Campaign shows 0 recipients | Check that your segment has opted-in contacts |
