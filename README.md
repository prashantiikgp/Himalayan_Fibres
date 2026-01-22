# Himalayan Fibers Email Marketing System

A production-grade email marketing automation system built with Python, FastAPI, Celery, and PostgreSQL.

## Features

- **Webhook Integration**: Receive Wix eCommerce events (orders, cart abandonment)
- **Email Automation**: Welcome emails, cart abandonment sequences, shipping updates
- **Campaign Management**: Create, schedule, and send email campaigns
- **Contact Management**: Import from Excel, segmentation, consent tracking
- **AI Content Generation**: Generate email/blog content using Tavily + Claude
- **Gmail SMTP**: Send emails via Gmail (500/day free, 2000/day Workspace)

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Gmail account with App Password

### 2. Setup

```bash
# Clone and enter directory
cd email_marketing

# Copy environment file
cp .env.example .env

# Edit .env with your credentials (see below)

# Start services
docker-compose up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# Access API docs
open http://localhost:8000/docs
```

### 3. Configure Credentials

Edit `.env` file with your credentials:

```env
# Gmail SMTP (Required)
SMTP_USER=info@himalayanfibre.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx  # Gmail App Password

# AI Content Generation (Optional)
TAVILY_API_KEY=tvly-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Wix Webhooks (Required for automation)
WIX_WEBHOOK_PUBLIC_KEY=your-key
```

## Getting Your Credentials

### Gmail App Password

1. Go to https://myaccount.google.com/security
2. Enable 2-Factor Authentication
3. Search "App passwords" in account settings
4. Generate new app password for "Mail"
5. Copy the 16-character password

### Wix Webhook Setup

1. Go to https://dev.wix.com/
2. Create a new app or select existing
3. Go to Webhooks section
4. Subscribe to events:
   - `wix.ecom.v1.order_created`
   - `wix.ecom.v1.cart_abandoned`
5. Set webhook URL: `https://your-domain/api/v1/webhooks/wix/order-created`
6. Copy the Public Key for JWT verification

### Tavily API Key (for AI content)

1. Go to https://tavily.com/
2. Sign up for free account
3. Copy your API key

### Anthropic API Key (for AI content)

1. Go to https://console.anthropic.com/
2. Create an API key
3. Copy the key

## Project Structure

```
email_marketing/
├── app/
│   ├── api/routes/          # API endpoints
│   │   ├── webhooks.py      # Wix webhook handlers
│   │   ├── contacts.py      # Contact CRUD + import
│   │   ├── templates.py     # Email template management
│   │   ├── campaigns.py     # Campaign management
│   │   ├── segments.py      # Contact segmentation
│   │   └── content.py       # AI content generation
│   ├── core/
│   │   ├── config.py        # Settings from .env
│   │   └── logging.py       # Structured logging
│   ├── db/
│   │   ├── models.py        # SQLAlchemy models
│   │   └── session.py       # Database connection
│   ├── services/
│   │   ├── email_service.py      # Gmail SMTP sender
│   │   ├── email_renderer.py     # Jinja2 template rendering
│   │   ├── segmentation.py       # Segment query builder
│   │   ├── contact_importer.py   # Excel import
│   │   └── content_generator.py  # AI content (Tavily + Claude)
│   └── workers/
│       ├── celery_app.py    # Celery configuration
│       └── tasks.py         # Background tasks
├── templates/               # PUT YOUR HTML TEMPLATES HERE
│   ├── transactional/       # welcome.html, order_confirmation.html, etc.
│   ├── abandoned/           # cart_abandoned_1h.html, _24h.html, _72h.html
│   ├── nurture/
│   │   ├── educational_series/
│   │   └── product_updates/
│   ├── campaigns/           # B2B templates
│   └── re_engagement/       # win-back emails
├── alembic/                 # Database migrations
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── main.py
```

## API Endpoints

### Webhooks
- `POST /api/v1/webhooks/wix/order-created` - Handle new orders
- `POST /api/v1/webhooks/wix/cart-abandoned` - Handle abandoned carts
- `GET /api/v1/webhooks/health` - Webhook health check

### Contacts
- `GET /api/v1/contacts` - List contacts (with filtering)
- `POST /api/v1/contacts` - Create contact
- `POST /api/v1/contacts/import/excel` - Import from Excel
- `GET /api/v1/contacts/stats/overview` - Contact statistics

### Templates
- `GET /api/v1/templates` - List templates
- `POST /api/v1/templates` - Create template
- `POST /api/v1/templates/import/html` - Import HTML template
- `POST /api/v1/templates/{id}/preview` - Preview with variables

### Campaigns
- `GET /api/v1/campaigns` - List campaigns
- `POST /api/v1/campaigns` - Create campaign
- `POST /api/v1/campaigns/{id}/approve` - Approve campaign
- `POST /api/v1/campaigns/{id}/send-now` - Send immediately

### Segments
- `GET /api/v1/segments` - List segments
- `POST /api/v1/segments` - Create segment
- `POST /api/v1/segments/create-defaults` - Create default segments
- `GET /api/v1/segments/{id}/contacts` - Preview segment contacts

### Content Generation
- `POST /api/v1/content/generate/email` - Generate email with AI
- `POST /api/v1/content/generate/blog` - Generate blog with AI
- `GET /api/v1/content/drafts` - List generated drafts
- `POST /api/v1/content/drafts/{id}/review` - Approve/reject draft

## Template Variables

When creating/importing templates, use these variables:

### Contact Variables
- `{{first_name}}` - Contact's first name
- `{{last_name}}` - Contact's last name
- `{{email}}` - Contact's email
- `{{company}}` - Company name

### Order Variables
- `{{order_id}}` - Wix order ID
- `{{order_total}}` - Order total with currency
- `{{items}}` - Array of order items

### Cart Variables
- `{{cart_total}}` - Cart total
- `{{checkout_url}}` - Return to checkout link

### System Variables
- `{{unsubscribe_url}}` - Unsubscribe link (required for campaigns)
- `{{company_name}}` - "Himalayan Fibers"

## Where to Put Your CloudHQ Templates

Export your CloudHQ templates as HTML and place them in:

```
templates/
├── transactional/
│   ├── welcome.html              # After first purchase
│   ├── order_confirmation.html   # Order placed
│   ├── shipping_update.html      # Order shipped
│   └── thank_you_review.html     # Request review
├── abandoned/
│   ├── cart_abandoned_1h.html    # 1 hour reminder
│   ├── cart_abandoned_24h.html   # 24 hour reminder
│   └── cart_abandoned_72h.html   # Last chance
├── nurture/
│   ├── educational_series/       # Educational emails
│   └── product_updates/          # Product news
├── campaigns/
│   ├── b2b_carpet_exporters.html
│   └── b2b_handicraft.html
└── re_engagement/
    ├── we_miss_you_30d.html
    └── we_miss_you_90d.html
```

Then import via API:
```bash
curl -X POST "http://localhost:8000/api/v1/templates/import/html" \
  -d "name=Welcome Email" \
  -d "slug=welcome" \
  -d "email_type=welcome" \
  -d "subject_template=Welcome to Himalayan Fibers, {{first_name}}!" \
  -d "html_content=$(cat templates/transactional/welcome.html)"
```

## Local Development (Without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (manually or via Docker)
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name redis -p 6379:6379 redis:7

# Run migrations
alembic upgrade head

# Start API
uvicorn main:app --reload

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info

# Start Celery beat (separate terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

## Monitoring

- **API Docs**: http://localhost:8000/docs
- **Flower (Celery)**: http://localhost:5555
- **Health Check**: http://localhost:8000/health

## License

Proprietary - Himalayan Fibers
