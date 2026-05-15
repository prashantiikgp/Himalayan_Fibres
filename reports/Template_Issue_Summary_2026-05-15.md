# Email Template Issue Summary & Remediation Plan

**Source:** `reports/Gmail & Whatsapp testing.pdf` (114 pages, tester review of every Gmail template, sent to "Rohit")
**Compiled:** 2026-05-15
**Status:** Issues catalogued + root-cause investigation done (see § F)

---

## F. Root-cause findings (code + live audit, 2026-05-15)

**Critical context: the report most likely predates commit `55e2e0b` (2026-05-11, "fix(email): kill duplicate-send false positive + Gmail render polish") being live.** That commit already targeted three of the biggest report themes. So part of the report may already be fixed — must re-test live before re-fixing.

- **B1 duplicate-send — ALREADY FIXED in code (`55e2e0b`).** `api_v2/routers/email_send.py:174` now includes `template_id` in the idempotency key (`generate_idempotency_key("single_send", contact.id, str(req.template_id))`), and failed rows now retry in place. The exact reported scenario (Order Delivered → Order Shipped blocked) is addressed. **Action: re-test live to confirm deployed, then close.** Caveat: broadcast/flow engines key on broadcast/flow id (not template_id) — lower risk, but note.
- **A2 broken images — REAL & CONFIRMED TODAY.** Live HEAD-check of all 55 image URLs in `hf_dashboard/config/email/shared.yml`: **7 return HTTP 400 (dead)**. These exactly match the report's broken-image complaints:
  - `Nettle Wool Collection/Burberry Series/1. Burberry Series.webp`
  - `Nettle Wool Collection/Burberry Series/2. Top View.webp`
  - `Nettle Wool Collection/Burberry Series/3. Close Up Image.webp`
  - `Nettle Wool Collection/Noor Series/Noor_Main.webp`
  - `Nettle Wool Collection/Noor Series/noor_Silver.webp`
  - `Plant Based/1.2 Nettle Yarn/1.2.4 Special Nettle Yarn/ERB Sepcial_1.webp`
  - `Plant Based/2.1 Hemp Fibre/2.1.1 Raw Hemp Fibre/Display.webp`
  - The other 48 URLs return 200 and use the same encoding scheme → not an encoding bug; these 7 objects no longer exist in the `wa-template-images` bucket. **Likely cause: commit `24ca013` "clean wa-template-images bucket" removed/renamed these.** Drives the broken Signature/Collections (Burberry, Noor), the 3rd Nettle "Three grades" image, and Hemp fibre display. **Action: re-upload these 7 (or repoint shared.yml to the surviving objects).**
- **A1/A3 footer & icons — `55e2e0b` did "Gmail render polish".** Social icons were rehosted off icons8 (Gmail image-proxy breakage) → public Supabase, bumped to 40×40, centered via `font-size:0`+inline-block, dark-mode bg fixes. Footer contact block is centered `<p>` with emoji + `<em>` text. **The report's footer complaints may be pre-`55e2e0b`; must re-test live to see if A1 is still real or already resolved.**
- **Image infra is otherwise sound:** absolute public Supabase HTTPS URLs, single source of truth in `shared.yml`, no cid/base64/relative paths. The architecture is fine — only specific dead objects are the problem. (Banner uses a 1-year *signed* URL — flag for future expiry, not urgent.)

**Net:** the "big infra" worry is smaller than feared. A2 reduces to **re-uploading 7 files**. B1 is **already fixed in code**. A1 may be **already polished**. The remaining real work concentrates on the **B-bugs (broken CTA links/buttons, GST column, recipient variable), A5 copy rewrites, and A6 spacing** — pending a live re-test to separate "already fixed" from "still broken".

---

## G. Wave 0 live-triage results (2026-05-15, baseline `55e2e0b` deployed)

Triaged via the **Email Broadcast → Preview iframe** (renders real template HTML, zero side effects). Faster and more decisive than test-sends for content/structure bugs. Gmail-client-specific items (real-Gmail footer alignment, image proxy) + B1 still need a real send.

