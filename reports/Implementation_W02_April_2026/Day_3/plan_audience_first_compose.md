# Audience-first compose flow — Email + WhatsApp

> **Revision 2** — incorporates review fixes:
> filter convention pinned (empty `target_segments` = applies to all);
> audience counts via `flows_engine._get_segment_contacts`;
> `all_opted_in` preserved as a 5th audience card;
> WA sender entry point pinned to `WhatsAppSender.send_template`;
> sidebar path pinned to `hf_dashboard/config/dashboard/sidebar.yml`;
> WA `status` field dropped (collides with DB-side Meta approval status).

## Context

V1 of the dashboard puts every email/WhatsApp template into one flat list,
regardless of which audience the template was authored for. Each campaign
defined for a particular segment (existing clients, churned/lapsed, Indian
carpet exporters, international yarn stores) has its own subject lines and
variable schemas, so a flat list forces the user to mentally match
templates to audiences on every send. There is also a shared library of
cross-segment templates (company intro, product showcases, seasonal
greetings, transactional, lifecycle) that has no first-class place in the
UI.

The data model already encodes the right structure:

- The disk layout under `campaign/{email,whatsapp}_campaign/` already
  separates `shared/` from per-segment folders (`existing_clients/`,
  `churned_clients/`, `potential_domestic/`, `international_email/`).
- `EmailTemplate.target_segments: list[Segment]` already exists and is
  populated in 21 of 27 shared YAMLs (e.g. `winback_60d_silent.yml` →
  `[churned_clients]`, `sustainability_field_story.yml` →
  `[potential_domestic, international_email, existing_clients]`).
- `services.email_campaign_loader.templates_for_segment(segment)` already
  returns the filtered list — but with one bug (see Step 0).

The work is therefore mostly UI rewiring on the email side, plus a
parallel WhatsApp compose page and one schema addition (`target_segments`
on `WhatsAppTemplate`) so the same filter pattern works there.

User confirmed scope: Email + WhatsApp. Audience taxonomy: the 4 canonical
segments matching the directory names and the `Segment` literal, plus
`all_opted_in` preserved as a generic blanket-send option.

## Filter convention (pinned)

**An empty `target_segments` list means "applies to all audiences".**
A non-empty list means "applies only to those audiences listed".

This requires a 1-line change to the loader (Step 0). The convention
matches the natural reading of the 6 unannotated shared YAMLs (e.g.
`order_confirmation`, `proforma_invoice` — transactional templates that
clearly should reach any segment) and avoids forcing busywork annotation
for templates that already work everywhere.

---

## Approach

A single conceptual flow, two pages (one per channel for now — they each
have very different send mechanics so a single Gradio page would balloon):

```
[ Pick audience ]  →  [ Pick template ]  →  [ Fill variables ]  →  [ Send ]
   5 cards              two tabs                template-driven      keep existing
   (4 segments +        (segment / shared)      slot system
    all opted-in)
```

Each tab shows the right slice automatically:

- **For this audience** (when audience ≠ "all opted-in")
  → `templates_for_segment(audience)` — templates whose `target_segments`
  *explicitly* names this segment.
- **From shared library** → templates whose `target_segments` is empty
  (= applies to all). Sub-tabs by tier mirror the folder layout
  (Company / Product / Category / Seasonal / Lifecycle / Transactional
  for email; Company / Product / Category / Utility for WhatsApp).
- When audience is **"all opted-in"**, the "For this audience" tab is
  hidden; only the shared library tab is shown.

A Meta-category badge (Marketing / Utility / Authentication) appears on
each WA template card.

The Broadcast/Individual mode toggle on the email page is preserved
as-is (orthogonal to audience choice).

---

## Step 0 — Fix `templates_for_segment` filter convention

**File:** `hf_dashboard/services/email_campaign_loader.py`, lines
138–143.

