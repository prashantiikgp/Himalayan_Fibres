"""pytest config for api_v2 — shared sys.path + test-mode env setup.

Runs BEFORE any test module imports api_v2.main. Two jobs:

  1. Add hf_dashboard/ to sys.path so `from services.X import Y` resolves.
  2. Force DATABASE_URL to a local SQLite file so tests never touch prod
     Postgres. We set this explicitly (not via setdefault) so the
     repo-root .env's DATABASE_URL doesn't leak into the test process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

# Force the v1 services to use a local SQLite test DB instead of prod
# Postgres. v1's settings layer treats *any* non-empty DATABASE_URL as
# "use Postgres", so we must clear it to "" (empty string) and route the
# SQLite path via SQLITE_PATH instead. main.py's load_dotenv() respects
# existing env vars so these values stick across the test process.
_TEST_DB = _HF_DASHBOARD / "data" / "test_api_v2.db"
_TEST_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = ""
os.environ["SQLITE_PATH"] = str(_TEST_DB)

# Satisfy the M1 fail-closed startup gate without leaking a real password.
os.environ.setdefault("APP_PASSWORD", "test_secret")
