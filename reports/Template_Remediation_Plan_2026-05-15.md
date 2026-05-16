# Email Template Remediation Plan

**Companion to:** `reports/Template_Issue_Summary_2026-05-15.md`
**Created:** 2026-05-15
**Decisions locked:** (1) plan full remediation now; (2) Prashant has the 7 original image files; (3) copy rewrites applied but reviewed per-template before ship; (4) duplicate-send re-tested live before closing.

> **⚠️ v1 is DEPRECATED — target v2 only (user directive 2026-05-15).** CLAUDE.md still documents v1 and is stale.
> - v1 (do not use): `hf_dashboard/` Gradio → `prashantiitkgp08/himalayan-fibers-dashboard`, deploy `scripts/deploy_hf.py`.
> - **v2 (focus):** Vite + `api_v2` (shares `hf_dashboard/` services) → `Prashantiitkgp08/Himalayan_Fibrer_v2`, live `https://prashantiitkgp08-himalayan-fibrer-v2.hf.space/`, **deploy `python scripts/deploy_hf_v2.py`**, API health `/api/v2/health`. Likely password-gated (`APP_PASSWORD`; Bearer token on `/api/v2/*`).
>
> Verification flow per wave: `git commit` → `python scripts/deploy_hf_v2.py` → wait Space **Running** + `/api/v2/health` ok → verify via `api_v2` endpoints (`POST /api/v2/email/render-preview`, `POST /api/v2/email/test-send`) and/or Playwright on the v2 Vite UI (handle login) → hand off only when checks pass. **Never run the app locally.**
> Templates + `shared.yml` are shared between v1/v2, so content fixes carry over; B1 (duplicate-send) is v2-specific in `api_v2/routers/email_send.py`.

---

## Template file map (verified 2026-05-15) — corrects earlier vague pointers

Templates live in **two** dirs, plus a seed-metadata layer — the earlier draft wrongly implied everything was under `templates/emails/`:

- `hf_dashboard/templates/emails/` — part-based transactional/onboarding/product-campaign templates (`hemp_focus.html`, `nettle_focus.html`, `wool_focus.html` [Tibetan], `collections_focus.html` [Signature], `yarn_categories_intro.html` [Yarn Lineup], `proforma_invoice.html`, `order_confirmation.html`, `order_delivered_feedback.html`, `order_shipped.html`, `order_in_production.html` [≈ Order Flow Step 1], `sample_invitation.html`, `sample_request_received.html`, `sample_shipped.html`, `sample_swatch_preparation.html`, `post_sample_followup.html`, `price_list_share.html`, `welcome.html` [Welcome New Subscriber], `welcome_day_3_sustainability.html`, `winback_60d_silent.html`, `onboarding_day_14_first_order.html`).
- `hf_dashboard/templates/campaigns/` — **standalone campaign HTML** (this dir was missed earlier): `sustainability_compliance_campaign.html`, `tariff_advantage_campaign.html`, `welcome_email_final.html`, `welcome_email_production.html`, `b2b_introduction_carpet_exporters.html`.
- `hf_dashboard/config/email/templates_seed/*.meta.yml` — per-template metadata (subject lines etc.) seeded to DB `EmailTemplate` rows via `email_campaign_loader.py`. Subject-line edits (e.g. Tariff "New Trade Tariffs?") and meta live here, **not** in the HTML.
- Shared: `partials/footer.html`, `partials/social_row.html`; macros in `partials/middle/` — incl. `cta_button.html`, `invoice_button.html`, `proforma_stamp.html`, `image_split.html`, `hero_image.html`, `image_grid.html`.
- Supabase uploader for Wave 1: **`scripts/upload_template_images.py`** (and `cleanup_wa_template_images.py` — the likely tool behind bucket-cleanup `24ca013` that deleted the 7).

---

## Wave 0 — Baseline truth (do first, ~half day)

Goal: separate "already fixed by `55e2e0b`" from "still broken", so we don't re-fix solved problems.

| Step | Action | Output |
|---|---|---|
| 0.1 | **Don't try to detect** whether `55e2e0b` is live (HF git log only shows "Upload…" commits — unreliable). Instead just `python scripts/deploy_hf.py` from current `main` so the live baseline == current code by construction. | Known live baseline |
| 0.2 | Via the live Send Email page, send a representative set to a test inbox: one campaign (Hemp), one with broken images (Collections/Signature), Proforma Invoice, Order Delivered Feedback, one Welcome, Sustainability Compliance. | Live screenshots |
| 0.3 | **B1 re-test:** send Order Delivered Feedback, then Order Shipped, then Post-Sample Follow-up to the same contact same day. Expect all 3 to send (no false "duplicate"). | B1 closed or reopened |
| 0.4 | Inspect footer/icon rendering in Gmail (desktop + mobile) on the live sends. | A1/A3 status: real vs already-fixed |
| 0.5 | Update `Template_Issue_Summary` § A/B status flags with live truth. | Trimmed real-issue list |