Change:
```python
def templates_for_segment(segment: str, *, status: str = "READY"):
    return [
        t for t in load_email_templates().values()
        if segment in t.target_segments
        and (status is None or t.status == status)
    ]
```
to split the two semantics cleanly:
```python
def templates_for_segment(segment: str, *, status: str = "READY"):
    """Templates explicitly targeted at this segment.

    Empty target_segments = NOT returned (use shared_templates() for those).
    """
    return [
        t for t in load_email_templates().values()
        if t.target_segments
        and segment in t.target_segments
        and (status is None or t.status == status)
    ]


def shared_templates(*, tier: str | None = None, status: str = "READY"):
    """Templates with empty target_segments (apply to all audiences)."""
    return [
        t for t in load_email_templates().values()
        if not t.target_segments
        and (tier is None or t.tier == tier)
        and (status is None or t.status == status)
    ]
```
The new `shared_templates(tier=...)` is what the "Shared library"
sub-tabs call. `templates_for_segment` now returns *only* explicitly-
targeted templates — perfect for the "For this audience" tab.

This is the convention the rest of the plan assumes.

## Step 1 — Email compose: restructure `email_broadcast.py`

**File:** `hf_dashboard/pages/email_broadcast.py`

**Keep verbatim:**
- `_RECIPIENT_VALUE_SEP`, `_format_recipient`, `_parse_recipient_value`,
  `_resolve_segment_contacts`, `_search_contacts` helpers (lines 61–~150).
- Variable-slot system: `MAX_VAR_SLOTS_SHORT/LONG`, `_build_slot_updates`
  (lines 154–219), `_collect_var_values` (lines 222–234),
  `_on_template_change` handler (lines 539–572), and all eight slot
  components in the right column (lines 469–480).
- Preview iframe + Desktop/Mobile toggle (lines 488–499).
- Send Now / Test send buttons + handlers.
- Invoice attachment accordion (lines 408–438).
- Broadcast / Individual mode radio (lines 360–365). It moves visually
  but keeps its handler `_on_mode_change` (lines 505–514) intact.

**Restructure (`build()` function, lines 349–500):**

Replace the current "left column = mode radio + template dropdown +
broadcast/individual groups" with this top-down layout:

1. **Audience picker (new)** — render 5 cards as a `gr.Radio` styled as
   tiles, in this order:
   - Existing clients
   - Churned / lapsed
   - Carpet exporters (potential_domestic)
   - International yarn stores
   - **All opted-in** (preserves the current default; visually distinct,
     e.g. amber accent to mark "blanket send")

   Counts come from
   `services.flows_engine._get_segment_contacts(db, segment_id)` — the
   same function `_resolve_segment_contacts` already calls at line 92.
   For `all_opted_in`, fall back to the existing branch in
   `_resolve_segment_contacts` at lines 84–89 (`Contact.consent_status
   IN ("opted_in", "pending")`).

   Component name: `audience_radio` (replaces current `segment_dropdown`
   at lines 376–378). Default value: `"all_opted_in"` (preserves V1
   default at line 1089).

2. **Send mode toggle (kept, repositioned)** — `mode_radio` with
   "Broadcast" / "Individual" stays as-is functionally, just rendered
   immediately below the audience picker. Its existing
   `_on_mode_change` handler is unchanged.

3. **Template browser (new)** — `gr.Tabs`:
   - **For this audience** (hidden when audience is `all_opted_in`)
     — `gr.Radio` populated from `templates_for_segment(audience)`.
     Card-style label via a small new `_format_template_card(tpl)`
     helper (mirror the shape of `_format_recipient`).
   - **From shared library** — `gr.Tabs` nested with one sub-tab per
     tier: Company / Product / Category / Seasonal / Lifecycle /
     Transactional. Each sub-tab calls `shared_templates(tier=<tier>)`
     from Step 0. Empty sub-tabs render an "(no templates yet)" placeholder
     rather than disappearing — keeps the layout stable.

4. **Variable form** — keep existing right-column slots untouched.

5. **Send controls** — keep existing buttons.

**New handler:** `_on_audience_change(audience)` updates BOTH the
recipient list (existing logic in `_on_segment_change`, lines 591–608,
now wired off the new picker) AND the contents of both template tabs.
Toggles visibility of the "For this audience" tab based on whether
`audience == "all_opted_in"`.

**Remove:** the global template dropdown at lines 367–372 (replaced by
the two-tab browser).

## Step 2 — Add `target_segments` to `WhatsAppTemplate`

**File:** `hf_dashboard/engines/campaign_schemas.py`

After line 113, add ONE field:

