/**
 * Typed accessors for Vite import.meta.env vars.
 *
 * Per STANDARDS production-readiness principle: never read import.meta.env
 * directly in feature code — always go through this module so the validation
 * happens once and downstream consumers get a typed string.
 */

import { z } from "zod";

const envSchema = z.object({
  VITE_SENTRY_DSN: z.string().default(""),
  VITE_POSTHOG_KEY: z.string().default(""),
  VITE_API_BASE: z.string().default(""),
  VITE_APP_ENV: z.enum(["development", "production", "test"]).default("development"),
  MODE: z.string().default("development"),
  PROD: z.boolean().default(false),
  DEV: z.boolean().default(true),
});

export type AppEnv = z.infer<typeof envSchema>;

let _env: AppEnv | null = null;

export function getEnv(): AppEnv {
  if (_env) return _env;
  const result = envSchema.safeParse(import.meta.env);
  if (!result.success) {
    // Should be impossible — schema has defaults for every field.
    // If this fires, something fundamental is wrong with the bundle.
    throw new Error(`Invalid env vars: ${result.error.message}`);
  }
  _env = result.data;
  return _env;
}

export const isProd = () => getEnv().PROD;
export const isDev = () => getEnv().DEV;

export const apiBase = (): string => {
  const base = getEnv().VITE_API_BASE.trim();
  return base || ""; // empty = same origin → /api/v2/...
};
