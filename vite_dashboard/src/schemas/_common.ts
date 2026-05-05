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
