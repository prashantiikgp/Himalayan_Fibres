# Plan: Himalayan Fibers Unified Dashboard (Gradio + FastAPI)

## Context

Build a single dashboard on Hugging Face Spaces that unifies **email marketing** and **WhatsApp messaging**. Uses **Gradio** (not Streamlit) because Gradio is built on FastAPI, allowing both the dashboard UI and WhatsApp webhook endpoints on the same port.

The design system is modeled after the Hotel Agent Ops Dashboard (`/home/prashant-agrawal/projects/hotel_agent/frontend/ops/`), which uses YAML-driven theming, HTML-rendered components, and sidebar navigation via `gr.Group` visibility toggling.

## Architecture

```
FastAPI app (port 7860)
├── POST /webhook/whatsapp    ← Meta sends inbound WA messages here
├── GET  /webhook/whatsapp    ← Meta webhook verification
└── Gradio Blocks mounted at "/" ← Dashboard UI
     ├── NavigationEngine (sidebar + page visibility toggling)
     ├── ThemeEngine (YAML → CSS variables → gr.themes.Base)
     └── Pages (each returns {update_fn, outputs})
```

```python
# Core pattern (app.py)
from fastapi import FastAPI
import gradio as gr

fastapi_app = FastAPI()

@fastapi_app.post("/webhook/whatsapp")
async def wa_webhook(request): ...

with gr.Blocks(theme=theme_engine.gradio_theme, css=full_css) as demo:
    # sidebar + pages built by NavigationEngine
    ...

app = gr.mount_gradio_app(fastapi_app, demo, path="/")
```

---

## Design System (Ported from Hotel Agent Ops Dashboard)

### Source Files to Reference

| Pattern | Hotel Agent Source |
|---------|-------------------|
| Navigation engine | `frontend/engines/navigation_engine.py` (580 lines) |
| Nav button component | `frontend/engines/nav_button.py` |
| Theme YAML | `frontend/config/shared/theme/default.yml` (280 lines) |
| Theme engine | `frontend/shared/theme.py` + `theme_css.py` |
| KPI card component | `frontend/components/kpi_card.py` |
| Styled table component | `frontend/components/html_builders.py` |
| Inline style helpers | `frontend/components/styles.py` |
| Chat bubble styles | `frontend/components/styles.py` (chat_bubble_user, chat_bubble_agent) |
| Config loader | `frontend/loader/config_loader.py` (311 lines) |
| Page contract | `frontend/ops/pages/overview.py`, `conversations.py` |
| Sidebar YAML | `frontend/config/ops/sidebar.yml` |

### Key Design Decisions (Matching Hotel Agent)

1. **Sidebar navigation via `gr.Group(visible=bool)` toggling** — not `gr.Tabs`. All pages pre-rendered but hidden. Button click = instant show/hide. Faster UX.
2. **All rich UI rendered as HTML strings** via `gr.HTML()` — KPI cards, tables, chat bubbles, badges, progress bars. Full CSS control.
3. **Theme YAML → CSS variables → inline styles** — single source of truth for colors, fonts, spacing, radii.
4. **`!important` CSS overrides** on Gradio defaults — dark theme, custom scrollbars, sidebar styling.
5. **Page contract: `build(ctx) → {"update_fn": fn, "outputs": [...]}`** — NavigationEngine wires button clicks to data refresh functions.
6. **Lazy theme proxies** (`COLORS.PRIMARY`, `FONTS.MD`, etc.) — avoids circular imports, used in all inline styles.

### Theme (Adapted for Himalayan Fibers)

```yaml
# config/theme/default.yml
theme:
  name: "Himalayan Fibers Dark"

  colors:
    primary:
      base: "#6366f1"       # Indigo (same as Hotel Agent)
      dark: "#4338ca"
      hover: "#4f46e5"
    semantic:
      success: "#22c55e"
      warning: "#f59e0b"
      error: "#ef4444"
    text:
      primary: "#e7eaf3"
      subtle: "#94a3b8"
      muted: "#64748b"
    surface:
      canvas_gradient: "linear-gradient(135deg, #0b1022, #0e132b)"
      card_bg: "#1e293b"
      block_bg: "rgba(15,23,42,.55)"
      input_bg: "rgba(15,23,42,.40)"
    border:
      default: "rgba(255,255,255,.08)"

  font_sizes:
    xs: "10px"
    sm: "11px"
    base: "12px"
    md: "13px"
    kpi: "24px"

  radii:
    sm: "4px"
    card: "8px"
    pill: "10px"
    bubble: "12px"

  spacing:
    cell_sm: "6px 8px"
    card: "12px 16px"
    badge_sm: "2px 8px"
```

