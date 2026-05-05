# Vite + Shadcn Migration — Phases Plan

**Companion to:** `README.md` (the audit). Read the audit first for context on why each phase exists.
**Date:** 2026-05-04
**Total wall-clock:** 6.5-12 weeks (one engineer; lower bound assumes prior Shadcn + TanStack Query experience). Phase 0 grew from 5-7 to 7-10 days when standards-driven setup was added — see Phase 0 §"Estimated effort" for the updated breakdown.

This document breaks each phase into concrete, executable work: backend endpoints, frontend components, schema changes, tests, acceptance criteria, and risks specific to that phase. Every task references back to bug IDs (`B1`-`B20`) and decision points (`§9.1`-`§9.7`) from the audit.

---

## 0. How to use this document

- **Phases are sequential by default.** Phase N+1 may not start until Phase N's acceptance criteria are met. The exception is Phase 0.5 (bug reproduction) which gates Phase 1+ but doesn't gate parallel backend prep.
- **Each phase ships to the v2 HF Space at completion.** The v1 Space stays live until Phase 5 closes.
- **Each phase has a dedicated branch** off `main` (e.g. `migration/phase-1-contacts`). Merge to `main` only after acceptance + a deploy to the v2 Space.
- **Bug fixes are only claimed when verified in Phase 0.5 reproduction.** A bug in §4 of the audit moves to "fixed" when (a) the v2 implementation lands AND (b) the reproduction screenshot can no longer be reproduced.
- **Sub-tasks inside a phase can run in parallel** when explicitly noted (e.g. backend + frontend tracks in Phase 1 onwards).

### Calendar overview (sequential, single-engineer pace)

```
Week 1     Phase 0    Foundation
Week 1-2   Phase 0.5  Reproduce bugs (overlaps with Phase 0 wrap)
Week 2-3   Phase 1    Contacts
Week 3-5   Phase 2    WhatsApp Inbox
Week 5-7   Phase 3    Broadcasts
Week 7-8   Phase 4    Template Studio
Week 8-9   Phase 5    Home + Flows + cleanup
Week 10    Buffer / v1 decommission
```

Two-engineer pace: Phase 1 starts during Phase 0 wrap (engineer 2 works on shared component library); Phases 2 + 4 can overlap (Phase 4 reuses WaPhonePreview + TemplateEditor primitives shipped in Phase 3 backend prep). Net: 6-7 weeks.

### Required green-lights before kickoff (from audit §9)

These must be answered before Phase 0 starts:

| # | Question | Default if no answer |
|---|---|---|
| §9.1 | Two-Space approach? | Yes (recommended) |
| §9.2 | Folder name `vite_dashboard/`? | Yes |
| §9.3 | Migration order | Order in this doc |
| §9.4 | Scheduling feature in Phase 3? | Yes |
| §9.5 | v1 freeze period before deletion? | 30-day freeze |
| §9.6 | Auth: Bearer or session? | Bearer (matches v1) |
| §9.7 | Plan D coordination | Option B (freeze + port) |
| §9.8 | Phase 5 rename target | `dashboard/` (locked) |
| §9.9 | Domain configs location | `config/dashboard/` (created 2026-05-04, see STANDARDS §11) |

---

## Production-readiness principle (no scaffolding)

**Decision:** every artifact this plan produces ships **production-ready**, not as scaffolding to be filled in later. This applies to YAMLs, Zod schemas, loaders, engines, components, API endpoints, and CI tooling.

### What "production-ready" means concretely

1. **YAMLs are complete, validated, and runnable from day one.** No placeholder values. Every key the schema declares is populated with a real value (not `TODO`, not empty string, not `null` unless null is the documented zero-value). Zod parses the YAML at boot and throws on any drift; that throw must never fire in normal operation.
2. **Schemas reflect every field a YAML uses, with no `any` escapes.** No `extra: 'allow'` unless the doc explicitly says why a particular file accepts unknown keys (e.g. egress reports). Strict mode (`extra: 'forbid'`) is the default.
3. **Loaders fail loud at boot.** `configLoader.bootstrap()` either returns fully-validated data or throws. No "graceful fallback to defaults" — defaults hide bugs.
4. **Engines produce typed outputs.** No `Record<string, unknown>` returns. Every engine's return type is a named TypeScript interface in `src/schemas/`.
5. **Components consume typed props.** No untyped props. No `as any`. Compile errors block merge.
6. **API endpoints have real implementations** (not 501 Not Implemented stubs). If a phase is too big to ship the full backend, the endpoint isn't declared yet — declare it the phase it actually ships.
7. **Phase 0 is a complete minimal product**, not an empty shell. v2 Space serves: a working login, a real Home page reading from `/api/v2/dashboard/home` (already exists in v1 — just expose via api_v2), the global `<AppShell>` with full sidebar nav, and 5 routes that show "Migrated in Phase N" with a link to the v1 equivalent. No `<ComingSoon />` blank screens.
8. **Migration scripts run cleanly against both SQLite (dev) and Postgres (prod).** Tested locally before any prod deploy. Idempotent (re-running is safe).
9. **Visual regression baselines must capture working UI**, not stubbed-out placeholders.
10. **Documentation is current at every phase merge.** No stale wording, no broken cross-references.

### What this changes vs the original plan

- Phase 0's "every route shows `<ComingSoon />`" is replaced with "every route loads its production YAML config + renders a usable page (Home is fully functional; other 5 routes show their real layout shell with a 'data wiring lands in Phase N' note that links to v1)."
- YAML files copied into `vite_dashboard/src/config/` are populated from `config/dashboard/` (the production source) at the moment Phase 0 starts, not as empty templates.
- Each per-phase task table item that says "skeleton" or "placeholder" is reframed as "minimum production-quality version."
- Bug fixes (B1-B20) ship inside the phase that owns the affected page; each fix is verified by a Playwright MCP step in that phase's verification section. No "fix in a later phase" deferrals unless explicitly noted.

### Why this matters

Scaffolding-first migrations carry two failure modes that this principle avoids:

1. **Half-built UI that ships to prod.** Stubs get forgotten; users hit "Coming soon" weeks after the deploy. Avoided here because Phase 0 has zero placeholder routes.
2. **YAML drift between schema and data.** When YAMLs are stubs, Zod validation is loose; when real data lands, validation tightens and breaks things. Avoided here because YAMLs are populated production data validated by strict schemas from day one.

### Trade-off

Phase 0 effort grows from 7-10 days to **8-12 days solo** because complete YAMLs + working Home page are larger than empty placeholders. This is intentional — the ~2 days of extra work upfront prevents the "half-built" failure modes above.

**Updated total:** 6.5-12 weeks (was 6.5-12 weeks).

---

## Standards and decisions reference

Every phase below assumes the decisions in [`STANDARDS_AND_DECISIONS.md`](./STANDARDS_AND_DECISIONS.md) hold. Quick index:

| § | Topic | Decision |
|---|---|---|
| 1 | Authentication | Bearer token in localStorage; no refresh; 401 → re-login |
| 2 | Schema migrations | Additive-only during dual-Space window; manual scripts under `scripts/migrations/` |
| 3 | Analytics | PostHog Cloud free tier; 15 critical events; no PII |
| 4 | Accessibility | WCAG 2.1 AA; eslint-plugin-jsx-a11y + axe-core in CI |
| 5 | Dark mode | Dark-only; `<html class="dark">` hardcoded |
| 6 | Browser support | Last 2 versions of Chrome/Edge/Safari/Firefox; ES2022 target |
| 7 | i18n | Deferred; English-only; UI strings centralized in `src/lib/strings.ts` for future swap |
| 8 | Visual regression | Storybook + Playwright + image-snapshot (free); revisit Chromatic later |
| 9 | Per-phase runbook | Pre-deploy checklist + 2h post-deploy watch (template below) |
| 10 | Onboarding | `vite_dashboard/README.md` shipped Phase 0; grows per phase |

If you're about to take a recurring decision (auth storage, lint config, browser test matrix, …), check the standards doc **first**. If it's not covered, propose an addition there before implementing.

---

## Per-phase runbook template

Every phase has acceptance criteria (the *what shipped*) plus a runbook (the *how we verify it landed safely*). Apply this template at every phase merge → deploy → monitor cycle.

### Pre-deploy checklist
- [ ] Acceptance criteria met (see phase section below)
- [ ] CI green on `migration/phase-N` branch
- [ ] Visual regression snapshots reviewed and approved
- [ ] Per-phase a11y checklist passed (Tab through, Esc closes, axe = 0 violations)
- [ ] Schema migration (if any) applied to prod DB; both v1 and v2 boot
- [ ] Sentry empty for new errors in last 24h on staging
- [ ] PostHog event firing verified for new events introduced this phase
- [ ] Manual test on Chrome desktop + Safari iOS

### Deploy
1. Merge `migration/phase-N` → `main` via PR
2. `python scripts/deploy_hf_v2.py`
3. Wait for HF Space build (~5 min); confirm "Running"
4. `curl https://himalayan-fibres-dashboard-v2.hf.space/api/v2/health` returns 200
5. Open SPA, log in, navigate the new page

### Post-deploy watch (2 hours)
- [ ] Sentry: zero new errors
- [ ] PostHog: events flowing within 5 min of first user action
- [ ] Smoke test: phase-specific paths (listed per phase)
- [ ] Slack `#dashboard-deploys`: post deploy summary

### Rollback
For Phases 1-4: v1 stays live; redirect team via Slack pin. No code rollback needed.
For Phase 5: `git checkout <previous-tag> && python scripts/deploy_hf_v2.py`.

### Playwright MCP verification — invocation pattern

Each phase has a "Playwright MCP verification" subsection at the end with concrete steps. Per CLAUDE.md, **never run the app locally** — drive the live HF Space URL with the Playwright MCP tools (headless) instead. The pattern across all phases:

1. **Navigate** to the live URL: `mcp__playwright__browser_navigate` with `https://himalayan-fibres-dashboard-v2.hf.space/<route>`
2. **Snapshot** the DOM accessibility tree: `mcp__playwright__browser_snapshot` — gives back element refs you can click/type into
3. **Interact**: `mcp__playwright__browser_click`, `mcp__playwright__browser_type`, `mcp__playwright__browser_fill_form`, `mcp__playwright__browser_select_option` using the refs from step 2
4. **Wait** for state changes: `mcp__playwright__browser_wait_for` with a selector or text
5. **Capture evidence**: `mcp__playwright__browser_take_screenshot` saved to `reports/audit_vite_migration_plan/verifications/phase_N/<step>.png`
6. **Inspect logs**: `mcp__playwright__browser_console_messages` to catch JS errors; `mcp__playwright__browser_network_requests` to verify API calls

For viewport-dependent verifications (mobile vs desktop), use `mcp__playwright__browser_resize` between snapshots.

**Output convention.** Each phase's verification produces a `verifications/phase_N/` folder with:
- `report.md` — pass/fail per step
- `step_*.png` — evidence screenshots
- `console.log` — captured browser console output

