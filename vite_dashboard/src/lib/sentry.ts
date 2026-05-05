/**
 * Sentry wiring — captures unhandled errors + React render failures.
 *
 * PII policy (per STANDARDS §3): events are scrubbed of emails, phone numbers,
 * and contact names before send. Names are only ever in component state, never
 * in error messages we throw, so the default scrubber + a `beforeSend` filter
 * is sufficient.
 */

import * as Sentry from "@sentry/react";
import { getEnv } from "./env";

export function initSentry(): void {
  const env = getEnv();
  if (!env.VITE_SENTRY_DSN) {
    if (env.DEV) console.warn("[sentry] VITE_SENTRY_DSN not set — errors will go to console only");
    return;
  }
  Sentry.init({
    dsn: env.VITE_SENTRY_DSN,
    environment: env.VITE_APP_ENV,
    integrations: [Sentry.browserTracingIntegration(), Sentry.replayIntegration()],
    tracesSampleRate: env.PROD ? 0.1 : 1.0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 1.0,
    beforeSend(event) {
      // Strip emails and Indian-format phone numbers from anywhere in the
      // event. STANDARDS §3 promises "no PII" in error reports — the default
      // scrubber misses stack-frame `vars` and exception messages, so we walk
      // the event JSON and replace patterns inline (review fix Mn5).
      const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
      const PHONE_RE = /\+?\d{1,3}[\s-]?\d{6,12}/g;

      const scrub = (s: string): string =>
        s.replace(EMAIL_RE, "<email>").replace(PHONE_RE, "<phone>");

      const walk = (value: unknown): unknown => {
        if (typeof value === "string") return scrub(value);
        if (Array.isArray(value)) return value.map(walk);
        if (value && typeof value === "object") {
          const out: Record<string, unknown> = {};
          for (const [k, v] of Object.entries(value)) out[k] = walk(v);
          return out;
        }
        return value;
      };

      return walk(event) as typeof event;
    },
  });
}

export const SentryErrorBoundary = Sentry.ErrorBoundary;