### Sidebar CSS (From Hotel Agent navigation_engine.py)

```css
.nav-sidebar {
  background: rgba(15,23,42,.45) !important;
  border: 1px solid rgba(255,255,255,.06) !important;
  border-radius: 12px !important;
  padding: 8px 4px !important;
  min-height: calc(100vh - 110px) !important;
  position: sticky !important;
  top: 8px !important;
}
.nav-sidebar .nav-btn button {
  text-align: left !important; padding: 10px 14px !important;
  border-radius: 8px !important; font-size: 13px !important;
  font-weight: 600 !important; color: #94a3b8 !important;
  background: transparent !important;
  border-left: 3px solid transparent !important;
}
.nav-sidebar .nav-btn-active button {
  background: rgba(99,102,241,.12) !important;
  color: #e7eaf3 !important;
  border-left: 3px solid #6366f1 !important;
}
```

### Component Patterns (HTML Builders)

**KPI Card** (from `frontend/components/kpi_card.py`):
```python
def render_kpi_card(value, label, color="", subtitle=""):
    return (
        f'<div style="background:{COLORS.CARD_BG}; border-radius:10px; '
        f'padding:14px 18px; text-align:center; min-width:100px; flex:1;">'
        f'<div style="font-size:24px; font-weight:700; color:{color};">{value}</div>'
        f'<div style="font-size:11px; color:{COLORS.TEXT_SUBTLE}; '
        f'text-transform:uppercase;">{label}</div>'
        f'</div>'
    )

def render_kpi_row(cards):
    return f'<div style="display:flex; gap:10px; flex-wrap:wrap;">{"".join(...)}</div>'
```

**Chat Bubbles** (from `frontend/components/styles.py`):
```python
# Inbound (left-aligned) — margin-right pushes left
f'<div style="background:{COLORS.CARD_BG}; border-radius:12px; '
f'padding:10px 14px; margin:4px 40px 4px 0;">...'

# Outbound (right-aligned) — margin-left pushes right
f'<div style="background:{COLORS.PRIMARY_TINT_STRONG}; border-radius:12px; '
f'padding:10px 14px; margin:4px 0 4px 40px;">...'
```

**Styled Table** (from `frontend/components/html_builders.py`):
```python
# Header: indigo tint background, bold, uppercase
# Cells: padding via SPACING.CELL_SM, monospace for IDs
# Badges: inline pill with colored bg
# Wrapped in section_card div with border-radius + card_bg
```

---

## Directory Structure

```
hf_dashboard/
├── app.py                          # FastAPI + Gradio mount + WhatsApp webhooks
├── engines/
│   ├── navigation_engine.py        # Sidebar + page visibility (port of Hotel Agent)
│   ├── nav_button.py               # Nav button component
│   └── theme_engine.py             # YAML → CSS variables → gr.themes.Base
├── pages/
│   ├── home.py                     # Health overview
│   ├── contacts.py                 # Contact database
│   ├── email_campaigns.py          # Email campaign management
│   ├── flows.py                    # Multi-step automations
│   ├── whatsapp.py                 # WA conversations + campaigns
│   └── templates_media.py          # Templates + product images
├── components/
│   ├── kpi_card.py                 # KPI card HTML builder
│   ├── styled_table.py            # Table with styled cells
│   ├── chat_bubbles.py             # Chat bubble HTML builder
│   ├── badges.py                   # Status/pill badge builder
│   ├── styles.py                   # Inline style helper functions
│   ├── section_card.py             # Section card wrapper
│   └── empty_state.py              # Empty state placeholder
├── services/
│   ├── __init__.py
│   ├── config.py                   # Pydantic settings (SMTP + WA)
│   ├── database.py                 # SQLite engine + session + CSV seeder
│   ├── models.py                   # SQLAlchemy models (SQLite-adapted)
│   ├── email_sender.py             # Sync SMTP (port of app/email_sender.py)
│   ├── email_renderer.py           # Jinja2 rendering (port of app/services/email_renderer.py)
│   ├── wa_sender.py                # Sync WhatsApp Cloud API (port of app/whatsapp/service.py)
│   ├── wa_config.py                # WA YAML config loader (port of app/whatsapp/config.py)
│   ├── wa_webhook.py               # Inbound WA message processing (port of app/whatsapp/webhook.py)
│   └── flows_engine.py             # Flow definitions + execution
├── loader/
│   └── config_loader.py            # YAML config loader (port of Hotel Agent pattern)
├── config/
│   ├── theme/
│   │   └── default.yml             # Theme colors, fonts, spacing, radii
│   ├── dashboard/
│   │   ├── sidebar.yml             # Navigation items
│   │   └── dashboard.yml           # Default page, title
│   └── whatsapp/
│       ├── settings.yml            # WA API config (copied from email_marketing)
│       ├── templates.yml           # WA template registry (copied)
│       └── messages.yml            # Quick replies (copied)
├── templates/                      # Email HTML templates (copied)
├── data/                           # CSV files for initial seeding
├── media/                          # Product images (uploaded via dashboard)
├── Dockerfile
├── requirements.txt
├── README.md                       # HF Spaces card
└── shared/
    ├── theme.py                    # Lazy theme proxies (COLORS, FONTS, etc.)
    └── theme_css.py                # Global CSS overrides
```

