# Himalayan Fibers — Claude session guide

## Deployment (READ THIS FIRST)

The dashboard is deployed to a **Hugging Face Space**. The Space is a git repo
and is configured in this repo as a git remote called `hf`.

```
git remote -v
# hf      https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard
# origin  https://github.com/prashantiikgp/Himalayan_Fibres.git
```

**To deploy any change:**

```bash
./scripts/deploy_hf.sh
```

That's the entire workflow. The script pushes `main` to `hf`; HF detects the
push, rebuilds the Docker image (`hf_dashboard/Dockerfile`), and restarts the
Space. Wait for the Space to show **Running** before verifying.

- **Live URL:** https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/
- **Build logs / Space settings:** https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard
- **No auth on the Space** — `APP_PASSWORD` is unset, so Playwright verification
  can hit the live URL directly with no login step.

### Auth for pushes

HF Space git pushes require an **HF access token** (write scope) as the git
password. The recommended setup is one-time:

```bash
git config --global credential.helper store
./scripts/deploy_hf.sh   # enter username=prashantiitkgp08 and the HF token once
```

After that, credentials live in `~/.git-credentials` and every future push is
non-interactive.

### Verification workflow (post-deploy)

Per user preference (2026-04-14): **never run the app locally.** The flow is
always:

1. Commit the change
2. `./scripts/deploy_hf.sh`
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
