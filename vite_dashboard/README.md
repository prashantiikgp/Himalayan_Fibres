# vite_dashboard

Internal Himalayan Fibres ops dashboard. Vite + React + Shadcn UI.

## 5-minute orientation

- **What:** the v2 rewrite of the Gradio dashboard at `../hf_dashboard/` (renamed to `dashboard/` after Phase 5). Same backend (`api_v2/` reuses `hf_dashboard/services/`), new frontend.
- **Where it runs:** Hugging Face Space `himalayan-fibers-dashboard-v2`.
- **Architecture:** see `../reports/audit_vite_migration_plan/diagrams/architecture.excalidraw`.
- **Standards:** see `../reports/audit_vite_migration_plan/STANDARDS_AND_DECISIONS.md`.
- **Migration plan:** see `../reports/audit_vite_migration_plan/PHASES.md`.

## Run locally

```bash
cd vite_dashboard
pnpm install
pnpm gen:types       # regenerate API types from running api_v2 (skip first-time)
pnpm dev             # http://localhost:5173
```

The api_v2 backend must be running separately:

```bash
cd ../api_v2
uv run uvicorn main:app --reload --port 7860
```

The Vite dev proxy (configured in `vite.config.ts`) forwards `/api/v2/*` to localhost:7860.

## Conventions (production-ready, no scaffolding)

- **YAML reads always go through `configLoader`.** Never `import yaml` directly in a component.
- **All UI strings live in `src/lib/strings.ts`.** No string literals in JSX.
- **Pages own their components.** Page-specific components live under `src/pages/<page>/components/`. Promote a component to `src/components/` only when 2+ pages use it.
- **Strict Zod schemas (`extra: 'forbid'`).** Every YAML key must be reflected in its schema. No `any`.
- **Bug fix references.** Code that fixes an audit bug uses a comment: `// fixes B1 (audit §4)`.

## Project structure

```
src/
├── config/         YAML configs (theme, sidebar, pages, shared)
├── schemas/        Zod validators for the YAML
├── loaders/        configLoader singleton (bootstraps + validates at boot)
├── engines/        Resolve YAML to render-unit shapes
├── components/     Global components (used by 2+ pages)
├── pages/          One folder per route; page-specific components inside
├── api/            Type-safe fetchers (schema.d.ts auto-generated)
├── lib/            Utilities (env, auth, sse, format, ...)
├── routes/         React Router defs (built from sidebar.yml)
└── styles/         Tailwind + theme CSS vars
```

## Tests

```bash
pnpm test              # Vitest component + unit tests
pnpm test:visual       # Playwright + Storybook visual regression
pnpm typecheck         # TypeScript strict-mode check
pnpm lint              # ESLint with jsx-a11y
```

## Where to find help

- Slack: `#dashboard-dev`
- Bug template: GitHub issues, label `dashboard`
- Architecture questions: read `../reports/audit_vite_migration_plan/STANDARDS_AND_DECISIONS.md` first; if not answered, post in Slack with the section number you read.
