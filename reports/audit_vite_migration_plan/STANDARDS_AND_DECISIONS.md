# Standards and Decisions — vite_dashboard

**Companion to:** `README.md` (audit) and `PHASES.md` (execution).
**Date:** 2026-05-04

This document fills the 10 gaps identified during plan review with concrete decisions, implementation snippets, and where each decision plugs into PHASES.md. Treat each section as locked-in unless explicitly revised. Decisions here are referenced from acceptance criteria in PHASES.md, so changing one means re-checking the affected phases.

---

## 1. Authentication

**Decision.** Bearer token stored in `localStorage`. Token value = the Space's `APP_PASSWORD`. No refresh flow. Expiry by manual rotation.

**Why this and not cookies / OAuth.** Internal tool, single shared password, ~5 users. Cookie sessions need server-side state; OAuth needs an identity provider. Both are overkill. localStorage + Bearer is the lowest-friction option that actually works behind HF Spaces' reverse proxy.

**Lifecycle.**

```
Login form submit
    └─> POST /api/v2/auth/login  { password }
         └─> if matches APP_PASSWORD: return 200 { token: <password> }
         └─> else: return 401
              └─> frontend: setToken(); redirect /home

API call
    └─> client adds `Authorization: Bearer ${getToken()}` header
         └─> backend deps.auth_dependency() compares to APP_PASSWORD
              └─> 200: proceed
              └─> 401: frontend clearToken(); redirect /login
```

**Code (Phase 0).**

```ts
// src/lib/auth.ts
const TOKEN_KEY = "hf_dashboard_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// src/api/client.ts
export async function apiFetch(path: string, opts: RequestInit = {}) {
  const token = getToken();
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (res.status === 401 && !path.endsWith("/auth/login")) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Auth expired");
  }
  return res;
}
```

**Risk.** localStorage is XSS-readable. Acceptable because (a) the dashboard renders no untrusted user content, (b) shared internal tool, (c) team has Slack and can rotate the password if exposed. Revisit if v2 ever hosts customer-facing content.

**Rotation.** Update `APP_PASSWORD` in HF Space Settings → users see 401 on next call → forced re-login. No code change needed.

---

## 2. Schema migration coordination

**Problem.** v1 (Gradio at `dashboard/`) and v2 (api_v2) both import `app/services/models.py` and connect to the same Postgres. During the dual-Space migration window, every schema change must work for **both** consumers.

**Migration policy during dual-Space window.**

| Allowed | Forbidden |
|---|---|
| `ADD COLUMN` (nullable) | `DROP COLUMN` |
| `ADD INDEX` | `RENAME COLUMN` |
| `CREATE TABLE` | `ALTER TYPE` (narrowing) |
| `ADD CONSTRAINT NOT VALID` | `ADD CONSTRAINT` (validating) on hot tables |

Anything in the right column waits until **after Phase 5** (v1 decommissioned).

**Playbook (every schema change follows this).**

1. Write migration script: `scripts/migrations/YYYY_MM_DD_description.py`
2. Update `app/services/models.py` AND any new `api_v2/schemas/*.py`
3. Run `pytest api_v2/tests/test_imports.py` — must pass (catches relative-import breakage)
4. Run migration locally against the dev SQLite DB first
5. Run migration manually against prod Postgres BEFORE the v2 deploy that depends on it: `python scripts/migrations/2026_05_15_add_scheduled_at.py`
6. Verify both v1 and v2 still boot (curl health endpoints)
7. Deploy v2 (`python scripts/deploy_hf_v2.py`)
8. Document in `MIGRATION_LOG.md` (one-liner per migration with date + description)

**Tooling choice.** Plain Python scripts using SQLAlchemy directly. **Not** Alembic — the team is small, the migration cadence is low (~once per phase), and Alembic adds config overhead that doesn't pay off at this scale.

**Migration script template:**

