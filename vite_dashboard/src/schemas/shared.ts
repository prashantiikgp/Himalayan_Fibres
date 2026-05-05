/**
 * Shared definitions consumed by multiple pages — KPIs, status badges, filter
 * specs.
 */

import { z } from "zod";
import { ColorToken, NonEmptyString, NonNegInt, SemanticColor } from "./_common";

/** A single KPI definition. Pages list KPI ids; engines hydrate them with data. */
export const KpiDef = z
  .object({
    id: NonEmptyString,
    label: NonEmptyString,
    /** What % the value compares against (for "12 / 500" style). Optional. */
    target: NonNegInt.optional(),
    color: ColorToken,
    /** Optional Lucide icon name. */
    icon: z.string().optional(),
    /** Maps to the API field path on the dashboard endpoint response. */
    api_field: NonEmptyString,
  })
  .strict();

export type KpiDefT = z.infer<typeof KpiDef>;

export const KpiConfig = z
  .object({
    kpis: z.array(KpiDef).min(1),
  })
  .strict();

export type KpiConfigT = z.infer<typeof KpiConfig>;

/** Status → label + color mapping. Used by <StatusBadge> across the app. */
export const StatusBadgeDef = z
  .object({
    id: NonEmptyString,
    label: NonEmptyString,
    color: SemanticColor,
  })
  .strict();

export type StatusBadgeDefT = z.infer<typeof StatusBadgeDef>;

export const StatusBadgesConfig = z
  .object({
    /** Map of domain → { status_id → def }. e.g. broadcast.sent, contact.opted_in */
    domains: z.record(z.string(), z.record(z.string(), StatusBadgeDef)),
  })
  .strict();

export type StatusBadgesConfigT = z.infer<typeof StatusBadgesConfig>;

/** A reusable filter spec referenced by multiple pages. */
export const FilterSpec = z
  .object({
    id: NonEmptyString,
    label: NonEmptyString,
    type: z.enum(["select", "multiselect", "date", "search", "boolean"]),
    /** API endpoint that returns the choices for select/multiselect, or `null` for static. */
    choices_endpoint: z.string().nullable(),
    /** Static choices when choices_endpoint is null. */
    static_choices: z
      .array(
        z
          .object({
            value: z.string(),
            label: NonEmptyString,
          })
          .strict(),
      )
      .default([]),
    placeholder: z.string().default(""),
  })
  .strict();

export type FilterSpecT = z.infer<typeof FilterSpec>;

export const FiltersConfig = z
  .object({
    filters: z.array(FilterSpec).min(1),
  })
  .strict();

export type FiltersConfigT = z.infer<typeof FiltersConfig>;
