# Himalayan Fibers — Claude session guide

## Deployment (READ THIS FIRST — do not improvise, do not use git push)

The dashboard is deployed to a **Hugging Face Space** via the
`huggingface_hub` Python SDK, **not** via git push. This is important —
past sessions have tried `git push` and broken because the HF Space is
not a git mirror of this repo:

- **HF Space layout is FLAT** — files live at the Space root (`app.py`,
  `services/`, `pages/`, `engines/`, etc.). There is NO `hf_dashboard/`
  wrapper folder on HF.
- **Local layout has the wrapper** — everything that runs on HF lives
  under `hf_dashboard/` so we can also have `app/`, `config/`,
  `scripts/`, etc. at the repo root.
- **Every HF commit is an upload, not a push.** If you inspect
  `git log` on the HF Space, every commit message is `Upload ... with
  huggingface_hub` or similar. That is the deploy mechanism.

**The ONE supported deploy command:**

```bash
python scripts/deploy_hf.py
```

This uses `HfApi.upload_folder` to copy the contents of `hf_dashboard/`
to the Space root in a single commit, skipping caches, local SQLite
DBs, local media uploads, and `.env` files. After it returns, HF
rebuilds the Docker image (`hf_dashboard/Dockerfile`) automatically.
Wait for the Space to show **Running** before verifying.

Options:
```bash
python scripts/deploy_hf.py --dry-run                  # list files, don't upload
python scripts/deploy_hf.py -m "Custom commit message" # override auto message
```

- **Live URL:** https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/
- **Build logs / Space settings:** https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard
- **No auth on the Space** — `APP_PASSWORD` is unset, so Playwright
  verification can hit the live URL directly with no login step.

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
2. `python scripts/deploy_hf.py`
3. Wait for the Space to report **Running**
4. Drive the live URL with the Playwright MCP tools (headless) to verify
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
