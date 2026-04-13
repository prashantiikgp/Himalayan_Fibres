"""ThemeEngine — converts theme.yml into Gradio runtime objects.

Produces:
  - ResolvedColors: flat namespace for HTML inline styles
  - ResolvedSpacing / ResolvedFonts / ResolvedRadii
  - KPI card style dict
  - Gradio theme: gr.themes.Base instance
"""

from __future__ import annotations

from functools import lru_cache

import gradio as gr

from engines.theme_schemas import ThemeConfig
from engines.theme_resolver import (
    ResolvedColors, ResolvedSpacing, ResolvedFonts, ResolvedRadii,
    resolve_colors, resolve_spacing, resolve_fonts, resolve_radii,
    resolve_kpi_style,
)


class ThemeEngine:
    """Converts validated ThemeConfig into runtime objects."""

    def __init__(self, config: ThemeConfig):
        self._config = config
        self._cfg = config.theme
        self._colors: ResolvedColors | None = None
        self._spacing: ResolvedSpacing | None = None
        self._fonts: ResolvedFonts | None = None
        self._radii: ResolvedRadii | None = None
        self._kpi_style: dict | None = None
        self._gradio_theme: gr.themes.Base | None = None

    @property
    def colors(self) -> ResolvedColors:
        if self._colors is None:
            self._colors = resolve_colors(self._config)
        return self._colors

    @property
    def spacing(self) -> ResolvedSpacing:
        if self._spacing is None:
            self._spacing = resolve_spacing(self._config)
        return self._spacing

    @property
    def fonts(self) -> ResolvedFonts:
        if self._fonts is None:
            self._fonts = resolve_fonts(self._config)
        return self._fonts

    @property
    def radii(self) -> ResolvedRadii:
        if self._radii is None:
            self._radii = resolve_radii(self._config)
        return self._radii

    @property
    def kpi_style(self) -> dict:
        if self._kpi_style is None:
            self._kpi_style = resolve_kpi_style(self._config)
        return self._kpi_style

    @property
    def gradio_theme(self) -> gr.themes.Base:
        if self._gradio_theme is None:
            self._gradio_theme = self._build_gradio_theme()
        return self._gradio_theme

    def _build_gradio_theme(self) -> gr.themes.Base:
        c = self._cfg.colors
        comp = self._cfg.components
        colors = self.colors

        primary_hue = gr.themes.Color(**c.primary.hue.model_dump())
        secondary_hue = gr.themes.Color(**c.secondary.hue.model_dump())
        neutral_hue = gr.themes.Color(**c.neutral.hue.model_dump())

        return gr.themes.Base(
            primary_hue=primary_hue,
            secondary_hue=secondary_hue,
            neutral_hue=neutral_hue,
            font=self._cfg.typography.font_family,
        ).set(
            body_background_fill=colors.CANVAS_GRADIENT,
            body_background_fill_dark=colors.CANVAS_GRADIENT,
            body_text_color=colors.TEXT,
            body_text_color_dark=colors.TEXT,
            body_text_color_subdued=colors.TEXT_SUBTLE,
            body_text_color_subdued_dark=colors.TEXT_SUBTLE,
            block_background_fill=colors.BLOCK_BG,
            block_background_fill_dark=colors.BLOCK_BG,
            block_border_color=colors.BORDER,
            block_border_color_dark=colors.BORDER,
            block_label_text_color=colors.LABEL,
            block_label_text_color_dark=colors.LABEL,
            block_title_text_color=colors.TEXT,
            block_title_text_color_dark=colors.TEXT,
            block_shadow=comp.block.shadow,
            block_shadow_dark=comp.block.shadow,
            block_radius=comp.block.radius,
            input_background_fill=colors.INPUT_BG,
            input_background_fill_dark=colors.INPUT_BG,
            input_border_color=colors.BORDER_INPUT,
            input_border_color_dark=colors.BORDER_INPUT,
            input_placeholder_color=colors.TEXT_MUTED,
            input_placeholder_color_dark=colors.TEXT_MUTED,
            input_radius=comp.input.radius,
            button_primary_background_fill=colors.PRIMARY_DARK,
            button_primary_background_fill_dark=colors.PRIMARY_DARK,
            button_primary_background_fill_hover=colors.PRIMARY_HOVER,
            button_primary_background_fill_hover_dark=colors.PRIMARY_HOVER,
            button_primary_text_color="#ffffff",
            button_primary_text_color_dark="#ffffff",
            button_primary_shadow=comp.button.primary_shadow,
            button_primary_shadow_dark=comp.button.primary_shadow,
            button_secondary_background_fill=colors.PRIMARY_SUBTLE,
            button_secondary_background_fill_dark=colors.PRIMARY_SUBTLE,
            button_secondary_text_color=colors.LABEL,
            button_secondary_text_color_dark=colors.LABEL,
            button_cancel_background_fill=comp.button.cancel_bg,
            button_cancel_background_fill_dark=comp.button.cancel_bg,
            button_cancel_text_color=comp.button.cancel_text,
            button_cancel_text_color_dark=comp.button.cancel_text,
            border_color_primary=colors.BORDER_INPUT,
            border_color_primary_dark=colors.BORDER_INPUT,
            checkbox_background_color=colors.INPUT_BG,
            checkbox_background_color_dark=colors.INPUT_BG,
            checkbox_background_color_selected=colors.PRIMARY,
            checkbox_background_color_selected_dark=colors.PRIMARY,
            table_border_color=colors.TABLE_BORDER,
            table_border_color_dark=colors.TABLE_BORDER,
            table_even_background_fill=colors.TABLE_EVEN,
            table_even_background_fill_dark=colors.TABLE_EVEN,
            table_odd_background_fill="transparent",
            table_odd_background_fill_dark="transparent",
            table_row_focus=colors.TABLE_ROW_FOCUS,
            table_row_focus_dark=colors.TABLE_ROW_FOCUS,
        )


@lru_cache(maxsize=1)
def get_theme_engine() -> ThemeEngine:
    """Singleton ThemeEngine, loading theme.yml on first call."""
    from loader.config_loader import get_config_loader
    loader = get_config_loader()
    config = loader.load_theme()
    return ThemeEngine(config)