---

## Implementation Steps

### Step 1: Theme + Config + Loader Layer

**Port from Hotel Agent:**
- `config/theme/default.yml` — adapt colors for Himalayan Fibers branding
- `engines/theme_engine.py` — port `ThemeEngine` from `frontend/shared/theme.py` + `frontend/sim_lab/engines/theme_engine.py`
- `shared/theme.py` — lazy proxies (COLORS, FONTS, SPACING, RADII)
- `shared/theme_css.py` — global CSS overrides (dark mode, scrollbars, footer hide)
- `loader/config_loader.py` — port from `frontend/loader/config_loader.py`, simplified for single audience

**Config files to create:**
- `config/dashboard/sidebar.yml` — 6 nav items (Home, Contacts, Email, Flows, WhatsApp, Templates)
- `config/dashboard/dashboard.yml` — default_page: "home", title: "Himalayan Fibers"

### Step 2: Navigation Engine + Components

**Port from Hotel Agent:**
- `engines/navigation_engine.py` — port `build_app_with_sidebar()` from `frontend/engines/navigation_engine.py`
  - Sidebar with `gr.Column(scale=0, min_width=200, elem_classes=["nav-sidebar"])`
  - Content area with `gr.Column(scale=5, elem_classes=["content-area"])`
  - `gr.Group(visible=bool)` per page, toggled on button click
  - Button click handler returns visibility updates + button style updates + page data
- `engines/nav_button.py` — port from `frontend/engines/nav_button.py`
  - `create_nav_button(item, is_active)` → `gr.Button` with ACTIVE/INACTIVE classes

**Components to port:**
- `components/kpi_card.py` — from `frontend/components/kpi_card.py`
- `components/styled_table.py` — from `frontend/components/html_builders.py` (render_table_with_styled_cells, cell builders)
- `components/styles.py` — from `frontend/components/styles.py` (inline style functions)
- `components/chat_bubbles.py` — from `frontend/components/styles.py` (chat_bubble_user, chat_bubble_agent)
- `components/badges.py` — status pill badges (pass/fail/sent/draft/etc.)
- `components/section_card.py` — card wrapper with optional accent border
- `components/empty_state.py` — empty state placeholder

### Step 3: Database + Services Layer

**`services/models.py`** — adapted from `app/db/models.py` + `app/whatsapp/models.py`
- Replace JSONB → JSONType(TypeDecorator)
- Models: Contact, Segment, EmailTemplate, Campaign, EmailSend, Flow, FlowRun, WAChat, WAMessage, WATemplate, ProductMedia
- Python-side defaults instead of server_default

**`services/database.py`** — SQLite engine + CSV seeder
- `seed_from_csv()` loads 948 contacts + 12 segments
- `seed_default_flows()` creates pre-defined flows
- WAL journal mode, `check_same_thread=False`, `busy_timeout=5000`

**`services/email_sender.py`** — near-direct port of `app/email_sender.py` (already sync smtplib)

**`services/email_renderer.py`** — direct port of `app/services/email_renderer.py` (pure Jinja2)

**`services/wa_sender.py`** — sync port of `app/whatsapp/service.py` (httpx.AsyncClient → httpx.Client)

**`services/wa_webhook.py`** — port inbound message processing from `app/whatsapp/webhook.py`
- Signature verification, contact creation, message storage, chat state updates

**`services/flows_engine.py`** — flow definitions + step execution + pending step checker

### Step 4: FastAPI Webhook Endpoints (in app.py)

```python
@fastapi_app.post("/webhook/whatsapp")
async def wa_webhook(request: Request):
    # Port from app/whatsapp/webhook.py
    # Signature verification → parse payload → store messages → update contacts

@fastapi_app.get("/webhook/whatsapp")
async def wa_verify(request: Request):
    # Meta handshake verification
```

### Step 5: Auth Gate

- Simple password check via `APP_PASSWORD` env var
- On app load, if not authenticated → show login form, hide dashboard
- Store auth state in `gr.State`

### Step 6: Page — Home (pages/home.py)

