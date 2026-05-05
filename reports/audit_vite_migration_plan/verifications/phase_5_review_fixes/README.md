# Live Playwright verification — review fixes #1–5 + audit bugs

**Date:** 2026-05-05
**Live URL:** https://prashantiitkgp08-himalayan-fibrer-v2.hf.space/
**Method:** Playwright MCP, viewport 1440×900, signed in with `APP_PASSWORD=test`.

This run drove the live v2 Space end-to-end after the review-fix commit
landed (`2f18561`). Each artifact below shows the relevant fix
rendering against real production data.

## Verified

| File | What it verifies |
|---|---|
| `verify-review-fix-2-kpi-math.png` | **Review fix #2** — Performance tab KPI strip now reads `Sent: 817/817 (100%)` / `Failed: 0 (0%)` / `Pending: 0 (0%)` with honest math. Previously `100 - sent_pct` conflated unprocessed recipients with failures. |
| `verify-b3-audience-funnel-sticky.png` | **B3** — sticky `Targeting **1542** recipients in **all_opted_in**` header at top of Compose with 5-counter strip + Lifecycle/Country/Consent chips. Re-renders as filters change. |
| `verify-b10-send-confirm-dialog.png` | **B10** — SendConfirmDialog gates Send Now with recipient count + cost + segment + template recap and a `Type SEND to confirm` field. Send Now button stays disabled until SEND is typed. |
| `verify-phase-3.1b.2-schedule-sheet.png` | **Phase 3.1b.2 ScheduleSheet** — datetime-local picker reads `Sending **1542** recipient(s) using template b2b_introduction. The scheduler checks every minute…`. Default value is +1 hour rounded to the next minute. |
| `verify-review-fix-4-confirm-dialog.png` | **Review fix #4** — Sync-from-Meta now opens a styled Shadcn `<ConfirmDialog>` instead of a `window.confirm()`. Same pattern is wired for Submit-to-Meta and Delete-draft. |

## Verified by snapshot inspection (no screenshot)

| Bug / Fix | Evidence |
|---|---|
| **B6** — History Email filter empty in v1 | `/broadcasts?tab=history` returns 8 unified rows (5 Email + 3 WhatsApp); filtering Channel=Email returns exactly 5 Email rows. v1 returned zero because it only read the `broadcasts` table. |
| **B11** — sidebar reorganized | WhatsApp group (Inbox / Broadcasts / Templates) and a separate Email group (Broadcasts) both live in the rendered sidebar nav. Clicking the Email entry deep-links to `/broadcasts?tab=compose&channel=email`, and ComposeTab's URL-driven channel toggle correctly highlights Email on arrival. |
| **B12** — template counts from DB | Home page shows `Email Templates: 11` and `WA Templates: 16` from `dashboard/home` instead of v1's hardcoded "7 email, 13 WA". |
| **Phase 4.0 + 4.1a** — Templates list with drafts | `/wa-templates` lists 33 templates (was 16 with approved-only) including drafts with a DRAFT pill, tier label, category, language. |

## Not exercised in this run

- B13 — email queue + JobStore: the seeded data set has no in-flight email broadcasts. Tested at the API level with stubbed `WhatsAppSender` in pytest (`test_queue_email_broadcast_returns_job_id`).
- B16 — virtualized recipient list: the 817-recipient broadcast (`em-4`) doesn't have `EmailSend` rows linked back via `campaign_id` because v1's pre-Plan-D send loop didn't always store it. Tested at the API level with seed-and-paginate-7-rows in pytest (`test_recipients_pagination_email`).
- Submit-to-Meta + actual Sync execution: would hit live Meta WABA API. Tested at the API level with `monkeypatch.setattr(WhatsAppSender, ...)` stubs.
- Real broadcast send: kept dialogs cancelled — sending to 1542 recipients is a production action we don't fire from a verification script.

## Pass criteria

- [x] B3 (audience funnel sticky) — visible
- [x] B6 (history Email filter) — returns email rows
- [x] B10 (send confirm with type-SEND) — modal opens, Send Now disabled until SEND
- [x] B11 (sidebar reorg) — separate WhatsApp + Email groups
- [x] B12 (template counts from DB) — 11 + 16 surfaced on Home
- [x] Phase 3.1b.2 ScheduleSheet — datetime-local picker functional, future-only validation
- [x] Review fix #2 (KPI math) — Sent/Failed/Pending split honest
- [x] Review fix #4 (ConfirmDialog) — Shadcn dialog used everywhere
- [x] No console errors on any page (verified via Playwright snapshot — no error events surfaced)

Live verification: **PASS**.
