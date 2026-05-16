# Email Template Standardization — Design (for review)

**Status:** DESIGN ONLY — no code until approved.
**Decisions locked:** (1) reviewed wave first; (2) width **768px** config-driven;
(3) **shell gains an optional "card" variant** (shadow / rounded / serif) so the
campaign templates' premium look is preserved *and* standardized fleet-wide —
not converged to the plain shell; (4) Wave 6 runs **after Wave 1 + Wave 4**.
**Companion to:** `Template_Remediation_Plan_2026-05-15.md` (slots in as **Wave 6**).

---

## 1. Goal

One shell + one set of shared components + one config file driving layout, so
**every** template renders identically for footer / social / CTA / banner /
width, and a change is a one-place edit. Eliminate the "renders here, broken
there" inconsistency at its structural root.

## 2. Current state (grounded in code)

**Already standardized (≈24 templates — the `templates/emails/*` family):**
- Shell `templates/emails/layout/base.html`: outer 100% table → inner
  `width="720"` table → `{% include banner %}` → `{% block content %}` →
  `{% include social_row %}` → `{% include footer %}`.
- Components: `partials/banner.html`, `partials/social_row.html`,
  `partials/footer.html`, `partials/middle/*` (cta_button, heading, paragraph…).
- Engine: `config/email/shared.yml` → `SharedEmailConfig` (Pydantic) →
  `load_shared_config()` → injected into every render via `build_send_variables`.
- Pattern each template uses: `{% extends 'layout/base.html' %}` + `{% block content %}` rows.

**NOT standardized (the divergent family — root of the inconsistency):**
- `templates/campaigns/{sustainability_compliance_campaign, tariff_advantage_campaign, welcome_email_final, welcome_email_production, b2b_introduction_carpet_exporters}.html` + `templates/transactional/welcome.html`.
- Each is a **full standalone HTML document**: own `<body>`, own outer card
  table (`max-width:640px`, box-shadow, Amiri font), **own inline banner**
  (some hot-link external `cloudhq` images, not the shared Supabase banner),
  **own footer table**, **own CTA `<a>` styles**. They do NOT use the shell
  or any partial. This is exactly why these specific templates carried the
  footer / greeting / spelling defects in the tester report.

**Hardcoded dimensions (not config):**
- `base.html:37` → `width="720"` + `max-width:720px` (two spots, one line)
- `partials/banner.html:3` → `width="720"` + `max-width:720px`
- content macros use `632`/`640` internally.

## 3. Proposed design

### 3a. Layout config block (the "component YAML" you asked for)

Add to `shared.yml` under a new `layout:` group and to `SharedEmailConfig`:

```yaml
layout:
  email_width: 768          # outer shell width (was hardcoded 720)
  content_max_width: 680    # inner content / image column ceiling
  card_radius: 0            # shell card corner radius
  # future: gutter, section_gap, button paddings, etc.
```

- New Pydantic sub-model `LayoutConfig` (mirrors the engine-schema rule —
  no inline `yaml.get`). Surfaced to templates as `{{ email_width }}` etc.
  via `build_send_variables` (same mechanism as `catalog_link`).
- `base.html` + `banner.html` reference `{{ email_width }}` instead of `720`.
  One knob → whole fleet. Adding a future shared dimension = one YAML line.

### 3a-bis. Shell "card" variant (locked decision)

`base.html` gains an optional card treatment driven by config + a per-template
opt-in, so the premium look (drop shadow, rounded corners, serif accent) is a
*shared* component, not per-template inline CSS:

```yaml
layout:
  card_variant: true          # fleet default on/off
  card_radius: 10
  card_shadow: "0 0 18px rgba(0,0,0,0.15)"
  card_margin: 20             # side gutter on mobile
  heading_font: "'Amiri', Georgia, serif"   # premium accent font
```

- Implemented as a conditional wrapper in `base.html` around the inner table
  (extra `<td>` padding + `style` from config), plus a `{% block %}`/param a
  template can override. Plain templates set it off; campaign templates inherit
  the card. Both styles now come from ONE place.

### 3b. Migrate the divergent family onto the shell

For each of the 6 templates:
1. Extract the **inner content** (the unique middle — copy, cards, CTAs).
2. Rewrite as `{% extends 'layout/base.html' %}{% block content %}…{% endblock %}`
   using `<tr><td>` rows + existing macros (heading/paragraph/cta_button), so
   it inherits the shared banner + social_row + footer automatically.
3. Move file to `templates/emails/<slug>.html`, **remove the slug from
   `NON_SHELL_TEMPLATE_FILES`** (today's stopgap), retire its
   `database.py:_seed_default_templates` entry (slug/id stays stable; DB
   `html_content` becomes irrelevant — file renders).
4. Drop the external `cloudhq` banner images → shared `banner_url`.

Net: all 30 templates become one family. `NON_SHELL_TEMPLATE_FILES` and the
`database.py` campaign-seed list both disappear (cleanup of today's stopgap).

### 3c. Width 720 → 768

- Single config value; verify the mobile responsive rule. **`base.html`
  currently has no `@media` width override and the inner table uses a fixed
  `width` attribute** → at 768 this must pair with a `max-width:100%` /
  small-screen rule or it horizontal-scrolls on phones. The width bump is
  therefore *coupled to* adding a responsive clamp — both ship together.
- Outlook (Word engine) honours the fixed `width` attr → renders at 768 on
  desktop, fine. No MSO ghost-table in `base.html` today (one less thing to
  sync), but we add a proper MSO conditional wrapper while we're in there.

## 4. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Migrating campaign templates **visually restyles them** (lose bespoke card/shadow/Amiri look) | This *is* the standardization — but show you a before/after render of each of the 6 before shipping (review gate, like Wave 4 copy). |
| Width 768 → mobile horizontal scroll | Width change bundled with a responsive `max-width:100%` clamp + mobile `@media`; verified on v2 render-preview + a real Gmail mobile send in Wave 5. |
| Campaign templates have unique sections (stat cards, doc-CTA grid) not in current macros | May need 1–2 new `partials/middle/*` macros (e.g., `info_card`, `stats_row` — some already exist). Cataloged per template during build. |
| Slug/id stability (flows, broadcasts reference slugs) | Slugs/ids unchanged; only the render source moves file-ward. Regression check: every slug still resolves (Wave 5). |
| Outlook desktop at 768 | Fixed `width` attr + added MSO conditional; verified. |

## 5. Sequencing

Proposed **Wave 6 — Standardization**, after Wave 1 (images) + Wave 4 (copy)
so we standardize the *final* copy/imagery, not a moving target. Steps:

1. Layout config block + schema + width knob + responsive clamp (no visual
   change yet beyond 720→768) → deploy → verify fleet unaffected.
2. Migrate the 6 divergent templates one at a time; per-template before/after
   render for your review before each ships.
3. Remove `NON_SHELL_TEMPLATE_FILES` + `database.py` campaign seed (stopgap
   cleanup) once all 6 are file-shell templates.
4. Full visual regression (folds into Wave 5).

## 6. Decisions (resolved 2026-05-15)

1. ✅ **Shell gains a card variant** (shadow/rounded/serif from config) — the
   premium look is preserved and standardized fleet-wide (§3a-bis), not
   converged to the plain shell.
2. ✅ **Width = 768px**, config-driven, bundled with the responsive clamp.
3. ✅ **Wave 6 runs after Wave 1 + Wave 4** (standardize final copy/imagery).

No open questions — design is ready to execute when Wave 1 + Wave 4 complete.
