/**
 * configLoader — singleton that loads + Zod-validates every YAML at boot.
 *
 * Per STANDARDS production-readiness principle: validation failures throw at
 * boot. main.tsx catches and renders a fatal error screen. No silent fallback
 * to defaults.
 *
 * YAMLs are imported by vite-plugin-yaml at build time, so the cost at runtime
 * is just Zod parsing — fast.
 */

import type { z } from "zod";

import themeYaml from "@/config/theme/default.yml";
import componentsYaml from "@/config/theme/components.yml";
import dashboardYaml from "@/config/dashboard/dashboard.yml";
import sidebarYaml from "@/config/dashboard/sidebar.yml";
import kpiYaml from "@/config/shared/kpi.yml";
import statusBadgesYaml from "@/config/shared/status_badges.yml";
import filtersYaml from "@/config/shared/filters.yml";

import homePageYaml from "@/config/pages/home.yml";
import contactsPageYaml from "@/config/pages/contacts.yml";
import waInboxPageYaml from "@/config/pages/wa_inbox.yml";
import broadcastsPageYaml from "@/config/pages/broadcasts.yml";
import waTemplatesPageYaml from "@/config/pages/wa_templates.yml";
import flowsPageYaml from "@/config/pages/flows.yml";

import {
  ThemeConfig,
  ComponentStylesConfig,
  type ThemeConfigT,
  type ComponentStylesConfigT,
} from "@/schemas/theme";
import { DashboardConfig, type DashboardConfigT } from "@/schemas/dashboard";
import { SidebarConfig, type SidebarConfigT } from "@/schemas/sidebar";
import {
  KpiConfig,
  StatusBadgesConfig,
  FiltersConfig,
  type KpiConfigT,
  type StatusBadgesConfigT,
  type FiltersConfigT,
} from "@/schemas/shared";
import {
  PAGE_SCHEMAS,
  PAGE_IDS,
  type PageId,
  type PageConfigByID,
} from "@/schemas/pages";

/** Thrown by configLoader.bootstrap() when any YAML fails Zod validation. */
export class ConfigValidationError extends Error {
  constructor(
    public readonly fileName: string,
    public readonly zodMessage: string,
  ) {
    super(`Config validation failed for ${fileName}:\n${zodMessage}`);
    this.name = "ConfigValidationError";
  }
}

function parseStrict<S extends z.ZodTypeAny>(
  schema: S,
  value: unknown,
  fileName: string,
): z.output<S> {
  const result = schema.safeParse(value);
  if (!result.success) {
    // Zod's toString() includes the path to the bad field — useful for the
    // fatal error screen.
    throw new ConfigValidationError(fileName, result.error.toString());
  }
  return result.data;
}

class ConfigLoader {
  private _theme: ThemeConfigT | null = null;
  private _components: ComponentStylesConfigT | null = null;
  private _dashboard: DashboardConfigT | null = null;
  private _sidebar: SidebarConfigT | null = null;
  private _kpis: KpiConfigT | null = null;
  private _statusBadges: StatusBadgesConfigT | null = null;
  private _filters: FiltersConfigT | null = null;
  private _pages = new Map<PageId, PageConfigByID[PageId]>();
  private _booted = false;

  /**
   * Load + validate every YAML. Call exactly once from main.tsx before
   * mounting the app. Throws ConfigValidationError on any validation failure.
   */
  bootstrap(): void {
    if (this._booted) return;

    this._theme = parseStrict(ThemeConfig, themeYaml, "theme/default.yml");
    this._components = parseStrict(
      ComponentStylesConfig,
      componentsYaml,
      "theme/components.yml",
    );
    this._dashboard = parseStrict(DashboardConfig, dashboardYaml, "dashboard/dashboard.yml");
    this._sidebar = parseStrict(SidebarConfig, sidebarYaml, "dashboard/sidebar.yml");
    this._kpis = parseStrict(KpiConfig, kpiYaml, "shared/kpi.yml");
    this._statusBadges = parseStrict(
      StatusBadgesConfig,
      statusBadgesYaml,
      "shared/status_badges.yml",
    );
    this._filters = parseStrict(FiltersConfig, filtersYaml, "shared/filters.yml");

    const pageYamls: Record<PageId, unknown> = {
      home: homePageYaml,
      contacts: contactsPageYaml,
      wa_inbox: waInboxPageYaml,
      broadcasts: broadcastsPageYaml,
      wa_templates: waTemplatesPageYaml,
      flows: flowsPageYaml,
    };

    for (const id of PAGE_IDS) {
      const schema = PAGE_SCHEMAS[id];
      const yaml = pageYamls[id];
      const parsed = parseStrict(schema, yaml, `pages/${id}.yml`);
      this._pages.set(id, parsed as PageConfigByID[typeof id]);
    }

    this._booted = true;
  }

  /** Throws if called before bootstrap(). Helps catch misuse. */
  private guard(): void {
    if (!this._booted) {
      throw new Error("configLoader.bootstrap() must be called before reading config");
    }
  }

  getTheme(): ThemeConfigT {
    this.guard();
    return this._theme!;
  }

  getComponents(): ComponentStylesConfigT {
    this.guard();
    return this._components!;
  }

  getDashboard(): DashboardConfigT {
    this.guard();
    return this._dashboard!;
  }

  getSidebar(): SidebarConfigT {
    this.guard();
    return this._sidebar!;
  }

  getKpis(): KpiConfigT {
    this.guard();
    return this._kpis!;
  }

  getStatusBadges(): StatusBadgesConfigT {
    this.guard();
    return this._statusBadges!;
  }

  getFilters(): FiltersConfigT {
    this.guard();
    return this._filters!;
  }

  getPage<T extends PageId>(id: T): PageConfigByID[T] {
    this.guard();
    const cfg = this._pages.get(id);
    if (!cfg) throw new Error(`Page config not found: ${id}`);
    return cfg as PageConfigByID[T];
  }
}

export const configLoader = new ConfigLoader();
