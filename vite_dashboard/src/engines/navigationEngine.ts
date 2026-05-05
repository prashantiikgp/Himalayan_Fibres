/**
 * navigationEngine — turns sidebar.yml into:
 *   1. A flat list of routes (consumed by React Router)
 *   2. A grouped tree (consumed by <NavSidebar>)
 *
 * The single source of truth for both is config/dashboard/sidebar.yml.
 * Adding a new page = one YAML edit + one route component, no other wiring.
 */

import { configLoader } from "@/loaders/configLoader";
import type { NavGroupT, NavItemT } from "@/schemas/sidebar";

export type NavRoute = {
  id: string;
  path: string;
  label: string;
  icon: string;
  landed_phase: number;
  channel: NavItemT["channel"];
};

function itemToRoute(item: NavItemT): NavRoute {
  return {
    id: item.id,
    path: item.path ?? `/${item.id.replace(/_/g, "-")}`,
    label: item.label,
    icon: item.icon,
    landed_phase: item.landed_phase,
    channel: item.channel,
  };
}

export const navigationEngine = {
  /** Flat list of routes for React Router. */
  getRoutes(): NavRoute[] {
    const sidebar = configLoader.getSidebar();
    return sidebar.sidebar.groups.flatMap((g) => g.items.map(itemToRoute));
  },

  /** Grouped tree for <NavSidebar>. */
  getGroups(): { id: string; label: string; routes: NavRoute[] }[] {
    const sidebar = configLoader.getSidebar();
    return sidebar.sidebar.groups.map((g: NavGroupT) => ({
      id: g.id,
      label: g.label,
      routes: g.items.map(itemToRoute),
    }));
  },

  /** Lookup a route by id. Throws if not found (sidebar misconfigured). */
  getRoute(id: string): NavRoute {
    const route = navigationEngine.getRoutes().find((r) => r.id === id);
    if (!route) throw new Error(`No route configured for id: ${id}`);
    return route;
  },

  /** Default landing path. */
  getDefaultPath(): string {
    const defaultId = configLoader.getDashboard().default_page;
    return navigationEngine.getRoute(defaultId).path;
  },
};
