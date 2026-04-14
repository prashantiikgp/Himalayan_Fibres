"""Deploy the Himalayan Fibers dashboard to Hugging Face Spaces.

This is the **only** supported deploy path. Do not use git push — the HF
Space is not a git mirror of this repo. Its commits are all
`huggingface_hub` uploads, and its folder layout is the contents of
`hf_dashboard/` flattened to the Space root (no `hf_dashboard/` wrapper).

What this script does:
    1. Uploads everything under `hf_dashboard/` to the Space root, one
       commit, via `HfApi.upload_folder`.
    2. Skips caches, local DB files, local media uploads, and .env files
       so nothing sensitive or machine-specific ends up on HF.

One-time setup:
    export HF_TOKEN=<your-hf-write-token>
    # Or put it in .env at the repo root (scripts/deploy_hf.py loads it).

Usage:
    python scripts/deploy_hf.py
    python scripts/deploy_hf.py -m "Custom commit message"

After the script returns, HF rebuilds the Docker image automatically.
Watch logs at:
    https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard
Live URL:
    https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "hf_dashboard"
SPACE_REPO_ID = "prashantiitkgp08/himalayan-fibers-dashboard"
SPACE_URL = f"https://huggingface.co/spaces/{SPACE_REPO_ID}"
LIVE_URL = "https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/"

# Paths under hf_dashboard/ that must NEVER ship to HF.
# - caches, compiled files: noise, slow uploads
# - data/*.db: local SQLite, HF uses Supabase via DATABASE_URL secret
# - media/: local uploaded files, persisted on the Space side
# - .env: never ship secrets
IGNORE_PATTERNS = [
    "__pycache__",
    "__pycache__/*",
    "**/__pycache__/**",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    ".DS_Store",
    ".env",
    ".env.*",
    "data/*.db",
    "data/*.db-journal",
    "data/*.db-shm",
    "data/*.db-wal",
    "media/**",
    "*.log",
]


def _load_token() -> str:
    """Resolve the HF write token from env, .env, or huggingface_hub login."""
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if token:
        return token

    # Try the repo root .env
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

    # Fall back to whatever huggingface_hub has cached. huggingface_hub >=1.0
    # exposes `get_token()` at the top level; older releases had it on
    # HfFolder. Try both so the script works across versions.
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
    """Short context for the HF commit message — commit SHA + clean/dirty."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy hf_dashboard/ to HF Space")
    parser.add_argument(
        "-m", "--message",
        default=None,
        help="Commit message for the HF upload (default: auto-generated with git SHA)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be uploaded, without actually uploading",
    )
    args = parser.parse_args()

    if not DASHBOARD_DIR.is_dir():
        raise SystemExit(f"ERROR: {DASHBOARD_DIR} not found")

    token = _load_token()
    git_tag = _git_summary()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit_message = args.message or f"Deploy from {git_tag} ({ts})"

    if args.dry_run:
        print("DRY RUN — files that would be uploaded:")
        skipped = 0
        uploaded = 0
        for p in sorted(DASHBOARD_DIR.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(DASHBOARD_DIR)
            rel_s = str(rel)
            if any(part == "__pycache__" for part in rel.parts) or rel_s.endswith(".pyc"):
                skipped += 1
                continue
            if rel.parts and rel.parts[0] == "media":
                skipped += 1
                continue
            if rel.parts and rel.parts[0] == "data" and rel_s.endswith((".db", ".db-journal", ".db-shm", ".db-wal")):
                skipped += 1
                continue
            print(f"  + {rel_s}")
            uploaded += 1
        print(f"\n{uploaded} file(s) would be uploaded, {skipped} skipped by ignore rules.")
        print(f"Commit message would be: {commit_message!r}")
        return 0

    from huggingface_hub import HfApi

    print(f"Uploading hf_dashboard/ → {SPACE_REPO_ID}")
    print(f"Commit message: {commit_message}")
    api = HfApi(token=token)
    api.upload_folder(
        folder_path=str(DASHBOARD_DIR),
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        commit_message=commit_message,
        ignore_patterns=IGNORE_PATTERNS,
    )

    print()
    print("✓ Upload complete. HF is rebuilding the Space now.")
    print(f"  Build logs:  {SPACE_URL}")
    print(f"  Live URL:    {LIVE_URL}")
    print()
    print("Wait for the Space to show 'Running' before verifying with Playwright MCP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
