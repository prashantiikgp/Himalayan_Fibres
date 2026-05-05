/**
 * themeEngine — turns the validated theme + components YAMLs into CSS custom
 * properties on `:root`. Tailwind utilities (bg-primary, text-text-muted)
 * resolve via these vars at render time.
 *
 * Called once at app boot (after configLoader.bootstrap()). No re-runs;
 * theme changes require a config edit + reload.
 */

import { configLoader } from "@/loaders/configLoader";
import type { ThemeConfigT, ComponentStylesConfigT } from "@/schemas/theme";

/** Build the flat var map (snake_case key → value). */
function buildThemeVars(theme: ThemeConfigT): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const [k, v] of Object.entries(theme.colors)) {
    vars[`--color-${k.replace(/_/g, "-")}`] = v;
  }
  for (const [k, v] of Object.entries(theme.fonts)) {
    vars[`--font-${k}`] = v;
  }
  for (const [k, v] of Object.entries(theme.radii)) {
    vars[`--radius-${k}`] = v;
  }
  for (const [k, v] of Object.entries(theme.spacing)) {
    vars[`--spacing-${k}`] = v;
  }
  return vars;
}

function buildComponentVars(c: ComponentStylesConfigT): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const [comp, fields] of Object.entries(c)) {
    for (const [field, value] of Object.entries(fields)) {
      // --data-table-row-height etc.
      const compKebab = comp.replace(/_/g, "-");
      const fieldKebab = field.replace(/_/g, "-");
      vars[`--${compKebab}-${fieldKebab}`] = value;
    }
  }
  return vars;
}

export const themeEngine = {
  /**
   * Apply the YAML-defined theme to the document root. Tailwind utilities
   * read these vars on every render, so a future hot-swap is supported but
   * not currently exposed.
   */
  applyToDocument(): void {
    const theme = configLoader.getTheme();
    const components = configLoader.getComponents();
    const root = document.documentElement;
    for (const [k, v] of Object.entries(buildThemeVars(theme))) {
      root.style.setProperty(k, v);
    }
    for (const [k, v] of Object.entries(buildComponentVars(components))) {
      root.style.setProperty(k, v);
    }
  },

  /** For tests: get the full var map without touching the DOM. */
  resolveVars(): Record<string, string> {
    return {
      ...buildThemeVars(configLoader.getTheme()),
      ...buildComponentVars(configLoader.getComponents()),
    };
  },
};
