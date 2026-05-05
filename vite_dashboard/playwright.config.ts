/**
 * Playwright config — visual regression + e2e (per STANDARDS §8).
 *
 * Visual snapshots live under tests/visual/__screenshots__/.
 * One screenshot per (story × browser × viewport) combination.
 * Diffs > 0.1% pixel difference fail the build; reviewer accepts intentional
 * changes by re-running with --update-snapshots.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["html", { open: "never" }], ["github"]]
    : [["html", { open: "on-failure" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.001,
      threshold: 0.1,
    },
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: process.env.CI
    ? {
        command: "pnpm preview",
        url: "http://localhost:4173",
        reuseExistingServer: false,
        timeout: 120 * 1000,
      }
    : undefined,
});