**Exit:** a confirmed list of what is *actually* still broken on the current build.

---

## Wave 1 — Confirmed infra fix: 7 dead images (A2)

Scope is fully known (audited 2026-05-15). Prashant supplies the 7 original files.

Dead objects in `wa-template-images` bucket (referenced by `hf_dashboard/config/email/shared.yml`):

1. `Product Images/Nettle Wool Collection/Burberry Series/1. Burberry Series.webp`
2. `Product Images/Nettle Wool Collection/Burberry Series/2. Top View.webp`
3. `Product Images/Nettle Wool Collection/Burberry Series/3. Close Up Image.webp`
4. `Product Images/Nettle Wool Collection/Noor Series/Noor_Main.webp`
5. `Product Images/Nettle Wool Collection/Noor Series/noor_Silver.webp`
6. `Product Images/Plant Based/1.2 Nettle Yarn/1.2.4 Special Nettle Yarn/ERB Sepcial_1.webp`
7. `Product Images/Plant Based/2.1 Hemp Fibre/2.1.1 Raw Hemp Fibre/Display.webp`

| Step | Action |
|---|---|
| 1.1 | Prashant provides the 7 source files (names/paths above). |
| 1.2 | Re-upload to the exact bucket paths via Supabase (service key) — reuse an existing `scripts/` uploader if present; else a one-shot script. Keep paths identical so **no `shared.yml` change needed**. |
| 1.3 | Re-run the URL audit (HEAD all 55 in `shared.yml`) → expect 55/55 = 200. |
| 1.4 | Live re-send: Collections/Signature, Nettle campaign, Hemp campaign, Sample Invitation, Yarn Lineup, Story, Welcome Day-3, Winback — confirm images render in Gmail. |

Fixes A2 for: Hemp, Nettle, Signature/Collections, Sample Invitation, Yarn Lineup, Story, Day-14, Welcome Day-3, Winback.

---

## Wave 2 — Functional bugs (B2–B11), highest user impact

Each needs a code trace first (file locations not yet confirmed), then fix.

