/**
 * Tailwind config — wires CSS variables emitted by themeEngine to Tailwind utilities.
 *
 * The flow:
 *   config/dashboard/theme/default.yml         (source of truth)
 *     → themeEngine.applyToDocument()          (boot — writes CSS vars on :root)
 *     → tailwind utilities resolve via var()    (this file)
 *     → <Button className="bg-primary">         (component consumes utility)
 *
 * Per STANDARDS §5 — dark mode is the only mode. `darkMode: 'class'` is set
 * but `<html class="dark">` is hardcoded in index.html. No system-preference
 * detection or toggle UI.
 */

import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        // CSS vars emitted by themeEngine from theme/default.yml + components.yml
        primary: {
          DEFAULT: "var(--color-primary)",
          foreground: "var(--color-primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--color-secondary)",
          foreground: "var(--color-secondary-foreground)",
        },
        success: {
          DEFAULT: "var(--color-success)",
          foreground: "var(--color-success-foreground)",
        },
        warning: {
          DEFAULT: "var(--color-warning)",
          foreground: "var(--color-warning-foreground)",
        },
        danger: {
          DEFAULT: "var(--color-error)",
          foreground: "var(--color-error-foreground)",
        },
        bg: "var(--color-bg)",
        card: {
          DEFAULT: "var(--color-card-bg)",
          foreground: "var(--color-text)",
        },
        muted: {
          DEFAULT: "var(--color-card-bg)",
          foreground: "var(--color-text-muted)",
        },
        border: "var(--color-border)",
        input: "var(--color-border)",
        ring: "var(--color-primary)",
        text: {
          DEFAULT: "var(--color-text)",
          muted: "var(--color-text-muted)",
          subtle: "var(--color-text-subtle)",
        },
      },
      fontSize: {
        xs: ["var(--font-xs)", { lineHeight: "1.4" }],
        sm: ["var(--font-sm)", { lineHeight: "1.45" }],
        md: ["var(--font-md)", { lineHeight: "1.5" }],
        lg: ["var(--font-lg)", { lineHeight: "1.4" }],
        xl: ["var(--font-xl)", { lineHeight: "1.3" }],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-card)",
        pill: "var(--radius-pill)",
      },
      spacing: {
        card: "var(--spacing-card)",
        section: "var(--spacing-section)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms ease-out",
        "slide-in-right": "slide-in-right 250ms ease-out",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
