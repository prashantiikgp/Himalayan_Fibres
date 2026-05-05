/**
 * kpiEngine — combines the KPI definitions from config/shared/kpi.yml with
 * runtime data from /api/v2/dashboard/home into typed <KpiCard> props.
 */

import { configLoader } from "@/loaders/configLoader";
import type { KpiDefT } from "@/schemas/shared";

export type KpiTile = {
  id: string;
  label: string;
  /** Display value. "12 / 500" if target is set, otherwise "12". */
  value: string;
  color: string;
  icon?: string;
};

export const kpiEngine = {
  /** Get the raw definitions for any code that needs them (e.g. tests). */
  getDefinitions(): KpiDefT[] {
    return configLoader.getKpis().kpis;
  },

  /** Look up a KPI by id. Throws if not configured. */
  getDefinition(id: string): KpiDefT {
    const def = kpiEngine.getDefinitions().find((k) => k.id === id);
    if (!def) throw new Error(`No KPI configured: ${id}`);
    return def;
  },

  /**
   * Hydrate KPI definitions with values from a dashboard data object.
   * `data` is the response from GET /api/v2/dashboard/home — a flat
   * Record<string, number>.
   */
  hydrate(ids: readonly string[], data: Record<string, number | undefined>): KpiTile[] {
    return ids.map((id) => {
      const def = kpiEngine.getDefinition(id);
      const value = data[def.api_field];
      const display = def.target
        ? `${value ?? 0} / ${def.target}`
        : String(value ?? 0);
      return {
        id: def.id,
        label: def.label,
        value: display,
        color: def.color,
        icon: def.icon,
      };
    });
  },
};
