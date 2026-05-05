/**
 * Theme tokens exposed to TS code that needs the actual color values
 * (e.g. Sentry's beforeBreadcrumb, PostHog property formatting, charting libs
 * that don't read CSS vars).
 *
 * Most components should use Tailwind utility classes (`bg-primary`,
 * `text-text-muted`) which resolve to CSS vars at render time. This module is
 * the escape hatch for the few cases where you need the raw value in JS.
 *
 * Values mirror config/dashboard/theme/default.yml. themeEngine writes the
 * same values to CSS vars at boot; this module is the build-time twin.
 *
 * If you change a value here, also change it in the YAML — or better, derive
 * one from the other (future improvement).
 */

export const TOKENS = {
  colors: {
    primary: "#6366f1",
    primaryForeground: "#ffffff",
    secondary: "#8b5cf6",
    secondaryForeground: "#ffffff",
    success: "#22c55e",
    warning: "#f59e0b",
    error: "#ef4444",
    bg: "#0f172a",
    cardBg: "rgba(30, 41, 59, 0.6)",
    border: "rgba(255, 255, 255, 0.06)",
    text: "#e7eaf3",
    textMuted: "#94a3b8",
    textSubtle: "#cbd5e1",
  },
  fonts: {
    xs: "11px",
    sm: "12px",
    md: "13px",
    lg: "16px",
    xl: "20px",
  },
  radii: {
    sm: "4px",
    md: "6px",
    card: "10px",
    pill: "16px",
  },
} as const;

export type ThemeTokens = typeof TOKENS;