Verifications run after the 2-hour watch as a final gate before marking a phase as accepted.

### Phase-specific smoke tests

Run after each deploy as part of the 2-hour watch:

| Phase | Smoke test path |
|---|---|
| 0 | Login + see `<ComingSoon />` on every nav route + Sentry test event captured |
| 0.5 | n/a (no deploy). Acceptance gate: `repro/README.md` committed with severity calibrations + 4-8 baseline screenshots saved in `reports/audit_vite_migration_plan/repro/` |
| 1 | Filter contacts by segment → edit one (Profile + Notes tab) → save → row updates |
| 2 | Open a conversation in 24h window → send text → see bubble appear; open closed-window contact → composer disabled, "Send template" CTA visible |
| 3 | Compose a 5-recipient email broadcast → confirm dialog → submit → poll job → completion notification fires |
| 4 | Edit an approved template → save → `_v2` clone created in list; Sync from Meta shows progress and increments count |
| 5 | Home page shows live KPI counts (compare to v1 numbers); sidebar grouped by channel; mobile viewport (414px) usable |

---

## Phase 0 — Foundation (1.5-2 weeks, was 1 week)

**Goal.** v2 HF Space deployed with **production-quality foundation**: full toolchain (TS types, tests, observability, deploy script), complete validated YAMLs, working configLoader + engines, a fully-functional Home page reading from real data, and shell renderings of the other 5 routes (each showing the page's real `<AppShell>` + sidebar position + "Full feature lands in Phase N" content card linking to the v1 equivalent). **No `<ComingSoon />` placeholders.** Every subsequent phase plugs into this foundation by replacing the route's content card with the actual page.

**Prerequisites.** All §9 decisions answered. v1 Space credentials available (`HF_TOKEN`).

### Backend tasks

| Task | File(s) | Notes |
|---|---|---|
| Scaffold `api_v2/` FastAPI app | `api_v2/main.py`, `api_v2/__init__.py` | Mirrors `hf_dashboard/app.py` structure |
| Health endpoint | `api_v2/routers/health.py` | `GET /api/v2/health` returns `{"status":"ok","version":"v2-phase0"}` |
| Auth middleware | `api_v2/deps.py::auth_dependency` | Bearer token check against `APP_PASSWORD` env var. Returns 401 if missing/wrong. (Cookie session is a Phase 0 alternative if §9.6 chooses it.) |
| Sentry wiring | `api_v2/main.py` | `sentry_sdk.init()` with `SENTRY_DSN` env var; capture FastAPI middleware |
| OpenAPI schema export | implicit via FastAPI | `/openapi.json` returns schema for type-gen |
| Static SPA mount | `api_v2/main.py` | Mount `static/` at `/` (catch-all to serve `index.html` for client-side routes) |
| Import smoke test | `api_v2/tests/test_imports.py` | Imports every module under `hf_dashboard/services/`, `engines/`, `loader/`. CI fails the build if any module won't load |
| pytest config | `api_v2/conftest.py`, `pyproject.toml` | DB fixture using SQLite for tests (matches local-dev pattern) |

### Frontend tasks

| Task | File(s) | Notes |
|---|---|---|
| Vite scaffold | `vite_dashboard/` | `pnpm create vite vite_dashboard --template react-ts`, then immediately commit production-grade `vite.config.ts` with vite-plugin-yaml + path aliases (`@`, `@domain`) configured |
| TailwindCSS + Shadcn UI | `tailwind.config.ts`, `components/ui/` | Use Shadcn CLI to generate base primitives. Tailwind theme extends from `src/styles/tokens.ts` which is generated at build time from `config/dashboard/theme/default.yml` — single source of truth |
| **Production YAMLs** | `vite_dashboard/src/config/{theme,dashboard,pages,shared}/*.yml` | **Complete, populated, runnable.** Theme + sidebar + 6 page YAMLs + shared/{kpi,status_badges,filters}.yml. Values come from `config/dashboard/` (the v1-shared source). No placeholder values. |
| **Production Zod schemas** | `vite_dashboard/src/schemas/**` | Strict `extra: 'forbid'`, no `any`, every YAML key reflected. Test suite covers each schema parsing its YAML successfully. |
| **configLoader (production)** | `vite_dashboard/src/loaders/configLoader.ts` | Singleton, async `bootstrap()` that loads + validates every YAML at app start. Throws on validation failure (caught by main.tsx and rendered as fatal error UI). No graceful fallback. |
| **Engines (production)** | `vite_dashboard/src/engines/{themeEngine,navigationEngine,pageEngine,kpiEngine,statusEngine,filterEngine}.ts` | Each typed; takes validated config; returns typed result. Unit tests cover each engine's transform. |
| React Router v6 | `src/App.tsx`, `src/routes/` | One route per page. Home is fully wired to `/api/v2/dashboard/home`. Other 5 routes render `<AppShell>` + a `<MigrationStatusCard>` ("Full feature lands in Phase N — open in v1") with link to v1 equivalent route. |
| TanStack Query | `src/lib/queryClient.ts` | Default staleTime 30s; window-focus refetch on. Production retry/error policy configured. |
| Theme tokens | `src/styles/theme.css`, `tailwind.config.ts` | Match `hf_dashboard/shared/theme.py::COLORS` exactly so v1 and v2 read as one product. CSS variables emitted by `themeEngine.applyToDocument()` at boot. |
| `<AppShell>` | `src/components/layout/AppShell.tsx` | Production sidebar with grouped nav from `config/dashboard/sidebar.yml` (no placeholder nav). Content area + header. Skip-to-content link for a11y. |
| `<NavSidebar>` | `src/components/layout/NavSidebar.tsx` | Reads from a `nav_items.ts` array (mirrors `config/dashboard/sidebar.yml` structure for now) |
| Sentry wiring | `src/main.tsx` | `Sentry.init()` with `VITE_SENTRY_DSN` |
| `openapi-typescript` pipeline | `package.json::scripts::gen:types`, `.husky/pre-commit` | `npx openapi-typescript http://localhost:7860/openapi.json -o src/api/schema.d.ts` |
| API fetcher base | `src/api/client.ts` | Type-safe wrapper using generated types; auth header injected |
| `<MigrationStatusCard>` | `src/components/layout/MigrationStatusCard.tsx` | Production component (not a placeholder): shows the page name, the phase the full feature ships in, and a working "Open in v1 dashboard" link to the equivalent v1 URL. Replaces the original `<ComingSoon />` placeholder per the production-readiness principle. |
| Login page | `src/routes/login.tsx` | If §9.6 chooses Bearer: simple password form → store in localStorage. If session: cookie set by FastAPI |
| Vitest config | `vitest.config.ts`, `src/test-setup.ts` | Component test runner |
| PostHog setup | `src/lib/analytics.ts`, `.env.example` | Per STANDARDS §3 — `posthog-js` init, `track()` helper, `VITE_POSTHOG_KEY` env var |
| a11y lint + axe | `.eslintrc.cjs`, `package.json` devDeps | `eslint-plugin-jsx-a11y`, `@axe-core/react` for dev-mode warnings |
| Storybook + Playwright | `vite_dashboard/.storybook/`, `vite_dashboard/tests/visual.spec.ts` | Visual regression per STANDARDS §8 |
| String constants | `src/lib/strings.ts` | Per STANDARDS §7 — central UI string registry to ease future i18n |
| Onboarding README | `vite_dashboard/README.md` | Per STANDARDS §10 — production minimum ships in Phase 0 (covers run-locally + structure + conventions); phases add sections as they land |
| Browser-not-supported guard | `vite_dashboard/index.html` | Inline JS check for `Promise` + `fetch` per STANDARDS §6 |

### Tooling tasks

| Task | File(s) | Notes |
|---|---|---|
| Multi-stage Dockerfile | `Dockerfile.v2` | Per audit §5.3 |
| Deploy script | `scripts/deploy_hf_v2.py` | Mirrors `scripts/deploy_hf.py`; uploads to `himalayan-fibers-dashboard-v2` |
| Create v2 HF Space | manual via HF UI | Owner: prashantiitkgp08; SDK: Docker; visibility: private during dev |
| GitHub Actions CI | `.github/workflows/v2-ci.yml` | Runs: `pytest api_v2/`, `cd vite_dashboard && pnpm install && pnpm lint && pnpm tsc --noEmit && pnpm test`, `pnpm test:visual` (Storybook+Playwright snapshots) |
| Pre-commit hook | `.husky/pre-commit` | Runs `pnpm gen:types` if API code changed |
| Bundle-size check | `vite_dashboard/scripts/check-bundle-size.cjs` | Fails CI if initial bundle > 500 KB gzipped |
| Migration scripts dir | `scripts/migrations/__init__.py`, `MIGRATION_LOG.md` | Per STANDARDS §2 — additive-only schema policy; one file per migration |
| Color contrast check | `scripts/check-contrast.py` | Per STANDARDS §4 — verifies theme YAML colors meet WCAG 2.1 AA at build time |
| Config-sync pre-commit hook | `.husky/pre-commit`, `tools/check-config-sync.sh` | Per STANDARDS §11 — diffs `config/dashboard/` vs `hf_dashboard/config/`; fails commit if they diverge during the dual-Space window |
| Plan D coordination audit | one-time review note in `MIGRATION_NOTES.md` | Per STANDARDS table §9.7 — list landed vs in-flight Plan D phases; freeze in-flight work; document anything to port forward to v2 API layer |

### Acceptance criteria

- [ ] v2 Space `himalayan-fibers-dashboard-v2` is live and serving the SPA at the Space URL
- [ ] Hitting any v2 route renders the production `<AppShell>` with grouped sidebar nav loaded from YAML (no hardcoded nav array)
- [ ] **Home page is fully functional** — KPIs, lifecycle bars, activity feed all populated with real data from `/api/v2/dashboard/home`. Matches v1 `/home` numerically.
- [ ] **Other 5 routes render `<MigrationStatusCard>`** showing phase + working v1 link. No `<ComingSoon />` blank screens.
- [ ] **All YAMLs validate at boot.** Deliberately introduce a typo in `config/theme/default.yml`; app shows the Zod error message as a fatal error screen (verifies fail-loud behavior). Revert the typo.
- [ ] **Every YAML config has a corresponding Zod schema** that parses it successfully. CI step runs `pnpm test:schemas` covering each.
- [ ] `GET /api/v2/health` returns 200; `GET /api/v2/openapi.json` returns the schema
- [ ] `GET /api/v2/dashboard/home` returns real counts (matches v1)
- [ ] Login page works (Bearer or session per §9.6)
- [ ] Sentry receives a test event from both backend and frontend (deliberate throw → captured in Sentry dashboard)
- [ ] PostHog receives a test `auth_login` event from the frontend
- [ ] CI runs (passing) on every push to a `migration/*` branch — includes pytest, eslint, vitest, Playwright visual, bundle-size
- [ ] `pnpm gen:types` produces a non-empty `vite_dashboard/src/api/schema.d.ts`
- [ ] Import smoke test passes (`pytest api_v2/tests/test_imports.py`)
- [ ] `axe` reports zero violations on `/login` and `/home` (Coming Soon)
- [ ] Color contrast check (`scripts/check-contrast.py`) passes against `config/theme/default.yml`
- [ ] Initial bundle ≤ 500 KB gzipped
- [ ] `python scripts/deploy_hf_v2.py --dry-run` lists files; full deploy works
- [ ] `vite_dashboard/README.md` production-minimum version committed (per STANDARDS §10) covering run-locally + structure + conventions

### Risks specific to Phase 0

- **HF Space build timeout.** First Docker build with Vite + Python may exceed HF's free-tier build limits. Mitigation: pre-warm by running Docker locally first; if HF build times out, slim the base image or move Vite build to GitHub Actions and upload the `dist/` directly.
- **CORS.** SPA + API on the same port avoids CORS, but only if FastAPI mounts the SPA at root and the API at `/api/v2`. Verify with a deliberate fetch from the SPA in the smoke test.
- **`openapi-typescript` schema drift.** The pre-commit hook runs only on the dev's machine. Add a CI step that regenerates types and fails the build if the committed file is stale.

### Estimated effort

Phase 0 absorbed standards-driven setup work in this revision (PostHog, axe + a11y lint, Storybook + Playwright visual regression, strings.ts, README, browser guard, migrations dir, contrast check, config-sync hook, Plan D audit) **and** the production-readiness expansion (complete YAMLs, full Zod coverage, working Home page, real engines). Updated estimate:

- Solo: 8-12 days
- With prior experience in this stack: 5-7 days
- Without (learning): 12-16 days

### Playwright MCP verification

Output: `verifications/phase_0/`

1. `browser_navigate` → `https://himalayan-fibres-dashboard-v2.hf.space` → expect production login page
2. `browser_snapshot` → screenshot the login form → save as `step_01_login.png`
3. `browser_type` password field → `browser_click` Login → `browser_wait_for` `/home` to load with real KPI numbers (no spinner left running)
4. `browser_take_screenshot` `/home` → save `step_04_home_real_data.png`. **Numbers must match v1 `/home` exactly** (open v1 in second tab; manual diff)
5. `browser_evaluate` → `await fetch('/api/v2/dashboard/home').then(r => r.json())` → response shape matches `<HomePage>`'s consumer types (verifies API is real, not stubbed)
6. `browser_navigate` to each Phase-1+ route (`/contacts`, `/wa-inbox`, `/broadcasts`, `/wa-templates`, `/flows`) → snapshot the `<MigrationStatusCard>`. Each card must show: page name, phase, working "Open in v1" link
7. `browser_click` the v1 link on `/contacts` → confirm new tab opens v1's contacts equivalent (verifies link is real, not `#`)
8. `browser_navigate` → `/api/v2/health` → response body contains `"status":"ok"`
9. `browser_navigate` → `/api/v2/openapi.json` → response is non-empty JSON; includes the dashboard.home schema
10. **YAML fail-loud test:** introduce a typo in `vite_dashboard/src/config/theme/default.yml` (e.g. rename `primary` → `primrary`) → redeploy or hot-reload → verify the app renders a fatal error screen with the Zod validation message naming the bad field. Revert the typo.
11. `browser_evaluate` → `() => { throw new Error('sentry test'); }` → manual check that Sentry captured the event
12. `browser_console_messages` → expect empty across every route (no JS errors anywhere)
13. `browser_resize` to 414×896 → snapshot `/home` and one MigrationStatusCard route → verify responsive layout works at mobile width; save as `step_13_mobile_*.png`

**Pass criteria:** all 13 steps complete; Home page numerically matches v1 (step 4); YAML typo reproduces fail-loud (step 10); v1 deep-links work (step 7); no console errors anywhere.

---

## Phase 0.5 — Reproduce reported bugs (2-3 days)

**Goal.** Calibrate audit severities by reproducing each High/Medium-severity bug on the live v1 Space using Playwright MCP. Save baseline screenshots that v2 must beat.

**Prerequisites.** Phase 0 acceptance met (so the dev environment is ready). v1 Space accessible.

### Tasks

| Task | Bug | Method |
|---|---|---|
| Reproduce template variable scroll | B1 | Open WA Inbox → pick `order_confirmation` → screenshot var area at 1440×900 and 1024×768. Count visible Textboxes. If all 4 visible at 1440px, demote B1 from "High (likely)" to "Medium" |
| Reproduce 8-slot always-visible | B5 | Open Email Broadcast → pick a 2-var template (e.g. `welcome`) → screenshot variable section. Confirm 6 empty `Variable N` slots are visible |
| Reproduce search-reset on extra keystroke | B9 | Open Email Broadcast → Individual mode → type "Raj" → click result → type "x". Confirm selection is lost |
| Reproduce Send Now / Test button proximity | B10 | Screenshot send button row at default zoom; measure visual distance |
| Reproduce email channel filter empty | B6 | Open Broadcast History → pick Email channel → confirm zero rows even after sending an email broadcast in another tab |
| Reproduce composer-enabled-with-no-window | B2 | Open WA Inbox → pick a contact with no inbound history → confirm message input is editable; type + send → confirm error appears |

### Output

Files in `reports/audit_vite_migration_plan/repro/`:

```
repro/
├── README.md                  # what each screenshot shows + final severity calibration
├── b1_order_confirmation_1440.png
├── b1_order_confirmation_1024.png
├── b2_composer_enabled.png
├── b2_send_error.png
├── b5_eight_slots.png
├── b6_email_filter_empty.png
├── b9_search_reset.gif        # animated; needs sequence of frames
└── b10_button_proximity.png
```

### Acceptance criteria

- [ ] Every High-severity bug from §4 has either a confirmed reproduction or a "could not reproduce — demote to X" entry in `repro/README.md`
- [ ] Every Medium-severity bug from §4 has the same
- [ ] Audit §4 severities are updated to match reproduction findings
- [ ] If B1 cannot be reproduced at 1440×900, the v2 plan for `<TemplateVariablesForm>` is simplified accordingly

### Risks

- **Playwright MCP can't authenticate to v1 Space.** v1 has no auth (`APP_PASSWORD` unset), so this should be straightforward. If it gains auth before Phase 0.5 runs, capture credentials via env.
- **Screenshots vary by browser/viewport.** Use Chromium at deterministic viewport (1440×900) for the "default" shots; explicitly note when smaller viewports change findings.

### Estimated effort

- 2-3 days for the full set above

### Playwright MCP verification — concrete steps

Output: `reports/audit_vite_migration_plan/repro/`

For each bug below, the pattern is: `browser_resize` → `browser_navigate` → `browser_snapshot` → interactions → `browser_take_screenshot`.

**B1 — WA template variable scroll.** v1 URL: `https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/`
1. `browser_resize` 1440×900 → `browser_navigate` "/" → click WhatsApp tab
2. `browser_click` first conversation → in tools panel `browser_select_option` Category → UTILITY, Template → order_confirmation
3. `browser_take_screenshot` → save `repro/b1_order_confirmation_1440.png`. Count visible Textboxes.
4. `browser_resize` 1024×768 → repeat snapshot → save `repro/b1_order_confirmation_1024.png`

**B2 — composer enabled with no window.**
1. `browser_navigate` "/wa_inbox" → click a contact with no inbound history
2. `browser_evaluate` → check the message-input element is `:not([disabled])` (capture as evidence)
3. `browser_type` input "Hello" → `browser_click` Send → `browser_wait_for` error toast
4. `browser_take_screenshot` → save `repro/b2_send_error.png`

**B5 — 8 always-visible variable slots.**
1. `browser_navigate` "/email_broadcast" → `browser_select_option` template → welcome (2-var template)
2. `browser_take_screenshot` of var area → save `repro/b5_eight_slots.png`. Count empty `Variable N` slots.

**B6 — email channel filter empty.**
1. `browser_navigate` "/broadcast_history" → click "Email" channel filter
2. `browser_snapshot` → expect zero rows in table
3. `browser_take_screenshot` → save `repro/b6_email_filter_empty.png`

**B9 — search reset on extra keystroke.**
1. `browser_navigate` "/email_broadcast" → click Individual mode → `browser_type` search "Raj"
2. `browser_wait_for` dropdown options → `browser_click` first match
3. `browser_type` search "x" (one more character)
4. `browser_snapshot` → confirm whether the previously-selected value cleared
5. Capture sequence as `repro/b9_search_reset.gif` (3 frames stitched manually if needed)

**B10 — button proximity.**
1. `browser_navigate` "/email_broadcast" → fill subject + pick a template
2. `browser_take_screenshot` of the send-button row → save `repro/b10_button_proximity.png`. Measure pixel distance between Send Now and Send Test.

After each capture, append findings to `repro/README.md`: file path, observed behavior, severity confirmation/demotion.

---

## Phase 1 — Contacts (1 week)

**Goal.** Migrate the Contacts page. Internal team uses v2 Contacts for daily ops by end of week. v1 Contacts stays live as a read-only fallback.

**Prerequisites.** Phase 0 acceptance. (Phase 0.5 nice-to-have but not blocking — Contacts has no high-severity reported bugs.)

### Backend tasks

#### New files

```
api_v2/
├── routers/
│   └── contacts.py          # all endpoints below
├── schemas/
│   ├── contacts.py          # Pydantic request/response models
│   └── segments.py          # Segment list response
└── tests/
    └── test_contacts.py
```

#### Endpoints

| Method | Path | Purpose | Reuses |
|---|---|---|---|
| GET | `/api/v2/contacts` | Paginated, filterable list | `services/segments.py`, `Plan D Phase 1.3` column-narrowing |
| GET | `/api/v2/contacts/{id}` | Full record + segments + activity + threaded notes | `services/interactions.py::get_interactions`, `services/segments.py::segments_for_contact` |
| PATCH | `/api/v2/contacts/{id}` | Edit (name, phone, email, lifecycle, consent, tags, notes) | `services/interactions.py::log_interaction(kind="manual_edit")` for diff summary |
| POST | `/api/v2/contacts` | Create | UUID + log `kind="imported"` |
| POST | `/api/v2/contacts/{id}/notes` | Append note | `models.ContactNote` |
| POST | `/api/v2/contacts/import` | Multipart CSV/Excel upload | Pandas read + per-row Contact insert |
| GET | `/api/v2/contacts.csv` | Streaming download of all contacts | `StreamingResponse` with `Plan D Phase 1.2` 9-column select |
| GET | `/api/v2/segments` | Active segments + counts | `services/segments.py::get_active_segments_cached` |

#### Pydantic schemas

```python
# api_v2/schemas/contacts.py

class ContactListQuery(BaseModel):
    segment: str | None = None
    lifecycle: str | None = None
    country: str | None = None
    channel: Literal["all", "email", "whatsapp", "both"] = "all"
    tags: list[str] = []
    search: str = ""
    page: int = 0
    page_size: int = 50

class ContactRow(BaseModel):
    id: str
    first_name: str
    last_name: str
    company: str
    email: str
    phone: str
    wa_id: str | None
    lifecycle: str
    tags: list[str]
    country: str
    segments: list[str]  # segment IDs
    channels: list[Literal["email", "whatsapp"]]

class ContactListResponse(BaseModel):
    contacts: list[ContactRow]
    total: int
    page: int
    page_size: int
    total_pages: int

class ContactDetail(ContactRow):
    customer_type: str
    customer_subtype: str
    geography: str
    consent_status: str
    notes: str
    threaded_notes: list[ContactNoteOut]
    activity: list[InteractionOut]
    matched_segments: list[SegmentSummary]
```

#### Tests

- `test_contacts_list_pagination` — 100-row fixture, page through, verify count
- `test_contacts_list_filter_by_segment` — verify rule engine filters correctly
- `test_contacts_list_search_by_name` — case-insensitive
- `test_contacts_get_detail` — includes notes + activity + segments
- `test_contacts_patch_diff_logged` — `manual_edit` interaction created with summary
- `test_contacts_create_idempotency` — duplicate email returns 409
- `test_contacts_import_csv` — known fixture, expected count
- `test_contacts_import_excel` — same with .xlsx
- `test_contacts_csv_streams` — response is `Content-Type: text/csv`; first chunk arrives before last row queried

### Frontend tasks

#### New components

```
vite_dashboard/src/
├── routes/
│   └── contacts.tsx              # main route component
├── components/
│   ├── tables/
│   │   ├── DataTable.tsx         # generic, TanStack Table-based
│   │   ├── DataTablePagination.tsx
│   │   └── DataTableColumnToggle.tsx
│   ├── filters/
│   │   ├── FilterBar.tsx
│   │   ├── SegmentFilter.tsx
│   │   ├── LifecycleFilter.tsx
│   │   ├── CountryFilter.tsx
│   │   ├── ChannelFilter.tsx
│   │   └── TagsFilter.tsx        # multiselect with autocomplete
│   ├── badges/
│   │   ├── StatusBadge.tsx       # used here for consent_status
│   │   ├── ChannelBadge.tsx
│   │   ├── LifecycleBadge.tsx
│   │   └── SegmentPill.tsx
│   ├── contacts/
│   │   ├── ContactsTable.tsx     # composes DataTable + columns
│   │   ├── ContactDrawer.tsx     # Sheet with tabs
│   │   ├── ContactDrawerProfile.tsx
│   │   ├── ContactDrawerTags.tsx
│   │   ├── ContactDrawerNotes.tsx
│   │   ├── ContactDrawerActivity.tsx
│   │   ├── AddContactDialog.tsx
│   │   └── ImportContactsDialog.tsx
│   └── ui/                       # Shadcn primitives (auto-generated)
│       ├── table.tsx
│       ├── sheet.tsx
│       ├── dialog.tsx
│       ├── input.tsx
│       ├── select.tsx
│       ├── multi-select.tsx      # custom (Shadcn doesn't ship one)
│       └── ...
└── api/
    └── contacts.ts               # type-safe fetchers + TanStack Query hooks
```

#### URL state

Route: `/contacts?segment=domestic_b2b&lifecycle=engaged&channel=both&tags=premium,wool&search=raj&page=2`

State synchronization handled by a custom `useUrlState` hook that mirrors filter state to/from query params. Filters survive reload, are shareable, and `useQuery` keys are derived from the URL state directly so two tabs with the same URL share the same cache entry.

#### Bug fixes shipped in this phase

- **B7 (JS bridge for row edit)** — gone by construction. `<ContactsTable>` row click → `onClick={() => openDrawer(id)}`.
- **B8 (modal mount race)** — gone by construction. Shadcn `<Sheet>` and `<Dialog>` handle mount/unmount cleanly.
- **B19 (no URL routing)** — solved here for Contacts; pattern carries to all subsequent pages.

### Schema/DB

No schema changes.

### Acceptance criteria

- [ ] Filter, search, paginate work; URL reflects state
- [ ] Add Contact dialog: required fields validated, Save commits, table refreshes
- [ ] Import CSV/Excel: progress shown, count of imported/skipped reported
- [ ] Edit drawer: all 4 tabs (Profile / Tags / Notes / Activity) work; Save commits with diff log
- [ ] Add note appends to threaded notes, refreshes activity
- [ ] Download CSV streams correctly (verify with `curl -o contacts.csv` from a terminal)
- [ ] Internal team uses v2 Contacts for daily ops for at least 3 days without falling back to v1
- [ ] No console errors in browser DevTools during normal use
- [ ] Mobile viewport (414px): filters collapse to a sheet, table scrolls horizontally, drawer goes full-screen

### Risks specific to Phase 1

- **Segment rule engine performance under JSON serialization.** v1 evaluates segments in Python after loading rows. v2 should do the same in the API layer, but be careful not to re-evaluate per-row in the response builder (batch the loaded contacts into one rule eval pass, like v1 does).
- **Adhoc contact rows from v1 (B14).** These exist in the DB. The v2 list API should optionally hide them via a query param `include_adhoc=false` (default false). Surfaces them only when explicitly requested.
- **Tag autocomplete dataset size.** With 1000+ contacts, the all-tags query at page-load time can be slow. Cache for 60s server-side.

### Estimated effort

- 5-7 days solo, with most of the time on `<DataTable>` (3-4 days for a robust implementation with sorting, virtualization, URL-sync, multi-select)

### Playwright MCP verification

Output: `verifications/phase_1/`

1. `browser_navigate` → v2 `/contacts` → `browser_snapshot` → verify table renders ≥1 row
2. `browser_select_option` Segment filter → "Engaged Domestic B2B" → `browser_wait_for` URL contains `?segment=`
3. `browser_take_screenshot` → save `step_02_filtered.png`. Verify URL persists filter (B19 fix).
4. `browser_click` "+ Add" → `browser_fill_form` (first_name, last_name, phone, email) → `browser_click` Save Contact
5. `browser_wait_for` toast "Contact added" → `browser_take_screenshot` → save `step_04_added.png`
6. `browser_click` first table row's Edit button → `browser_wait_for` drawer
7. Click each drawer tab (Profile / Tags / Notes / Activity); `browser_take_screenshot` each (`step_07a_profile.png` … `step_07d_activity.png`)
8. `browser_type` in Notes tab → click Add Note → verify new note appears in thread
9. Edit a Profile field → click Save changes → `browser_wait_for` toast → verify table row updates without page reload
10. `browser_console_messages` → expect no errors
11. `browser_resize` 414×896 → snapshot mobile layout → save `step_11_mobile.png`. Verify filters collapse and drawer goes full-screen
12. **B7+B8 verified by construction:** drawer open/close + row edit buttons work without the JS bridge

**Pass criteria:** all 11 steps complete; URL state survives reload (Cmd+R after step 2, snapshot still shows the filter applied); no console errors.

---

## Phase 2 — WhatsApp Inbox (1.5 weeks)

**Goal.** Migrate the team's most-used page. Fix B1 and B2. Ship real-time inbound message updates via SSE.

**Prerequisites.** Phase 0 + Phase 0.5 + Phase 1 acceptance. Phase 0.5 is critical here — B1 and B2 are the headline fixes.

### Backend tasks

#### New files

```
api_v2/
├── routers/
│   └── wa_inbox.py
├── schemas/
│   ├── wa_inbox.py
│   └── wa_messages.py
├── services/                    # NEW — v2-only services that don't fit in hf_dashboard/
│   └── wa_event_bus.py          # in-memory pub/sub for webhook → SSE
└── tests/
    └── test_wa_inbox.py
```

#### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/wa/conversations` | Active conversations list (one JOIN query, mirrors `wa_inbox.py:_get_active_conversations`) |
| GET | `/api/v2/wa/conversations/{contact_id}` | Header + last 50 messages |
| GET | `/api/v2/wa/conversations/{contact_id}/window` | Returns `{is_open: bool, hours_remaining: int}` |
| GET | `/api/v2/wa/conversations/stream` | **SSE** — streams `{contact_id, message}` events as the webhook receives them |
| POST | `/api/v2/wa/conversations/{contact_id}/messages` | Send text or media (validates 24h window) |
| POST | `/api/v2/wa/conversations/{contact_id}/template-sends` | Send template (bypasses window) |
| POST | `/api/v2/wa/media` | Multipart upload → Meta media_id |
| GET | `/api/v2/wa/contacts/search?q=...` | For Start New Conversation autocomplete |
| GET | `/api/v2/wa/templates` | List active templates (for the template sheet) |
| GET | `/api/v2/wa/templates/{name}` | Full template incl. variables (for the variables form) |

#### SSE wiring

The current webhook handler (`hf_dashboard/app.py:75-96`) writes to the DB. Add a side-effect: publish an event to `wa_event_bus`. The SSE endpoint subscribes per-connection.

```python
# api_v2/services/wa_event_bus.py
import asyncio
from collections import defaultdict

class WaEventBus:
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, contact_id: str | None) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=100)
        key = contact_id or "*"  # "*" = all conversations
        self._subscribers[key].add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue, contact_id: str | None):
        key = contact_id or "*"
        self._subscribers[key].discard(q)

    async def publish(self, contact_id: str, event: dict):
        for key in (contact_id, "*"):
            for q in self._subscribers.get(key, set()):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # drop event for slow consumer

bus = WaEventBus()
```

The webhook handler is updated to call `await bus.publish(contact_id, event)` after the DB commit. The SSE endpoint uses `EventSourceResponse` (from `sse-starlette`).

#### Tests

- `test_conversations_list_returns_one_per_contact` — 50-message fixture for 5 contacts
- `test_conversation_window_open_when_inbound_within_24h`
- `test_conversation_window_closed_when_no_inbound`
- `test_send_text_succeeds_when_window_open`
- `test_send_text_blocked_when_window_closed` — returns 412 Precondition Failed
- `test_send_template_works_outside_window` — bypasses
- `test_sse_receives_event_from_webhook` — fire webhook fixture, assert SSE consumer receives event within 1s

### Frontend tasks

#### New components

```
vite_dashboard/src/
├── routes/
│   └── wa-inbox.tsx                # /wa-inbox/:contactId?
├── components/
│   ├── chat/
│   │   ├── ConversationList.tsx
│   │   ├── ConversationListItem.tsx     # avatar + name + preview + unread badge
│   │   ├── ChatPanel.tsx
│   │   ├── ChatHeader.tsx               # name + 24h-window chip
│   │   ├── ChatMessages.tsx             # virtualized list of bubbles
│   │   ├── MessageBubble.tsx            # routes to MessageBubbleText / Media
│   │   ├── MessageBubbleText.tsx
│   │   ├── MessageBubbleMedia.tsx       # image, document, audio, video
│   │   ├── ChatComposer.tsx             # text input + attach + send
│   │   ├── ChatComposerDisabled.tsx     # shown when window closed (B2 fix)
│   │   ├── MediaAttachmentDialog.tsx
│   │   ├── WindowChip.tsx               # green "23h left" / amber "closed"
│   │   └── StartNewConversation.tsx     # contact search + select
│   ├── templates/
│   │   ├── TemplateSheet.tsx            # Shadcn Sheet, opened from composer
│   │   ├── TemplateCategoryFilter.tsx
│   │   ├── TemplatePicker.tsx
│   │   ├── TemplateVariablesForm.tsx    # B1 fix: vertical stack, no scroll
│   │   ├── TemplatePreview.tsx          # WhatsApp-style bubble preview
│   │   └── TemplateSendButton.tsx
│   └── ...
├── hooks/
│   ├── useConversationStream.ts         # SSE consumer
│   └── useWindowStatus.ts               # 24h window calculation
└── api/
    └── wa_inbox.ts
```

#### Key behavioral fixes

- **B1 (variable scroll).** `<TemplateVariablesForm>` renders one Textbox per variable in a `<div className="flex flex-col gap-3">` — natural height. The container has no `overflow-y` constraint. The preview underneath is in a separate sibling `<TemplatePreview>` that itself can scroll if too tall, but the variables are always fully visible.
- **B2 (composer disabled state).** `<ChatComposer>` reads from `useWindowStatus(contactId)`. When `is_open === false`, it renders `<ChatComposerDisabled>` instead — a banner saying "This conversation's 24-hour window is closed (or no inbound message yet). Send a template to start." with a primary button "Send template" that opens `<TemplateSheet>`. The text input is not rendered at all in this state.
- **Real-time updates (B18).** `useConversationStream(contactId)` opens an EventSource to `/api/v2/wa/conversations/stream?contact_id={id}`. On each event, invalidate the `["wa", "conversations", contactId, "messages"]` query and let TanStack refetch the latest messages.

#### URL state

Route: `/wa-inbox/:contactId?` — picking a conversation deep-links it. Refreshing the page restores the conversation. Sharing the URL with a teammate jumps them to the same chat.

### Schema/DB

No schema changes for messaging. Optional: add an `unread_count` column on `WAChat` if not already present (audit didn't verify). Migration script under `scripts/migrations/` if needed.

### Acceptance criteria

- [ ] Active conversation switching works; URL updates
- [ ] Send text in 24h window works
- [ ] Composer is **disabled** with the B2-fix CTA when window is closed
- [ ] Send media (image, document) works
- [ ] Send template (with all 4 vars of `order_confirmation` visible without scroll — **B1 fix**) works
- [ ] Filled-template message appears in chat after send (substituted body, not "[Template: ...]")
- [ ] Inbound message from webhook appears in active chat **without page reload** (within 2s — verify with a test webhook fixture)
- [ ] 24h-window chip in chat header shows correct hours-remaining or "closed"
- [ ] Start New Conversation: search returns matching contacts, picking one opens the chat with the new-conversation banner
- [ ] Mobile viewport (414px): conversation list as a slide-over Sheet from the left edge; chat full-width when a conversation is selected
- [ ] All v1 functionality replicated (no regression)

### Risks specific to Phase 2

- **SSE behind HF Space proxy.** Test in Phase 0 (per audit §7 risks). If broken, fall back to TanStack Query's `refetchInterval: 5000` for the messages query — slightly worse UX but functional.
- **Webhook → SSE wiring requires async pubsub.** The current webhook handler in `hf_dashboard/app.py` is sync-style (uses sync DB). The v2 webhook handler in `api_v2/main.py` should be async and call `await bus.publish(...)` after DB commit. **Critical:** v1's webhook handler stays in v1; the v2 webhook handler is registered on the v2 Space's domain. Update Meta's webhook URL to v2 ONLY when v2 reaches parity.
- **Media uploads to Meta.** `WhatsAppSender.upload_media()` is sync. Call it from FastAPI's `BackgroundTasks` or use `run_in_threadpool` to avoid blocking the event loop.
- **Variable form stale state.** Switching templates should reset variable values. Use a key-prop trick: `<TemplateVariablesForm key={template.name} />` so React unmounts/remounts the form on template change.

### Estimated effort

- 7-10 days solo (this is the most complex page in v2)
- ~3 days are SSE wiring + testing
- ~3 days are chat UI components (bubbles, attachments, virtualization)
- ~2 days are template sheet + variables form + B1/B2 fixes
- ~2 days for mobile responsive + polish

### Playwright MCP verification

Output: `verifications/phase_2/`

1. `browser_navigate` → `/wa-inbox` → `browser_snapshot` → verify ConversationList renders
2. `browser_click` an active conversation (one with `last_wa_inbound_at` within 24h) → `browser_wait_for` chat header
3. `browser_take_screenshot` → save `step_03_chat_open.png`. Verify WindowChip shows hours-remaining (e.g. "23h left")
4. `browser_type` in composer "Test message" → `browser_click` Send → `browser_wait_for` outbound bubble appears
5. `browser_take_screenshot` → save `step_05_text_sent.png`
6. **B1 fix verification:** `browser_click` "Send template" button → `browser_wait_for` TemplateSheet
7. `browser_select_option` Template → `order_confirmation`
8. `browser_take_screenshot` of the variables area → save `step_08_b1_vars.png`. **All 4 variable fields must be visible without scrolling.**
9. `browser_evaluate` → `() => Array.from(document.querySelectorAll('[data-template-var]')).every(el => el.getBoundingClientRect().bottom < window.innerHeight)` → must return `true`
10. Fill all 4 variables → `browser_click` Send Template → verify filled body appears in chat (substituted, not "[Template: ...]")
11. **B2 fix verification:** `browser_navigate` to a contact with no inbound history (or window > 24h) → `browser_snapshot`
12. `browser_evaluate` → confirm message-input element has `disabled` attribute or is not present in DOM
13. `browser_take_screenshot` → save `step_13_b2_disabled.png`. Verify "Send a template to open a conversation" CTA visible
14. **SSE verification:** keep tab open; from another tool fire a test webhook payload to `/webhook/whatsapp`; within 3s the new bubble should appear without page reload
15. `browser_take_screenshot` after SSE delivery → save `step_15_sse.png`
16. `browser_resize` 414×896 → verify ConversationList collapses to slide-over Sheet; chat is full-width

**Pass criteria:** all 16 steps complete; B1 verified by step 9 returning `true`; B2 verified by composer disabled state; SSE delivers inbound within 3s.

---

## Phase 3 — Broadcasts unified (1.5 weeks)

**Goal.** Merge 4 v1 pages (`broadcasts.py`, `broadcast_history.py`, `email_broadcast.py`, `email_analytics.py`) into one v2 page with 3 tabs: **Compose / History / Performance**. Add scheduling. Move email sending to `BackgroundTasks` (B13). Fix B3, B6, B10.

**Prerequisites.** Phase 0, 0.5, 1, 2 acceptance. Phase 2 ships the WaPhonePreview component which Phase 3 reuses.

### Backend tasks

#### New files

```
api_v2/
├── routers/
│   ├── broadcasts.py              # all endpoints below
│   └── jobs.py                    # job status polling (shared infra for async sends)
├── schemas/
│   ├── broadcasts.py
│   └── jobs.py
├── services/
│   ├── broadcast_jobs.py          # BackgroundTasks orchestration; in-memory job table
│   └── scheduler.py               # cron-ish loop that fires due scheduled broadcasts
└── tests/
    ├── test_broadcasts.py
    └── test_scheduler.py
```

#### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/broadcasts` | Unified list reading both `Broadcast` and `Campaign` tables, normalized into one shape |
| GET | `/api/v2/broadcasts/{id}` | Detail + recipients (paginated) |
| POST | `/api/v2/broadcasts/audience-preview` | Body: filters → returns funnel + breakdown |
| POST | `/api/v2/broadcasts/cost-estimate` | Body: filters + template → returns cost cards |
| POST | `/api/v2/broadcasts/wa` | Send WA broadcast (synchronous; small batches OK) |
| POST | `/api/v2/broadcasts/email` | Queue email broadcast (`BackgroundTasks`); returns `{job_id, broadcast_id}` |
| GET | `/api/v2/jobs/{job_id}/status` | `{status: "queued"\|"running"\|"done"\|"failed", progress: 0-100, message: str}` |
| PATCH | `/api/v2/broadcasts/{id}` | Schedule (set `scheduled_at`) or cancel a scheduled broadcast |
| GET | `/api/v2/broadcasts/{id}/performance` | KPIs + per-recipient table |

#### Schema changes

Migration script under `scripts/migrations/2026_05_add_scheduled_at.py`:

```python
# Adds:
#   ALTER TABLE broadcasts ADD COLUMN scheduled_at TIMESTAMP WITH TIME ZONE;
#   ALTER TABLE campaigns ADD COLUMN scheduled_at TIMESTAMP WITH TIME ZONE;
# Idempotent: checks information_schema.columns first.
```

Update `services/models.py` to add `scheduled_at` to both `Broadcast` and `Campaign`. **Mirror this in v1's `services/models.py` since both backends share the file** — but note that v1 won't expose the new field through any UI; it's only read/set by v2.

#### Background job orchestration

Simple in-memory job table (since HF Space runs one container):

```python
# api_v2/services/broadcast_jobs.py
class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobState] = {}

    def create(self, job_type: str) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = JobState(status="queued", progress=0, ...)
        return job_id

    def update(self, job_id: str, **fields): ...
    def get(self, job_id: str) -> JobState: ...

# Survives process restart? No — explicit non-goal for now.
# Documented in router as "Jobs are in-memory; lost on container restart."
```

#### Scheduler

Background task started in `api_v2/main.py`:

```python
async def scheduler_loop():
    while True:
        await asyncio.sleep(60)  # check once per minute
        async with db_session() as db:
            due = db.query(Broadcast).filter(
                Broadcast.scheduled_at <= datetime.now(UTC),
                Broadcast.status == "scheduled",
            ).all()
            for b in due:
                # mark sending; enqueue
                b.status = "sending"
                db.commit()
                background_tasks.add_task(execute_broadcast, b.id)
```

Same loop checks both `Broadcast` and `Campaign` tables.

#### Tests

- `test_broadcasts_list_unified` — fixture has 3 Broadcast rows + 2 Campaign rows; list returns 5 normalized rows
- `test_broadcasts_history_email_filter_returns_email_only` — **B6 fix verified**
- `test_audience_preview_funnel` — verify counts match v1 `_render_audience_kpis`
- `test_email_broadcast_queues_returns_job_id`
- `test_email_broadcast_progress_updates` — start, poll, see progress increment
- `test_scheduler_fires_due_broadcast` — set scheduled_at to past, run scheduler tick, verify status flips

### Frontend tasks

#### New components

```
vite_dashboard/src/
├── routes/
│   ├── broadcasts.tsx                 # /broadcasts (with tab state)
│   └── broadcasts.$id.tsx             # /broadcasts/:id (detail + performance)
├── components/
│   ├── broadcasts/
│   │   ├── BroadcastsTabs.tsx
│   │   ├── tab-compose/
│   │   │   ├── ComposeTab.tsx
│   │   │   ├── ChannelToggle.tsx       # WA / Email
│   │   │   ├── RecipientPicker.tsx     # segment OR individual
│   │   │   ├── AudienceFunnel.tsx      # B3 fix: sticky "Targeting N people"
│   │   │   ├── CostEstimate.tsx
│   │   │   ├── TemplateEditor.tsx      # reused in Phase 4
│   │   │   ├── EmailPreview.tsx        # iframe srcdoc
│   │   │   ├── WaPreview.tsx           # reuses TemplatePreview from Phase 2
│   │   │   ├── ScheduleSheet.tsx       # datetime picker
│   │   │   ├── SendConfirmDialog.tsx   # B10 fix: shows count + cost before send
│   │   │   └── SendProgress.tsx        # polls job status
│   │   ├── tab-history/
│   │   │   ├── HistoryTab.tsx
│   │   │   ├── BroadcastsTable.tsx     # composes DataTable + StatusBadge
│   │   │   └── ChannelFilter.tsx       # WA / Email / All
│   │   └── tab-performance/
│   │       ├── PerformanceTab.tsx
│   │       ├── PerformanceKpis.tsx
│   │       └── RecipientsTable.tsx
│   └── ...
├── hooks/
│   ├── useAudiencePreview.ts        # debounced; refetches as filters change
│   ├── useCostEstimate.ts
│   └── useJobProgress.ts            # polls /api/v2/jobs/:id/status
└── api/
    └── broadcasts.ts
```

#### Key behavioral fixes

- **B3 (audience target buried).** `<AudienceFunnel>` is a sticky header at the top of the Compose tab: "Targeting **N** people in **Segment Name**". As filters change, `useAudiencePreview` debounces a POST to `/audience-preview` and the headline re-renders.
- **B6 (history email filter).** `<BroadcastsTable>` reads from `/api/v2/broadcasts` which queries both tables. The channel filter actually works.
- **B10 (button proximity).** Send Now requires `<SendConfirmDialog>`: "You're about to send to **245 people** at an estimated cost of **₹612**. Type SEND to confirm." No more easy misclick.
- **B13 (sync send loop).** Email Send Now → `POST /api/v2/broadcasts/email` returns immediately with `{job_id}`. UI shows `<SendProgress>` polling status. WA still sync (no rate limit, no need for async).
- **B15 (dead Scheduled tab).** v1's `email_analytics.py::_TABS` had a "Scheduled" tab that always showed empty because nothing set `status="scheduled"`. v2 adds real scheduling (`scheduled_at` column) and the History tab filter includes `Scheduled` only when there are due-but-not-yet-fired broadcasts. No empty dead tab.
- **B16 (recipient table 100-row cap).** v1's `_render_recipient_table` capped at 100 silently. `<RecipientsTable>` in the Performance tab uses TanStack Table virtualization + cursor pagination via `GET /api/v2/broadcasts/{id}/recipients?cursor=...`. No silent truncation.

#### URL state

- `/broadcasts?tab=history&channel=email&status=completed&page=2` — tab state in URL
- `/broadcasts/:id` — detail view; deep-linkable
- `/broadcasts?tab=compose&channel=email&template=order_confirmation&segment=domestic_b2b` — compose state in URL (so partial drafts survive reload)

### Acceptance criteria

- [ ] Compose tab: pick channel, pick recipients, pick template, fill variables, see live preview, see live cost, click Send → confirmation dialog → submit
- [ ] Audience funnel headline updates as filters change
- [ ] WA Send is synchronous (small batch, finishes in seconds)
- [ ] Email Send queues, UI polls progress, completion notification appears
- [ ] Schedule: pick a future datetime, broadcast goes to "scheduled" state, scheduler fires it at the chosen time (verify with a 1-min-future test)
- [ ] History tab: shows both WA and Email broadcasts in a unified table
- [ ] Channel filter for Email actually returns email broadcasts (**B6 verified**)
- [ ] Performance tab: per-broadcast KPIs + recipient table (paginated, no 100-row cap)
- [ ] Send confirmation dialog shows recipient count + estimated cost
- [ ] All v1 functionality replicated; no regression in WA broadcasting
- [ ] B15 verified: no empty "Scheduled" tab in History when no scheduled broadcasts exist
- [ ] B16 verified: per-broadcast recipient list scrolls past 100 rows without truncation; cursor pagination works

### Risks specific to Phase 3

- **In-memory job store loses state on container restart.** Documented limitation. If the team restarts the v2 Space mid-broadcast, the job is orphaned (sends already-completed but UI doesn't know). Mitigation: persist job state to a DB table in a follow-up.
- **Scheduler fires multiple times in HF Spaces auto-scaling.** HF doesn't auto-scale free tier (one replica), so safe. If we upgrade to paid: add a row-level lock.
- **Migration script needs to run before Phase 3 deploys.** Add it to `scripts/migrations/` with a manual-run note in this file. Run against the prod DB **before** the v2 Phase 3 deploy that depends on `scheduled_at`.
- **Drift between Broadcast and Campaign tables.** Long-term, these should be merged. Phase 3 normalizes them in the API layer; Phase 6 (out of scope) would unify the schema.

### Estimated effort

- 7-10 days solo
- ~2 days backend job infra + scheduler
- ~3 days Compose tab (richest UI)
- ~2 days History + Performance tabs
- ~2 days schema migration + email queue + polling
- ~1 day mobile + polish

### Playwright MCP verification

Output: `verifications/phase_3/`

1. `browser_navigate` → `/broadcasts` → `browser_snapshot` → expect 3 tabs (Compose / History / Performance)
2. **B3 verification:** `browser_select_option` Segment → "Engaged Domestic B2B" → `browser_wait_for` sticky header
3. `browser_take_screenshot` → save `step_03_b3_audience.png`. Header text must contain "Targeting" + a number + segment name
4. `browser_select_option` Template → `order_confirmation` → wait for CostEstimate to populate
5. `browser_take_screenshot` of cost cards → save `step_05_cost.png`
6. **B10 verification:** `browser_click` Send Now → `browser_wait_for` SendConfirmDialog
7. `browser_take_screenshot` → save `step_07_b10_confirm.png`. Dialog must show recipient count and cost
8. `browser_type` "SEND" → `browser_click` Confirm → `browser_wait_for` SendProgress component
9. **B13 verification:** `browser_network_requests` → confirm `POST /api/v2/broadcasts/email` returned within 1s with `{job_id}` (synchronous request, async send)
10. Poll: `browser_wait_for` text "Send complete" (timeout 10 min) → `browser_take_screenshot` → save `step_10_complete.png`
11. **B6 verification:** `browser_click` History tab → `browser_select_option` Channel → "Email"
12. `browser_snapshot` → expect ≥1 row (the email broadcast just sent) → save `step_12_b6_history.png`
13. **B16 verification:** `browser_click` a broadcast with >100 recipients → Performance tab → recipient table
14. `browser_evaluate` → `() => document.querySelectorAll('[data-recipient-row]').length` → must return >100 (or scroll triggers more rows via virtualization)
15. **B15 verification:** History tab Status filter → confirm "Scheduled" tab/option only appears when scheduled broadcasts exist; not a permanent dead tab
16. **Scheduling verification:** Compose tab → click Schedule → pick datetime 2 min in future → submit
17. Wait 3 min; refresh history → `browser_snapshot` → broadcast moved from "scheduled" → "sent"
18. `browser_console_messages` → expect no errors
19. `browser_resize` 414×896 → mobile snapshot → tabs collapse to dropdown

**Pass criteria:** all 19 steps complete; bug fixes B3/B6/B10/B13/B15/B16 individually verified by their named steps; scheduler fires within ±1 min of scheduled time.

---

## Phase 4 — Template Studio (1 week)

**Goal.** Migrate WA template authoring. Drop the over-engineered folder tree. Reuse `<TemplateEditor>` and `<WaPhonePreview>` from earlier phases.

**Prerequisites.** Phase 0, 0.5, 3 acceptance.

### Backend tasks

#### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/wa/templates` | List with status, tier, search |
| GET | `/api/v2/wa/templates/{id}` | Full record |
| POST | `/api/v2/wa/templates/{id}/save` | Save (clone-on-edit if approved) |
| POST | `/api/v2/wa/templates/{id}/submit` | Submit to Meta |
| POST | `/api/v2/wa/templates/sync` | Sync from Meta (returns job_id; uses BackgroundTasks because sync is slow for many templates) |
| POST | `/api/v2/wa/templates/{id}/upload-header` | Multipart asset upload → public URL |
| POST | `/api/v2/wa/templates` | Create new draft |
| DELETE | `/api/v2/wa/templates/{id}` | Delete draft (only drafts; submitted templates are immutable) |

#### Tests

- `test_save_creates_clone_when_editing_approved` — verify `_v2` suffix logic
- `test_submit_to_meta_marks_pending`
- `test_sync_from_meta_creates_jobs` — async; verify job state transitions

### Frontend tasks

#### New components

```
vite_dashboard/src/
├── routes/
│   ├── wa-templates.tsx          # /wa-templates (list)
│   └── wa-templates.$id.tsx      # /wa-templates/:id (editor)
├── components/
│   ├── wa-templates/
│   │   ├── TemplateList.tsx       # composes DataTable + StatusBadge + tier column
│   │   ├── TemplateListFilters.tsx  # search + status + tier
│   │   ├── TemplateForm.tsx       # name, category, language, header, body, footer, buttons
│   │   ├── ButtonsEditor.tsx      # FieldArray; up to 3 buttons
│   │   ├── HeaderUploader.tsx     # drag-drop with preview
│   │   ├── ApprovedBanner.tsx     # warning before clone-on-edit
│   │   ├── SubmitDialog.tsx       # confirm submit to Meta
│   │   ├── SyncProgress.tsx       # toast with progress bar
│   │   └── WaPhonePreview.tsx     # ALREADY BUILT in Phase 2; just imported here
│   └── ...
└── api/
    └── wa_templates.ts
```

#### Behavioral changes

- **Drop folder tree visualization.** `<TemplateList>` is just a `<DataTable>` with columns: Status, Name, Tier, Category, Language, Submitted At. Filterable + searchable. No tree.
- **Tier column** shows the inferred tier (company/category/product/utility) as a small text label. No filter sidebar.
- **B17 (tier hardcoded sets).** Out of scope for Phase 4 unless cheap. Tier inference stays server-side (`services/wa_templates.py::infer_tier`); v3+ moves it to YAML.
- **Live preview** updates on every form field change via TanStack Query's `select` with debounced state.
- **Clone-on-edit warning.** Loading an approved template into the form shows `<ApprovedBanner>` at the top: "🔒 This is Meta-approved. Saving will create a new draft `name_v2`."

### Schema/DB

No new columns. Optional: `WATemplate.tier` if we move tier inference out of Python. Phase 4 keeps it computed.

### Acceptance criteria

- [ ] List with search + status filter + tier column works
- [ ] Editor: every field type works (TEXT/IMAGE/DOCUMENT header, buttons of all 3 types)
- [ ] Live preview updates on field changes
- [ ] Save (draft): persists, list refreshes
- [ ] Save on an approved template: creates `_v2` clone, original untouched
- [ ] Submit: posts to Meta, status flips to PENDING
- [ ] Sync: shows progress, populates approved templates
- [ ] Upload header asset: file → public URL → form auto-fills
- [ ] All v1 functionality replicated

### Risks specific to Phase 4

- **Meta API rate limits during Sync.** If a workspace has 50+ templates, syncing all hits the API repeatedly. Use the existing `WhatsAppSender.sync_templates_from_meta` which already batches; just make it async and stream progress.
- **Header asset URL must be HTTPS.** v1 already validates `PUBLIC_BASE_URL`; v2 inherits this. Verify the v2 Space serves uploaded assets over HTTPS.
- **B4 (positional vars).** Two templates use `"1"`, `"2"` as variable names. Phase 4 doesn't fix this in code — fix is to re-submit those templates to Meta with named placeholders, which is a one-time data fix unrelated to v2.

### Estimated effort

- 5-7 days solo. ~half on the editor form (rich), ~half on list + submit/sync flows.

### Playwright MCP verification

Output: `verifications/phase_4/`

1. `browser_navigate` → `/wa-templates` → `browser_snapshot` → expect list with status + tier columns + search
2. `browser_type` search "order_" → `browser_snapshot` → list filters
3. `browser_click` an APPROVED template → `browser_wait_for` ApprovedBanner + form populated
4. `browser_take_screenshot` → save `step_04_approved_banner.png`
5. Edit body text → `browser_click` Save Draft → `browser_wait_for` toast
6. `browser_snapshot` list → verify a `_v2` clone now exists (clone-on-edit; original stays approved) → save `step_06_clone.png`
7. `browser_click` the new draft → `browser_click` Submit to Meta → `browser_wait_for` confirm dialog → confirm
8. `browser_wait_for` status flip to PENDING (may take seconds) → `browser_take_screenshot` → save `step_08_pending.png`
9. `browser_click` "Sync from Meta" → `browser_wait_for` progress toast → wait completion
10. `browser_take_screenshot` → save `step_09_synced.png`. Verify list count increases or matches Meta WABA count
11. `browser_click` New Draft → `browser_fill_form` (name, body) → drag-drop a header asset (or `browser_evaluate` to set `header_asset_url`)
12. Verify WaPhonePreview updates live as fields change → `browser_take_screenshot` → save `step_12_preview.png`
13. `browser_console_messages` → no errors
14. `browser_network_requests` → confirm Meta API calls (POST to `graph.facebook.com/.../message_templates`) returned 200

**Pass criteria:** all 14 steps complete; clone-on-edit produces `_v2` only, never overwrites approved; submit + sync flows function end-to-end against Meta.

---

## Phase 5 — Home + Flows + Cleanup (1 week)

**Goal.** Migrate the last two pages. Reorganize the sidebar (B11). Decommission v1 Space. Land the cleanup commit (rename `hf_dashboard/` → `dashboard/`).

**Prerequisites.** Phase 0-4 acceptance. Team has been using v2 for daily ops for at least 2 weeks.

### Backend tasks

#### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/dashboard/home` | KPIs + lifecycle + activity (one batched query, mirroring `home.py::_home_counters_cached`) |
| GET | `/api/v2/flows` | List flows |
| GET | `/api/v2/flows/{id}/runs` | Recent runs of a flow |
| POST | `/api/v2/flows/{id}/runs` | Start a flow on a segment |

Note: v1's `pages/home.py` reads `os.getenv("GMAIL_REFRESH_TOKEN")` for the Email-API status indicator. v2 should expose this through a small `GET /api/v2/system/status` endpoint that returns `{gmail_configured: bool, wa_configured: bool}`. Don't expose the env vars themselves to the frontend.

#### Template-count fix (B12)

`v1/home.py:366-367` hardcodes "Templates: 7 email, 13 WA". v2 reads counts from DB:

```python
# api_v2/routers/dashboard.py::home
email_template_count = db.query(EmailTemplate).filter(EmailTemplate.is_active).count()
wa_template_count = db.query(WATemplate).filter(WATemplate.is_draft.is_(False), WATemplate.status == "APPROVED").count()
```

### Frontend tasks

#### New components

```
vite_dashboard/src/
├── routes/
│   ├── home.tsx                # /home (default route)
│   └── flows.tsx               # /flows (read-only)
├── components/
│   ├── dashboard/
│   │   ├── DashboardGrid.tsx
│   │   ├── StatusStrip.tsx       # API connection indicators (top of page)
│   │   ├── KpiRow.tsx            # ALREADY BUILT in Phase 1; reused
│   │   ├── LifecycleBars.tsx
│   │   └── ActivityFeed.tsx
│   ├── flows/
│   │   ├── FlowsTable.tsx        # read-only list with status
│   │   ├── FlowDetailDrawer.tsx  # steps + recent runs
│   │   └── StartFlowDialog.tsx   # pick segment + start date
│   └── ...
└── api/
    ├── dashboard.ts
    └── flows.ts
```

#### Sidebar reorganization (B11)

Update `src/components/layout/NavSidebar.tsx` with grouped navigation:

```ts
const NAV_GROUPS = [
  { items: [{ id: "home", label: "Home", icon: HomeIcon }] },
  { items: [{ id: "contacts", label: "Contacts", icon: UsersIcon }] },
  {
    label: "WhatsApp",
    items: [
      { id: "wa-inbox", label: "Inbox", icon: MessageSquareIcon },
      { id: "broadcasts", label: "Broadcasts", icon: SendIcon, channel: "wa" },
      { id: "wa-templates", label: "Templates", icon: FileTextIcon },
    ],
  },
  {
    label: "Email",
    items: [
      { id: "broadcasts", label: "Broadcasts", icon: SendIcon, channel: "email" },
      // analytics rolled into broadcasts/performance tab in Phase 3
    ],
  },
  { items: [{ id: "flows", label: "Flows", icon: GitBranchIcon }] },
];
```

### Cleanup tasks

These run **after** v2 acceptance + v1 decommissioning. **The cleanup commit is the LAST commit of Phase 5.**

| Step | Action |
|---|---|
| 1 | Verify team has used v2 exclusively for ≥2 weeks |
| 2 | Take a final v1 backup: `python scripts/deploy_hf.py --dry-run > v1-final-state.txt` and commit |
| 3 | Update CLAUDE.md to reflect v2-only deployment workflow |
| 4 | Delete (or freeze) the v1 HF Space via the HF UI |
| 5 | Remove `scripts/deploy_hf.py` from the repo (kept in git history) |
| 6 | Delete `hf_dashboard/pages/`, `hf_dashboard/app.py`, `hf_dashboard/components/` (the Gradio-specific bits) |
| 7 | Rename `hf_dashboard/` → `dashboard/`. Update all imports in `api_v2/` |
| 8 | Update `scripts/deploy_hf_v2.py` to reference `dashboard/` instead of `hf_dashboard/` |
| 9 | Final commit: `chore: decommission v1 Gradio dashboard, rename hf_dashboard/ → dashboard/` |

### Visual regression — full-page snapshots

Per STANDARDS §8, Phase 5 extends the visual regression suite from component-level (which Phases 0-4 grew) to full-page screenshots of every route. Add stories under `vite_dashboard/.storybook/pages/`:

| Story | Route | Captures |
|---|---|---|
| `pages/home.stories.tsx` | `/home` | desktop + mobile (414px) |
| `pages/contacts.stories.tsx` | `/contacts` | with filters open + drawer open |
| `pages/wa-inbox.stories.tsx` | `/wa-inbox` | conversation selected + window-closed state |
| `pages/broadcasts.stories.tsx` | `/broadcasts` | each tab (Compose / History / Performance) |
| `pages/wa-templates.stories.tsx` | `/wa-templates` | list + editor with WhatsApp preview |
| `pages/flows.stories.tsx` | `/flows` | populated + empty |

Run as part of CI on every PR after Phase 5 ships. Diff > 0.1% pixel = blocked PR.

### Acceptance criteria

- [ ] Home renders with live KPI counts from DB (no hardcoded numbers — **B12 fix**)
- [ ] Lifecycle bars match v1 visual
- [ ] Activity feed shows recent EmailSend + WAMessage events
- [ ] Status strip shows Email + WA API connection states correctly
- [ ] Flows table renders all flows with their status
- [ ] Start Flow dialog works
- [ ] Sidebar grouped per **B11 fix** (Home / Contacts / WhatsApp ▸ ... / Email ▸ ... / Flows)
- [ ] Mobile viewport (414px): sidebar collapses to a hamburger menu — verifies **B20 fix** holistically across all v2 pages
- [ ] All B-bugs from §4 are either closed or explicitly deferred
- [ ] v1 Space is decommissioned (deleted or frozen for 30 days per §9.5)
- [ ] Cleanup commit landed on main; CI passes after rename

### Risks specific to Phase 5

- **Rename breaks `services/` imports.** Every file under `api_v2/` that does `from services.X import Y` (because `services/` was sym-mounted from `hf_dashboard/services/`) needs to become `from app.services.X import Y`. Use a codemod or careful find-replace. The Phase 0 import smoke test catches breakage but won't auto-fix.
- **Existing references in `scripts/`.** Any one-off CLI script that imports from `hf_dashboard.services.X` will break. Audit `scripts/` directory before the rename; update or document.
- **Sidebar Broadcasts is double-listed.** The audit's proposed grouping has Broadcasts under both WhatsApp and Email. Resolve: one Broadcasts entry (under a top-level "Compose" group?) or two with channel filter pre-selected. Decide before the sidebar refactor.

### Estimated effort

- 4-6 days
- ~2 days for Home + Flows pages
- ~1 day for sidebar reorganization
- ~1-2 days for cleanup commit + verification

### Playwright MCP verification

Output: `verifications/phase_5/`

1. `browser_navigate` → `/home` → `browser_snapshot` → verify status strip + 2 KPI rows + lifecycle bars + activity feed all render
2. `browser_take_screenshot` → save `step_01_home.png`
3. **B12 verification:** `browser_evaluate` → fetch `/api/v2/dashboard/home` → record returned counts. Compare to v1 Space's `/home` rendering (open v1 in second tab; manual visual diff). Counts must match (no hardcoded values)
4. `browser_take_screenshot` of activity feed → save `step_04_activity.png`. Latest event must be from <24h ago.
5. `browser_navigate` → `/flows` → `browser_snapshot` → verify FlowRunsTable renders
6. `browser_take_screenshot` → save `step_06_flows.png`
7. **B11 verification:** `browser_snapshot` sidebar → verify grouped nav (Home / Contacts / WhatsApp ▸ ... / Email ▸ ... / Flows). Template Studio appears under WhatsApp group
8. `browser_take_screenshot` of sidebar → save `step_08_b11_sidebar.png`
9. **B20 verification:** `browser_resize` 414×896 → snapshot every route → verify hamburger menu replaces sidebar; chat goes full-width on `/wa-inbox`; tabs become dropdown on `/broadcasts`
10. Screenshot each route at mobile width → save `step_10_mobile_<route>.png`
11. `browser_console_messages` across the full traversal → expect zero errors
12. **Decommissioning verification (after v1 Space deleted):** `browser_navigate` → v1 URL `https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/` → confirm 404 or redirect
13. **Repo rename verification:** local check — `python -c "import dashboard.services.models"` succeeds; `import hf_dashboard` fails. `python scripts/deploy_hf_v2.py --dry-run` references `dashboard/` not `hf_dashboard/`

**Pass criteria:** all 13 steps complete; B11/B12/B20 individually verified; v1 Space confirmed offline; rename smoke test passes.

### Final acceptance — overall migration

After Phase 5 verification passes, run a single end-to-end traversal across all 6 routes at desktop (1440×900) AND mobile (414×896) viewports to confirm holistic feature parity. Save the combined screenshot grid (12 images) as `verifications/final_acceptance.png`. Commit. The migration is complete.

---

## Cross-phase considerations

### CI / branch protection

- `main` is protected. PRs require: green CI, 1 approving review, branch up-to-date.
- A `migration/phase-N-*` branch must rebase onto `main` after each upstream merge.
- The v2 Space auto-deploys from `main` only after merge (via a GitHub Actions workflow that runs `scripts/deploy_hf_v2.py`).

### Commit hygiene

- Each PR maps to one phase or one major sub-task within a phase.
- Commit messages reference bug IDs: `wa-inbox: fix B1 (variable scroll) by removing tp-vars-box overflow`.
- No drive-by changes outside the phase scope.

### Rollback strategy

If a phase ships and the team hits a blocker, **revert to v1 by switching the bookmark** — v1 stays live throughout. No code rollback required. The v2 Space stays in whatever state it's in until the issue is fixed.

### Type generation cadence

- `pnpm gen:types` runs:
  - On every backend PR (CI step that fails if types are stale)
  - In the `dev` script for hot-reload sync
  - As a pre-commit hook for backend changes

### Performance budgets

| Metric | Budget | Verification |
|---|---|---|
| Initial bundle (gzipped) | ≤ 500 KB | CI step using `vite-bundle-visualizer` |
| API endpoint p95 | ≤ 500 ms | Sentry performance monitoring |
| Time-to-interactive (Contacts page) | ≤ 1.5 s | Lighthouse run as a CI smoke test |
| SSE reconnect time | ≤ 3 s | Manual verify in Phase 2 acceptance |

### Test coverage

- Backend: aim for ≥70% line coverage by end of Phase 5. Phase 0 adds coverage tooling.
- Frontend: focus on critical paths (send broadcast, send WA template) rather than line %. Component tests for shared primitives (`<DataTable>`, `<StatusBadge>`).

### Observability

- Sentry captures all unhandled errors (FE + BE)
- Sentry performance: API endpoint timing + frontend route changes
- Slack alert: any 5xx in prod → Slack channel
- No PII in error reports — Sentry config strips emails, phone numbers, contact names

### Documentation as we go

- Each phase adds to a `MIGRATION_NOTES.md` in this folder: what shipped, what surprises came up, what carried over to the next phase.
- API surface docs auto-generated from FastAPI's `/docs` (Swagger UI).
- Component docs auto-generated from Storybook (Phase 0 adds Storybook scaffolding).

---

## Definition of done (overall migration)

- [ ] All 9 v1 Gradio pages have a v2 equivalent at functional parity or better
- [ ] All bugs B1-B20 from audit §4 are either resolved (with linked PR) or explicitly deferred (with linked issue)
- [ ] v2 Space is the team's daily-driver
- [ ] v1 Space is decommissioned (deleted or read-only)
- [ ] `hf_dashboard/` renamed to `app/`; old Gradio code removed
- [ ] `scripts/deploy_hf.py` removed; `scripts/deploy_hf_v2.py` (renamed `scripts/deploy_hf.py` post-cleanup) is the single deploy command
- [ ] CLAUDE.md updated to reference the v2 architecture
- [ ] CI runs green; type generation pipeline functional
- [ ] Sentry receives events from prod; no critical alerts fired in the past 7 days
- [ ] Performance budgets met
- [ ] Migration notes archived in `reports/audit_vite_migration_plan/`

---

## Appendix A — Component dependency graph

```
Phase 1 (Contacts) ships:
  ├── DataTable          (used by: Phase 3 history, Phase 4 templates, Phase 5 flows)
  ├── FilterBar          (used by: Phase 3 history, Phase 4 templates)
  ├── StatusBadge        (used by: Phase 3, 4, 5)
  ├── ChannelBadge       (used by: Phase 3 history)
  ├── SegmentPill        (used by: Phase 3 audience picker)
  └── ContactDrawer      (no other consumers)

Phase 2 (WA Inbox) ships:
  ├── ChatPanel          (no other consumers)
  ├── MessageBubble      (no other consumers)
  ├── WaPhonePreview     (used by: Phase 3 compose tab, Phase 4 editor)
  └── TemplateVariablesForm  (used by: Phase 3 compose tab)

Phase 3 (Broadcasts) ships:
  ├── TemplateEditor     (used by: Phase 4 editor — same component, expanded)
  ├── EmailPreview       (no other consumers)
  ├── RecipientPicker    (no other consumers)
  ├── AudienceFunnel     (no other consumers)
  ├── CostEstimate       (no other consumers)
  └── SendConfirmDialog  (no other consumers)

Phase 4 (Template Studio) ships:
  ├── ButtonsEditor      (no other consumers)
  └── HeaderUploader     (no other consumers)

Phase 5 (Home + Flows) ships:
  ├── DashboardGrid      (no other consumers)
  ├── LifecycleBars      (no other consumers)
  ├── ActivityFeed       (no other consumers)
  └── FlowsTable         (composes DataTable from Phase 1)
```

Read top-to-bottom: each phase depends on the components shipped in earlier phases. The graph informs why **Phase 1 must ship first** (its DataTable + StatusBadge are used by every other phase) and why **Phase 2 should precede Phase 3** (Phase 3 reuses `WaPhonePreview` and `TemplateVariablesForm`).

---

## Appendix B — Phase deliverables checklist (printable)

```
Phase 0 — Foundation (production-ready, not scaffolding)
  Backend
    [ ] api_v2 FastAPI app + health endpoint (working)
    [ ] Auth middleware (Bearer or session per §9.6)
    [ ] /api/v2/dashboard/home returning real data (matches v1)
    [ ] Sentry wiring
    [ ] Static SPA mount
    [ ] Import smoke test
    [ ] pytest config + first endpoint tests
  Frontend
    [ ] Vite + Shadcn project with production vite.config.ts (yaml plugin + aliases)
    [ ] Complete YAMLs in src/config/ (theme, sidebar, 6 pages, shared) - no placeholders
    [ ] Zod schemas for every YAML; strict extra:forbid; tests cover each schema
    [ ] configLoader singleton with bootstrap() that fails loud on bad YAML
    [ ] All 6 engines (theme, navigation, page, kpi, status, filter) typed + unit-tested
    [ ] React Router with real routes; /home is fully functional; others render <MigrationStatusCard>
    [ ] TanStack Query with production retry/error config
    [ ] Theme tokens matching v1 (CSS vars emitted by themeEngine)
    [ ] <AppShell> + <NavSidebar> reading sidebar.yml; skip-to-content link
    [ ] Sentry wiring
    [ ] openapi-typescript pipeline + pre-commit hook
    [ ] Login page (real, not stubbed)
    [ ] Vitest config + first component tests
  Tooling
    [ ] Multi-stage Dockerfile
    [ ] Deploy script
    [ ] HF Space created
    [ ] GitHub Actions CI
    [ ] Pre-commit hook
    [ ] Bundle-size check

Phase 0.5 — Reproduce bugs
  [ ] B1 reproduction screenshots (1440px + 1024px)
  [ ] B2 reproduction
  [ ] B5 reproduction
  [ ] B6 reproduction
  [ ] B9 reproduction
  [ ] B10 reproduction
  [ ] repro/README.md with severity calibrations

Phase 1 — Contacts
  [ ] 8 endpoints implemented + tested
  [ ] DataTable component
  [ ] FilterBar + sub-filters
  [ ] StatusBadge, ChannelBadge, SegmentPill
  [ ] ContactDrawer (4 tabs)
  [ ] Add + Import dialogs
  [ ] URL state sync
  [ ] Mobile responsive
  [ ] Daily-ops adoption (3+ days)

Phase 2 — WhatsApp Inbox
  [ ] 8+ endpoints + SSE
  [ ] ChatPanel + MessageBubble
  [ ] ChatComposer with disabled state (B2)
  [ ] TemplateSheet + TemplateVariablesForm (B1)
  [ ] WindowChip
  [ ] StartNewConversation
  [ ] SSE event consumption
  [ ] Mobile responsive
  [ ] Real-time inbound verified

Phase 3 — Broadcasts
  [ ] 8 endpoints + scheduler + jobs
  [ ] Schema migration (scheduled_at)
  [ ] BroadcastsTabs (3 tabs)
  [ ] AudienceFunnel sticky header (B3)
  [ ] SendConfirmDialog (B10)
  [ ] Email queue + progress polling (B13)
  [ ] Unified history reads both tables (B6)
  [ ] Schedule sheet
  [ ] Performance tab
  [ ] Mobile responsive

Phase 4 — Template Studio
  [ ] 8 endpoints
  [ ] TemplateList (no folder tree)
  [ ] TemplateForm + ButtonsEditor + HeaderUploader
  [ ] ApprovedBanner clone-on-edit warning
  [ ] Submit + Sync flows with progress
  [ ] Live preview (reuses WaPhonePreview)

Phase 5 — Home + Flows + Cleanup
  [ ] Home endpoints + page
  [ ] Live template counts (B12)
  [ ] Flows endpoints + read-only page
  [ ] Sidebar reorganization (B11)
  [ ] Mobile responsive (B20 verified holistically)
  [ ] v1 Space decommissioned
  [ ] Cleanup commit landed
```
