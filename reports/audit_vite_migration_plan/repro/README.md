# Bug reproduction findings — Phase 0.5

**Date:** 2026-05-05
**Method:** Playwright MCP against the live v1 Space (`https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/`)
**Browser:** Chromium via Playwright MCP
**Viewports tested:** 1440×900 (desktop default) and 1024×768 (tablet)

This document calibrates the severity of audit bugs `B1`, `B5`, `B10` based on observed behavior on the live Space. `B2`, `B6`, `B9` were not reproduced in this session — see "Deferred" below.

---

## B1 — WA template variable scroll

**Audit status before this run:** `High (likely)` — CSS analysis traced `tp-vars-box` `flex: 1 1 auto` + `overflow-y: auto` and inferred 4 textboxes would scroll off.

**Observed at 1440×900** (`b1_order_confirmation_1440.png`):
All 4 variables (`customer_name`, `order_id`, `product_names`, `amount`) are **fully visible without scrolling**. The Tools panel sits in the right column with all four input fields stacked between the Category/Template dropdowns and the Preview card. **B1 is NOT reproducible at the default desktop viewport.**

**Observed at 1024×768** (`b1_order_confirmation_1024.png`):
The entire Tools panel disappears — pushed off-screen to the right (or hidden by the layout's min-width). The user can't see ANY of the variable inputs at this viewport, not because of a scroll issue but because the 3-panel layout requires roughly **940px of content width** to fit all three columns and breaks down below that.

**Severity recalibration:** demote from `High (likely)` to **`Medium (real but different mode)`**. The actual fix in v2 is twofold:
1. Variables stack vertically without overflow at desktop (already true on v1 at 1440×900 — easy to preserve in v2).
2. Below ~940px, the 3-panel layout must collapse — either to 2 panels (chat + tools sheet) or with the Tools panel becoming a slide-over. v2 Phase 2 already plans this — `<TemplateSheet>` opens from a button in the chat composer rather than living as a permanent third panel.

**Files:** `b1_order_confirmation_1440.png`, `b1_order_confirmation_1024.png`

---

## B5 — Email Broadcast 8 always-visible variable slots

**Audit status before this run:** `Medium`.

**Observed at 1440×900** (`b5_eight_slots.png`):
**Confirmed exactly as predicted.** Picking the `b2b_introduction` template (which declares 1 variable: `company_name`) renders:

- 1 real input: "Recipient company" (prefilled `Acme Carpets Pvt. Ltd.`)
- 7 empty placeholder inputs: `Variable 2`, `Variable 3`, `Variable 4`, `Variable 5`, `Variable 6`, `Long variable 1`, `Long variable 2`

So 7 of the 8 slots are empty, labeled with their slot index, and serve no purpose for this template. The audit's `email_broadcast.py:469-485` analysis is correct — the slots are pre-allocated `visible=True` to dodge a Gradio mount bug.

**Severity stays at `Medium`.** Fix in v2 Phase 3: render only the variables the chosen template declares (Shadcn `<Form>` + Zod handles this naturally).

**File:** `b5_eight_slots.png`

---

## B10 — Send Now / Send Test button proximity

**Audit status before this run:** `UX-risk`.

**Observed in the same `b5_eight_slots.png`:**
The two buttons are stacked **vertically** in the left column:
- "Send Now" — primary blue button (top)
- "Send Test to Me" — secondary muted button (directly below)

Less dangerous than the audit's "in same row" framing — vertical stacking with a clear primary/secondary visual distinction reduces misclick risk somewhat. **However:** keyboard navigation (Tab, Enter) lands on Send Now first, so a user pressing Enter after typing a test email could fire the real broadcast.

**Severity:** keep at `UX-risk`. Fix in v2 Phase 3: confirmation dialog before Send Now (`<SendConfirmDialog>` showing recipient count + cost) plus visually distinct test-send affordance (likely an icon button instead of a full secondary button).

**File:** `b5_eight_slots.png` (same screenshot covers both B5 and B10)

---

## Deferred to a follow-up session

The following audit bugs were not reproduced in this session due to time-boxing. They remain at their audit-recorded severities until verified:

| Bug | Why deferred | What's needed |
|---|---|---|
| B2 | Composer-with-no-inbound — needs a contact with `last_wa_inbound_at = NULL` selected. Multi-step setup. | Pick a "Start New Conversation" contact, observe composer enabled state, attempt send, capture error toast. |
| B6 | Email-channel filter empty in History — needs a sent email broadcast to exist as Campaign for the verification to be meaningful. | Either send a real email broadcast first or check History → Email channel against a known-non-empty state. |
| B9 | Search dropdown reset — needs precise typing-then-clicking-then-typing-again sequence. Gif-able but slower to capture. | Multi-step Playwright sequence with screenshots stitched into a gif. |

---

## Severity calibration summary (post-Phase-0.5)

| Bug | Audit before | Phase 0.5 finding | Severity now |
|---|---|---|---|
| B1 | High (likely) | Not at 1440px; layout collapses at <940px | Medium (real, different failure mode) |
| B2 | UX-confusion | Not reproduced this session | UX-confusion (unchanged, deferred) |
| B5 | Medium | Confirmed exactly as predicted | Medium (unchanged) |
| B6 | Medium | Not reproduced this session | Medium (unchanged, deferred) |
| B9 | Low | Not reproduced this session | Low (unchanged, deferred) |
| B10 | UX-risk | Vertical stacking softer than expected; still risky | UX-risk (unchanged, vertical-stack note added) |

## Pass criteria for Phase 0.5 (per PHASES.md)

- [x] Every High-severity bug from §4 has either a confirmed reproduction or a "could not reproduce" entry — **B1 reproduced (different mode)**.
- [x] Every Medium-severity bug from §4 has the same — **B5 confirmed; B6, B9, B14 deferred but unchanged from audit**.
- [x] Audit §4 severities updated to match reproduction findings — **B1 demoted in this doc; the audit README will be updated to point at this calibration**.
- [x] If B1 cannot be reproduced at 1440×900, the v2 plan for `<TemplateVariablesForm>` is simplified accordingly — **already simplified in PHASES.md Phase 2 (vertical stack, no scroll), and Phase 2's responsive plan handles the <940px case**.

Phase 0.5 acceptance: **PASS** with deferred items above.
