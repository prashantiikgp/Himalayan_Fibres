"""Theme resolver — framework-agnostic config → resolved dataclasses.

Converts ThemeConfig (Pydantic model from theme.yml) into flat dataclasses
(ResolvedColors, ResolvedSpacing, ResolvedFonts, ResolvedRadii) plus
KPI card style dict. No Gradio dependency here.
"""

from __future__ import annotations

from dataclasses import dataclass

from engines.theme_schemas import LayoutFile, ThemeConfig


@dataclass(frozen=True)
class ResolvedColors:
    """Flat color namespace resolved from theme.yml."""

    PRIMARY: str; PRIMARY_DARK: str; PRIMARY_HOVER: str
    PRIMARY_LIGHT: str; PRIMARY_SUBTLE: str
    SECONDARY: str; SECONDARY_DARK: str
    SUCCESS: str; WARNING: str; ERROR: str; INFO: str
    TEXT: str; TEXT_SUBTLE: str; TEXT_MUTED: str; LABEL: str
    CANVAS_START: str; CANVAS_END: str; CANVAS_GRADIENT: str
    BLOCK_BG: str; CARD_BG: str; CARD_BG_GRADIENT: str; INPUT_BG: str
    BORDER: str; BORDER_INPUT: str; GRID: str; GRID_ZERO: str
    TABLE_BORDER: str; TABLE_EVEN: str; TABLE_ROW_FOCUS: str
    PRIMARY_TINT: str = "rgba(99,102,241,.06)"
    PRIMARY_TINT_STRONG: str = "rgba(99,102,241,.12)"
    OVERLAY_SUBTLE: str = "rgba(255,255,255,.03)"
    OVERLAY_LIGHT: str = "rgba(255,255,255,.07)"
    OVERLAY_MEDIUM: str = "rgba(255,255,255,.10)"
    OVERLAY_STRONG: str = "rgba(255,255,255,.15)"
    INFO_TEXT: str = "#a5b4fc"
    ACCENT_PURPLE: str = "#c4b5fd"


@dataclass(frozen=True)
class ResolvedSpacing:
    CELL_SM: str; CELL_LG: str; CARD: str; CARD_COMPACT: str
    SECTION_MARGIN: str; BADGE_SM: str; BADGE_LG: str


@dataclass(frozen=True)
class ResolvedFonts:
    XXS: str; XS: str; SM: str; BASE: str
    MD: str; LG: str; XL: str; KPI: str


@dataclass(frozen=True)
class ResolvedRadii:
    SM: str; MD: str; LG: str; PILL: str; CARD: str; BUBBLE: str


@dataclass(frozen=True)
class ResolvedPanelLayout:
    """Structural CSS tokens for full-height dashboard panels."""

    MIN_HEIGHT_EXPR: str
    BORDER_RADIUS: str
    PADDING: str
    BACKGROUND: str
    BORDER: str
    CHAT_BACKGROUND: str
    CHAT_BORDER: str


def resolve_colors(config: ThemeConfig) -> ResolvedColors:
    c = config.theme.colors
    ext = c.extended
    return ResolvedColors(
        PRIMARY=c.primary.base, PRIMARY_DARK=c.primary.dark,
        PRIMARY_HOVER=c.primary.hover, PRIMARY_LIGHT=c.primary.light,
        PRIMARY_SUBTLE=c.primary.subtle,
        SECONDARY=c.secondary.base, SECONDARY_DARK=c.secondary.dark,
        SUCCESS=c.semantic.success, WARNING=c.semantic.warning,
        ERROR=c.semantic.error, INFO=c.semantic.info,
        TEXT=c.text.primary, TEXT_SUBTLE=c.text.subtle,
        TEXT_MUTED=c.text.muted, LABEL=c.text.label,
        CANVAS_START=c.surface.canvas_start, CANVAS_END=c.surface.canvas_end,
        CANVAS_GRADIENT=c.surface.canvas_gradient,
        BLOCK_BG=c.surface.block_bg, CARD_BG=c.surface.card_bg,
        CARD_BG_GRADIENT=c.surface.card_bg_gradient, INPUT_BG=c.surface.input_bg,
        BORDER=c.border.default, BORDER_INPUT=c.border.input,
        GRID=c.border.grid, GRID_ZERO=c.border.grid_zero,
        TABLE_BORDER=c.table.border, TABLE_EVEN=c.table.even_row,
        TABLE_ROW_FOCUS=c.table.row_focus,
        PRIMARY_TINT=ext.primary_tint, PRIMARY_TINT_STRONG=ext.primary_tint_strong,
        OVERLAY_SUBTLE=ext.overlay_subtle, OVERLAY_LIGHT=ext.overlay_light,
        OVERLAY_MEDIUM=ext.overlay_medium, OVERLAY_STRONG=ext.overlay_strong,
        INFO_TEXT=ext.info_text, ACCENT_PURPLE=ext.accent_purple,
    )


def resolve_spacing(config: ThemeConfig) -> ResolvedSpacing:
    s = config.theme.spacing
    return ResolvedSpacing(
        CELL_SM=s.cell_sm, CELL_LG=s.cell_lg,
        CARD=s.card, CARD_COMPACT=s.card_compact,
        SECTION_MARGIN=s.section_margin,
        BADGE_SM=s.badge_sm, BADGE_LG=s.badge_lg,
    )


def resolve_fonts(config: ThemeConfig) -> ResolvedFonts:
    f = config.theme.font_sizes
    return ResolvedFonts(
        XXS=f.xxs, XS=f.xs, SM=f.sm, BASE=f.base,
        MD=f.md, LG=f.lg, XL=f.xl, KPI=f.kpi,
    )


def resolve_radii(config: ThemeConfig) -> ResolvedRadii:
    r = config.theme.radii
    return ResolvedRadii(
        SM=r.sm, MD=r.md, LG=r.lg,
        PILL=r.pill, CARD=r.card, BUBBLE=r.bubble,
    )


def resolve_panel_layout(layout: LayoutFile) -> ResolvedPanelLayout:
    p = layout.layout.panels
    return ResolvedPanelLayout(
        MIN_HEIGHT_EXPR=p.min_height_expr,
        BORDER_RADIUS=p.border_radius,
        PADDING=p.padding,
        BACKGROUND=p.background,
        BORDER=p.border,
        CHAT_BACKGROUND=p.chat_background,
        CHAT_BORDER=p.chat_border,
    )


def resolve_kpi_style(config: ThemeConfig) -> dict:
    colors = resolve_colors(config)
    k = config.theme.components.kpi_card
    return dict(
        background=colors.CARD_BG_GRADIENT,
        border_radius=k.border_radius,
        padding=k.padding,
        value_size=k.value_size,
        label_size=k.label_size,
        label_color=colors.TEXT_SUBTLE,
    )
