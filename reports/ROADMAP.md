# Himalayan Fibers Email Marketing - Project Roadmap

## Current Status: Data Import Complete ✅

### Contact Database Summary

| Customer Type | Count | Geography | Email Status |
|--------------|-------|-----------|--------------|
| **Potential B2B** (Carpet Exporters) | 504 | India | ✅ Ready |
| **Yarn Stores** | 310 | International (US/UK) | ✅ Ready |
| **Existing Clients** | 127 | India | ⚠️ Need Email Addresses |
| **Total** | **941** | | **814 ready to email** |

### Files Structure
```
data/
├── contacts.csv              # Master list (941 contacts)
├── segments.csv              # 11 pre-defined segments
├── campaigns.csv             # Campaign records
├── email_sends.csv           # Email tracking
├── by_type/
│   ├── potential_b2b.csv     # 504 carpet exporters
│   ├── yarn_store.csv        # 310 yarn stores
│   └── existing_client.csv   # 127 past customers
└── reports/
    └── existing_clients_need_email.csv  # Companies needing email
```

---

## What To Do Next (Recommended Order)

### Phase 1: Email Templates (This Week)
**Goal: Create professional email templates for each customer segment**

#### 1.1 Introduction/Welcome Emails
- [ ] **Carpet Exporters Introduction** - Introduce Himalayan Fibers to potential B2B clients
- [ ] **Yarn Store Introduction** - Introduce wholesale yarn offerings to US/UK stores
- [ ] **Customer Welcome** - Welcome email for new paying customers

#### 1.2 Product Showcase Emails
- [ ] **Hemp Yarn Catalog** - Showcase hemp yarn products
- [ ] **Nettle Fiber Catalog** - Showcase nettle fiber products
- [ ] **Wool Collection** - Showcase wool products
- [ ] **Custom/Bulk Order Info** - Information for large orders

#### 1.3 Educational/Nurture Emails
- [ ] **Himalayan Fiber Story** - Company background, sustainability
- [ ] **Hemp Benefits** - Educational content about hemp fibers
- [ ] **Production Process** - Behind-the-scenes manufacturing
- [ ] **Case Studies** - Success stories with existing clients

---

### Phase 2: First Campaign Launch
**Goal: Send your first email campaign to test the system**

#### 2.1 Test Campaign (Small Batch)
1. Select 10-20 contacts from Potential B2B segment
2. Create introduction email
3. Send test campaign
4. Monitor delivery, opens, clicks

#### 2.2 Full Campaign Rollout
1. **Campaign 1**: Introduction to Carpet Exporters (504 contacts)
2. **Campaign 2**: Introduction to Yarn Stores (310 contacts)
3. **Campaign 3**: Re-engagement with Existing Clients (once emails added)

---

### Phase 3: Automation Setup
**Goal: Set up automated email sequences**

#### 3.1 Wix Integration
- [ ] Test webhook for new orders
- [ ] Set up welcome email automation
- [ ] Set up cart abandonment sequence

#### 3.2 Email Sequences
- **New Lead Sequence**: Introduction → Product Info → Case Study → Offer
- **Post-Purchase Sequence**: Thank You → Product Care → Review Request
- **Re-engagement Sequence**: Check-in → New Products → Special Offer

---

### Phase 4: Analytics & Optimization
**Goal: Track performance and improve**

- [ ] Set up email tracking (opens, clicks)
- [ ] Monitor bounce rates
- [ ] A/B test subject lines
- [ ] Build dashboard for metrics

---

## Immediate Action Items

### TODAY:
1. ✅ Data import complete
2. **Create first email template** (Introduction to Carpet Exporters)
3. **Test Gmail SMTP** - Verify email sending works

### THIS WEEK:
1. Create 3-4 email templates
2. Send test campaign to small batch
3. Verify Wix webhook integration

### NEXT WEEK:
1. Full campaign rollout to Potential B2B
2. Create yarn store campaign
3. Collect emails for existing clients

---

## Campaign Ideas by Segment

### For Carpet Exporters (504 contacts)
| Campaign | Subject Line Ideas | Goal |
|----------|-------------------|------|
| Introduction | "Premium Himalayan Fibers for Your Carpets" | Awareness |
| Product Focus | "Hemp Yarn - The Future of Sustainable Carpets" | Interest |
| Case Study | "How [Client] Reduced Costs with Our Fibers" | Trust |
| Offer | "Exclusive Pricing for New Partners" | Conversion |

### For Yarn Stores (310 contacts)
| Campaign | Subject Line Ideas | Goal |
|----------|-------------------|------|
| Introduction | "Wholesale Himalayan Yarns - Direct from Source" | Awareness |
| Product Catalog | "2025 Yarn Collection - Hemp, Nettle, Wool" | Interest |
| Sustainability | "Eco-Friendly Yarns Your Customers Will Love" | Values |
| Bulk Pricing | "Wholesale Pricing for US/UK Retailers" | Conversion |

### For Existing Clients (127 contacts - once emails added)
| Campaign | Subject Line Ideas | Goal |
|----------|-------------------|------|
| Thank You | "Thank You for Being a Valued Customer" | Retention |
| New Products | "New Arrivals - Exclusive Preview for You" | Upsell |
| Feedback | "Help Us Serve You Better" | Engagement |
| Referral | "Refer a Partner, Earn Rewards" | Expansion |

---

## Technical Checklist

### Before First Campaign:
- [ ] Verify Gmail SMTP credentials work
- [ ] Test email sending to your own email
- [ ] Verify unsubscribe link works
- [ ] Check email renders correctly in Gmail, Outlook, mobile

### Email Best Practices:
- Send from: `info@himalayanfibre.com`
- Include physical address (CAN-SPAM compliance)
- Include unsubscribe link
- Keep subject lines under 50 characters
- Optimal send times: Tuesday-Thursday, 10 AM - 2 PM recipient time

---

## Data Still Needed

### Priority 1: Existing Client Emails
The 127 existing clients from your sales data need email addresses.
**File to update**: `data/reports/existing_clients_need_email.csv`

### Priority 2: Contact Person Names for Yarn Stores
The yarn store file has store names but missing contact person names.
Would improve personalization.

### Priority 3: More International Contacts
Currently only US/UK yarn stores.
Consider adding: Europe, Australia, Canada markets.

---

## Quick Commands

```bash
# Start the application
cd /home/prashant-agrawal/projects/email_marketing
source myvenv/bin/activate

# View contact stats
python -c "from app.data_manager import DataManager; dm = DataManager(); print(dm.get_contact_stats())"

# Get contacts for a campaign
python -c "
from app.data_manager import DataManager
dm = DataManager()
# Get carpet exporters
carpet = dm.search_contacts(customer_type='potential_b2b', customer_subtype='carpet_exporter')
print(f'Carpet Exporters: {len(carpet)}')
# Get yarn stores
yarn = dm.search_contacts(customer_type='yarn_store')
print(f'Yarn Stores: {len(yarn)}')
"

# Re-run data import
python scripts/import_all_data.py
```

---

## Next: Create Your First Email Template

Ready to create the first email template? Choose one:

1. **Introduction to Carpet Exporters** - Best for immediate outreach
2. **Introduction to Yarn Stores** - For US/UK market
3. **Welcome Email for New Customers** - For Wix automation

Let me know which one to start with!
