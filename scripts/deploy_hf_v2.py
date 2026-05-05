"""Deploy the v2 dashboard (vite_dashboard + api_v2) to its Hugging Face Space.

Companion to scripts/deploy_hf.py (which deploys v1 from hf_dashboard/).
While the migration window is open both Spaces ship in parallel; this
script targets the v2 Space only.

What it uploads (Space layout — flat at the Space root):
    Dockerfile           ← copy of Dockerfile.v2 renamed to Dockerfile
    api_v2/              ← FastAPI backend
    hf_dashboard/        ← shared services/engines/loader (until Phase 5)
    config/              ← shared domain configs (config/dashboard/)
    vite_dashboard/      ← frontend source — built INSIDE the Docker stage
                            via `pnpm build`; the dist/ output is NOT uploaded

The HF Space build runs the multi-stage Dockerfile end-to-end:
    Stage 1: node:20-alpine    pnpm install + pnpm build → dist/
    Stage 2: python:3.11-slim  uvicorn + FastAPI serve dist/ + /api/v2

Token resolution mirrors deploy_hf.py:
    1. HF_TOKEN env var
    2. HF_TOKEN in .env at repo root
    3. huggingface_hub cached token (huggingface-cli login)

One-time setup before first run:
    1. Create the Space at https://huggingface.co/new-space
       owner: prashantiitkgp08, name: himalayan-fibers-dashboard-v2
       SDK: Docker, hardware: CPU basic (free), visibility: private
    2. Set Space Secrets (Settings → Variables and secrets):
         APP_PASSWORD          (gates /api/v2/auth/login)
         DATABASE_URL          (Supabase Postgres URL — same as v1)
         GMAIL_REFRESH_TOKEN   (optional, mirrors v1)
         GMAIL_CLIENT_ID       (optional)
         GMAIL_CLIENT_SECRET   (optional)
         WA_TOKEN              (optional, mirrors v1)
         WA_PHONE_NUMBER_ID    (optional)
         WA_VERIFY_TOKEN       (optional)
         WA_APP_SECRET         (optional)
         SENTRY_DSN            (optional)
         POSTHOG_KEY           (optional)
    3. Optionally set the public URL of the Space in Space metadata.

Usage:
    python scripts/deploy_hf_v2.py
    python scripts/deploy_hf_v2.py --dry-run
    python scripts/deploy_hf_v2.py -m "Custom message"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPACE_REPO_ID = "prashantiitkgp08/himalayan-fibers-dashboard-v2"
SPACE_URL = f"https://huggingface.co/spaces/{SPACE_REPO_ID}"
LIVE_URL = "https://prashantiitkgp08-himalayan-fibers-dashboard-v2.hf.space/"

# Files at the v2 Space root come from these locations in this repo.
# Each entry: (source path inside this repo, target name on the Space).
# `Dockerfile.v2` is renamed to `Dockerfile` because HF Spaces with the
# Docker SDK look for that exact filename.
SOURCES: list[tuple[str, str]] = [
    ("Dockerfile.v2", "Dockerfile"),
    ("api_v2", "api_v2"),
    ("hf_dashboard", "hf_dashboard"),  # shared services/engines/loader
    ("config", "config"),  # config/dashboard/ + repo-level config
    ("vite_dashboard", "vite_dashboard"),  # source — built inside Docker
]

# Patterns excluded from EVERY uploaded folder.
IGNORE_PATTERNS = [
    "__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    ".DS_Store",
    ".env",
    ".env.*",
    "*.log",
    # vite_dashboard build/dev artifacts — built inside the Docker stage
    "node_modules/**",
    "dist/**",
    ".vite/**",
    "playwright-report/**",
    "test-results/**",
    "coverage/**",
    # local SQLite DBs — prod uses DATABASE_URL via Space Secret
    "data/*.db",
    "data/*.db-journal",
    "data/*.db-shm",
    "data/*.db-wal",
    "media/**",
    # repo-only test artifacts
    "verifications/**",
    "repro/**",
]


def _load_token() -> str:
    """Resolve the HF write token (mirrors deploy_hf.py)."""
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if token:
        return token

    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
            token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
            if token:
                return token
        except ImportError:
            pass

    try:
        from huggingface_hub import get_token as _hf_get_token

        cached = _hf_get_token()
        if cached:
            return cached
    except ImportError:
        pass
    try:
        from huggingface_hub import HfFolder  # type: ignore[attr-defined]

        cached = HfFolder.get_token()
        if cached:
            return cached
    except Exception:
        pass

    raise SystemExit(
        "ERROR: HF token not found.\n"
        "Set HF_TOKEN in your environment or .env, or run:\n"
        "    huggingface-cli login"
    )


def _git_summary() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True
        ).strip()
        return f"{sha}{'+dirty' if dirty else ''}"
    except Exception:
        return "unknown"


def _build_staging_dir(tmp_root: Path) -> Path:
    """Assemble the upload tree under a tmp dir with the Space's flat layout.

    Returns the path of the staging dir; HfApi.upload_folder uploads its
    contents to the Space root in one commit.
    """
    staging = tmp_root / "staging"
    staging.mkdir()

    for src_rel, target_rel in SOURCES:
        src = REPO_ROOT / src_rel
        dst = staging / target_rel
        if not src.exists():
            print(f"  ! Missing source: {src_rel}, skipping")
            continue
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  + {target_rel}")
        else:
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.pyo",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    ".DS_Store",
                    ".env",
                    ".env.*",
                    "node_modules",
                    "dist",
                    ".vite",
                    "playwright-report",
                    "test-results",
                    "coverage",
                    "*.log",
                    "verifications",
                    "repro",
                ),
            )
            file_count = sum(1 for _ in dst.rglob("*") if _.is_file())
            print(f"  + {target_rel}/  ({file_count} files)")
    return staging


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy v2 dashboard to its HF Space")
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Commit message (default: auto-generated with git SHA)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stage files but don't upload",
    )
    args = parser.parse_args()

    # Validate sources upfront — fail fast if anything's missing.
    for src_rel, _ in SOURCES:
        if not (REPO_ROOT / src_rel).exists():
            raise SystemExit(f"ERROR: required source missing: {src_rel}")

    token = None if args.dry_run else _load_token()

    git_tag = _git_summary()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit_message = args.message or f"v2 deploy from {git_tag} ({ts})"

    print(f"Target Space: {SPACE_REPO_ID}")
    print(f"Commit message: {commit_message}")
    print(f"Staging upload tree:")

    with tempfile.TemporaryDirectory(prefix="hf_v2_deploy_") as tmp:
        staging = _build_staging_dir(Path(tmp))

        if args.dry_run:
            files = list(staging.rglob("*"))
            print(
                f"\nDRY RUN — {sum(1 for f in files if f.is_file())} files staged at {staging}"
            )
            print("(not uploading; staging dir will be cleaned up)")
            return 0

        from huggingface_hub import HfApi

        api = HfApi(token=token)
        print()
        print("Uploading…")
        api.upload_folder(
            folder_path=str(staging),
            repo_id=SPACE_REPO_ID,
            repo_type="space",
            commit_message=commit_message,
            ignore_patterns=IGNORE_PATTERNS,
        )

    print()
    print("✓ Upload complete. HF is rebuilding the Space (Docker build ≈ 5-8 min).")
    print(f"  Build logs:  {SPACE_URL}")
    print(f"  Live URL:    {LIVE_URL}")
    print()
    print("Verify after build finishes (Status: Running):")
    print(f"  curl {LIVE_URL}api/v2/health")
    return 0


if __name__ == "__main__":
    sys.exit(main())
