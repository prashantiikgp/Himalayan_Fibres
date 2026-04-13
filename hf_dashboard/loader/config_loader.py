"""YAML config loader for the dashboard.

Loads theme, sidebar, and dashboard configs from config/ directory.
Caches loaded configs to avoid re-reading YAML on every access.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from engines.theme_schemas import (
    ThemeConfig,
    SidebarFile,
    DashboardConfig,
)

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return the parsed dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ConfigLoader:
    """Loads and caches YAML configs for the dashboard."""

    def __init__(self, config_dir: Path = _CONFIG_DIR):
        self._config_dir = config_dir
        self._theme: ThemeConfig | None = None
        self._sidebar: SidebarFile | None = None
        self._dashboard: DashboardConfig | None = None

    def load_theme(self) -> ThemeConfig:
        if self._theme is None:
            path = self._config_dir / "theme" / "default.yml"
            data = _load_yaml(path)
            self._theme = ThemeConfig(**data)
            log.info("Loaded theme: %s", self._theme.theme.name)
        return self._theme

    def load_sidebar(self) -> SidebarFile:
        if self._sidebar is None:
            path = self._config_dir / "dashboard" / "sidebar.yml"
            data = _load_yaml(path)
            self._sidebar = SidebarFile(**data)
            log.info("Loaded sidebar: %d nav items", len(self._sidebar.sidebar.nav_items))
        return self._sidebar

    def load_dashboard(self) -> DashboardConfig:
        if self._dashboard is None:
            path = self._config_dir / "dashboard" / "dashboard.yml"
            data = _load_yaml(path)
            self._dashboard = DashboardConfig(**data)
            log.info("Loaded dashboard config: %s", self._dashboard.dashboard.title)
        return self._dashboard


@lru_cache(maxsize=1)
def get_config_loader() -> ConfigLoader:
    """Singleton config loader."""
    return ConfigLoader()
