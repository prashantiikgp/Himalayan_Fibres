/**
 * Vite config — production setup for vite_dashboard.
 *
 * Decisions baked in (see reports/audit_vite_migration_plan/STANDARDS_AND_DECISIONS.md):
 *   §6  Browser support — build target `es2022` covers Chrome 120+, Edge 120+, Safari 16+, Firefox 120+.
 *   §8  Visual regression — bundle output goes under dist/; Playwright tests target this.
 *   §11 Repo layout — `@domain` alias resolves to ../config/dashboard so domain YAMLs are
 *       imported by the front-end with a stable, refactor-safe path.
 *
 * vite-plugin-yaml imports `*.yml` files at build time as JS objects. Strict
 * Zod schemas validate them at boot — a typo throws a fatal error, never a
 * silent fallback (per STANDARDS §11 / production-readiness principle).
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import yaml from "@modyfi/vite-plugin-yaml";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => ({
  plugins: [react(), yaml()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@domain": path.resolve(__dirname, "../config/dashboard"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    // Proxy api_v2 in dev so cookies and auth headers behave like prod (same origin).
    proxy: {
      "/api/v2": {
        target: "http://localhost:7860",
        changeOrigin: false,
      },
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: mode !== "production",
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // Split vendor chunks so cache invalidation is per-library, not per-build.
        manualChunks: {
          "react-vendor": ["react", "react-dom", "react-router-dom"],
          "query-vendor": ["@tanstack/react-query", "@tanstack/react-table"],
          "ui-vendor": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-popover",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-toast",
          ],
          "obs-vendor": ["@sentry/react", "posthog-js"],
        },
      },
    },
  },
  // Vitest config lives in vitest.config.ts (separate file so this stays
  // pure Vite). See STANDARDS §8 for testing strategy.
}));
