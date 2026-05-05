/**
 * PostHog analytics wrapper (per STANDARDS §3).
 *
 * No PII. Identifies via stable anonymous IDs only. Internal tool, ~5 users.
 * Events listed in STANDARDS §3 are the canonical set; new events go through
 * code review and an entry there.
 */

import posthog from "posthog-js";
import { getEnv } from "./env";

let initialized = false;

export function initAnalytics(): void {
  if (initialized) return;
  const env = getEnv();
  if (!env.VITE_POSTHOG_KEY) {
    if (env.DEV) {
      console.warn("[analytics] VITE_POSTHOG_KEY not set — events will be logged to console only");
    }
    initialized = true;
    return;
  }
  posthog.init(env.VITE_POSTHOG_KEY, {
    api_host: "https://app.posthog.com",
    capture_pageview: true,
    autocapture: false,
    persistence: "localStorage",
    loaded: () => {
      initialized = true;
    },
  });
  initialized = true;
}

export function track(event: string, props?: Record<string, unknown>): void {
  const env = getEnv();
  if (!env.VITE_POSTHOG_KEY) {
    if (env.DEV) console.warn("[analytics]", event, props ?? {});
    return;
  }
  posthog.capture(event, props);
}
