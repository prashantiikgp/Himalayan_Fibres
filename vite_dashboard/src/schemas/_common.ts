/**
 * Primitive Zod types reused across schemas.
 *
 * Per STANDARDS production-readiness principle: strict validation, no `any`,
 * no `extra: 'allow'` unless explicitly justified per-schema.
 */

import { z } from "zod";

/** Hex/rgba color string. Permissive — themeEngine renders whatever the YAML says. */
export const ColorToken = z.string().min(3).describe("Hex (#abc / #aabbcc) or rgba(...) color");

/** CSS length token: "12px", "1rem", "100%", "calc(...)". */
export const CssLength = z.string().min(1);

/** Non-empty string. */
export const NonEmptyString = z.string().min(1);

/** A positive integer. */
export const PosInt = z.number().int().positive();

/** A non-negative integer. */
export const NonNegInt = z.number().int().min(0);

/** A bounded float in [0, 1] — for opacities, ratios, etc. */
export const Ratio = z.number().min(0).max(1);

/** Common semantic-color labels used by status badges. */
export const SemanticColor = z.enum([
  "primary",
  "secondary",
  "success",
  "warning",
  "error",
  "neutral",
]);

export type SemanticColorT = z.infer<typeof SemanticColor>;

/* ── HowToUse (Phase 6.2) ─────────────────────────────────────────────── */

/** One section inside a HowToUse accordion. */
export const HowToUseSection = z
  .object({
    title: NonEmptyString,
    body: NonEmptyString,
  })
  .strict();

export type HowToUseSectionT = z.infer<typeof HowToUseSection>;

/** Replaces the per-page `<h1>title</h1><p>subtitle</p>` header. The
 * accordion is collapsed by default; the summary is visible above it. */
export const HowToUse = z
  .object({
    summary: NonEmptyString,
    sections: z.array(HowToUseSection).default([]),
  })
  .strict();

export type HowToUseT = z.infer<typeof HowToUse>;
