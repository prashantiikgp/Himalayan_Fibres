/**
 * filterEngine — looks up filter specs from config/shared/filters.yml.
 *
 * Pages reference filter ids in their YAML (e.g. contacts.yml has
 * filters: ["segment", "lifecycle", ...]); <FilterBar> uses this engine to
 * hydrate them.
 */

import { configLoader } from "@/loaders/configLoader";
import type { FilterSpecT } from "@/schemas/shared";

export const filterEngine = {
  /** All defined filter specs. */
  getAll(): FilterSpecT[] {
    return configLoader.getFilters().filters;
  },

  /** Look up a filter by id. Throws if not configured. */
  get(id: string): FilterSpecT {
    const spec = filterEngine.getAll().find((f) => f.id === id);
    if (!spec) throw new Error(`No filter spec configured: ${id}`);
    return spec;
  },

  /** Hydrate a list of filter ids into a list of specs in the requested order. */
  resolve(ids: readonly string[]): FilterSpecT[] {
    return ids.map((id) => filterEngine.get(id));
  },
};
