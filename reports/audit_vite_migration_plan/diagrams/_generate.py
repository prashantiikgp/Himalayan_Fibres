"""Generate .excalidraw diagram files for the vite_dashboard architecture.

Produces 7 files in this directory:
  architecture.excalidraw    - full-app data flow (configs -> loaders -> engines -> components)
  page_home.excalidraw       - Home page layout
  page_contacts.excalidraw   - Contacts page (filter + table + drawer)
  page_wa_inbox.excalidraw   - WhatsApp Inbox 3-panel
  page_broadcasts.excalidraw - Broadcasts (3 tabs)
  page_wa_templates.excalidraw - Template Studio (list + editor + preview)
  page_flows.excalidraw      - Flows page

Run: python _generate.py
"""

import json
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

# Excalidraw colors (matching the official palette)
C_BLUE = "#a5d8ff"        # configs
C_ORANGE = "#ffd8a8"      # loaders
C_VIOLET = "#d0bfff"      # engines
C_GREEN = "#b2f2bb"       # components / pages
C_PINK = "#ffc9c9"        # backend / api
C_YELLOW = "#ffec99"      # notes / annotations
C_GRAY = "#e9ecef"        # neutral
C_STROKE = "#1e1e1e"
C_STROKE_LIGHT = "#868e96"

_id_counter = [0]
_seed_counter = [1]
_now = int(time.time() * 1000)


def _next_id() -> str:
    _id_counter[0] += 1
    return f"el{_id_counter[0]}"


def _next_seed() -> int:
    _seed_counter[0] += 1
    return _seed_counter[0]


def rect(x, y, w, h, *, fill=C_GRAY, stroke=C_STROKE, stroke_width=2,
         roundness=True, opacity=100):
    return {
        "id": _next_id(),
        "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": stroke, "backgroundColor": fill,
        "fillStyle": "solid", "strokeWidth": stroke_width,
        "strokeStyle": "solid", "roughness": 1, "opacity": opacity,
        "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if roundness else None,
        "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
        "isDeleted": False, "boundElements": [],
        "updated": _now, "link": None, "locked": False,
    }


def text(x, y, w, h, content, *, size=18, color=C_STROKE, align="center",
         valign="middle", bold=False):
    # fontFamily: 1=Virgil (handwriting), 2=Helvetica, 3=Cascadia (mono), 5=Excalifont
    family = 5 if bold else 2
    return {
        "id": _next_id(),
        "type": "text",
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
        "isDeleted": False, "boundElements": [],
        "updated": _now, "link": None, "locked": False,
        "fontSize": size, "fontFamily": family,
        "text": content, "textAlign": align, "verticalAlign": valign,
        "containerId": None, "originalText": content, "lineHeight": 1.25,
        "baseline": int(size * 0.85),
    }


def labeled_rect(x, y, w, h, label, *, fill=C_GRAY, stroke=C_STROKE, size=16, bold=False):
    """A box with a centered text label."""
    return [
        rect(x, y, w, h, fill=fill, stroke=stroke),
        text(x, y, w, h, label, size=size, align="center", valign="middle", bold=bold),
    ]


def arrow(x1, y1, x2, y2, *, color=C_STROKE, stroke_width=2, dashed=False):
    return {
        "id": _next_id(),
        "type": "arrow",
        "x": x1, "y": y1,
        "width": abs(x2 - x1), "height": abs(y2 - y1),
        "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": stroke_width,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None,
        "roundness": {"type": 2},
        "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
        "isDeleted": False, "boundElements": [],
        "updated": _now, "link": None, "locked": False,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    }


def write_excalidraw(filename: str, elements: list, *, bg="#ffffff"):
    payload = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": bg},
        "files": {},
    }
    out_path = OUT_DIR / filename
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out_path.relative_to(OUT_DIR.parent)}")


def reset_counters():
    """Reset per-file id counters so each file gets stable ids."""
    _id_counter[0] = 0
    _seed_counter[0] = 1


# ═══════════════════════════════════════════════════════════════════════════
# 1. Architecture diagram
# ═══════════════════════════════════════════════════════════════════════════

