"""Global CSS overrides for the Gradio dashboard.

Passed to `mount_gradio_app(css=DASHBOARD_CSS)` in app.py. Uses !important
to override Gradio's default styling and enforce the dark theme.

Panel layout tokens (.conv-list-panel / .chat-panel / .tools-panel) are
pulled from config/theme/layout.yml via the ThemeEngine so they live in a
schema-validated config, not as Python literals. The engine fails loud at
module-import time if the YAML is malformed.
"""

from engines.theme_engine import get_theme_engine

_STATIC_CSS = """
/* -- Remove Gradio footer -- */
footer { display: none !important; }

/* -- Template Studio: three panels with distinct accent colors --
   Each column gets its own background tint and border so the boundaries
   between list / editor / preview are unmistakable. */
.ts-list-panel,
.ts-editor-panel,
.ts-preview-panel {
    border-radius: 12px !important;
    padding: 12px !important;
    min-height: calc(100vh - 140px) !important;
    overflow-y: auto !important;
    display: flex !important;
    flex-direction: column !important;
}
.ts-list-panel {
    background: rgba(99, 102, 241, 0.05) !important;   /* indigo tint */
    border: 1px solid rgba(99, 102, 241, 0.28) !important;
}
.ts-editor-panel {
    background: rgba(16, 185, 129, 0.05) !important;   /* emerald tint */
    border: 1px solid rgba(16, 185, 129, 0.28) !important;
}
.ts-preview-panel {
    background: rgba(59, 130, 246, 0.05) !important;   /* blue tint */
    border: 1px solid rgba(59, 130, 246, 0.28) !important;
}

/* Tighten field spacing inside the editor panel so the form doesn't
   stretch with wasted vertical gaps. */
.ts-editor-panel .form,
.ts-editor-panel .block {
    gap: 6px !important;
}
.ts-editor-panel label {
    margin-bottom: 2px !important;
}
.ts-editor-panel .wrap { padding: 2px 0 !important; }

/* Panel section headers (same style for all three) */
.ts-panel-title {
    font-weight: 700 !important;
    color: #e7eaf3 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
    margin: 0 0 10px 0 !important;
    padding-bottom: 6px !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
}
.ts-list-panel .ts-panel-title { color: #c7d2fe !important; }
.ts-editor-panel .ts-panel-title { color: #a7f3d0 !important; }
.ts-preview-panel .ts-panel-title { color: #93c5fd !important; }


/* -- Global font sizing -- */
body { font-size: 12px !important; }

/* -- Header bar -- */
.header-bar {
    background: rgba(15,23,42,.80) !important;
    border-bottom: 1px solid rgba(255,255,255,.06) !important;
    padding: 8px 20px !important;
    margin-bottom: 4px !important;
}
.header-bar h1 {
    font-size: 16px !important;
    font-weight: 700 !important;
    color: #e7eaf3 !important;
    margin: 0 !important;
}

/* -- Main layout: sidebar + content -- */
.main-layout {
    display: flex !important;
    align-items: stretch !important;
    min-height: calc(100vh - 80px) !important;
    gap: 8px !important;
    padding: 0 !important;
    margin-top: 4px !important;
}

/* -- Sidebar navigation -- */
.nav-sidebar {
    background: rgba(15,23,42,.45) !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 12px !important;
    padding: 8px 4px !important;
    min-height: calc(100vh - 80px) !important;
    height: 100% !important;
    position: sticky !important;
    top: 8px !important;
    align-self: flex-start !important;
}
.nav-sidebar .nav-btn {
    margin: 1px 0 !important;
}
.nav-sidebar .nav-btn button {
    text-align: left !important;
    padding: 10px 14px !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
    background: transparent !important;
    border: none !important;
    border-left: 3px solid transparent !important;
    transition: background 0.15s !important;
    cursor: pointer !important;
    width: 100% !important;
    justify-content: flex-start !important;
}
.nav-sidebar .nav-btn button:hover {
    background: rgba(99,102,241,.08) !important;
}
.nav-sidebar .nav-btn-active button {
    background: rgba(99,102,241,.12) !important;
    color: #e7eaf3 !important;
    border-left: 3px solid #6366f1 !important;
}

/* -- Nav separator -- */
.nav-separator {
    height: 1px;
    background: rgba(255,255,255,.06);
    margin: 6px 8px;
}

/* -- Content area -- */
.content-area {
    padding: 0 8px !important;
    min-height: calc(100vh - 80px) !important;
    gap: 0 !important;
}

/* Remove stray borders + shadows from Gradio groups */
.content-area .group_container,
.content-area > .group_container > .group_container {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
}

/* -- Page left column (filters + KPI cards) -- */
.page-left-col {
    background: rgba(15,23,42,.50) !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 8px !important;
    padding: 10px !important;
}

/* -- Contacts page right column: fixed viewport height so the table scrolls
      internally and the footer is always visible without page scrolling -- */
.contacts-right-col {
    display: flex !important;
    flex-direction: column !important;
    flex-wrap: nowrap !important;  /* override Gradio .column default wrap */
    gap: 6px !important;
    height: calc(100vh - 110px) !important;
    max-height: calc(100vh - 110px) !important;
    overflow: hidden !important;
}
.contacts-right-col .contacts-table-host {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 8px !important;
    background: rgba(15,23,42,.40) !important;
}
.contacts-right-col .contacts-table-host > * { margin: 0 !important; }
/* Visible scrollbar inside the table */
.contacts-right-col .contacts-table-host::-webkit-scrollbar {
    width: 10px !important;
}
.contacts-right-col .contacts-table-host::-webkit-scrollbar-thumb {
    background: rgba(99,102,241,.45) !important;
    border-radius: 5px !important;
    border: 2px solid transparent !important;
    background-clip: padding-box !important;
}
.contacts-right-col .contacts-table-host::-webkit-scrollbar-thumb:hover {
    background: rgba(99,102,241,.7) !important;
    background-clip: padding-box !important;
}
.contacts-right-col .contacts-table-host::-webkit-scrollbar-track {
    background: rgba(255,255,255,.03) !important;
}

/* Also constrain the left column so the page height doesn't grow past viewport */
.page-left-col {
    max-height: calc(100vh - 110px) !important;
    overflow-y: auto !important;
}

/* -- Compact top bar above the contacts table -- */
.contacts-top-bar { gap: 8px !important; align-items: center !important; }
.contacts-top-bar .block { margin: 0 !important; }
.contacts-top-bar input[type="text"] {
    height: 34px !important;
    font-size: 12px !important;
}
.contacts-top-bar button {
    height: 34px !important;
    font-size: 12px !important;
    white-space: nowrap !important;
}

/* -- Compact footer bar under the table: legend + pagination together -- */
.contacts-footer-bar {
    gap: 8px !important;
    align-items: center !important;
    background: rgba(15,23,42,.55) !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 8px !important;
    padding: 4px 10px !important;
    margin-top: 2px !important;
    flex-wrap: nowrap !important;
    flex-grow: 0 !important;
    flex-shrink: 0 !important;
    min-height: 40px !important;
}
.contacts-footer-bar .block { margin: 0 !important; flex-grow: 0 !important; }
.contacts-footer-bar button {
    height: 30px !important;
    font-size: 12px !important;
    padding: 4px 12px !important;
    min-width: 36px !important;
}
/* Make the Legend button more prominent */
.contacts-footer-bar > div:first-child button {
    height: 32px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 4px 16px !important;
    background: rgba(99,102,241,.18) !important;
    border: 1px solid rgba(99,102,241,.4) !important;
    color: #c7d2fe !important;
}
.contacts-footer-bar > div:first-child button:hover {
    background: rgba(99,102,241,.28) !important;
}
.contacts-footer-bar input[type="number"] {
    height: 30px !important;
    font-size: 11px !important;
    text-align: center !important;
    padding: 2px 4px !important;
    width: 50px !important;
}
/* Let the range label take the flexible middle space */
.contacts-footer-bar > div:nth-child(2) { flex: 1 1 auto !important; }
.contacts-footer-bar label { display: none !important; }

/* -- JS bridge elements: in DOM for JS to read/click, visually hidden -- */
.hf-bridge-hidden {
    position: absolute !important;
    left: -9999px !important;
    width: 1px !important;
    height: 1px !important;
    opacity: 0 !important;
    pointer-events: none !important;
    overflow: hidden !important;
}

/* -- Per-row Edit button inside the contacts table -- */
.hf-row-edit-btn {
    background: rgba(99,102,241,.15) !important;
    border: 1px solid rgba(99,102,241,.35) !important;
    color: #c7d2fe !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    padding: 3px 10px !important;
    border-radius: 4px !important;
    cursor: pointer !important;
    transition: background 0.12s ease !important;
    white-space: nowrap !important;
}
.hf-row-edit-btn:hover {
    background: rgba(99,102,241,.30) !important;
    color: #e0e7ff !important;
}

/* -- Edit drawer modal: right-anchored wider layout -- */
.hf-modal.hf-modal-drawer {
    width: 620px !important;
    max-width: 94vw !important;
}
.hf-modal.hf-modal-drawer .tab-nav button {
    font-size: 12px !important;
}

/* -- Contacts table: gradient header, striped rows, softer borders -- */
.contacts-table-host table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
}
.contacts-table-host thead th {
    background: linear-gradient(180deg, rgba(30,41,59,.98), rgba(15,23,42,.98)) !important;
    border-bottom: 1px solid rgba(99,102,241,.25) !important;
    color: #cbd5e1 !important;
    text-transform: uppercase !important;
    letter-spacing: .5px !important;
    font-weight: 600 !important;
    font-size: 10px !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 2 !important;
}
.contacts-table-host tbody tr {
    transition: background 0.12s ease !important;
}
.contacts-table-host tbody tr:nth-child(odd) {
    background: rgba(255,255,255,.015) !important;
}
.contacts-table-host tbody tr:nth-child(even) {
    background: rgba(15,23,42,.35) !important;
}
.contacts-table-host tbody tr:hover {
    background: rgba(99,102,241,.10) !important;
}
.contacts-table-host tbody td {
    border-bottom: 1px solid rgba(255,255,255,.04) !important;
    color: #e2e8f0 !important;
}

/* -- Legend under the contacts table -- */
.contacts-legend details {
    background: rgba(15,23,42,.50);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 8px;
    padding: 8px 12px;
    margin-top: 8px;
    color: #94a3b8;
    font-size: 11px;
}
.contacts-legend summary {
    cursor: pointer;
    font-weight: 600;
    color: #e7eaf3;
    font-size: 12px;
    padding: 4px 0;
    user-select: none;
}
.contacts-legend .legend-body {
    display: flex;
    gap: 16px;
    margin-top: 10px;
    flex-wrap: wrap;
}
.contacts-legend .legend-col {
    flex: 1 1 220px;
    min-width: 0;
}
.contacts-legend .legend-col h4 {
    margin: 0 0 6px 0;
    font-size: 11px;
    font-weight: 700;
    color: #e7eaf3;
    text-transform: uppercase;
    letter-spacing: .4px;
}
.contacts-legend .legend-col p {
    margin: 0 0 6px 0;
    line-height: 1.45;
}
.contacts-legend .legend-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    margin: 2px 4px 2px 0;
    font-weight: 600;
}
.contacts-legend .legend-tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.1);
    color: #94a3b8;
    margin: 2px 3px 2px 0;
}

/* -- HF Modal overlay (Add Contact, Import) --
   The column itself becomes the centered card. The backdrop is faked with a
   huge box-shadow spread (100vmax) so we don't need a separate DOM element. */
.hf-modal {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    z-index: 9999 !important;
    width: 560px !important;
    max-width: 92vw !important;
    max-height: 85vh !important;
    overflow-y: auto !important;
    background: #0f172a !important;
    border: 1px solid rgba(255,255,255,.14) !important;
    border-radius: 12px !important;
    padding: 20px !important;
    box-shadow: 0 0 0 100vmax rgba(0,0,0,.62), 0 20px 60px rgba(0,0,0,.55) !important;
    flex-grow: 0 !important;
    min-width: 0 !important;
}
.hf-modal .block { background: transparent !important; }
.hf-modal .form { background: transparent !important; border: none !important; }
.hf-modal-title {
    margin: 0 0 14px 0 !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #e7eaf3 !important;
}
.hf-modal.hf-modal-wide { width: 820px !important; max-width: 94vw !important; }

/* Hidden state — modal stays mounted (avoids Svelte mount race on first
   open) but is not rendered until the class is removed. */
.hf-modal.hf-modal-closed { display: none !important; }

@media (max-width: 768px) {
    .hf-modal { width: 95vw !important; max-height: 92vh !important; }
    .hf-modal.hf-modal-wide { width: 95vw !important; }
}

/* -- Scrollbar styling -- */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 3px; }

/* -- Chat transcript scroll -- */
.chat-transcript-scroll {
    max-height: calc(100vh - 280px) !important;
    overflow-y: auto !important;
    padding-right: 8px !important;
}

/* -- Hide Gradio block borders in content -- */
.content-area .block { border: none !important; box-shadow: none !important; }
.content-area .form { border: none !important; box-shadow: none !important; background: transparent !important; }

/* -- Compact dropdowns -- */
.content-area .wrap { gap: 4px !important; }

/* -- Prevent auto-scroll on HF Spaces -- */
html, body { scroll-behavior: auto !important; overflow-anchor: none !important; }
.gradio-container { overflow: visible !important; }

/* -- Fix group borders -- */
.group_container { border: none !important; box-shadow: none !important; background: transparent !important; }

/* -- Inbox 3-panel layout: visible separation -- */
.content-area > .group_container > .row {
    gap: 8px !important;
}

/* Chat messages grow to fill vertical space */
.chat-panel .chat-messages-slot {
    flex: 1 1 auto !important;
    min-height: 0 !important;
}

/* Pin send row to the bottom of the chat panel */
.chat-panel .chat-send-row {
    margin-top: auto !important;
    flex: 0 0 auto !important;
    padding: 8px 10px !important;
    gap: 6px !important;
    background: rgba(15,23,42,.55) !important;
    border-top: 1px solid rgba(255,255,255,.08) !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
}
.chat-panel .chat-send-row > * { margin: 0 !important; }
.chat-panel .chat-send-row .chat-send-input textarea,
.chat-panel .chat-send-row .chat-send-input input {
    min-height: 36px !important;
    height: 36px !important;
    padding: 6px 10px !important;
    resize: none !important;
}
.chat-panel .chat-send-row .chat-send-btn button {
    height: 36px !important;
    min-width: 72px !important;
    padding: 0 14px !important;
}
.chat-panel .chat-send-result {
    flex: 0 0 auto !important;
    padding: 0 10px 6px 10px !important;
}

/* Active Chats radio shares vertical space with Start New section below. */
.conv-list-panel .wa-conv-radio,
.conv-list-panel .wa-new-conv-radio {
    flex: 1 1 auto !important;
    min-height: 0 !important;
}

/* Small section titles + dividers inside the conv list */
.conv-list-panel .conv-section-title {
    font-size: 10px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    color: #64748b !important;
    margin: 4px 0 6px 2px !important;
}
.conv-list-panel .conv-section-divider {
    height: 1px !important;
    background: rgba(255,255,255,.06) !important;
    margin: 10px 0 !important;
    flex: 0 0 auto !important;
}
.conv-list-panel .conv-section-hint {
    font-size: 9px !important;
    color: #64748b !important;
    font-style: italic !important;
    margin: 4px 2px 0 2px !important;
}

/* -- WhatsApp Inbox rebuild (W02 April 2026) -- */

/* Panel 1 — header row (title + refresh icon) and refresh caption */
.conv-list-panel { overflow: hidden !important; }
.conv-list-panel .conv-header-row {
    flex: 0 0 auto !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
    gap: 6px !important;
    margin-bottom: 4px !important;
}
.conv-list-panel .conv-refresh-caption {
    flex: 0 0 auto !important;
    font-size: 9px !important;
    color: #64748b !important;
    font-style: italic !important;
    margin: 0 2px 8px 2px !important;
    line-height: 1.3 !important;
}
.conv-list-panel .conv-refresh-btn button {
    height: 28px !important;
    min-width: 36px !important;
    padding: 0 8px !important;
    font-size: 14px !important;
}

/* Two scroll regions inside Panel 1 — radio lists scroll, search boxes pinned */
.conv-list-panel .wa-active-scroll,
.conv-list-panel .wa-new-scroll {
    flex: 1 1 auto !important;
    min-height: 60px !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.04) !important;
    border-radius: 6px !important;
    padding: 4px !important;
    margin-top: 4px !important;
}
.conv-list-panel .wa-active-scroll { flex-grow: 3 !important; }
.conv-list-panel .wa-new-scroll    { flex-grow: 2 !important; }

/* Panel 2 — hide the inline gr.File (drop-zone moves into the modal) */
.chat-panel .chat-media-input { display: none !important; }
.chat-panel .chat-send-row .chat-send-input {
    flex: 1 1 0 !important;
    min-width: 0 !important;
}
.chat-panel .chat-attach-btn button,
.chat-panel .chat-attach-clear button {
    height: 36px !important;
    min-width: 36px !important;
    padding: 0 8px !important;
    font-size: 14px !important;
}
.chat-panel .chat-attach-chip {
    flex: 0 0 auto !important;
    padding: 4px 8px !important;
    background: rgba(99,102,241,.12) !important;
    border: 1px solid rgba(99,102,241,.3) !important;
    border-radius: 6px !important;
    font-size: 10px !important;
    color: #c7d2fe !important;
    max-width: 140px !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}

/* Attachment modal — show the gr.File only when inside the modal */
.wa-attach-modal { display: flex !important; flex-direction: column !important; gap: 10px !important; }
.wa-attach-modal .chat-media-input { display: block !important; }
.wa-attach-modal .wa-attach-actions { display: flex !important; gap: 8px !important; justify-content: flex-end !important; }

/* Panel 3 — flex column with fixed Past Activity, flex variables, capped preview */
.tools-panel { overflow: hidden !important; padding: 10px !important; }
.tools-panel .tp-activity-box {
    flex: 0 0 25% !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 6px !important;
    padding: 6px 8px !important;
    margin-bottom: 8px !important;
}
.tools-panel .tp-category,
.tools-panel .tp-template,
.tools-panel .tp-send-btn,
.tools-panel .tp-send-result { flex: 0 0 auto !important; }
.tools-panel .tp-vars-box {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    padding: 4px 0 !important;
}
.tools-panel .tp-preview-box {
    flex: 0 0 auto !important;
    max-height: 30% !important;
    overflow-y: auto !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-left: 2px solid rgba(34,197,94,.4) !important;
    background: rgba(34,197,94,.04) !important;
    border-radius: 6px !important;
    padding: 8px 10px !important;
    margin: 8px 0 !important;
}
.tools-panel .wa-var-slot { margin: 2px 0 !important; }
.tools-panel .wa-var-slot textarea,
.tools-panel .wa-var-slot input {
    min-height: 28px !important;
    height: 28px !important;
    font-size: 11px !important;
    padding: 4px 8px !important;
    resize: none !important;
}
.tools-panel .wa-var-slot label span {
    font-size: 9px !important;
    color: #94a3b8 !important;
}
"""


