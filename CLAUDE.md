# Himalayan Fibers — Claude session guide

## Deployment (READ THIS FIRST — do not improvise, do not use git push)

**⚠️ There are TWO Hugging Face Spaces (parallel migration). v1 is
DEPRECATED. Target v2 only.**

| | v1 — DEPRECATED, do not deploy/test | **v2 — THE FOCUS** |
|---|---|---|
| App | `hf_dashboard/` Gradio + FastAPI | `vite_dashboard/` SPA + `api_v2/` FastAPI (shares `hf_dashboard/` services until "Phase 5") |
| Space | `prashantiitkgp08/himalayan-fibers-dashboard` | `Prashantiitkgp08/Himalayan_Fibrer_v2` |
| Live URL | ~~prashantiitkgp08-himalayan-fibers-dashboard.hf.space~~ | **https://prashantiitkgp08-himalayan-fibrer-v2.hf.space/** |
| Deploy | ~~`python scripts/deploy_hf.py`~~ | **`python scripts/deploy_hf_v2.py`** |
| Auth | none | **password-gated** — `APP_PASSWORD` Space secret; `/api/v2/*` needs `Authorization: Bearer <APP_PASSWORD>` |
| Health | — | `GET /api/v2/health` |

Deployment is via the `huggingface_hub` Python SDK (`HfApi.upload_folder`),
**not** git push — the HF Space is not a git mirror of this repo (flat
layout at Space root; HF history unrelated). Every HF commit is an
upload (`Upload ... with huggingface_hub`), not a push.

**The ONE supported deploy command (v2):**

```bash
python scripts/deploy_hf_v2.py
```

Uploads `Dockerfile.v2`→`Dockerfile`, `api_v2/`, `hf_dashboard/`,
`config/`, `vite_dashboard/` (frontend built inside the multi-stage
Docker build) in a single commit, skipping caches, local SQLite DBs,
and `.env`. After it returns, HF rebuilds the Docker image (≈5–8 min:
pnpm build + FastAPI). Wait for the Space to show **Running** and
`/api/v2/health` to return `status: ok` before verifying.

Options:
```bash
python scripts/deploy_hf_v2.py --dry-run                  # list files, don't upload
python scripts/deploy_hf_v2.py -m "Custom commit message" # override auto message
```

`scripts/deploy_hf.py` (v1) still exists but **must not be used** — it
targets the deprecated Space.

- **v2 live URL:** https://prashantiitkgp08-himalayan-fibrer-v2.hf.space/
- **v2 build logs / settings:** https://huggingface.co/spaces/Prashantiitkgp08/Himalayan_Fibrer_v2
- **v2 is password-gated.** Verifying via `api_v2` (curl) or Playwright
  needs the `APP_PASSWORD`; pass it as a Bearer token to `/api/v2/*`.
  Useful endpoints: `POST /api/v2/email/render-preview` (server-side
  Jinja render of a template), `POST /api/v2/email/test-sends`, and
  `POST /api/v2/email/attachments` (multipart upload → Supabase →
  ref used as `{kind}_url` + email attachment).
- **Required v2 Space secrets** (HF Space → Settings → Variables &
  secrets — values mirror the repo `.env`, exact case-sensitive names):
  `APP_PASSWORD`, `DATABASE_URL`, **`SUPABASE_URL`**,
  **`SUPABASE_SERVICE_KEY`** (the service_role key — needed by
  `services/supabase_storage.py` for the catalogue/price-list/footer-icon
  uploads AND the per-send document-upload endpoint; without these the
  upload route 500s `"SUPABASE_URL is not set"`). Secrets are read at
  container start — adding/renaming one needs a Space restart/rebuild
  (a redeploy, or `HfApi.add_space_secret` which auto-restarts). They
  must be on the **v2** Space (`Prashantiitkgp08/Himalayan_Fibrer_v2`),
  not the deprecated v1.
- **Templates + `hf_dashboard/config/email/shared.yml` are shared**
  between v1 and v2, so email-template fixes apply to both; the
  duplicate-send dedupe logic is v2-specific in
  `api_v2/routers/email_send.py`.

### Auth for uploads

`scripts/deploy_hf.py` looks for the HF write token in this order:

1. `HF_TOKEN` environment variable
2. `HF_TOKEN` in the repo-root `.env`
3. Whatever `huggingface-cli login` cached (usually `~/.cache/huggingface/token`)

Get a write token at https://huggingface.co/settings/tokens. One-time
setup: either `export HF_TOKEN=...` in your shell profile, or run
`huggingface-cli login` once and paste the token there. After that,
every future deploy is non-interactive.

### Git is still useful — but only for version history

The repo has `origin → github.com/prashantiikgp/Himalayan_Fibres`. Use
regular `git commit` locally to version your changes. Push to `origin`
if you want a GitHub backup. **Do NOT add an `hf` remote and do NOT
`git push` to HF** — those past attempts failed because HF's history is
unrelated and its layout is different. The Python upload script is the
only correct path.

### Verification workflow (post-deploy)

Per user preference (2026-04-14): **never run the app locally.** The
flow is always:

1. Commit the change locally (`git commit`)
2. `python scripts/deploy_hf_v2.py`
3. Wait for the v2 Space to report **Running** + `/api/v2/health` ok
   (note: HF can lag 1–3 min before the Docker rebuild starts — poll
   for a non-RUNNING transition, then RUNNING again, so you don't catch
   the old build)
4. Verify via `api_v2` endpoints (Bearer `APP_PASSWORD`) and/or drive
   the v2 Vite UI with Playwright MCP headless (handle the login gate)
5. Only hand off once checks pass

## Project layout (short)

- `hf_dashboard/` — the thing that runs on HF Spaces (FastAPI + Gradio, entry
  point `hf_dashboard/app.py`, containerized by `hf_dashboard/Dockerfile`)
- `app/` — the separate FastAPI email-marketing backend (`main.py`), not
  deployed to HF Spaces; shares the same Postgres/Supabase DB when run
- `config/` — repo-level YAML (blog, media catalog, WhatsApp templates)
- `hf_dashboard/config/` — dashboard-local YAML (theme, sidebar, pages)
- `scripts/` — one-shot CLI tools (template submission, migrations, deploy)

## Schema / DB conventions

- Production DB is Postgres (Supabase), via `DATABASE_URL` secret on the Space.
  Local dev falls back to SQLite under `hf_dashboard/data/`.
- `hf_dashboard/services/database.py::ensure_db_ready` calls `create_all` —
  it creates **new** tables but never ALTERs existing ones. Any column added
  to an existing table needs a migration script under `scripts/`.
- `WATemplate` exists in **both** `hf_dashboard/services/models.py` and
  `app/whatsapp/models.py`, mapped to the same `wa_templates` table. Keep
  schema changes additive and mirror them to both files.

## Engine config rule

Every engine must load YAML through a Pydantic schema (see
`hf_dashboard/engines/theme_schemas.py` + `loader/config_loader.py` for the
pattern). Never `yaml.safe_load(...).get("key", default)` inline in a page or
handler.