def gen_architecture():
    reset_counters()
    elems = []

    # Title
    elems.append(text(80, 30, 1500, 40,
                      "Himalayan Fibres - vite_dashboard Architecture",
                      size=32, align="left", bold=True))
    elems.append(text(80, 78, 1500, 24,
                      "YAML configs flow through Zod-validated loaders and engines into typed React components",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Lane headers
    lane_y = 130
    elems.append(text(80, lane_y, 280, 30, "YAML CONFIGS", size=18, bold=True, align="center"))
    elems.append(text(440, lane_y, 280, 30, "LOADERS", size=18, bold=True, align="center"))
    elems.append(text(800, lane_y, 280, 30, "ENGINES", size=18, bold=True, align="center"))
    elems.append(text(1160, lane_y, 360, 30, "COMPONENTS / PAGES", size=18, bold=True, align="center"))

    # Row 1 - Theme
    y = 180
    elems += labeled_rect(80, y, 280, 80,
                          "config/theme/\n  default.yml\n  components.yml",
                          fill=C_BLUE, size=14)
    elems += labeled_rect(440, y, 280, 80,
                          "configLoader.bootstrap()\n(singleton, lazy, Zod-validated)",
                          fill=C_ORANGE, size=14)
    elems += labeled_rect(800, y, 280, 80,
                          "themeEngine\nemits :root CSS vars\n-> Tailwind extends",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 80,
                          "<AppShell> + globals.css\nTailwind utilities resolve to YAML colors",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 40, 440, y + 40))
    elems.append(arrow(720, y + 40, 800, y + 40))
    elems.append(arrow(1080, y + 40, 1160, y + 40))

    # Row 2 - Sidebar / Dashboard
    y = 290
    elems += labeled_rect(80, y, 280, 80,
                          "config/dashboard/\n  sidebar.yml\n  dashboard.yml",
                          fill=C_BLUE, size=14)
    elems += labeled_rect(800, y, 280, 80,
                          "navigationEngine\n-> React Router routes\n+ <NavSidebar> tree",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 80,
                          "<NavSidebar> + <NavGroup>\nRoute /home, /contacts, /wa-inbox, ...",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 40, 800, y + 40))
    elems.append(arrow(1080, y + 40, 1160, y + 40))

    # Row 3 - Per-page
    y = 400
    elems += labeled_rect(80, y, 280, 90,
                          "config/pages/\n  home.yml\n  contacts.yml\n  wa_inbox.yml\n  ...",
                          fill=C_BLUE, size=13)
    elems += labeled_rect(440, y, 280, 90,
                          "usePageConfig(pageId)\nhook -> typed page config",
                          fill=C_ORANGE, size=14)
    elems += labeled_rect(800, y, 280, 90,
                          "pageEngine\nlayout descriptor\n+ page-scoped CSS vars",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 90,
                          "<HomePage> / <ContactsPage> / ...\n<PageContainer> + *.module.css",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 45, 440, y + 45))
    elems.append(arrow(720, y + 45, 800, y + 45))
    elems.append(arrow(1080, y + 45, 1160, y + 45))

    # Row 4 - Shared (KPI, status, filters)
    y = 520
    elems += labeled_rect(80, y, 280, 90,
                          "config/shared/\n  kpi.yml\n  status_badges.yml\n  filters.yml",
                          fill=C_BLUE, size=13)
    elems += labeled_rect(800, y, 280, 90,
                          "kpiEngine\nstatusEngine\nfilterEngine",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 90,
                          "<KpiRow>, <StatusBadge>,\n<FilterBar>, <DataTable>",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 45, 800, y + 45))
    elems.append(arrow(1080, y + 45, 1160, y + 45))

    # Row 5 - Backend integration (api_v2)
    y = 660
    elems.append(text(80, y - 25, 1440, 24,
                      "-- BACKEND -------------------------------------------------------------",
                      size=12, color=C_STROKE_LIGHT, align="left"))
    elems += labeled_rect(80, y, 280, 80,
                          "api_v2/routers/*.py\n(FastAPI + Pydantic)",
                          fill=C_PINK, size=14)
    elems += labeled_rect(440, y, 280, 80,
                          "/openapi.json\n-> openapi-typescript",
                          fill=C_ORANGE, size=14)
    elems += labeled_rect(800, y, 280, 80,
                          "src/api/schema.d.ts\n(auto-generated)",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 80,
                          "src/api/contacts.ts, waInbox.ts, ...\n(typed fetchers)",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 40, 440, y + 40))
    elems.append(arrow(720, y + 40, 800, y + 40))
    elems.append(arrow(1080, y + 40, 1160, y + 40))

    # Row 6 - Domain configs (shared between v1 + v2)
    y = 770
    elems += labeled_rect(80, y, 280, 80,
                          "config/dashboard/  <- shared\n  whatsapp/, email/, contacts/",
                          fill=C_BLUE, size=13)
    elems += labeled_rect(440, y, 280, 80,
                          "Vite alias @domain\n-> ../../config/dashboard/",
                          fill=C_ORANGE, size=14)
    elems += labeled_rect(800, y, 280, 80,
                          "schemas/domain.ts\n(Zod validates at boot)",
                          fill=C_VIOLET, size=14)
    elems += labeled_rect(1160, y, 360, 80,
                          "Pages import templates,\npricing, segments directly",
                          fill=C_GREEN, size=14)
    elems.append(arrow(360, y + 40, 440, y + 40))
    elems.append(arrow(720, y + 40, 800, y + 40))
    elems.append(arrow(1080, y + 40, 1160, y + 40))

    # Notes
    y = 880
    elems.append(text(80, y, 1440, 22,
                      "*  Zod schemas validate every YAML at boot - typos throw a fatal error, never silent fallback",
                      size=14, color=C_STROKE, align="left"))
    elems.append(text(80, y + 26, 1440, 22,
                      "*  Vite plugin imports YAML at build time - fast startup, HMR on edit",
                      size=14, color=C_STROKE, align="left"))
    elems.append(text(80, y + 52, 1440, 22,
                      "*  Page CSS vars are scoped to .<page-name>-page root - no cross-page bleed",
                      size=14, color=C_STROKE, align="left"))
    elems.append(text(80, y + 78, 1440, 22,
                      "*  Domain configs (templates, pricing) live in shared config/dashboard/ - single source of truth for v1 + v2",
                      size=14, color=C_STROKE, align="left"))

    write_excalidraw("architecture.excalidraw", elems)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Per-page diagrams