```python
# scripts/migrations/2026_05_15_add_scheduled_at.py
"""Adds scheduled_at to broadcasts and campaigns for Phase 3 scheduling."""
from sqlalchemy import create_engine, text
import os

def up(engine):
    with engine.begin() as conn:
        for table in ["broadcasts", "campaigns"]:
            # information_schema check makes this idempotent
            exists = conn.execute(text(f"""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = 'scheduled_at'
            """)).first()
            if not exists:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN scheduled_at TIMESTAMPTZ"))
                print(f"added scheduled_at to {table}")
            else:
                print(f"scheduled_at already exists on {table}, skipping")

if __name__ == "__main__":
    # Local-test path: SQLite fallback that mirrors prod schema
    # Run: `python scripts/migrations/2026_05_15_add_scheduled_at.py --sqlite`
    # (This catches `ALTER TABLE ... ADD COLUMN` syntax issues before prod.)
    import sys
    if "--sqlite" in sys.argv:
        engine = create_engine("sqlite:///hf_dashboard/data/dashboard.db")
    else:
        engine = create_engine(os.environ["DATABASE_URL"])
    up(engine)
```

**Test cadence.** Always test against SQLite first (`--sqlite`); only run against prod Postgres after the SQLite run is clean.

**Cleanup migrations** (drop columns, rename tables) live in `scripts/migrations/post_v1_decommission/` and run only after Phase 5 acceptance.

---

## 3. Analytics / event tracking

**Decision.** PostHog Cloud (free tier — 1M events/month, 6-month retention).

**Why PostHog.** Free tier covers our volume comfortably. Self-hosted upgrade path if we exceed free limits or want data isolation. Better DX than Mixpanel for small teams. Sentry handles errors; PostHog handles user actions — they don't overlap.

**Retention caveat.** Free tier keeps events for 6 months. The migration window (6-11 weeks) fits comfortably, but **multi-quarter funnel comparisons** (e.g. Q1 vs Q3 broadcast conversion) won't be possible without upgrading to a paid tier. If long-range analytics is wanted, plan to (a) self-host PostHog OR (b) export weekly aggregates to a Google Sheet OR (c) upgrade after 4 months of usage data has accumulated.

**Events to track (Phase 0 sets up the helper; phases 1-5 add events as they ship):**

| Event | Properties | Phase |
|---|---|---|
| `$pageview` (auto) | path | 0 |
| `auth_login` | success: bool | 0 |
| `auth_logout` | — | 0 |
| `contact_added` | source: "manual" \| "import" | 1 |
| `contact_imported` | count: number | 1 |
| `contact_edited` | fields_changed: string[] | 1 |
| `wa_message_sent` | type: "text" \| "media" | 2 |
| `wa_template_sent` | template_name | 2 |
| `wa_inbound_received` | (server-side) | 2 |
| `broadcast_composed` | channel: "wa" \| "email", recipients: number | 3 |
| `broadcast_sent` | channel, recipients, scheduled: bool | 3 |
| `broadcast_failed` | channel, error_class | 3 |
| `template_drafted` | name | 4 |
| `template_submitted` | name, category | 4 |
| `template_synced` | count: number | 4 |

**Setup (Phase 0).**

```ts
// src/lib/analytics.ts
import posthog from "posthog-js";

if (import.meta.env.VITE_POSTHOG_KEY) {
  posthog.init(import.meta.env.VITE_POSTHOG_KEY, {
    api_host: "https://app.posthog.com",
    capture_pageview: true,
    autocapture: false,  // explicit events only — keeps the data clean
  });
}

export const track = (event: string, props?: Record<string, unknown>) => {
  posthog.capture(event, props);
};
```

**PII policy.** No emails, phone numbers, contact names, or message content in event properties. Use IDs (`contact_id`, `template_name`) where useful. PostHog's `identify` is **not** called — we don't need per-user identification for an internal team this small.

**Dashboards in PostHog (Phase 5).** Three dashboards: (1) daily active users, (2) broadcast funnel (composed → sent → succeeded), (3) WA inbox volume.

---

## 4. Accessibility (a11y)

**Target.** WCAG 2.1 Level AA.

**v1 baseline.** Effectively zero a11y. Keyboard nav broken (Gradio focus management); icon-only buttons have no labels; modals trap focus inconsistently. v2 starts from zero and builds in correctly.