```python
target_segments: list["Segment"] = Field(default_factory=list)
```

Keep the `Segment` definition where it is (lines 171–176). Forward-
reference is fine — `EmailTemplate` already does it at line 163.

Do **not** add `status` to `WhatsAppTemplate`. The Meta-side approval
status is already tracked on the `WATemplate` DB model (APPROVED /
PENDING / REJECTED), and adding a YAML-level `status` would create two
sources of truth.

Default `[]` means "applies to all audiences" — matches the email
convention from Step 0. Existing WA YAMLs continue to validate without
edits.

## Step 3 — Build `services/wa_campaign_loader.py`

**New file** mirroring `email_campaign_loader.py`:

- `load_wa_templates() -> dict[str, WhatsAppTemplate]` — walks
  `campaign/whatsapp_campaign/shared/{company,category,product,utility}_templates/**/*.yml`.
- `templates_for_segment(segment)` — explicit-only filter, mirrors the
  Step 0 email version.
- `shared_templates(tier=None)` — empty-`target_segments` filter.
- `templates_by_tier(tier)`.
- `get_template(name)`.
- `reload()`.

Reuse `_load_yaml` and the directory-walking pattern from
`email_campaign_loader.py` (lines 66–101) verbatim. Change only the
schema class (`WhatsAppTemplate`) and the directory list (`_TEMPLATE_DIRS`
becomes `["company_templates", "category_templates", "product_templates",
"utility_templates"]`).

## Step 4 — Annotate WA YAMLs with `target_segments` (only where restricted)

**Files:** `campaign/whatsapp_campaign/shared/**/*.yml`

Per the Step 0 convention, `target_segments` is added **only when the
template should be restricted**. Templates that apply to everyone leave
the field absent (default `[]`).

Concrete annotations:
- `followup_interest_v2.yml` →
  `target_segments: [potential_domestic, international_email]`
  (only prospects need followup).
- All other existing WA shared templates (sample_shipped_v2,
  sample_request_thanks, company_intro_b2b, catalog_browse, all
  category overviews, sustainability_field_story) → leave unrestricted.

Net: ~1 file changed. Lighter than originally scoped because the
"empty = all" convention removes most of the work.

## Step 5 — New page `pages/wa_broadcast.py`

**New file** modeled on the restructured `email_broadcast.py` from
Step 1. Same audience-first layout:

1. **Audience picker** — same 5 cards as email, same count source.
2. **Template browser** — two tabs (For this audience / Shared) and
   sub-tabs Company / Product / Category / Utility. Each card carries a
   Meta-category badge (Marketing / Utility / Authentication) read from
   `WhatsAppTemplate.meta_category`.
3. **Variable form** — WA templates use positional placeholders
   (`{{1}}, {{2}}, …`). Verified placeholder counts: max is 3
   (`sample_shipped_v2`); all others ≤ 1. The existing 6+2 slot system
   on the email page is more than enough; reuse `MAX_VAR_SLOTS_SHORT`
   without bumping. Use `_VAR_RE` (`wa_template_studio.py` line 464) to
   detect placeholders, populate slots in numeric order, and feed values
   back as the `components` list to `WhatsAppSender.send_template`.
4. **Send entry point**:

   ```python
   from services.wa_sender import WhatsAppSender
   sender = WhatsAppSender()
   ok, message_id, error = sender.send_template(
       to_phone=...,
       template_name=tpl.name,
       language=tpl.language,
       components=[...],   # built from slot values
   )
   ```
   Confirmed signature at `wa_sender.py:94` (`def send_template(...)`).
   Use the same broadcast-loop pattern as `email_sender.py` for
   per-recipient sending.

Keep `wa_template_studio.py` untouched — it remains the template
**author** surface; this new page is the **dispatch** surface.

## Step 6 — Sidebar / navigation

**File:** `hf_dashboard/config/dashboard/sidebar.yml` (confirmed
location).

Edits:
- Rename current "Email Broadcast" entry → "Email Compose".
- Add a new "WhatsApp Compose" entry pointing to `pages/wa_broadcast.py`,
  ordered next to "WhatsApp Studio".
- "WhatsApp Studio" stays unchanged (template authoring).

---

## Critical files to modify

