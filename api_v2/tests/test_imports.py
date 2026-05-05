"""Smoke test — every hf_dashboard/services, /engines, /loader module imports
cleanly under the api_v2 sys.path setup. Catches relative-import breakage
before any feature code depends on it.

Per PHASES.md Phase 0 — this is the gate that confirms shared imports work.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

# Modules whose import we must NOT break. Listed here as the canonical
# inventory for the dual-Space window.
SHARED_SERVICES = [
    "services.database",
    "services.config",
    "services.contact_schema",
    "services.segments",
    "services.interactions",
    "services.email_sender",
    "services.email_personalization",
    "services.template_seed",
    "services.email_campaign_loader",
    "services.wa_config",
    "services.wa_sender",
    "services.wa_template_builder",
    "services.media_store",
    "services.ttl_cache",
    "services.flows_engine",
    "services.broadcast_engine",
    "services.models",
]

SHARED_ENGINES = [
    "engines.navigation_engine",
    "engines.theme_schemas",
    "engines.cache_schemas",
    "engines.wa_schemas",
    "engines.campaign_schemas",
]

SHARED_LOADERS = [
    "loader.config_loader",
]


@pytest.mark.parametrize("module_name", SHARED_SERVICES + SHARED_ENGINES + SHARED_LOADERS)
def test_shared_module_imports(module_name: str) -> None:
    """Every listed module must import without raising.

    If this test fails, the rename of hf_dashboard → dashboard in Phase 5
    will likely break too — fix the import first.
    """
    importlib.import_module(module_name)