| Issue | Template(s) checked | Live verdict |
|---|---|---|
| **A2** broken images | `collections_focus` | 🔴 **STILL BROKEN.** Burberry hero renders as alt-text only + large empty gap below. Banner (signed URL) renders fine. Confirms the 7-dead-URL audit. |
| **B5** Proforma PDF button missing | `proforma_invoice` | 🔴 **STILL BROKEN.** Body says "one-click download button below the summary" + "stamped PDF is attached" but there is **no button/link** between summary and signature. |
| **B6** GST/Tax column missing | `proforma_invoice` | 🔴 **STILL BROKEN.** Summary = Subtotal / Courier (estimated) / Total due. No GST line. |
| **B7** "Dear Himalayan Fibres," | `sustainability` | 🔴 **STILL BROKEN.** Renders `Dear **Himalayan Fibres**,` — `company_name` bound to sender. Confirms it's a context-layer bug (template var is correct). |
| **B8** risky claims | `sustainability` | 🔴 **STILL PRESENT.** "73% (European Textile Council 2024)", "Carbon-Negative Production", "climate-positive", "buyers love to tell", "future of sustainable textiles" all render. |
| **B9** "Fibers" spelling | `sustainability` (heading "Why Himalayan **Fibers** Meet…") | 🔴 **STILL PRESENT** — and wider than first thought (not just welcome templates). |
| **B10** truncated `"Let'"` ending | `sustainability` | 🟢 **NOT REPRODUCING.** Renders complete: "Let's discuss how our fibers can help you win more export orders." Likely already fixed — drop from scope pending final regression. |
| **A1** footer icon↔text "disconnected/far-left" | `collections_focus`, `proforma_invoice`, `sustainability` | 🟡 **LIKELY ALREADY IMPROVED.** Current footer is a **centered inline-emoji text block** (`📍 Address:` / `📧 … | 📞 …` as `<em>`), not a broken icon-image-vs-centered-text split. The report's "icons too far left, rows disconnected" almost certainly describes the pre-`55e2e0b` build. Needs one real-Gmail check to close, but structurally the reported defect is gone. |

**Wave 0 net:** the **functional bugs are confirmed real on the current build** (A2, B5, B6, B7, B8, B9) → Wave 1/2 proceed as planned. **B10 is already fixed.** **A1 is likely already resolved** by `55e2e0b` (down-scopes Wave 3 substantially) — pending one real-Gmail confirmation.

> **⚠️ Initial triage ran on deprecated v1; RE-CONFIRMED on v2** (`Prashantiitkgp08/Himalayan_Fibrer_v2`) on 2026-05-15 via `POST /api/v2/email/render-preview` (Bearer auth). Focus is **v2 only**.

### v2-confirmed verdicts (render-preview, 10 templates)

