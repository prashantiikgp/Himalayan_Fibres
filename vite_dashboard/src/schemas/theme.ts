/**
 * Theme schema — validates config/theme/default.yml + components.yml.
 *
 * The theme YAML is the single source of truth for colors, fonts, radii,
 * spacing. themeEngine reads this validated object and emits CSS custom
 * properties on :root, which Tailwind utilities then consume via var().
 */

import { z } from "zod";
import { ColorToken, CssLength, NonEmptyString } from "./_common";

const ColorPalette = z
  .object({
    primary: ColorToken,
    primary_foreground: ColorToken,
    secondary: ColorToken,
    secondary_foreground: ColorToken,
    success: ColorToken,
    success_foreground: ColorToken,
    warning: ColorToken,
    warning_foreground: ColorToken,
    error: ColorToken,
    error_foreground: ColorToken,
    bg: ColorToken,
    card_bg: ColorToken,
    border: ColorToken,
    text: ColorToken,
    text_muted: ColorToken,
    text_subtle: ColorToken,
  })
  .strict();

const FontSizes = z
  .object({
    xs: CssLength,
    sm: CssLength,
    md: CssLength,
    lg: CssLength,
    xl: CssLength,
  })
  .strict();

const Radii = z
  .object({
    sm: CssLength,
    md: CssLength,
    card: CssLength,
    pill: CssLength,
  })
  .strict();

const Spacing = z
  .object({
    card: CssLength,
    section: CssLength,
  })
  .strict();

export const ThemeConfig = z
  .object({
    name: NonEmptyString,
    colors: ColorPalette,
    fonts: FontSizes,
    radii: Radii,
    spacing: Spacing,
  })
  .strict();

export type ThemeConfigT = z.infer<typeof ThemeConfig>;

/** components.yml — per-component style overrides. */
export const ComponentStylesConfig = z
  .object({
    data_table: z
      .object({
        header_padding: CssLength,
        header_font_size: CssLength,
        row_hover_bg: ColorToken,
        row_height: CssLength,
      })
      .strict(),
    kpi_card: z
      .object({
        padding: CssLength,
        title_font_size: CssLength,
        label_font_size: CssLength,
      })
      .strict(),
    status_badge: z
      .object({
        padding: CssLength,
        radius: CssLength,
      })
      .strict(),
  })
  .strict();

export type ComponentStylesConfigT = z.infer<typeof ComponentStylesConfig>;
