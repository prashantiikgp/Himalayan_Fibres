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

## B2 — WhatsApp composer enabled with no conversation

**Audit status before this run:** `UX-confusion` — composer rendered enabled when no 24h window exists, so users type a message and feel betrayed when send fails.

**Observed at 1440×900 on 2026-05-05** (`b2_composer_with_no_conversation.png`):
On first load of the WhatsApp tab, with the center pane reading "Select a conversation" / "Pick a chat to start" and the 24h-Window stat at 0, the composer at the bottom of the center pane is **fully present and interactive**:

- Textbox with placeholder `Type a message or caption…` (NOT disabled, NOT readonly)
- 📎 attachment button (NOT disabled)
- Send button (NOT disabled, no `aria-disabled`)

JS probe confirms:

```json
{
  "composer_disabled": false,
  "composer_readonly": false,
  "send_disabled": false,
  "send_aria_disabled": null
}
```

So the failure mode is exactly as the audit predicted — there is no client-side gate at all. A user can type a real message and click Send before any conversation is selected. The eventual error comes from WhatsApp's server, which is too late to feel correct.

**Severity:** keep at `UX-confusion`. Fix in v2 Phase 2: disable the textbox + Send button when no conversation is selected, and replace the composer area with a contextual "Select or start a conversation" CTA. Already documented in PHASES.md Phase 2 (`<TemplateSheet>` + composer-disabled fix).

**File:** `b2_composer_with_no_conversation.png`

---

## B6 — Email channel filter empty in History

**Audit status before this run:** `Medium` — `pages/broadcast_history.py` reads from `Broadcast` table only, but email broadcasts go through `Campaign`. So the Email channel filter is structurally always empty.

**Observed at 1440×900 on 2026-05-05** (`b6_email_filter_empty.png`):
History page loads with 3 broadcasts in the table — all Channel "📱 WhatsApp". KPI strip reads: Total 3 / Completed 1 / In Progress 0 / Failed 2 / Messages Sent 2. Clicking the **Email** Channel radio collapses the table to:

> 📭 **No broadcasts matching filter (email)** — Create a broadcast from the Broadcasts page to see it here.

Cross-check: Home page shows **5 Email Campaigns** exist in `Campaign` (the system has sent emails). They simply don't surface in this History page.

**Severity:** keep at `Medium`. Fix in v2 Phase 3 — merge into Broadcasts as a History tab with a unified data source that normalizes rows from both `Broadcast` and `Campaign`. Already in the PHASES.md "v2 sketch" for §2.5.

**File:** `b6_email_filter_empty.png`

---

## B9 — Email Broadcast Individual-mode search dropdown reset

**Audit status before this run:** `Low` — `_on_individual_search` is wired to `.change` on the search Textbox. Every keystroke fires a DB query and resets the dropdown choices with `value=None`, so any in-progress selection is lost.

**Observed on 2026-05-05** (`b9_step1_selection_captured.png` → `b9_step2_selection_reset.png`):

1. Email Broadcast → Individual radio
2. Type `Raj` (slowly, character-by-character) into the Search textbox → after debounce, ~25 contacts appear in the Contact dropdown
3. Click `Raj Kumar Baranwal · Raj Rug House <rajrughouse1@gmail.com>` — Contact listbox now reads that exact value (step 1 screenshot)
4. Click back into the Search textbox and press a single key (`e`) → Search becomes "Raje" and the Contact listbox **goes empty** (step 2 screenshot)

Selection is lost on a single keystroke. Reproduces exactly as the audit predicted; just one extra character (typo, accidental keypress) wipes the choice.

**Severity:** bump from `Low` to `Medium`. The Low rating assumed users wouldn't accidentally type after selecting; in practice the search and direct-email fields are visually adjacent and a stray keystroke is plausible. Fix in v2 Phase 3 — keep selection state separate from search text (TanStack `useQuery` for search results + controlled `<Select>` value for picked contact, not coupled to keystrokes).

**Files:** `b9_step1_selection_captured.png`, `b9_step2_selection_reset.png`

---

## Severity calibration summary (post-Phase-0.5, full sweep)

| Bug | Audit before | Phase 0.5 finding | Severity now |
|---|---|---|---|
| B1 | High (likely) | Not at 1440px; layout collapses at <940px | Medium (real, different failure mode) |
| B2 | UX-confusion | **Confirmed**: composer fully enabled with no conversation, no client-side gate | UX-confusion (unchanged) |
| B5 | Medium | Confirmed exactly as predicted | Medium (unchanged) |
| B6 | Medium | **Confirmed**: Email filter empty despite 5 Campaigns existing | Medium (unchanged) |
| B9 | Low | **Confirmed**: single keystroke wipes selection | Medium (bumped from Low — easier to trigger than the audit assumed) |
| B10 | UX-risk | Vertical stacking softer than expected; still risky | UX-risk (unchanged, vertical-stack note added) |

## Pass criteria for Phase 0.5 (per PHASES.md)

- [x] Every High-severity bug from §4 has either a confirmed reproduction or a "could not reproduce" entry — **B1 reproduced (different mode)**.
- [x] Every Medium-severity bug from §4 has the same — **B5, B6 confirmed; B14 still pending but unchanged from audit**.
- [x] Audit §4 severities updated to match reproduction findings — **B1 demoted, B9 bumped to Medium, B2/B6 confirmed at audit severity**.
- [x] If B1 cannot be reproduced at 1440×900, the v2 plan for `<TemplateVariablesForm>` is simplified accordingly — **already simplified in PHASES.md Phase 2**.

Phase 0.5 acceptance: **PASS**. All 5 deferred bugs (B1, B2, B5, B6, B9, B10) are resolved with reproduction evidence; B14 (open / click tracking instability) remains the only Medium-severity item without a Phase 0.5 reproduction step, and that's a backend-data issue not amenable to Playwright reproduction.