- `hf_dashboard/services/email_campaign_loader.py` (Step 0 — add
  `shared_templates`, tighten `templates_for_segment`)
- `hf_dashboard/pages/email_broadcast.py` (restructure)
- `hf_dashboard/engines/campaign_schemas.py` (add 1 field to
  `WhatsAppTemplate`)
- `hf_dashboard/services/wa_campaign_loader.py` (new)
- `hf_dashboard/pages/wa_broadcast.py` (new)
- `campaign/whatsapp_campaign/shared/utility_templates/followup_interest_v2.yml`
  (single annotation)
- `hf_dashboard/config/dashboard/sidebar.yml` (rename + add)

## Functions and utilities to reuse

- `services.email_campaign_loader.templates_for_segment` — segment-
  specific filter (post Step 0).
- `services.email_campaign_loader.shared_templates` — shared-library
  filter (new, Step 0).
- `services.email_campaign_loader.templates_by_tier` — keep, used by the
  audit script and one-off needs.
- `services.flows_engine._get_segment_contacts` — audience counts and
  recipient resolution. Already imported at `email_broadcast.py:92`.
- `_resolve_segment_contacts` (`email_broadcast.py:81`) — reuse for the
  `all_opted_in` branch.
- `_build_slot_updates`, `_collect_var_values`, `_on_template_change`
  (`email_broadcast.py:154–572`) — variable-slot mechanism, untouched.
- `_VAR_RE` (`wa_template_studio.py:464`) — placeholder detection for
  WA.
- `services.wa_sender.WhatsAppSender.send_template` — `wa_sender.py:94`.

## Verification

Per `CLAUDE.md`: never run locally; deploy to HF Space and drive the
live URL with Playwright.

1. `python scripts/validate_campaigns.py` — confirms the new schema
   field validates cleanly across every existing YAML, including the
   `followup_interest_v2.yml` annotation.
2. `python scripts/deploy_hf.py` — deploy to
   `prashantiitkgp08-himalayan-fibers-dashboard.hf.space`.
3. Wait for the Space to show **Running**.
4. Playwright MCP verification, headless on the live URL:
   - Navigate to **Email Compose**. Confirm 5 audience cards render
     with non-zero counts (4 segments + "All opted-in"). Default
     selection should be "All opted-in".
   - With "All opted-in" selected, the "For this audience" tab should
     be hidden; only the shared library tab is shown.
   - Click each of the 4 segment cards in turn; confirm "For this
     audience" tab appears and reflects different templates per segment
     (e.g. `winback_60d_silent` only on Churned).
   - On Existing clients, click "Shared library" tab; confirm sub-tabs
     show Company / Product / Category / Seasonal / Lifecycle /
     Transactional. Empty sub-tabs render placeholder text, not
     disappear.
   - Pick a template; confirm variable slots re-label, preview iframe
     re-renders, and the Test Send button uses the slot values (not
     hardcoded stubs — the Phase 1 bug fix should still hold).
   - Toggle Broadcast → Individual mode; confirm the existing
     individual-search UI still appears unchanged.
   - Repeat the same sweep on **WhatsApp Compose** (new page),
     confirming Meta-category badges show on cards and that
     `followup_interest_v2` only appears for `potential_domestic` and
     `international_email`.
   - Save before/after screenshots: 5 audiences × 2 channels = 10
     screenshots, plus 1 for the Broadcast/Individual toggle still
     working. Saved as `verify-*.png` at repo root.

## Out of scope (explicitly deferred)

Carry-forward list for **Day_4 planning** (in priority order):

1. **Reconcile the 13 granular CRM segments** in
   `config/segments/customer_segments.yml` with the 4 canonical
   campaign segments — likely as a sub-segment refinement dropdown
   inside each top-level audience card.
2. **Tags as cross-cutting filters** — add `tags: list[str]` to both
   `EmailTemplate` and `WhatsAppTemplate`, surface as side-rail
   facets in the template browser.
3. **Braze-style content blocks** — lift duplicated product-card /
   company-info paragraphs into reusable Jinja partials registered in
   a shared library and `{% include %}`-d from templates.
4. **Unify into a single `compose.py`** with a channel toggle as
   step 2 — only worth doing once email and WA send pipelines share
   more infrastructure.
