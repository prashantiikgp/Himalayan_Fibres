"""Shared theme facade — lazy re-exports from ThemeEngine.

Usage:
    from shared.theme import COLORS, FONTS, SPACING, RADII, build_theme

All values are driven by config/theme/default.yml via the
YAML -> Loader -> ThemeEngine pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import gradio as gr
    from engines.theme_resolver import (
        ResolvedColors, ResolvedSpacing, ResolvedFonts, ResolvedRadii,
    )


def _engine():
    """Lazy import to avoid circular imports at module level."""
    from engines.theme_engine import get_theme_engine
    return get_theme_engine()


class _ColorsProxy:
    """Proxy forwarding attribute access to ResolvedColors."""

    def __getattr__(self, name: str) -> str:
        return getattr(_engine().colors, name)


COLORS = _ColorsProxy()


class _DataclassProxy:
    """Proxy forwarding attribute access to a dataclass on ThemeEngine."""

    def __init__(self, attr_name: str):
        self._attr = attr_name

    def __getattr__(self, name: str):
        return getattr(getattr(_engine(), self._attr), name)


SPACING = _DataclassProxy("spacing")
FONTS = _DataclassProxy("fonts")
RADII = _DataclassProxy("radii")


class _DictProxy:
    """Proxy lazily resolving a dict property from ThemeEngine."""

    def __init__(self, attr_name: str):
        self._attr = attr_name
        self._resolved: dict | None = None

    def _resolve(self) -> dict:
        if self._resolved is None:
            self._resolved = getattr(_engine(), self._attr)
        return self._resolved

    def __getitem__(self, key):
        return self._resolve()[key]

    def get(self, key, default=None):
        return self._resolve().get(key, default)


KPI_CARD_STYLE = _DictProxy("kpi_style")


def build_theme() -> "gr.themes.Base":
    """Build the Gradio theme from theme.yml config."""
    return _engine().gradio_theme
