/**
 * Pure helpers for the Phase 8.2 WaTemplatePicker.
 *
 * Kept separate from the React component so they can be unit-tested
 * without a DOM and reused by Compose / TemplateSheet without lifting
 * the UI state into a shared hook.
 */

import type { TemplateRegistryEntry, WATemplateOut } from "@/api/wa";

export type EnrichedTemplate = WATemplateOut & {
  /** Joined from the registry; "Other" when the template isn't in YAML. */
  intent_label: string;
  /** Display name from registry; falls back to the raw `name`. */
  display_name: string;
};

export function joinWithRegistry(
  templates: readonly WATemplateOut[],
  registry: readonly TemplateRegistryEntry[],
): EnrichedTemplate[] {
  const byName = new Map<string, TemplateRegistryEntry>();
  for (const e of registry) byName.set(e.name, e);
  return templates.map((t) => {
    const reg = byName.get(t.name);
    return {
      ...t,
      intent_label: reg?.intent_label ?? "Other",
      display_name: reg?.display_name ?? t.name,
    };
  });
}

export type CategoryFilter = "ALL" | "MARKETING" | "UTILITY" | "AUTHENTICATION";

export function filterByCategory<T extends { category: string | null }>(
  rows: readonly T[],
  category: CategoryFilter,
): T[] {
  if (category === "ALL") return [...rows];
  return rows.filter((r) => (r.category ?? "").toUpperCase() === category);
}

export function filterByIntent<T extends { intent_label: string }>(
  rows: readonly T[],
  intent: string,
): T[] {
  if (intent === "ALL") return [...rows];
  return rows.filter((r) => r.intent_label === intent);
}

export function filterBySearch<T extends { name: string; body_text: string }>(
  rows: readonly T[],
  search: string,
): T[] {
  const q = search.trim().toLowerCase();
  if (!q) return [...rows];
  return rows.filter(
    (r) =>
      r.name.toLowerCase().includes(q) ||
      (r.body_text ?? "").toLowerCase().includes(q),
  );
}

/** Intent labels present in the supplied set, in canonical UI order. */
export function availableIntents<T extends { intent_label: string }>(
  rows: readonly T[],
): string[] {
  const seen = new Set<string>(rows.map((r) => r.intent_label));
  // Canonical order matches the registry mapping in api_v2/routers/wa.py.
  const order = ["Intro", "Order", "Sample", "Catalog", "Follow-up", "Test", "Other"];
  return order.filter((label) => seen.has(label));
}