Each page follows the Hotel Agent contract:
```python
def build(ctx) -> dict:
    # Create gr.HTML output components
    kpis_html = gr.HTML(value="")
    activity_html = gr.HTML(value="")

    def _refresh():
        # Query DB, build HTML strings
        kpis = render_kpi_row([...])
        activity = _build_activity_log()
        return (kpis, activity)

    return {"update_fn": _refresh, "outputs": [kpis_html, activity_html]}
```

**Layout within page (two-column via `gr.Row`):**
- Left `gr.Column(scale=1)`: Quick actions (Test SMTP, Test WA buttons), connection status, key metrics
- Right `gr.Column(scale=3)`: Recent activity log, system overview

**Also calls `check_pending_flow_steps()` on load for automation.**

### Step 7: Page — Contacts (pages/contacts.py)

- Left col: `gr.Dropdown` filters (consent, type, country, segment) + KPI cards (total, opted-in, WA-reachable)
- Right col: Contact table (`gr.HTML` styled table), action buttons (opt-in/opt-out), import section (`gr.File` + preview)
- Dropdown `.change()` events wired to filter + re-render table

### Step 8: Page — Email Campaigns (pages/email_campaigns.py)

- Left col: Status/segment filters + KPI cards (campaigns, daily limit)
- Right col: Campaign list table, create form (`gr.Textbox` for name/subject, `gr.Dropdown` for template/segment), send section with `gr.HTML` progress rendering
- **Idempotency**: Port `generate_idempotency_key()` from `app/workers/tasks.py`
- **Confirmation**: Two-step send — button click shows recipient count warning, checkbox confirmation required
- **Send loop**: Synchronous with periodic `gr.HTML` updates showing progress

### Step 9: Page — Flows (pages/flows.py)

- Left col: Flow selector, channel filter, start flow form (segment dropdown, date picker) + KPI cards
- Right col: Flow step visualization (HTML with step cards + arrows), active flow runs table

### Step 10: Page — WhatsApp (pages/whatsapp.py)

- Left col: Chat list (HTML with contact names, last message, unread badge), quick template send dropdown + KPI cards
- Right col: Conversation view (chat bubbles via `components/chat_bubbles.py` in scrollable div), reply input (`gr.Textbox` + `gr.Button`), image upload (`gr.File`), WA bulk campaign section
- **24h window**: Show warning if outside messaging window, suggest template send

### Step 11: Page — Templates & Media (pages/templates_media.py)

- Left col: Channel toggle (radio), template selector, upload buttons + info cards
- Right col: Three sections toggled by radio:
  - Email: HTML preview via `gr.HTML()`, variable list
  - WhatsApp: Template list with status badges, variable schema
  - Media: Image gallery (`gr.HTML` grid), upload (`gr.File`), send-to-contact form

### Step 12: Deployment

**`Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/media
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
```

**`requirements.txt`:**
```
gradio>=4.44.0
fastapi>=0.109.0
uvicorn>=0.27.0
sqlalchemy>=2.0.25
pandas>=2.2.0
openpyxl>=3.1.2
jinja2>=3.1.3
httpx>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.1.0
pyyaml>=6.0.1
Pillow>=10.2.0
email-validator>=2.1.0
python-dateutil>=2.8.2
```

**`README.md`:** HF Spaces card (sdk: docker)

---

## Gaps Addressed from Review

| Gap | Fix |
|-----|-----|
| WA inbound messages (Critical #1) | FastAPI webhook endpoints via `mount_gradio_app` |
| Flow automation timing (Critical #2) | Background thread checking every 30 min |
| Duplicate send protection (Critical #3) | Port `generate_idempotency_key()` + UNIQUE constraint |
| Phone normalization (High #4) | Normalize + set wa_id during CSV seeding |
| Unsubscribe (High #5) | mailto: link in templates for v1 |
| Confirmation before send (High #6) | Two-step: warning + checkbox |
| CSV field mapping (High #7) | Explicit mapping in seed_from_csv() |
| WA token expiry (High #8) | Health check warning on Home page |

## Secrets (HF Spaces Environment Variables)

- `SMTP_USER`, `SMTP_PASSWORD` — Gmail
- `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_WABA_ID`, `WA_APP_SECRET` — Meta WhatsApp
- `APP_PASSWORD` — Dashboard login

## Testing

1. Local: `cd hf_dashboard && uvicorn app:app --port 7860` — verify all 6 pages
2. Email: Test SMTP + send test email
3. WhatsApp: Test WA API + send hello_world template
4. Webhook: `curl -X POST localhost:7860/webhook/whatsapp` with test payload
5. Campaign: Small segment send with progress + idempotency check
6. Deploy: Push to HF Spaces, set secrets, verify