**Standards v2 enforces.**

1. **Keyboard navigation.** Every interactive element reachable via Tab. Tab order matches visual order. Esc closes dialogs and sheets.
2. **Focus indicators.** 2px ring, high contrast. Shadcn provides this via `focus-visible:ring-2`.
3. **Color contrast.** Body text 4.5:1 minimum, large text (18pt+) 3:1. Verified against the YAML theme palette in Phase 0 using `npm pkg run check:contrast`.
4. **ARIA labels** on icon-only buttons. Example: `<Button aria-label="Edit contact"><PencilIcon /></Button>`.
5. **Landmarks.** `<main>`, `<nav>`, `<aside>` in `<AppShell>` so screen readers can jump between regions.
6. **Forms.** Every `<input>` has an associated `<Label>`. Errors set `aria-invalid="true"` and link to the error message via `aria-describedby`.
7. **Modal focus trap.** Shadcn `<Dialog>` and `<Sheet>` handle this; verify with manual keyboard test in Phase 1.
8. **Skip-to-content link** at the top of `<AppShell>`, hidden until Tab-focused, jumps past the sidebar.
9. **Reduced motion.** Respect `prefers-reduced-motion` for animations (Tailwind's `motion-safe:` and `motion-reduce:` variants).

**Tooling.**

```json
// package.json devDependencies
{
  "eslint-plugin-jsx-a11y": "^6.x",
  "@axe-core/react": "^4.x",
  "axe-playwright": "^2.x"
}
```

- ESLint plugin runs at lint time → blocks PR with a11y violations
- `@axe-core/react` runs in dev mode → console warnings during local development
- `axe-playwright` runs in Phase 0 visual regression tests → fails CI

**Per-phase a11y checklist.** Added to each PHASES.md acceptance criteria:

- [ ] Tab through every interactive element; reach all of them
- [ ] Esc closes any modal/sheet that opened
- [ ] Tested with VoiceOver (Mac) or NVDA (Windows) — every button announces a sensible label
- [ ] No `eslint-plugin-jsx-a11y` warnings in committed code
- [ ] `axe` reports zero violations on the route's primary state

---

## 5. Dark mode strategy

**Decision.** **Dark mode only.** No light mode in v2.

**Rationale.** v1 is dark-only and the team is used to it. Adding light mode now means doubling the design effort for every component for zero stated need. If a team member requests light mode later, switching is a 2-day refactor (Tailwind `darkMode: 'class'` + a toggle in `<AppShell>`).

**Implementation.**

```ts
// tailwind.config.ts
export default {
  darkMode: 'class',  // ready for future toggle, but always 'dark' for now
  // ...
};
```

```html
<!-- vite_dashboard/index.html -->
<html lang="en" class="dark">
  ...
</html>
```

The `class="dark"` is hardcoded. No system-preference detection. No toggle button.

**Theme tokens** in `config/theme/default.yml` are dark-mode values directly. No `light:` / `dark:` variants in YAML.

---

## 6. Browser support matrix

**Targets.**

| Browser | Versions | Why |
|---|---|---|
| Chrome | last 2 stable (current = 122+) | Primary dev + ops |
| Edge | last 2 stable | Founder uses Windows |
| Safari (macOS) | last 2 stable (16+) | Mac users |
| Safari (iOS) | last 2 stable (16+) | Mobile ops |
| Firefox | last 2 stable | Cover the long tail |

**Vite build.target:** `["chrome120", "edge120", "safari16", "firefox120"]`. Compiles to ~ES2022 — small bundle, modern features available.

**Not supported:**
- Internet Explorer (any version)
- Legacy Edge (pre-Chromium)
- Browsers older than 2 years from current

**Unsupported-browser fallback.** `index.html` includes a tiny inline script that checks for `Promise` and `fetch`; if missing, replaces `<body>` with a "Browser not supported, please update" message.

```html
<script>
  if (typeof Promise === 'undefined' || typeof fetch === 'undefined') {
    document.body.innerHTML = '<div style="font-family:system-ui;padding:40px;text-align:center;"><h1>Browser not supported</h1><p>Please update Chrome, Edge, Safari, or Firefox to the latest version.</p></div>';
  }
</script>
```

**Manual testing matrix (per phase acceptance):** at minimum Chrome on Windows + Safari on iOS. Founder verifies macOS Safari before each phase ships.

---

## 7. Internationalization (i18n)

**Decision.** **Defer.** v2 ships English-only.

**Rationale.**

- The dashboard is internal-team-only. ~5 users, all comfortable in English.
- Customer-facing content (WA templates, email bodies) is bilingual already, but lives in the **DB**, not in UI strings. v2 already renders user-supplied bilingual content correctly because it's just data passing through.
- `react-i18next` would add ~5KB to the bundle for ~50 strings of value. Bad ratio at this scale.

**Phase 0 prep that costs almost nothing.** All UI copy goes through one constant file:

```ts
// src/lib/strings.ts
export const STRINGS = {
  contacts: {
    addButton: "Add Contact",
    importButton: "Import",
    searchPlaceholder: "Search...",
    // ...
  },
  // ...
} as const;
```

This makes a future i18n migration mechanical: replace the constant with `t("contacts.addButton")`, drop in `react-i18next`, add `hi.json`.

**Defer to Phase 6+ unless a team member explicitly asks earlier.** YAML configs (sidebar labels, page titles) stay in English; if/when we go i18n we'll add a `locale:` key per string.

---

## 8. Visual regression testing

**Decision.** **Storybook + Playwright + image-snapshot.** Free, self-hosted, sufficient for our scale.

**Why this and not Chromatic.** Chromatic is excellent ($149/month team plan) but our scale doesn't justify it yet. Free Playwright setup gives 80% of the value. Revisit if false positives become a maintenance burden.

**Setup (Phase 0).**

```bash
pnpm dlx storybook init
pnpm add -D @playwright/test playwright-core
pnpm add -D @storybook/test-runner
```

**One story per visual variant per component.**

```tsx
// src/components/badges/StatusBadge.stories.tsx
export default { component: StatusBadge };
export const Approved = { args: { status: "APPROVED" } };
export const Pending = { args: { status: "PENDING" } };
export const Rejected = { args: { status: "REJECTED" } };
export const Draft = { args: { status: "DRAFT" } };
```

**Visual regression test:**

```ts
// vite_dashboard/tests/visual.spec.ts
import { test, expect } from '@playwright/test';

test.describe('StatusBadge', () => {
  for (const variant of ['approved', 'pending', 'rejected', 'draft']) {
    test(variant, async ({ page }) => {
      await page.goto(`/iframe.html?id=statusbadge--${variant}`);
      await expect(page).toHaveScreenshot(`status-${variant}.png`);
    });
  }
});
```

CI runs on every PR. Diffs > 0.1% pixel difference fail the build. Reviewer accepts the new screenshot intentionally if the change is desired.

**What to capture (cumulative across phases):**

- Phase 0: `<Button>`, `<Input>`, `<StatusBadge>`, `<KpiCard>` (Shadcn primitives + first composed)
- Phase 1: `<DataTable>` (4 states: empty, loading, loaded, error), `<ContactDrawer>` (4 tabs)
- Phase 2: `<MessageBubble>` (out/in × text/image/document), `<TemplateSheet>`
- Phase 3: `<AudienceFunnel>`, `<BroadcastsTable>`, `<SendConfirmDialog>`
- Phase 4: `<TemplateForm>`, `<WaPhonePreview>`
- Phase 5: full-page screenshots of `/home`, `/contacts`, `/wa-inbox`, `/broadcasts`, `/wa-templates`, `/flows`

---

## 9. Migration runbook (per-phase template)

Every phase in PHASES.md gains a runbook section using this template. Template added to PHASES.md in the same edit that pulls in this doc.

### Pre-deploy checklist

- [ ] Acceptance criteria met (see PHASES.md §N)
- [ ] CI green on `migration/phase-N` branch
- [ ] Visual regression snapshots reviewed and approved
- [ ] a11y per-phase checklist passed
- [ ] Schema migration (if any) applied to prod DB; both v1 and v2 boot
- [ ] Sentry empty for new errors in last 24h on staging (or local-dev)
- [ ] PostHog event firing verified for new events introduced this phase
- [ ] Manual test on Chrome desktop + Safari iOS

### Deploy steps

1. Merge `migration/phase-N` → `main` via PR
2. Run `python scripts/deploy_hf_v2.py`
3. Wait for HF Space build (~5 min); confirm "Running" status
4. `curl https://himalayan-fibres-dashboard-v2.hf.space/api/v2/health` returns 200
5. Open the SPA in a browser, log in, navigate to the new page

### Post-deploy monitoring (2-hour watch)

- [ ] Sentry: no new errors in `prod-v2` project
- [ ] PostHog: events for the new pages flowing within 5 minutes of first user action
- [ ] Smoke test: 3 critical user paths still work end-to-end
  - Phase 1: filter contacts → edit one → save
  - Phase 2: send a template message
  - Phase 3: compose + send a small broadcast
  - Phase 4: edit + save a draft template
  - Phase 5: view home KPIs match v1
- [ ] Slack `#dashboard-deploys`: post deploy summary with: phase, time, what's new, how to roll back

### Rollback procedure

v1 stays live throughout the migration window — there is **no code rollback needed** for any phase 1-4. Just direct the team to the v1 URL via Slack pin until v2 is fixed.

For Phase 5 (after v1 is decommissioned), rollback means re-deploying the previous v2 release: `git checkout <previous-tag> && python scripts/deploy_hf_v2.py`. v2 is the only Space at that point.

---

## 10. Onboarding doc

**Decision.** Create `vite_dashboard/README.md` in Phase 0 as the single entry point for new developers. Phase 0 ships a **production-minimum** version (run-locally + structure + conventions + tests sections). Each later phase appends a "Phase N additions" subsection covering what shipped.

**Production minimum (Phase 0):**

````markdown
# vite_dashboard

Internal Himalayan Fibres ops dashboard. Vite + React + Shadcn.

## 5-minute orientation

- **What:** the v2 rewrite of the Gradio dashboard at `../dashboard/`. Same backend, new frontend.
- **Where it runs:** Hugging Face Space `himalayan-fibres-dashboard-v2`.
- **Architecture:** see `../reports/audit_vite_migration_plan/diagrams/architecture.excalidraw`.
- **Standards:** see `../reports/audit_vite_migration_plan/STANDARDS_AND_DECISIONS.md`.
- **Migration plan:** see `../reports/audit_vite_migration_plan/PHASES.md`.

## Run locally

```
cd vite_dashboard
pnpm install
pnpm gen:types       # regenerate API types from running api_v2
pnpm dev             # http://localhost:5173
```

The api_v2 backend must be running separately:

```
cd ../api_v2
uv run uvicorn main:app --reload --port 7860
```

## Make a small change (15-min walkthrough)

1. Open `src/pages/home/HomePage.tsx`
2. Find the welcome heading
3. Edit the text; save
4. Browser hot-reloads
5. Run `pnpm test` — should pass
6. Run `pnpm lint` — should pass
7. Commit on a `feature/<name>` branch; push; open PR

## Where to find help

- Slack: `#dashboard-dev`
- Bug template: GitHub issues, label `dashboard`
- Architecture questions: read `STANDARDS_AND_DECISIONS.md` first; if not answered, post in Slack with the section number you read

## Project structure

```
src/
├── config/      YAML configs (theme, sidebar, pages)
├── schemas/     Zod validators for the YAML
├── loaders/     ConfigLoader singleton
├── engines/     Resolve YAML to render-unit shapes
├── components/  Global components (used by 2+ pages)
├── pages/       One folder per route; page-specific components inside
├── api/         Type-safe fetchers (schema.d.ts auto-generated)
├── lib/         Utilities (auth, sse, format, ...)
├── routes/      React Router defs
└── styles/      Tailwind + theme CSS vars
```

## Conventions

- One folder per page under `src/pages/`. Page-specific components live inside.
- Promote a component to `src/components/` only when 2+ pages use it.
- All YAML reads go through `configLoader`. Never call YAML imports directly in a component.
- Every UI string lives in `src/lib/strings.ts`. No string literals in JSX.
- Bug fixes reference the bug ID from the audit: `// fixes B1: variable scroll`.

## Tests

- `pnpm test` — Vitest component tests
- `pnpm test:visual` — Playwright + Storybook visual regression
- `pnpm test:e2e` — Playwright end-to-end (Phase 5+)
````

This README ships in Phase 0 with placeholders for Phase-specific sections; each phase adds its own subsection as it ships.

---

## Cross-references

- **Audit:** `README.md` — what we're fixing and why
- **Phases:** `PHASES.md` — when each thing ships
- **Decisions:** this file — how we make recurring choices
- **Diagrams:** `diagrams/*.excalidraw` — visual reference
- **Onboarding:** `vite_dashboard/README.md` — first read for new devs (created Phase 0)

## 11. Repo layout — final names

**Decisions (locked 2026-05-04):**

- **`hf_dashboard/` → `dashboard/`** (rename happens in Phase 5, after v1 decommission)
- **`config/dashboard/`** subfolder created at repo root as the **single source of truth** for shared domain configs

### `config/dashboard/` is the canonical location for shared domain YAMLs

Created during this decision. Mirrors what `hf_dashboard/config/` contained:

```
config/                                # already existed at repo root
├── assets/, blog/, brand/, media/, products/, segments/, templates/, whatsapp/
├── email_config.yml, email_settings.yml, image_assets.yml
└── dashboard/                         # ← NEW — single source of truth for v1 + v2
    ├── theme/                         # default.yml, components.yml, layout.yml
    ├── dashboard/                     # sidebar.yml, dashboard.yml
    ├── pages/                         # one .yml per page (home, contacts, wa_inbox, ...)
    ├── whatsapp/                      # templates.yml, pricing.yml, media_guidelines.yml, ...
    ├── email/                         # shared.yml + templates_seed/*.meta.yml
    ├── contacts/                      # schema.yml
    └── cache/                         # ttl.yml, egress_row_widths.yml
```

**During the migration window (Phases 0-4):**
- v1 (Gradio at `hf_dashboard/`) continues reading from `hf_dashboard/config/` — no v1 changes
- v2 (`vite_dashboard/`) reads from `config/dashboard/` via Vite alias `@domain` → `../config/dashboard`
- **Both directories must stay in sync.** When updating a domain YAML (template, pricing, segment), edit `config/dashboard/X.yml` AND copy to `hf_dashboard/config/X.yml`. Recommended: add a pre-commit hook that errors if the two diverge, or just edit `config/dashboard/` and `cp -r config/dashboard/* hf_dashboard/config/` before committing.

**Phase 5 cleanup (post-v1-decommission):**
- Rename `hf_dashboard/` → `dashboard/`
- Update `dashboard/loader/config_loader.py` to read from `../config/dashboard/`
- Delete `dashboard/config/{whatsapp,email,contacts,...}/` (now redundant — content lives in `config/dashboard/`)
- Update the 56 files that reference `hf_dashboard` (23 .py + 18 .md + 15 .yml) to `dashboard`
- Update `scripts/deploy_hf.py` (or remove — replaced by `scripts/deploy_hf_v2.py`)

**Why we don't rename now.** v1 is the team's daily driver. A 56-file rename has subtle breakage risk (a missed import, a YAML referencing the old path) that doesn't pay off until Phase 5 anyway. `config/dashboard/` gets us the structural benefit (single source for v2) without the rename risk.

---

## Change log

| Date | Section | Change |
|---|---|---|
| 2026-05-04 | initial | Document created with all 10 gap decisions |
| 2026-05-04 | §11 | Repo layout decisions: `hf_dashboard → dashboard` (Phase 5); `config/dashboard/` created (immediate). Domain YAMLs duplicated to `config/dashboard/` as source of truth |
