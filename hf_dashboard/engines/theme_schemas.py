"""Theme YAML Pydantic schemas — config/theme/default.yml + layout.yml."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# -- Color schemas --

class ColorHueScale(BaseModel):
    c50: str; c100: str; c200: str; c300: str; c400: str
    c500: str; c600: str; c700: str; c800: str; c900: str; c950: str


class PrimaryColorConfig(BaseModel):
    base: str; dark: str; hover: str; light: str; subtle: str
    hue: ColorHueScale


class SecondaryColorConfig(BaseModel):
    base: str; dark: str; hue: ColorHueScale


class NeutralColorConfig(BaseModel):
    hue: ColorHueScale


class SemanticColorConfig(BaseModel):
    success: str; warning: str; error: str; info: str


class TextColorConfig(BaseModel):
    primary: str; subtle: str; muted: str; label: str


class SurfaceColorConfig(BaseModel):
    canvas_start: str; canvas_end: str; canvas_gradient: str
    block_bg: str; card_bg: str; card_bg_gradient: str; input_bg: str


class BorderColorConfig(BaseModel):
    default: str; input: str; grid: str; grid_zero: str


class TableColorConfig(BaseModel):
    border: str; even_row: str; row_focus: str


class ExtendedColorsConfig(BaseModel):
    primary_tint: str = "rgba(99,102,241,.06)"
    primary_tint_strong: str = "rgba(99,102,241,.12)"
    overlay_subtle: str = "rgba(255,255,255,.03)"
    overlay_light: str = "rgba(255,255,255,.07)"
    overlay_medium: str = "rgba(255,255,255,.10)"
    overlay_strong: str = "rgba(255,255,255,.15)"
    info_text: str = "#a5b4fc"
    accent_purple: str = "#c4b5fd"


class ColorsConfig(BaseModel):
    primary: PrimaryColorConfig
    secondary: SecondaryColorConfig
    neutral: NeutralColorConfig
    semantic: SemanticColorConfig
    text: TextColorConfig
    surface: SurfaceColorConfig
    border: BorderColorConfig
    table: TableColorConfig
    extended: ExtendedColorsConfig = Field(default_factory=ExtendedColorsConfig)


# -- Component schemas --

class BlockComponentConfig(BaseModel):
    shadow: str = ""; radius: str = "10px"


class InputComponentConfig(BaseModel):
    radius: str = "8px"


class ButtonComponentConfig(BaseModel):
    primary_shadow: str = ""; cancel_bg: str = ""; cancel_text: str = ""


class KPICardComponentConfig(BaseModel):
    border_radius: str = "12px"; padding: str = "16px 20px"
    value_size: str = "28px"; label_size: str = "12px"


class ComponentsConfig(BaseModel):
    block: BlockComponentConfig = Field(default_factory=BlockComponentConfig)
    input: InputComponentConfig = Field(default_factory=InputComponentConfig)
    button: ButtonComponentConfig = Field(default_factory=ButtonComponentConfig)
    kpi_card: KPICardComponentConfig = Field(default_factory=KPICardComponentConfig)


# -- Other schemas --

class TypographyConfig(BaseModel):
    font_family: list[str] = Field(default_factory=list)


class SpacingConfig(BaseModel):
    cell_sm: str = "6px 8px"
    cell_lg: str = "6px 10px"
    card: str = "12px 16px"
    card_compact: str = "10px 14px"
    section_margin: str = "16px 0 8px"
    badge_sm: str = "2px 8px"
    badge_lg: str = "4px 12px"


class FontSizesConfig(BaseModel):
    xxs: str = "9px"; xs: str = "10px"; sm: str = "11px"
    base: str = "12px"; md: str = "13px"; lg: str = "16px"
    xl: str = "20px"; kpi: str = "24px"


class RadiiConfig(BaseModel):
    sm: str = "4px"; md: str = "6px"; lg: str = "8px"
    pill: str = "10px"; card: str = "8px"; bubble: str = "12px"


# -- Root schemas --

class ThemeDefinition(BaseModel):
    name: str = "Himalayan Fibers Dark"
    colors: ColorsConfig
    typography: TypographyConfig = Field(default_factory=TypographyConfig)
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    spacing: SpacingConfig = Field(default_factory=SpacingConfig)
    font_sizes: FontSizesConfig = Field(default_factory=FontSizesConfig)
    radii: RadiiConfig = Field(default_factory=RadiiConfig)


class ThemeConfig(BaseModel):
    theme: ThemeDefinition


# -- Sidebar schemas --

class NavItem(BaseModel):
    id: str
    label: str
    icon: str
    badge: str | None = None
    separator_before: bool = False
    module: str | None = None


class SidebarConfig(BaseModel):
    collapsible: bool = False
    default_collapsed: bool = False
    nav_items: list[NavItem] = Field(default_factory=list)


class SidebarFile(BaseModel):
    sidebar: SidebarConfig


# -- Dashboard schemas --

class DashboardDefinition(BaseModel):
    default_page: str = "home"
    title: str = "Himalayan Fibers"
    subtitle: str = ""


class DashboardConfig(BaseModel):
    dashboard: DashboardDefinition


# -- Layout schemas (config/theme/layout.yml) --
# Strict: extra = "forbid" so typos in YAML keys fail at load time instead of
# silently becoming no-ops. Matches the "engines need proper schema so we
# don't leak information" rule.

class PanelLayoutTokens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_height_expr: str = "calc(100vh - 160px)"
    border_radius: str = "10px"
    padding: str = "10px"
    background: str = "rgba(15,23,42,.50)"
    border: str = "1px solid rgba(255,255,255,.06)"
    chat_background: str = "rgba(15,23,42,.35)"
    chat_border: str = "1px solid rgba(255,255,255,.08)"


class LayoutDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panels: PanelLayoutTokens = Field(default_factory=PanelLayoutTokens)


class LayoutFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: LayoutDefinition