def _build_panel_css() -> str:
    """Render the three full-height sibling panels from layout.yml tokens.

    Kept as a function so schema changes fail loudly at import time and so
    tests can drive a mock engine if needed.
    """
    layout = get_theme_engine().panel_layout
    # Note: overflow-y intentionally NOT set on .conv-list-panel /
    # .tools-panel — both columns now manage their own internal scroll
    # regions (see wa_inbox.py rebuild). Setting it here would beat any
    # later override in _STATIC_CSS due to source-order cascade.
    return (
        "\n/* -- Full-height sibling panels (layout.yml) -- */\n"
        ".conv-list-panel, .tools-panel {\n"
        f"    background: {layout.BACKGROUND} !important;\n"
        f"    border: {layout.BORDER} !important;\n"
        f"    border-radius: {layout.BORDER_RADIUS} !important;\n"
        f"    padding: {layout.PADDING} !important;\n"
        f"    min-height: {layout.MIN_HEIGHT_EXPR} !important;\n"
        "    display: flex !important;\n"
        "    flex-direction: column !important;\n"
        "}\n"
        ".chat-panel {\n"
        f"    background: {layout.CHAT_BACKGROUND} !important;\n"
        f"    border: {layout.CHAT_BORDER} !important;\n"
        f"    border-radius: {layout.BORDER_RADIUS} !important;\n"
        "    padding: 0 !important;\n"
        f"    min-height: {layout.MIN_HEIGHT_EXPR} !important;\n"
        "    display: flex !important;\n"
        "    flex-direction: column !important;\n"
        "}\n"
    )


DASHBOARD_CSS = _STATIC_CSS + _build_panel_css()