| Issue | v2 status | Evidence |
|---|---|---|
| **A2** broken images | 🔴 **REAL on v2** | Rendered HTML references dead URLs returning HTTP 400: `collections_focus` (Burberry Series 1, Top View 2, Noor_Main), `nettle_focus` (ERB Sepcial_1), `hemp_focus` (Display.webp). Social icons (wa/ig/fb png) all 200 → **A3 social icons OK on v2**. |
| **B5** Proforma PDF button | 🔴 **REAL on v2** | Body says "one-click download button below the summary" but no download/PDF anchor exists in the render. |
| **B6** GST/Tax column | 🔴 **REAL on v2** | No `gst`/`tax` markup in `proforma_invoice` template. |
| **B7** "Dear Himalayan Fibres," | 🔴 **REAL on v2** | `Dear <strong>Himalayan Fibres</strong>` in `sustainability` **and** `tariff_advantage` — `company_name` bound to sender. Context-layer bug confirmed. |
| **B8** risky claims | 🔴 **REAL on v2** | `sustainability` renders 73% / Carbon-Negative / climate-positive / "buyers love to tell" / "future of sustainable textiles". |
| **B9** "Fibers" misspelling | 🔴 **REAL on v2, wider than reported** | "Himalayan Fibers" in `sustainability` ×3, `tariff_advantage` ×1, `welcome_final` ×2 (report only flagged welcome templates). |
| **B10** truncated `"Let'"` | 🟢 **FIXED on v2** | Ends complete: "Let's discuss how our fibers can help you win…". Drop from scope (regression-verify only). |
| **B2/B3/B4** broken/missing CTAs | 🟡 **consistent with report** | No feedback/catalog/sample-request anchors found by text marker in `order_delivered_feedback` / `nettle_focus` / `sample_invitation` — matches "not visible / dead". Exact cause pinned in the Wave 2 code traces (#6–#8). |
| **A1** footer alignment | ⏳ pending | Real-Gmail visual check folded into the B1 test-send email (#3). Structurally still the centered inline-emoji `<em>` block (no broken icon/text split) → likely already improved. |

**B1 re-test on v2 (`POST /api/v2/email/test-sends`, contact 06412435 → prashant.mine@gmail.com):**
- `order_delivered_feedback` → ✅ sent (id 50)
- `order_shipped` (different template, same contact, same day) → ✅ **sent (id 51), NOT blocked** — the exact reported failure scenario
- repeat `order_delivered_feedback` → ✅ correctly deduped ("already sent earlier today", returns id 50, no resend)
- **B1 = FIXED on v2.** Close it (regression-verify only).

**NEW — B12 (found during B1 test):** `post_sample_followup` render **hard-crashes**: `Render failed: 'fibre_sent' is undefined`. Templates lack default guards for required variables → a send with missing vars 500s instead of degrading. Add to Wave 2. Likely affects other templates with required vars (audit needed).

**Real-Gmail check (ids 50/51 read back from prashant.mine@gmail.com inbox):**
- **A1 footer → RESOLVED on v2.** Delivered footer is a clean centered block: `📍 Address: …` / `📧 … 📞 …` / policy links — emoji adjacent to its text. The report's "icons far-left / disconnected" pattern is gone (pre-fix v1 artefact). Down-scope Wave 3 to A4/A6 only.
- **B2 — NOT reproducing on v2 (earlier "pinned" was a false alarm).** I first read it off Gmail's *plaintext* body, which strips `mailto:` when linkifying. The **rendered HTML href is correct**: `mailto:info@himalayanfibres.com?subject=…` (verified in render-preview output; template `order_delivered_feedback.html:23` + `cta_button` macro both emit `mailto:`). Code comment there: *"Interim: mailto until /reviews page lives on the Wix site"* — intentional. The report's "→ 404" was the deprecated v1 build. **B2 = resolved on v2**; a real reviews page is a separate product backlog item, not a remediation bug. **Lesson: verify links via render-preview HTML, never Gmail plaintext.**

### Wave 0 FINAL (v2, 2026-05-15)

| Verdict | Issues |
|---|---|
| ✅ **Already fixed / not reproducing on v2** (regression-verify only) | **B1** duplicate-send, **B10** truncated ending, **A1** footer alignment, A3 social icons, **B2** (valid `mailto:` interim — v1 artefact) |
| 🔴 **Confirmed real on v2** | **A2** (7 dead images), **B5** (no Proforma PDF button), **B6** (no GST line), **B7** (`Dear Himalayan Fibres`), **B8** (risky claims), **B9** ("Fibers" — welcome_final, sustainability, tariff) |
| 🆕 **New** | **B12** — render hard-crashes on missing required var (`post_sample_followup` → `'fibre_sent' is undefined`); audit other templates |
| 🟡 **Await Wave 2 trace** | **B3** (catalog button), **B4** (sample/catalog CTA visibility) |

**Wave 0 complete.** Net effect: Wave 3 shrinks to A4+A6 (A1 done); B1/B10/**B2** drop to regression-only; Wave 2 gains B12. Active Wave 2 set: **B5, B6, B7, B9, B12** + B3/B4 traces. B8 is copy (Wave 4). Proceed to Wave 1 (7 images — needs originals) and Wave 2.

---

## (original catalogue below)

> Page numbers below refer to the PDF so screenshots can be cross-referenced.
> Many templates were reviewed twice: once for **UI/rendering** and once for **content/tone**. Both passes are merged per template here.

---

## A. Cross-cutting issues (fix once, applies to almost every template)

These are the highest-leverage fixes — each appears in nearly every template, so they belong in shared partials/infra, not per-template edits.

| # | Issue | Where it shows | Root-cause hypothesis |
|---|-------|----------------|------------------------|
| **A1** | **Footer contact icons mis-aligned with text** — icons sit far left, text is center-aligned separately, rows visually disconnected, uneven spacing | ~Every template (Hemp, Price List, Proforma, Sample Invitation, Sample Shipped, Nettle, Signature, Tibetan, Yarn Lineup, Story, Day-14, Order Confirmation, Order Delivered, Order Flow, Order Shipped, Post-Sample, Sample Flow, Sample Ack, Welcome ×4, Winback) | Shared footer partial uses a layout that breaks in Gmail (likely flex/float that Gmail strips). Needs a table-based icon+text row. |
| **A2** | **Broken / missing images** — broken-image placeholder, empty white space where image should be | Hemp (img-3), Price List (post-banner section), Proforma (footer icons), Sample Invitation (3rd "Blend" image), Sample Shipped (footer icons), Nettle (3rd of "Three grades"), Signature (multiple), Yarn Lineup (Signature blends), Story (post-hero + beside-text), Day-14 (both sections), Welcome Day-3 (multiple), Winback (hero) | Image hosting/URL or bucket permission problem; possibly hot-linking a source Gmail blocks, or a path that 404s. Needs a single hosting/CDN audit. |
| **A3** | **Footer/contact icons not rendering** (broken icon glyphs, not just misaligned) | Proforma, Sample Invitation, Sample Shipped, others | Icon source (font/SVG/remote PNG) not Gmail-safe. Use hosted PNGs with absolute https URLs + alt text. |
| **A4** | **WhatsApp / CTA buttons oversized** relative to body | Price List, Proforma, Order Shipped ("TRACK SHIPMENT"), general note | Shared button style: reduce height, padding, font size/weight, width. |
| **A5** | **Content tone too casual / D2C-artisan for B2B carpet exporters** | Hemp, Order Flow Step 1, Post-Sample, Sample Invitation, Sample Ack, Welcome New Subscriber, Welcome Final, Welcome Production, Welcome Day-3, Winback, (Sustainability & Tariff partly) | Copy was written D2C. Needs B2B/export rewrite — specific line-by-line replacements given in report (captured per template below). |
| **A6** | **Excessive empty whitespace / image-text proportion imbalance** in image-beside-text sections | Nettle, Tibetan, Day-14, Story, Price List, Order Delivered | Layout: reduce image size or expand content, collapse empty containers when image missing. |

---

## B. Bug / functional issues (not cosmetic)

| # | Issue | Template(s) | Pages | Notes |
|---|-------|-------------|-------|-------|
| **B1** | **"Duplicate, already sent today" blocks a *different* template** — sent Order Delivered, then Order Shipped / Post-Sample Follow-up was blocked as duplicate | Sender logic (affects all) | 16–20 | ⚠️ Possibly already addressed by commit `55e2e0b` "kill duplicate-send false positive" — needs confirmation whether this report predates that fix. Also reported again under Proforma ("already sent earlier today" blocks resending a corrected invoice). |
| **B2** | **"Share Your Feedback" button → 404 page** | Order Delivered – Feedback Request | 7–13 | Link target broken / route missing. |
| **B3** | **"SEE THE FULL CATALOG" button does nothing** | Campaign Nettle yarn | 39–41 | Catalog link missing/broken. |
| **B4** | **"Sample Request" & "Catalog" buttons not visible** | Onboarding Day-14, Sample Invitation Free Sample CTA | 53–55, 72–75 | CTA missing/hidden in render. |
| **B5** | **PDF download button not visible** though email says "one-click download below" | Transactional Proforma Invoice | 27–33, 93–97 | Stamped-PDF download CTA absent in received email. |
| **B6** | **GST / Tax column missing** from invoice breakdown (only Subtotal, Courier, Total) | Proforma Invoice, Order Confirmation | 28, 57, 94 | Add `GST/Tax Amount` line → Subtotal / GST / Courier / Grand Total. |
| **B7** | **Wrong recipient variable — "Dear Himalayan Fibres,"** (greeting addresses the sender, not the buyer) | Sustainability Compliance, Tariff Advantage | 80, 85 | Template var bug — should be `{{customer_name}}` / `{{company_name}}`. |
| **B8** | **Compliance/legal-risky claims** — unverifiable "73% (European Textile Council 2024)", "Carbon-Negative Production", "climate-positive", "Compliance Risk – None", "15–25% cost advantage" | Sustainability Compliance, Tariff Advantage | 81–87 | Soften to non-absolute, non-certified wording (report gives exact safer phrasings). |
| **B9** | **Brand spelled "Fibers" instead of "Fibres"** | Welcome Final, Welcome Production | 107, 113 | Global string fix. |
| **B10** | **Incomplete trailing text — email ends with `"Let'"`** | Sustainability Compliance | 82 | Truncated content. |
| **B11** | **Time-relative copy will go stale** — "Three days ago you joined our list" breaks if sent manually/late | Welcome Day-3 Sustainability Story | 103–105 | Replace with evergreen phrasing. |

---

## C. Per-template breakdown

### Campaign — Hemp Yarn (pp. 3–6; screenshots pp. 5)
- Banner image + product look **repetitive**, not appealing [A6].
- Image-3 **not loading** [A2].
- Footer + WhatsApp button **not rendering correctly** [A1/A3/A4].
- English **too complex** for Indian carpet exporters [A5].
- "design partner, Auroville" → must be **changed to our client name**.
- Content doesn't appeal to Indian carpet exporters; **emphasise yarn applicability & functionality**.

### Order Delivered – Feedback Request (pp. 7–13; screenshots pp. 9–12)
- Icons/images **not displaying** [A2/A3].
- Icon ↔ text **misaligned** [A1].
- **"Share Your Feedback" button → 404** [B2].

### Error — Duplicate send across different templates (pp. 16–20)
- Sending Order Shipped after Order Delivered → blocked "Duplicate, already sent today" [B1].
- Same with Post-Sample Follow-up — different template/flow still blocked [B1].

### Transactional — Price List Share (pp. 21–26 UI; pp. 88–92 content; screenshots pp. 23–24)
- Image/content section after main banner **broken** (desktop + mobile) [A2].
- Social icons (WA/IG/FB) **mis-aligned**, uneven spacing — desktop only; mobile OK [A1].
- Excessive blank space above "Our current yarn price list" [A6].
- ✅ "Download the Price List (PDF)" button **works correctly**.
- WhatsApp button slightly oversized [A4].
- Content: replace "Quick note" → "Please find attached our current yarn price list…"; "worth saying out loud" → "A few important details:"; "Most are doable" → "Most customizations can be accommodated."; remove "book a call below" if no booking CTA; keep "rates may shift slightly with the new harvest" [A5].

### Transactional — Proforma Invoice (pp. 27–33 UI; pp. 93–97 content; screenshots pp. 29–32)
- **GST/Tax column missing** [B6].
- **PDF download button not visible** [B5].
- Footer/content icons **broken** [A3].
- "already sent earlier today" blocks resending a corrected invoice [B1].
- Footer alignment broken [A1]; WhatsApp button large [A4].
- Content: "Courier (estimated)" → "Courier Charges" unless genuinely unfinalized; "Once payment lands" → "Once payment is received"/"Upon payment confirmation"; consider adding payment terms / bank details / GSTIN / dispatch-after-payment.

### Sample Invitation – Free Sample CTA (pp. 34–36 UI; pp. 72–75 content)
- 3rd product image "Blend — Signature collections" **broken** [A2].
- Footer icons broken/mis-aligned [A1/A3].
- **Sample Request CTA button not visible** [B4].
- Keep all 3 category images equal size, consistent titles/spacing [A6].
- Content too casual: "small yarn-spinning project", "feel right in your hand", "That's not us", "No high-pressure follow-up" → report provides a full refined B2B rewrite [A5].

### Sample Shipped – Tracking (pp. 37–38)
- Footer location/email/phone icons **broken/partial** — only placeholders visible [A3/A1].

### Campaign — Nettle Yarn (pp. 39–41)
- Excessive empty space above & below text in image-beside-content section [A6].
- 3rd image of "Three grades, four uses" **not loading** [A2].
- **"SEE THE FULL CATALOG" button not working** [B3].
- Icon ↔ text mis-aligned [A1].

### Campaign — Signature Collections Focus (pp. 42–44)
- Image after hero **not displaying**; image beside text **missing**; 1st & 2nd collection images broken [A2].
- Icons mis-aligned with text below [A1].

### Campaign — Tibetan Wool Yarn (pp. 45–47)
- Image oversized vs text in 2 sections — unbalanced [A6].
- Footer icons higher than text — mis-aligned [A1].
- ✅ Content/tone is good and premium — **no content changes needed**, UI only.

### Campaign — Yarn Lineup Overview (pp. 48–50)
- "Signature blends — Burberry, Noor, Snow White" image **not displaying** (desktop) [A2].
- Footer icon ↔ text mis-aligned — **desktop only**, mobile OK [A1].

### Campaign — Story / Customer Case Study (pp. 51–52)
- Image after hero **not displaying**; image beside text **missing** [A2].
- Footer icon ↔ text mis-aligned [A1].

### Onboarding — Day 14, First Order Nudge (pp. 53–55)
- Images beside text **not displaying** (both sections) [A2].
- Excessive empty gap after sections — unbalanced [A6].
- **"Sample Request" & "Catalog" buttons not visible** [B4].
- Footer mis-aligned [A1].

### Order Confirmation (pp. 56–57)
- **Add GST/Tax line** in invoice summary (Subtotal / GST / Shipping / Total) [B6].
- Footer icon ↔ text mis-aligned [A1].
- Otherwise good.

### Order Delivered – Feedback Request (content pass) (pp. 58–60)
- Too much gap after "We hope your order from Himalayan Fibres" — reduce [A6].
- Footer alignment [A1].
- Otherwise fine.

### Order Flow Step 1 – In Preparation (pp. 61–63)
- "Looking forward to hearing how the yarn feels in your hands" reads D2C/craft — make B2B [A5].
- Footer alignment [A1].

### Order Shipped – Tracking (pp. 64–65)
- "TRACK SHIPMENT" button oversized — reduce height/padding/font/width [A4].
- Footer alignment [A1].
- Suggested: add summary line "Your parcel has been handed over to the courier and is now in transit."; more spacing between social icons & divider; footer address text compressed — improve line-height [A6].

### Post-Sample Follow-up – "How did it feel?" (pp. 66–68)
- Tone too casual: "did the fibre feel right" (emotional), "Some folks want" (informal), "No pressure either way" (salesy) — report gives full refined B2B version [A5].
- Footer alignment [A1].

### Sample Flow Step 1 – Swatch Preparation (pp. 69–71)
- Content largely OK (B2B sample/dispatch copy).
- Footer alignment [A1].

### Sample Request – Acknowledgment (pp. 76–78)
- Casual lines: "Quick note", "Big enough to feel and to swatch with", "What we'll ask afterward", "No high-pressure follow-up", "felt right" — refined version provided [A5].
- Footer: icons disconnected from text, center-aligned content vs far-left icons, uneven [A1].

### Sustainability Compliance (pp. 79–83)
- **"Dear Himalayan Fibres," — wrong recipient variable** [B7].
- **Risky claims**: "73% (European Textile Council 2024)", "Carbon-Negative Production", "climate-positive", "Your buyers love to tell", "The future of sustainable textiles" — soften (safer wordings provided) [B8].
- **Email ends with truncated `"Let'"`** [B10].
- Reduce emoji-heavy CTAs; add clean CTA block (Download Technical Catalogue / Request Sustainability Documentation / Schedule Sample Dispatch).
- Footer alignment [A1]. (Noted as one of the strongest drafts overall.)

### Tariff Advantage (pp. 84–87)
- **"Dear Himalayan Fibres," — wrong recipient variable** [B7].
- Soften claims: "15–25% cost advantage", "meet international eco-standards", "Compliance Risk — None", "command higher prices", "Perfect for" [B8].
- "Did you know?" yellow box — text dense, increase line-spacing/padding.
- Subject "New Trade Tariffs?" feels fear-based — premium alternatives suggested.
- Footer alignment [A1].

### Welcome — New Subscriber (pp. 98–101)
- Footer icons far left, content centered, disconnected, uneven [A1].
- Casual lines: "small workshop", "conscious brands", "build something beautiful", "Take a look at our catalogue", "popular across Europe and the US" — B2B rewrites provided [A5].
- ✅ "EXPLORE OUR PRODUCTS" button is well-sized here.

### Welcome — Day 3 Sustainability Story (pp. 102–105)
- Multiple images **broken** → empty white space [A2].
- Footer alignment [A1].
- Replace several lines with B2B/evergreen phrasing, incl. "Three days ago you joined our list" → evergreen [A5/B11].

### Welcome — Email Final (pp. 106–108)
- "Fibers" → "Fibres" [B9].
- Replace "Thanks for signing up…", "Let us know what you're planning to build…", "crafted for conscious brands and export-ready markets.", "popular across Europe and the US." with B2B versions [A5].
- Footer spacing still needs balancing [A1] (cleaner than older templates).

### Winback — 60-Day Silent (pp. 109–111)
- Image **broken** [A2].
- Replace "Quick honest note" → "Quick update"; "No pitch coming" → "Just wanted to share a brief update"; "If not, also fine — no follow-up after this." → B2B reconnect line [A5].
- Footer alignment [A1].

### Welcome — Email Production (pp. 112–114)
- ✅ Cleaner & better aligned than older templates; footer significantly improved.
- Social icons below CTA not perfectly horizontal — minor spacing [A1].
- "Fibers" → "Fibres" [B9]; same B2B copy replacements as Welcome Final [A5].

---

## D. Remediation order (corrected — superseded by the 6-wave plan)

> Reconciled 2026-05-15 with § F findings + the post-review code verification.
> **Authoritative execution doc: `reports/Template_Remediation_Plan_2026-05-15.md`.** This list is the high-level rationale only.

1. **Wave 0 — baseline.** Deploy current `main` (don't try to detect if `55e2e0b` is live) so the live build == current code, then live-send a representative set + re-test B1.
2. **B1 duplicate-send — already fixed in code** (`api_v2/routers/email_send.py:174`, idempotency key now includes `template_id`). *Not* "keyed on day, not template" — that was the old bug, now corrected. Only needs live confirmation in Wave 0, then close.
3. **A2 broken images — scoped & confirmed.** Not a hosting-architecture problem: 7 specific objects deleted from the `wa-template-images` bucket (likely by `24ca013`). Re-upload the 7 originals to identical paths via `scripts/upload_template_images.py` (no `shared.yml` change). Highest-certainty quick win.
4. **B2–B5 broken/missing CTAs** — trace then fix feedback 404 route, dead catalog link, invisible Sample/Catalog buttons, Proforma PDF button.
5. **B6 GST column** — add GST/Tax line to `proforma_invoice.html` + `order_confirmation.html` invoice summary.
6. **B7 recipient name — context bug, NOT a template typo.** Templates already correctly use `Dear {{company_name}}` (`campaigns/*_campaign.html:39`); `company_name` is wrongly bound to the *sender* in `email_personalization.py::build_send_variables`. Fix in the data layer.
7. **A1/A3/A4 shared UI** — *only what Wave 0 proves still broken* (much may be resolved by `55e2e0b`'s render polish): footer table-row rebuild, icon hosting, button sizing — one shared change each.
8. **A5/B8/B9/B10/B11 content pass** — apply the report's line-level rewrites template-by-template; **Prashant reviews each before ship**.
9. **A6 spacing/proportion polish** — per-template layout + empty-image-cell collapse.

---

## E. Questions — status

**Resolved:**
1. ~~Duplicate-send (B1) predate `55e2e0b`?~~ → Yes; fixed in code, re-test live in Wave 0.
2. ~~Image hosting (A2)?~~ → Public Supabase `wa-template-images` bucket; 7 objects deleted, re-upload originals.
3. ~~Content rewrites wholesale vs reviewed?~~ → Apply per-template, **Prashant reviews each before ship**.

**Still open (block Wave 4):**
4. **Client name (Hemp):** correct name replacing "design partner, Auroville"?
5. **Sustainability/Tariff claims (B8):** are the 73% stat / carbon-negative / 15–25% cost advantage verifiable, or soften all?
6. **Canonical URLs:** do real URLs already exist for the feedback/review page (B2) and full catalog (B3), or should I locate them in config during the Wave 2 traces?