# ═══════════════════════════════════════════════════════════════════════════

def gen_home():
    reset_counters()
    elems = []

    # Title
    elems.append(text(80, 30, 1200, 36,
                      "Home page  /home", size=28, align="left", bold=True))
    elems.append(text(80, 75, 1200, 22,
                      "config/pages/home.yml drives section visibility, KPI list, lifecycle stages",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # AppShell sidebar
    elems += labeled_rect(80, 130, 200, 700, "<NavSidebar>\n(global)", fill=C_GREEN, size=14)

    # Status strip
    elems += labeled_rect(310, 130, 990, 60,
                          "<StatusStrip>  Email: OK  -  WhatsApp: OK",
                          fill=C_YELLOW, size=14)

    # KPI Row 1
    elems += labeled_rect(310, 210, 240, 100, "Emails Today\n12 / 500", fill=C_GREEN, size=14)
    elems += labeled_rect(560, 210, 240, 100, "WA Today\n45 / 1000", fill=C_GREEN, size=14)
    elems += labeled_rect(810, 210, 240, 100, "Contacts\n347", fill=C_GREEN, size=14)
    elems += labeled_rect(1060, 210, 240, 100, "24h Window\n12 open", fill=C_GREEN, size=14)

    # KPI Row 2
    elems += labeled_rect(310, 320, 196, 90, "Opted In\n284", fill=C_GREEN, size=14)
    elems += labeled_rect(516, 320, 196, 90, "Pending\n63", fill=C_GREEN, size=14)
    elems += labeled_rect(722, 320, 196, 90, "WA Ready\n289", fill=C_GREEN, size=14)
    elems += labeled_rect(928, 320, 196, 90, "Email Camps\n14", fill=C_GREEN, size=14)
    elems += labeled_rect(1134, 320, 166, 90, "WA Camps\n8", fill=C_GREEN, size=14)

    # Lifecycle bars card
    elems += labeled_rect(310, 420, 600, 220,
                          "<LifecycleBars>\n\n  -  New Lead       [====      ]  45\n"
                          "  -  Engaged Lead   [======    ]  82\n"
                          "  -  Customer       [===       ]  19\n"
                          "  -  Repeat         [=         ]   8",
                          fill=C_GREEN, size=14, bold=False)

    # Activity feed
    elems += labeled_rect(920, 420, 380, 410,
                          "<ActivityFeed>\n\n  10:42  out  Email to raj@...\n"
                          "  10:38  in   WA from Priya: Hi! ...\n"
                          "  10:30  out  WA to Anil: order_...\n"
                          "  10:22  out  Email to neha@...\n"
                          "  09:58  in   WA from ...",
                          fill=C_GREEN, size=14, bold=False)

    # Side panel (getting started + system)
    elems += labeled_rect(310, 650, 600, 180,
                          "Getting Started + System\n(KPI counts, daily limits)\nReads from /api/v2/dashboard/home",
                          fill=C_GRAY, size=14)

    # Footer note
    elems += labeled_rect(80, 850, 1220, 60,
                          "Components: <KpiRow> <KpiCard> (global)  +  <LifecycleBars> <ActivityFeed> <StatusStrip> (page-specific in pages/home/components/)",
                          fill=C_YELLOW, size=13)

    write_excalidraw("page_home.excalidraw", elems)


def gen_contacts():
    reset_counters()
    elems = []

    elems.append(text(80, 30, 1200, 36, "Contacts page  /contacts",
                      size=28, align="left", bold=True))
    elems.append(text(80, 75, 1200, 22,
                      "URL state: ?segment=...&lifecycle=...&channel=...&page=2&search=raj",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Sidebar (global)
    elems += labeled_rect(80, 130, 200, 720, "<NavSidebar>\n(global)", fill=C_GREEN, size=14)

    # Filter sidebar (page)
    elems += labeled_rect(310, 130, 240, 720,
                          "<FilterBar>\n\n  Segment    [v]\n  Lifecycle  [v]\n  Country    [v]\n"
                          "  Channel    [v]\n  Tags       [v] (multi)",
                          fill=C_GREEN, size=14, bold=False)

    # Top bar
    elems += labeled_rect(580, 130, 720, 60,
                          "Search...                      [+ Add]   [Import]",
                          fill=C_YELLOW, size=14)

    # Table header
    elems += labeled_rect(580, 210, 720, 40,
                          "Name | Company | Channels | Lifecycle | Email | Phone | Segments | Tags | Edit",
                          fill=C_GRAY, size=12)

    # Table rows
    for i, name in enumerate(["Raj K  -  Acme Yarns", "Priya M  -  Mountain Mills", "Anil S  -  Carpet Co", "Neha P  -  ..."]):
        y = 260 + i * 50
        elems += labeled_rect(580, y, 720, 44, name, fill="#ffffff", size=13)

    # Pagination
    elems += labeled_rect(580, 470, 720, 50, "[<]  Page 2 of 7  [>]    Showing 51-100 of 347",
                          fill=C_GRAY, size=13)

    # Drawer (slides in from right)
    elems += labeled_rect(900, 540, 400, 320,
                          "<ContactDrawer>\n(opens on row click)\n\n[Profile] [Tags] [Notes] [Activity]\n\n"
                          "First name, Last name, Phone, Email,\nCompany, Country, Lifecycle, Consent\n\n[Cancel] [Save changes]",
                          fill=C_BLUE, size=13)
    elems.append(arrow(740, 280, 900, 540, color=C_STROKE_LIGHT, dashed=True))

    # Footer note
    elems += labeled_rect(80, 880, 1220, 50,
                          "Endpoints: GET /api/v2/contacts (paginated)  +  GET/PATCH/POST /api/v2/contacts/{id}  +  POST /api/v2/contacts/import  +  GET /api/v2/contacts.csv",
                          fill=C_YELLOW, size=12)

    write_excalidraw("page_contacts.excalidraw", elems)


def gen_wa_inbox():
    reset_counters()
    elems = []

    elems.append(text(80, 30, 1400, 36,
                      "WhatsApp Inbox  /wa-inbox/:contactId",
                      size=28, align="left", bold=True))
    elems.append(text(80, 75, 1400, 22,
                      "3-panel layout. SSE stream pushes inbound messages without page reload.",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Sidebar (global)
    elems += labeled_rect(80, 130, 180, 720, "<NavSidebar>\n(global)", fill=C_GREEN, size=14)

    # Panel 1 - Conversations
    elems += labeled_rect(290, 130, 280, 720,
                          "<ConversationList>\n\n  Search active...\n\n"
                          "  ( ) Raj K  -  Acme\n      order_confirm... 10:42\n\n"
                          "  (*) Priya M  -  Mountain  (3)\n      Hi! Are you ... 10:38\n\n"
                          "  ( ) Anil S  -  Carpet Co\n      Sample req... 09:58\n\n"
                          "  ---  Start New  ---\n  Search contact...",
                          fill=C_GREEN, size=13, bold=False)

    # Panel 2 - Chat
    elems += labeled_rect(600, 130, 480, 720,
                          "<ChatPanel>",
                          fill=C_GREEN, size=14, bold=True)
    # Chat header
    elems += labeled_rect(620, 150, 440, 60,
                          "Priya M  |  +91 98765 43210  |  [open] 23h left",
                          fill="#ffffff", size=13)
    # Messages area
    elems += labeled_rect(620, 220, 440, 480,
                          "<ChatMessages>\n\n   out: Hi! This is HF\n              10:41\n\n"
                          "   in:  Hey! Are you still ...\n              10:42\n\n"
                          "   out: Thanks! Yes - tap below ...\n              10:43",
                          fill="#ffffff", size=13, bold=False)
    # Composer
    elems += labeled_rect(620, 710, 440, 60,
                          "<ChatComposer>\n[Type a message...]   [attach]   [Send]",
                          fill="#ffffff", size=13)

    # Panel 3 - Tools / Template Sheet
    elems += labeled_rect(1110, 130, 410, 720,
                          "<TemplateSheet>\n(opens from 'Send template' button)\n\n"
                          "  Category [v]   Template [v]\n\n"
                          "  --  Variables  --\n"
                          "  customer_name   [Priya M     ]\n"
                          "  order_id        [HF-2026-0042]\n"
                          "  product_names   [Nettle Yarn ]\n"
                          "  amount          [12,500      ]\n\n"
                          "  --  Preview  --\n"
                          "  Hi Priya M,\n  Thank you for your order...\n\n"
                          "  [Send Template]",
                          fill=C_BLUE, size=13, bold=False)

    # B1 fix annotation
    elems += labeled_rect(1110, 870, 410, 50,
                          "B1 fix: variables stack vertically,\nno scroll required - all 4 visible",
                          fill=C_YELLOW, size=12)

    # B2 fix annotation
    elems += labeled_rect(620, 780, 440, 50,
                          "B2 fix: composer DISABLED if 24h window closed,\nshows 'Send template' CTA instead",
                          fill=C_YELLOW, size=12)

    write_excalidraw("page_wa_inbox.excalidraw", elems)


def gen_broadcasts():
    reset_counters()
    elems = []

    elems.append(text(80, 30, 1400, 36,
                      "Broadcasts  /broadcasts (Compose / History / Performance)",
                      size=28, align="left", bold=True))
    elems.append(text(80, 75, 1400, 22,
                      "Merges 4 v1 pages into 1. Email sends queue via BackgroundTasks.",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Sidebar
    elems += labeled_rect(80, 130, 180, 720, "<NavSidebar>", fill=C_GREEN, size=14)

    # Tabs
    elems += labeled_rect(290, 130, 1230, 60,
                          "  [ Compose ]   History   Performance       Channel: (*) WA  ( ) Email",
                          fill=C_YELLOW, size=14)

    # Sticky audience header (B3 fix)
    elems += labeled_rect(290, 210, 1230, 60,
                          "Targeting 245 people in 'Engaged Domestic B2B'  -  Reach 87% of segment",
                          fill=C_PINK, size=14, bold=True)

    # Left - RecipientPicker + AudienceFunnel
    elems += labeled_rect(290, 290, 380, 540,
                          "<RecipientPicker>\n\n  Segment           [v]\n  Countries (multi) [v]\n  Lifecycle (multi) [v]\n"
                          "  Consent (multi)   [v]\n  Tags (multi)      [v]\n  Max recipients [____]\n\n"
                          "  --  <AudienceFunnel>  --\n  Segment: 312  ->  Eligible: 287  ->  Final: 245\n\n"
                          "  Geography breakdown\n  Lifecycle breakdown",
                          fill=C_GREEN, size=13, bold=False)

    # Center - TemplateEditor
    elems += labeled_rect(700, 290, 460, 540,
                          "<TemplateEditor>\n\n  Template [v] (MARKETING only)\n\n  Subject: ...\n\n"
                          "  --  Variables  --\n  customer_name [____]\n  ...\n\n  --  <CostEstimate>  --\n"
                          "  Recipients  +  Per msg  +  Total  +  Delivery",
                          fill=C_GREEN, size=13, bold=False)

    # Right - Preview
    elems += labeled_rect(1190, 290, 330, 540,
                          "<EmailPreview> / <WaPreview>\n(iframe srcdoc / phone mockup)\n\n"
                          "  [Desktop] [Mobile]",
                          fill=C_GREEN, size=13, bold=False)

    # Action bar
    elems += labeled_rect(290, 850, 1230, 60,
                          "[Test (1 message)]    [Schedule...]    [Send Now] -> Confirm dialog (B10)",
                          fill=C_YELLOW, size=14)

    write_excalidraw("page_broadcasts.excalidraw", elems)


def gen_wa_templates():
    reset_counters()
    elems = []

    elems.append(text(80, 30, 1400, 36,
                      "WA Template Studio  /wa-templates",
                      size=28, align="left", bold=True))
    elems.append(text(80, 75, 1400, 22,
                      "Author + submit + sync WhatsApp templates against Meta WABA API",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Sidebar
    elems += labeled_rect(80, 130, 180, 720, "<NavSidebar>", fill=C_GREEN, size=14)

    # Left - list
    elems += labeled_rect(290, 130, 320, 720,
                          "<TemplateList>\n\n  [+ New Draft]  [Sync from Meta]\n\n"
                          "  Status [v]   Tier [v]   Search...\n\n"
                          "  [APPROVED] welcome_message  -  en\n  [APPROVED] order_confirmation  -  en\n"
                          "  [APPROVED] order_tracking  -  en\n  [PENDING ] thank_you_v2  -  en\n"
                          "  [DRAFT   ] snow_white_v3  -  en\n  [REJECTED] catalog_intro  -  en",
                          fill=C_GREEN, size=13, bold=False)

    # Center - editor
    elems += labeled_rect(640, 130, 480, 720,
                          "<TemplateForm>\n\n  Name [order_confirmation]\n"
                          "  Category [UTILITY  v]   Language [en  v]\n\n"
                          "  Header format [TEXT/IMAGE/DOCUMENT/NONE  v]\n"
                          "  Header text/asset URL\n"
                          "  Upload header asset (drag-drop)\n\n"
                          "  Body text\n  [Hi {{customer_name}}, ...]\n\n"
                          "  Footer (optional)\n\n"
                          "  --  <ButtonsEditor>  --\n  Type | Text | URL/Phone\n  ...\n\n"
                          "  [Save Draft]   [Submit to Meta]",
                          fill=C_GREEN, size=13, bold=False)

    # Right - Phone preview
    elems += labeled_rect(1150, 130, 370, 720,
                          "<WaPhonePreview>\n(reuses Phase 2 component)\n\n"
                          "  [Phone mockup with WhatsApp UI]\n  Header bar  -  contact name  -  online\n\n"
                          "  [Bubble showing template]\n  Hi {customer_name},\n  Thank you for your order!\n  Order: {order_id}\n  ...\n\n"
                          "  [Visit website] button",
                          fill=C_GREEN, size=13, bold=False)

    # Annotation
    elems += labeled_rect(640, 870, 480, 50,
                          "Approved templates: save creates _v2 clone\n(clone-on-edit; original stays untouched)",
                          fill=C_YELLOW, size=12)

    write_excalidraw("page_wa_templates.excalidraw", elems)


def gen_flows():
    reset_counters()
    elems = []

    elems.append(text(80, 30, 1200, 36, "Flows  /flows",
                      size=28, align="left", bold=True))
    elems.append(text(80, 75, 1200, 22,
                      "Multi-step automated send sequences. Read-only in v2 (editor deferred).",
                      size=14, align="left", color=C_STROKE_LIGHT))

    # Sidebar
    elems += labeled_rect(80, 130, 200, 700, "<NavSidebar>", fill=C_GREEN, size=14)

    # KPI strip
    elems += labeled_rect(310, 130, 320, 100, "Active\n3", fill=C_GREEN, size=14)
    elems += labeled_rect(650, 130, 320, 100, "Completed\n42", fill=C_GREEN, size=14)
    elems += labeled_rect(990, 130, 310, 100, "Total Flows\n7", fill=C_GREEN, size=14)

    # Left - Flow picker + start
    elems += labeled_rect(310, 250, 350, 580,
                          "Select Flow\n\n  Flow [v]  (welcome_sequence_v2)\n  Channel [v] (Email / WhatsApp)\n\n"
                          "Start Flow\n  Segment [v]\n  Start date [2026-05-04]\n\n  [Start Flow]",
                          fill=C_GREEN, size=14, bold=False)

    # Right - Flow details + runs table
    elems += labeled_rect(680, 250, 620, 280,
                          "<FlowDetails>\n\n  Step 1 (Day 0)  -  welcome\n          |\n          v\n  Step 2 (Day 3)  -  followup_interest\n          |\n          v\n"
                          "  Step 3 (Day 7)  -  catalog_browse",
                          fill=C_GREEN, size=14, bold=False)

    elems += labeled_rect(680, 550, 620, 280,
                          "<FlowRunsTable>\n\n  Flow            Status     Step  Sent  Next\n  welcome_seq    Active     2/3   245   2026-05-07\n"
                          "  ...",
                          fill=C_GREEN, size=14, bold=False)

    write_excalidraw("page_flows.excalidraw", elems)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Combined file (all diagrams stacked vertically with section headers)
# ═══════════════════════════════════════════════════════════════════════════

def _shift_element(el: dict, dy: int, id_prefix: str) -> dict:
    """Return a copy of el with y shifted by dy and id namespaced."""
    new_el = dict(el)
    new_el["id"] = f"{id_prefix}_{el['id']}"
    new_el["y"] = el["y"] + dy
    # arrows store positions in two places - root y AND points relative to (x,y).
    # Only the root y needs shifting; points are relative so they stay the same.
    return new_el


def _max_y(elements: list) -> int:
    """Largest y + height across elements - used to compute next section offset."""
    max_y = 0
    for el in elements:
        bottom = el["y"] + el.get("height", 0)
        if bottom > max_y:
            max_y = bottom
    return max_y


def gen_combined():
    """Stack architecture + 6 page diagrams vertically into one .excalidraw file.

    Reads the individual .excalidraw files generated above and concatenates
    their elements with progressive y offsets and a section header between
    each. Element ids are namespaced (e.g. "arch_el1", "home_el1") so the
    combined file has no id collisions.
    """
    sections = [
        ("arch", "architecture.excalidraw", "ARCHITECTURE - full data flow"),
        ("home", "page_home.excalidraw", "PAGE - Home (/home)"),
        ("contacts", "page_contacts.excalidraw", "PAGE - Contacts (/contacts)"),
        ("wa_inbox", "page_wa_inbox.excalidraw", "PAGE - WhatsApp Inbox (/wa-inbox)"),
        ("broadcasts", "page_broadcasts.excalidraw", "PAGE - Broadcasts (/broadcasts)"),
        ("wa_templates", "page_wa_templates.excalidraw", "PAGE - Template Studio (/wa-templates)"),
        ("flows", "page_flows.excalidraw", "PAGE - Flows (/flows)"),
    ]

    SECTION_GAP = 120  # vertical gap between sections (room for header + breathing room)
    SECTION_HEADER_HEIGHT = 80  # space reserved at the top of each section for its title

    combined_elems: list = []
    current_y_offset = 0
    section_id = 0

    for prefix, filename, title in sections:
        path = OUT_DIR / filename
        if not path.exists():
            print(f"  skip - {filename} not found")
            continue

        data = json.loads(path.read_text())
        section_elems = data.get("elements", [])

        # Banner above the section: a thick horizontal divider + section title
        section_id += 1
        # The header sits in the SECTION_HEADER_HEIGHT block at the top of this section
        header_y = current_y_offset + 20
        combined_elems.append({
            "id": f"section_div_{section_id}",
            "type": "rectangle",
            "x": 60, "y": header_y,
            "width": 1480, "height": 50,
            "angle": 0,
            "strokeColor": "#1971c2", "backgroundColor": "#d0bfff",
            "fillStyle": "solid", "strokeWidth": 3, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100,
            "groupIds": [], "frameId": None,
            "roundness": {"type": 3},
            "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
            "isDeleted": False, "boundElements": [],
            "updated": _now, "link": None, "locked": False,
        })
        combined_elems.append({
            "id": f"section_title_{section_id}",
            "type": "text",
            "x": 80, "y": header_y + 10,
            "width": 1440, "height": 30,
            "angle": 0,
            "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None,
            "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
            "isDeleted": False, "boundElements": [],
            "updated": _now, "link": None, "locked": False,
            "fontSize": 22, "fontFamily": 5,  # Excalifont (bold-feel)
            "text": title, "textAlign": "left", "verticalAlign": "middle",
            "containerId": None, "originalText": title, "lineHeight": 1.25,
            "baseline": 19,
        })

        # Shift all section elements to sit below the header
        section_dy = current_y_offset + SECTION_HEADER_HEIGHT
        shifted = [_shift_element(el, section_dy, prefix) for el in section_elems]
        combined_elems.extend(shifted)

        # Advance y offset by the original section's max y + gap
        original_max_y = _max_y(section_elems)
        current_y_offset += SECTION_HEADER_HEIGHT + original_max_y + SECTION_GAP

    # Top-level title above everything
    combined_elems.insert(0, {
        "id": "doc_title",
        "type": "text",
        "x": 80, "y": -100,
        "width": 1500, "height": 50,
        "angle": 0,
        "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
        "isDeleted": False, "boundElements": [],
        "updated": _now, "link": None, "locked": False,
        "fontSize": 40, "fontFamily": 5,
        "text": "Himalayan Fibres - vite_dashboard (full visualization)",
        "textAlign": "left", "verticalAlign": "middle",
        "containerId": None,
        "originalText": "Himalayan Fibres - vite_dashboard (full visualization)",
        "lineHeight": 1.25, "baseline": 34,
    })
    combined_elems.insert(1, {
        "id": "doc_subtitle",
        "type": "text",
        "x": 80, "y": -45,
        "width": 1500, "height": 28,
        "angle": 0,
        "strokeColor": "#868e96", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _next_seed(), "version": 1, "versionNonce": _next_seed(),
        "isDeleted": False, "boundElements": [],
        "updated": _now, "link": None, "locked": False,
        "fontSize": 16, "fontFamily": 2,
        "text": "Architecture + 6 page wireframes. Open in excalidraw.com -> File -> Open.",
        "textAlign": "left", "verticalAlign": "middle",
        "containerId": None,
        "originalText": "Architecture + 6 page wireframes. Open in excalidraw.com -> File -> Open.",
        "lineHeight": 1.25, "baseline": 13,
    })

    write_excalidraw("combined.excalidraw", combined_elems)


# ═══════════════════════════════════════════════════════════════════════════
# Run all
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    gen_architecture()
    gen_home()
    gen_contacts()
    gen_wa_inbox()
    gen_broadcasts()
    gen_wa_templates()
    gen_flows()
    gen_combined()
    print("done - 7 individual + 1 combined .excalidraw file")