| Bug | Fix approach | Likely area |
|---|---|---|
| **B2** "Share Your Feedback" → 404 | Trace the feedback CTA URL builder; point at the real review/feedback route; verify route exists & is reachable from live. | `order_delivered_feedback.html` + URL/link config in `shared.yml` or personalization |
| **B3** "SEE THE FULL CATALOG" dead | Trace catalog link var; set to canonical catalog URL; verify. | `nettle_focus.html` + link config |
| **B4** Sample Request / Catalog buttons not visible | Determine why CTA renders empty (missing var → empty href → button hidden, or conditional). Ensure CTA always renders with valid href. | `sample_invitation.html`, Onboarding Day-14 template + button macro in `partials/middle/` |
| **B5** Proforma PDF download button missing | Confirm whether stamped-PDF URL is injected into context; render a visible "Download Proforma Invoice (PDF)" button when present. | `proforma_invoice.html` + invoice context builder |
| **B6** GST/Tax column missing | Add `GST / Tax Amount` line to invoice summary block: Subtotal → GST/Tax → Courier → Grand Total. Source GST value from order data. | `proforma_invoice.html`, `order_confirmation.html` + order context |
| **B7** "Dear Himalayan Fibres," wrong recipient | **Not a template typo.** Both campaign templates already use the correct var: `campaigns/{sustainability_compliance,tariff_advantage}_campaign.html:39` → `Dear <strong>{{company_name}}</strong>,`. Bug is that `company_name` is **bound to the sender's company** instead of the recipient's. Fix in the context/personalization layer (`hf_dashboard/services/email_personalization.py::build_send_variables`) — bind `company_name` to the contact's company with a name/blank fallback. | `email_personalization.py` (data), not the templates |
| **B10** Sustainability email ends `"Let'"` | Restore/complete the truncated closing copy. | `campaigns/sustainability_compliance_campaign.html` |
| **B11** "Three days ago you joined…" goes stale | Replace with evergreen phrasing (report's suggested line). | `welcome_day_3_sustainability.html` |
| **B9** "Fibers" → "Fibres" | Global string fix. | `welcome.html`, welcome production/final templates |

B8 (risky claims) is handled in Wave 4 (copy).

---

## Wave 3 — Shared UI polish (A1, A3, A4, A6) — only what Wave 0 proves still broken

One change to a shared partial propagates to all templates.

| Item | Fix | File |
|---|---|---|
| **A1** Footer contact row icon↔text alignment | If Wave 0 shows still broken: rebuild contact block as a Gmail-safe **table row** (`icon cell` + `text cell`, `valign="middle"`), not centered `<p>`+emoji. Single fix, all templates. | `templates/emails/partials/footer.html` |
| **A3** Footer/contact icons not rendering | Ensure all icon `src` are public Supabase PNGs (audit them like Wave 1); add `alt`. | `footer.html`, `social_row.html`, `shared.yml` |
| **A4** Oversized WhatsApp/CTA buttons | Reduce shared button height/padding/font-size/weight/width in the button macro; one change covers Price List, Proforma, Order Shipped, etc. | button macro in `partials/middle/` |
| **A6** Whitespace / image-text imbalance | In `image_split` macro: tighten vertical padding, balance image vs content column, **collapse the image cell when URL is empty/broken** (prevents big empty gaps). Per-template image-size tuning where flagged (Nettle, Tibetan, Day-14, Story, Order Delivered). | `partials/middle/image_split.html` (+ named templates) |

---

## Wave 4 — Copy rewrites (A5, B8) — per-template, **reviewed before ship**

Apply the report's explicit line-level rewrites. Per decision: I edit, **Prashant reviews each template's new copy before it deploys**. Batch by review session.

> **Fleet-wide claim rule (added from /review):** soften *every* unverifiable
> quantified claim (e.g. "3–4× longer", "four times faster CO₂", "73%",
> "15–25%") to qualitative wording — not only the 2 B8 templates. Hemp's
> were softened in this wave.
> **Welcome Production note:** the "no copy change" entry below refers to its
> *UI*; its *copy* still needs the 4 B2B replacements (same as Welcome Final).

| Template | Change set | Status |
|---|---|---|
| Hemp campaign | Client name → "Carpet Designer, Bhadohi / Mirzapur"; reframed apparel/bedding → carpets/rugs; claims softened; English simplified | ✅ done (commit `9d3ca64`), v2-verify in flight |
| Order Flow Step 1 | "feels in your hands" → B2B phrasing. |
| Post-Sample Follow-up | Apply report's full refined B2B version. |
| Sample Invitation (copy) | Apply report's refined B2B version. |
| Sample Request Ack | Replace 5 casual lines per report. |
| Welcome New Subscriber | 5 replacements per report. |
| Welcome Final / Production | 4 replacements + "Fibers"→"Fibres" (B9 done in Wave 2). |
| Welcome Day-3 | Line replacements + evergreen (B11 done in Wave 2). |
| Winback | 3 replacements per report. |
| Price List Share (copy) | "Quick note"→formal open, etc. |
| Proforma (copy) | "Courier (estimated)" / "Once payment lands" wording; payment terms block. |
| **B8** Sustainability Compliance | Soften "73% (ETC 2024)", "Carbon-Negative", "climate-positive", "buyers love to tell", "future of sustainable textiles" → report's safer wordings; add clean CTA block; reduce emojis. **Pending Prashant: are any claims verifiable?** |
| **B8** Tariff Advantage | Soften "15–25% cost advantage", "meet international eco-standards", "Compliance Risk—None", "command higher prices", "Perfect for"; reconsider fear-based subject; pad "Did you know?" box. |

Templates the report rated good and **needing no copy change**: Tibetan Wool (UI only), Sample Flow Step 1, Order Confirmation (only GST+footer), Welcome Production (UI only).

---

## Wave 5 — Full regression & sign-off

- Re-send **every** template via the live Send Email page; screenshot Gmail desktop + mobile.
- Walk the full § C catalogue; mark each issue closed/deferred.
- Final pass of the URL audit (expect 100% 200).
- Update both report docs to "Resolved" with evidence links.

---

## Wave 6 — Template standardization (DESIGN APPROVED-PENDING)

Full design: **`reports/Template_Standardization_Design_2026-05-15.md`**.
Summary: lift layout dimensions (width 720→**768**, content width, etc.) into
`shared.yml`+`SharedEmailConfig` as config knobs; migrate the 6 divergent
standalone templates (`campaigns/*` + `transactional/welcome.html`) onto
`base.html` + shared partials so all 30 templates are one family; retire the
`NON_SHELL_TEMPLATE_FILES` / `database.py` campaign-seed stopgap. Per-template
before/after render review gate. Runs **after Wave 1 + Wave 4** so we
standardize final copy/imagery. 3 open questions in the design doc.

---

## Dependencies / inputs needed from Prashant

1. **7 original image files** (Wave 1) — names/paths listed above.
2. **Correct client name** to replace "design partner, Auroville" in Hemp (Wave 4).
3. **Claim verifiability** (Wave 4/B8) — which of: 73% ETC-2024 stat, carbon-negative, 15–25% cost advantage can stay vs soften-all.
4. **Per-template copy review** availability (Wave 4) — batched review sessions.
5. **Canonical URLs** for feedback/review page (B2) and full catalog (B3) if not already in config.

## Sequencing rationale

Wave 0 prevents wasted effort on already-fixed items. Wave 1 is the one fully-scoped, confirmed-real fix → quick win. Wave 2 (functional bugs) is highest user-facing impact. Wave 3 is shared/high-leverage but gated on Wave 0 truth. Wave 4 is the largest surface but lowest risk and human-paced by review. Wave 5 proves it.
