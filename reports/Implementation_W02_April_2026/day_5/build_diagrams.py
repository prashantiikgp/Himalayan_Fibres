"""Generate Excalidraw diagrams for the Phase 7.8 UI plan.

Run: python build_diagrams.py
Outputs 4 .excalidraw files in this directory:
  01-contact-drawer-flows-tab.excalidraw      — drawer with the new Flows tab
  02-flow-detail-page.excalidraw              — /flows/:id wireframe
  03-sample-dispatch-storyboard.excalidraw    — end-to-end timeline
  04-membership-state-machine.excalidraw      — state transitions
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUTDIR = Path(__file__).resolve().parent
random.seed(7)


def sid() -> int:
    return random.randint(1, 2**31 - 1)


def eid() -> str:
    return "el-" + "".join(random.choices("abcdef0123456789", k=12))


C = {
    "bg":         "#ffffff",
    "card":       "#f8fafc",
    "card2":      "#f1f5f9",
    "border":     "#cbd5e1",
    "text":       "#0f172a",
    "muted":      "#64748b",
    "primary":    "#6366f1",
    "primary_bg": "#eef2ff",
    "success":    "#22c55e",
    "success_bg": "#dcfce7",
    "warning":    "#f59e0b",
    "warning_bg": "#fef3c7",
    "danger":     "#ef4444",
    "danger_bg":  "#fee2e2",
    "neutral":    "#64748b",
    "neutral_bg": "#e2e8f0",
}


def _common(stroke: str, stroke_w: int = 1, dashed: bool = False) -> dict:
    return {
        "version": 1,
        "versionNonce": sid(),
        "isDeleted": False,
        "id": eid(),
        "strokeColor": stroke,
        "strokeWidth": stroke_w,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 0,
        "opacity": 100,
        "angle": 0,
        "seed": sid(),
        "groupIds": [],
        "frameId": None,
        "boundElements": [],
        "updated": 1736000000000,
        "link": None,
        "locked": False,
    }


def rect(x, y, w, h, *, fill="transparent", stroke=C["border"], stroke_w=1, rounded=False, dashed=False):
    e = _common(stroke, stroke_w, dashed)
    e.update({
        "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "fillStyle": "solid" if fill != "transparent" else "hachure",
        "backgroundColor": fill,
        "roundness": {"type": 3} if rounded else None,
    })
    return e


def diamond(x, y, w, h, *, fill="transparent", stroke=C["border"]):
    e = _common(stroke, 2)
    e.update({
        "type": "diamond",
        "x": x, "y": y, "width": w, "height": h,
        "fillStyle": "solid" if fill != "transparent" else "hachure",
        "backgroundColor": fill,
        "roundness": None,
    })
    return e


def ellipse(x, y, w, h, *, fill="transparent", stroke=C["border"]):
    e = _common(stroke, 2)
    e.update({
        "type": "ellipse",
        "x": x, "y": y, "width": w, "height": h,
        "fillStyle": "solid" if fill != "transparent" else "hachure",
        "backgroundColor": fill,
        "roundness": None,
    })
    return e


def text(x, y, content, *, size=16, color=C["text"], align="left", w=None, bold=False):
    estimated_w = w or max(40, int(len(content) * size * 0.55))
    estimated_h = int(size * 1.25)
    e = _common(color)
    e.update({
        "type": "text",
        "x": x, "y": y, "width": estimated_w, "height": estimated_h,
        "fillStyle": "hachure",
        "backgroundColor": "transparent",
        "roundness": None,
        "text": content,
        "fontSize": size,
        "fontFamily": 5 if bold else 1,
        "textAlign": align,
        "verticalAlign": "top",
        "containerId": None,
        "originalText": content,
        "lineHeight": 1.25,
        "autoResize": True,
    })
    return e


def arrow(x1, y1, x2, y2, *, color=C["text"], dashed=False, width=2):
    e = _common(color, width, dashed)
    e.update({
        "type": "arrow",
        "x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1,
        "fillStyle": "hachure",
        "backgroundColor": "transparent",
        "roundness": None,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": "arrow",
    })
    return e


def line(x1, y1, x2, y2, *, color=C["border"], dashed=False, width=1):
    e = _common(color, width, dashed)
    e.update({
        "type": "line",
        "x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1,
        "fillStyle": "hachure",
        "backgroundColor": "transparent",
        "roundness": None,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
    })
    return e


def pill(x, y, label, *, fill, stroke, text_color):
    """Small rounded label pill."""
    w = max(60, int(len(label) * 7) + 16)
    h = 22
    return [
        rect(x, y, w, h, fill=fill, stroke=stroke, rounded=True),
        text(x + 8, y + 5, label, size=10, color=text_color, bold=True),
    ], w


def button(x, y, label, *, w=120, h=34, primary=False, danger=False):
    if primary:
        bg = C["primary"]
        stroke = C["primary"]
        tc = "#ffffff"
    elif danger:
        bg = C["bg"]
        stroke = C["danger"]
        tc = C["danger"]
    else:
        bg = C["bg"]
        stroke = C["border"]
        tc = C["text"]
    return [
        rect(x, y, w, h, fill=bg, stroke=stroke, rounded=True),
        text(x + (w // 2) - int(len(label) * 3.5), y + 9, label, size=12, color=tc, bold=primary),
    ]


def save(elements, name):
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }
    out = OUTDIR / f"{name}.excalidraw"
    out.write_text(json.dumps(doc, indent=2))
    print(f"  wrote {out.name}  ({len(elements)} elements)")


# ─────────────────────────────────────────────────────────────────────
# Diagram 1 — Contact drawer with the new Flows tab
# ─────────────────────────────────────────────────────────────────────


def diagram_drawer():
    e: list[dict] = []
    DX, DY = 60, 40
    W, H = 520, 820

    # Page label
    e.append(text(DX, DY - 30, "Phase 7.8 — Contact drawer with the new \"Flows\" tab",
                  size=18, bold=True))

    # Drawer shell
    e.append(rect(DX, DY, W, H, fill=C["bg"], stroke=C["border"], stroke_w=2, rounded=True))

    # Header
    e.append(text(DX + 24, DY + 20, "Sample Tester", size=22, bold=True))
    e.append(text(DX + 24, DY + 50, "Sample Co Pvt Ltd", size=12, color=C["muted"]))
    bp1, w1 = pill(DX + 24, DY + 76, "EMAIL", fill=C["primary_bg"], stroke=C["primary"], text_color=C["primary"])
    e += bp1
    bp2, _ = pill(DX + 24 + w1 + 8, DY + 76, "WHATSAPP", fill=C["success_bg"], stroke=C["success"], text_color=C["success"])
    e += bp2

    # Lifecycle quick-action strip (existing pattern)
    e.append(rect(DX + 24, DY + 116, W - 48, 38, fill=C["card2"], rounded=True, dashed=True))
    e.append(text(DX + 38, DY + 130, "✉ Replied   ⭐ Interested   ✓ Converted   ✕ Not interested",
                  size=11, color=C["muted"]))

    # Tab row — 5 tabs, "Flows" is active
    tab_y = DY + 168
    e.append(line(DX + 24, tab_y + 36, DX + W - 24, tab_y + 36, color=C["border"]))
    tabs = [("Profile", False), ("Tags", False), ("Notes (2)", False),
            ("Activity", False), ("Flows (1)", True)]
    tab_x = DX + 28
    for label, active in tabs:
        tw = len(label) * 8 + 18
        if active:
            e.append(rect(tab_x, tab_y, tw, 36, fill=C["primary_bg"], stroke=C["primary"], rounded=True))
            e.append(text(tab_x + 8, tab_y + 11, label, size=12, color=C["primary"], bold=True))
        else:
            e.append(text(tab_x + 8, tab_y + 11, label, size=12, color=C["muted"]))
        tab_x += tw + 6

    # ─── Flows tab body ───
    body_y = DY + 222

    e.append(text(DX + 24, body_y, "Active flows (1)", size=15, bold=True))

    # Sample Dispatch card (waiting_event)
    cy = body_y + 32
    ch = 220
    e.append(rect(DX + 24, cy, W - 48, ch, fill=C["card"], stroke=C["border"], rounded=True))

    e.append(text(DX + 40, cy + 16, "Sample Dispatch", size=14, bold=True))
    pp, _ = pill(DX + 220, cy + 14, "WAITING EVENT",
                 fill=C["warning_bg"], stroke=C["warning"], text_color=C["warning"])
    e += pp

    e.append(text(DX + 40, cy + 48, "Step 2 of 3 — Sample shipped", size=12))

    # Progress bar
    bar_w = 380
    e.append(rect(DX + 40, cy + 76, bar_w, 8, fill=C["neutral_bg"], rounded=True))
    e.append(rect(DX + 40, cy + 76, int(bar_w * 0.66), 8, fill=C["primary"], rounded=True))

    e.append(text(DX + 40, cy + 96, "Next: waiting for samples_shipped event",
                  size=11, color=C["muted"]))
    e.append(text(DX + 40, cy + 114, "Started: 3 days ago", size=11, color=C["muted"]))

    # Action buttons row
    btn_y = cy + 154
    e += button(DX + 40, btn_y, "Mark sample shipped", w=180, primary=True)
    e += button(DX + 232, btn_y, "Pause", w=80)
    e += button(DX + 322, btn_y, "Stop", w=80, danger=True)

    # Annotation arrow + label pointing to the Mark button
    e.append(arrow(DX + W + 20, btn_y - 30, DX + 130, btn_y + 5, color=C["primary"], dashed=True))
    e.append(text(DX + W + 30, btn_y - 50,
                  "Inline-expand form\nopens here when clicked\n(see §3.7)",
                  size=12, color=C["primary"]))

    # Past flows
    pf_y = cy + ch + 24
    e.append(text(DX + 24, pf_y, "▸ Past flows (2)", size=12, color=C["muted"]))

    # Add to flow row
    af_y = pf_y + 40
    e.append(text(DX + 24, af_y, "Add to flow", size=14, bold=True))
    e.append(rect(DX + 24, af_y + 28, 320, 40, fill=C["bg"], stroke=C["border"], rounded=True))
    e.append(text(DX + 36, af_y + 40, "— Select a flow —              ▾",
                  size=12, color=C["muted"]))
    e += button(DX + 360, af_y + 28, "Add", w=80, h=40, primary=True)

    save(e, "01-contact-drawer-flows-tab")


# ─────────────────────────────────────────────────────────────────────
# Diagram 2 — /flows/:id detail page
# ─────────────────────────────────────────────────────────────────────


def diagram_flow_detail():
    e: list[dict] = []
    DX, DY = 40, 40
    W, H = 1200, 760

    e.append(text(DX, DY - 30, "Phase 7.8 — Flow detail page  /flows/:id",
                  size=18, bold=True))

    # Outer page frame
    e.append(rect(DX, DY, W, H, fill=C["bg"], stroke=C["border"], stroke_w=2, rounded=True))

    # Top bar
    e.append(text(DX + 24, DY + 20, "← Back to flows", size=12, color=C["primary"]))

    # Title + trigger pill
    e.append(text(DX + 24, DY + 56, "Sample Dispatch", size=26, bold=True))
    pp, pw = pill(DX + 320, DY + 64, "TAG: SAMPLES_REQUESTED",
                  fill=C["warning_bg"], stroke=C["warning"], text_color=C["warning"])
    e += pp
    cp, _ = pill(DX + 320 + pw + 8, DY + 64, "MULTI",
                 fill="#ede9fe", stroke="#a855f7", text_color="#a855f7")
    e += cp

    e.append(text(DX + 24, DY + 96,
                  "Triggered when a contact is tagged samples_requested. 3 steps.",
                  size=12, color=C["muted"]))

    # KPI cards
    kpi_y = DY + 136
    kpi_cards = [
        ("Active", "12", C["primary"]),
        ("Waiting event", "5", C["warning"]),
        ("Completed", "47", C["success"]),
        ("Failed", "1", C["danger"]),
    ]
    cx = DX + 24
    for label, value, color in kpi_cards:
        e.append(rect(cx, kpi_y, 220, 90, fill=C["card"], stroke=C["border"], rounded=True))
        e.append(text(cx + 16, kpi_y + 14, label, size=11, color=C["muted"], bold=True))
        e.append(text(cx + 16, kpi_y + 36, value, size=32, color=color, bold=True))
        cx += 232

    # Tabs
    tab_y = DY + 252
    e.append(line(DX + 24, tab_y + 36, DX + W - 24, tab_y + 36, color=C["border"]))
    detail_tabs = [("Members", True), ("Steps", False), ("Step Runs", False)]
    tab_x = DX + 28
    for label, active in detail_tabs:
        tw = len(label) * 9 + 24
        if active:
            e.append(rect(tab_x, tab_y, tw, 36, fill=C["primary_bg"], stroke=C["primary"], rounded=True))
            e.append(text(tab_x + 12, tab_y + 11, label, size=13, color=C["primary"], bold=True))
        else:
            e.append(text(tab_x + 12, tab_y + 11, label, size=13, color=C["muted"]))
        tab_x += tw + 8

    # Filters above the table
    filter_y = DY + 308
    e.append(rect(DX + 24, filter_y, 220, 36, fill=C["bg"], stroke=C["border"], rounded=True))
    e.append(text(DX + 36, filter_y + 11, "Status: All     ▾", size=12, color=C["muted"]))
    e.append(rect(DX + 256, filter_y, 280, 36, fill=C["bg"], stroke=C["border"], rounded=True))
    e.append(text(DX + 268, filter_y + 11, "Search by contact…", size=12, color=C["muted"]))

    # Members table
    tbl_y = DY + 360
    cols = [
        ("Contact",     280),
        ("Status",      150),
        ("Step",        140),
        ("Next fire",   170),
        ("Started",     150),
        ("Actions",     230),
    ]
    cx = DX + 24
    e.append(rect(DX + 24, tbl_y, W - 48, 36, fill=C["card2"], stroke=C["border"], rounded=True))
    for label, w in cols:
        e.append(text(cx + 12, tbl_y + 11, label, size=11, color=C["muted"], bold=True))
        cx += w
    e.append(line(DX + 24, tbl_y + 36, DX + W - 24, tbl_y + 36, color=C["border"]))

    # Sample rows
    rows = [
        ("Anita Sharma\nanita@brand.in", "WAITING EVENT", "warning", "2 of 3", "—", "3d ago"),
        ("Carlos Vega\ncarlos@blue-yarn.co", "ACTIVE",        "primary", "3 of 3", "in 4d 2h", "10d ago"),
        ("Mei Tan\nmei@taichi-textiles.tw","WAITING EVENT", "warning", "2 of 3", "—", "1d ago"),
        ("Ravi Singh\nravi@himachal-fabric.in","FAILED",     "danger",  "2 of 3", "—", "8d ago"),
    ]
    ry = tbl_y + 36
    for row in rows:
        cx = DX + 24
        # Contact name + email
        contact_lines = row[0].split("\n")
        e.append(text(cx + 12, ry + 8, contact_lines[0], size=12, bold=True))
        if len(contact_lines) > 1:
            e.append(text(cx + 12, ry + 28, contact_lines[1], size=10, color=C["muted"]))
        cx += 280

        # Status pill
        tone = row[2]
        bg_map = {"primary": C["primary_bg"], "warning": C["warning_bg"],
                  "danger": C["danger_bg"], "success": C["success_bg"]}
        st_map = {"primary": C["primary"], "warning": C["warning"],
                  "danger": C["danger"], "success": C["success"]}
        sp, _ = pill(cx + 12, ry + 14, row[1],
                     fill=bg_map[tone], stroke=st_map[tone], text_color=st_map[tone])
        e += sp
        cx += 150

        e.append(text(cx + 12, ry + 18, f"Step {row[3]}", size=12))
        cx += 140
        e.append(text(cx + 12, ry + 18, row[4], size=12, color=C["muted"]))
        cx += 170
        e.append(text(cx + 12, ry + 18, row[5], size=12, color=C["muted"]))
        cx += 150

        # Action buttons
        e += button(cx + 8, ry + 8, "Pause", w=70)
        e += button(cx + 88, ry + 8, "Resume", w=80)
        e += button(cx + 178, ry + 8, "Stop", w=50, danger=True)

        ry += 60
        e.append(line(DX + 24, ry, DX + W - 24, ry, color=C["border"]))

    save(e, "02-flow-detail-page")


# ─────────────────────────────────────────────────────────────────────
# Diagram 3 — Sample Dispatch storyboard (end-to-end timeline)
# ─────────────────────────────────────────────────────────────────────


def diagram_storyboard():
    e: list[dict] = []
    DX, DY = 40, 40

    e.append(text(DX, DY - 30,
                  "Sample Dispatch — end-to-end operator workflow",
                  size=18, bold=True))

    # Timeline backbone
    track_y = DY + 60
    e.append(line(DX + 60, track_y, DX + 1380, track_y, color=C["border"], width=3))

    steps = [
        # (label, sublabel, icon, x, color)
        ("Operator tags\nsamples_requested", "via drawer\nTags tab",      "🏷",  DX + 100,  C["primary"]),
        ("Trigger evaluator\ncreates membership","status=active\nstep=0",  "⚙",   DX + 320,  C["muted"]),
        ("Tick fires step 0",                   "Email + WA\nack sent",   "✉",   DX + 540,  C["success"]),
        ("Membership parks",                    "status=\nwaiting_event", "⏸",   DX + 760,  C["warning"]),
        ("Operator clicks\nMark sample shipped","tracking_id\ncourier",   "📦",  DX + 980,  C["primary"]),
        ("Tick fires step 1",                   "Email + WA\nwith tracking","✉", DX + 1200, C["success"]),
        ("Tick fires step 2 (T+7d)",            "post_sample\n_followup", "✉",   DX + 1380, C["success"]),
    ]

    for label, sublabel, icon, x, color in steps:
        # Node
        e.append(ellipse(x - 24, track_y - 24, 48, 48, fill=C["bg"], stroke=color))
        e.append(text(x - 10, track_y - 14, icon, size=20))
        # Label above
        e.append(text(x - 80, track_y - 80, label, size=12, color=C["text"], bold=True, w=160))
        # Sublabel below
        e.append(text(x - 70, track_y + 36, sublabel, size=11, color=C["muted"], w=140))

    # Annotations
    note_y = track_y + 120

    e.append(rect(DX + 80, note_y, 480, 110, fill=C["primary_bg"], stroke=C["primary"], rounded=True))
    e.append(text(DX + 96, note_y + 14, "Auto-enrollment", size=13, bold=True, color=C["primary"]))
    e.append(text(DX + 96, note_y + 38,
                  "Phase 7.7's tag-trigger evaluator runs inline\n"
                  "with the tag-add transaction. Within 60 seconds\n"
                  "the scheduler tick claims the membership and\n"
                  "fires step 0 (email + WA template).",
                  size=11, color=C["text"]))

    e.append(rect(DX + 600, note_y, 380, 110, fill=C["warning_bg"], stroke=C["warning"], rounded=True))
    e.append(text(DX + 616, note_y + 14, "Operator intervention", size=13, bold=True, color=C["warning"]))
    e.append(text(DX + 616, note_y + 38,
                  "Membership waits indefinitely for the\n"
                  "samples_shipped tag. Operator clicks the Mark\n"
                  "button when physical samples ship — passing\n"
                  "tracking_id + courier as drawer form input.",
                  size=11, color=C["text"]))

    e.append(rect(DX + 1020, note_y, 420, 110, fill=C["success_bg"], stroke=C["success"], rounded=True))
    e.append(text(DX + 1036, note_y + 14, "Auto-completion", size=13, bold=True, color=C["success"]))
    e.append(text(DX + 1036, note_y + 38,
                  "Step 1 renders tracking from\n"
                  "membership.metadata_json. Step 2 fires 7 days\n"
                  "later (timer-gated). Membership status flips\n"
                  "to 'completed' — visible in past flows section.",
                  size=11, color=C["text"]))

    # Operator-control swim lane (bottom)
    sl_y = note_y + 170
    e.append(rect(DX + 80, sl_y, 1360, 100, fill=C["card2"], stroke=C["border"],
                  rounded=True, dashed=True))
    e.append(text(DX + 96, sl_y + 14, "Operator can also at any point:",
                  size=13, bold=True))
    e.append(text(DX + 96, sl_y + 40,
                  "• Click Pause → membership status='paused' → tick skips it. Click Resume → status='active', next_fire_at=now → tick claims on next pass.",
                  size=11, color=C["text"]))
    e.append(text(DX + 96, sl_y + 60,
                  "• Click Stop → membership status='stopped' (terminal). The contact is removed from the active set; a new tag-add starts a fresh membership.",
                  size=11, color=C["text"]))
    e.append(text(DX + 96, sl_y + 80,
                  "• Pause/Resume/Stop are also accessible from the /flows/:id Members table — same actions, different surface.",
                  size=11, color=C["text"]))

    save(e, "03-sample-dispatch-storyboard")


# ─────────────────────────────────────────────────────────────────────
# Diagram 4 — Membership state machine
# ─────────────────────────────────────────────────────────────────────


def diagram_state_machine():
    e: list[dict] = []
    DX, DY = 40, 40

    e.append(text(DX, DY - 30, "FlowMembership state machine",
                  size=18, bold=True))

    # State node helper
    def state_node(x, y, label, color, fill):
        e.append(ellipse(x, y, 180, 80, fill=fill, stroke=color))
        e.append(text(x + 90 - len(label) * 4, y + 30, label, size=14, color=color, bold=True))

    # Layout positions
    P_INIT     = (DX + 60,  DY + 80)
    P_ACTIVE   = (DX + 380, DY + 80)
    P_WAIT     = (DX + 700, DY + 80)
    P_PAUSED   = (DX + 380, DY + 240)
    P_COMPLETE = (DX + 700, DY + 400)
    P_STOPPED  = (DX + 380, DY + 400)
    P_FAILED   = (DX + 60,  DY + 400)

    # Initial pseudo-state
    e.append(ellipse(P_INIT[0] + 70, P_INIT[1] + 30, 30, 30, fill=C["text"], stroke=C["text"]))
    e.append(text(P_INIT[0], P_INIT[1] - 10, "(trigger fires)", size=10, color=C["muted"]))

    # States
    state_node(*P_ACTIVE,   "active",        C["primary"], C["primary_bg"])
    state_node(*P_WAIT,     "waiting_event", C["warning"], C["warning_bg"])
    state_node(*P_PAUSED,   "paused",        C["muted"],   C["card2"])
    state_node(*P_COMPLETE, "completed",     C["success"], C["success_bg"])
    state_node(*P_STOPPED,  "stopped",       C["muted"],   C["card2"])
    state_node(*P_FAILED,   "failed",        C["danger"],  C["danger_bg"])

    # Transitions
    transitions = [
        # init → active
        (P_INIT[0] + 100, P_INIT[1] + 40, P_ACTIVE[0], P_ACTIVE[1] + 40,
         "trigger fires", C["text"]),
        # active → waiting_event (event-gated next step)
        (P_ACTIVE[0] + 180, P_ACTIVE[1] + 30, P_WAIT[0], P_WAIT[1] + 30,
         "next step has\ntrigger_event", C["warning"]),
        # waiting_event → active (event arrives)
        (P_WAIT[0], P_WAIT[1] + 50, P_ACTIVE[0] + 180, P_ACTIVE[1] + 50,
         "matching tag\nadded", C["primary"]),
        # active → paused (operator)
        (P_ACTIVE[0] + 90, P_ACTIVE[1] + 80, P_PAUSED[0] + 90, P_PAUSED[1],
         "operator: Pause", C["muted"]),
        # paused → active (operator)
        (P_PAUSED[0] + 100, P_PAUSED[1], P_ACTIVE[0] + 100, P_ACTIVE[1] + 80,
         "operator: Resume", C["primary"]),
        # active → completed (last step done)
        (P_ACTIVE[0] + 180, P_ACTIVE[1] + 70, P_COMPLETE[0], P_COMPLETE[1] + 30,
         "last step fired", C["success"]),
        # active → stopped (operator)
        (P_ACTIVE[0] + 80, P_ACTIVE[1] + 80, P_STOPPED[0] + 80, P_STOPPED[1],
         "operator: Stop", C["muted"]),
        # active → failed (3 consecutive failures)
        (P_ACTIVE[0], P_ACTIVE[1] + 80, P_FAILED[0] + 180, P_FAILED[1] + 30,
         "3 consecutive\nstep failures", C["danger"]),
        # active self-loop (advance to next non-event step)
        (P_ACTIVE[0] + 30, P_ACTIVE[1], P_ACTIVE[0] + 150, P_ACTIVE[1],
         "advance step\n(timer-gated)", C["primary"]),
    ]

    for x1, y1, x2, y2, lbl, color in transitions:
        e.append(arrow(x1, y1, x2, y2, color=color))
        # Label midway, offset slightly upward
        mx, my = (x1 + x2) // 2 - len(lbl) * 3, (y1 + y2) // 2 - 28
        e.append(text(mx, my, lbl, size=11, color=color))

    # Self-loop curve approximation for active (top arc)
    # (Excalidraw arrows can't curve in this simple representation; the
    # straight horizontal arrow above conveys it.)

    # Legend
    lg_y = DY + 540
    e.append(text(DX + 60, lg_y, "Tone legend (operator UI):",
                  size=13, bold=True))
    legend_pills = [
        ("active — sends scheduled",       C["primary_bg"], C["primary"]),
        ("waiting_event — needs operator",  C["warning_bg"], C["warning"]),
        ("paused — held; resumable",        C["card2"],      C["muted"]),
        ("completed — done",                C["success_bg"], C["success"]),
        ("stopped — terminal by operator",  C["card2"],      C["muted"]),
        ("failed — 3 step errors",          C["danger_bg"],  C["danger"]),
    ]
    lx = DX + 60
    ly = lg_y + 30
    for label, fill, stroke in legend_pills:
        sp, w = pill(lx, ly, label.upper().split(" — ")[0],
                     fill=fill, stroke=stroke, text_color=stroke)
        e += sp
        e.append(text(lx + w + 8, ly + 3, "— " + label.split(" — ")[1],
                      size=11, color=C["text"]))
        ly += 28

    save(e, "04-membership-state-machine")


# ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("Building Phase 7.8 diagrams in", OUTDIR)
    diagram_drawer()
    diagram_flow_detail()
    diagram_storyboard()
    diagram_state_machine()
    print("Done.")
