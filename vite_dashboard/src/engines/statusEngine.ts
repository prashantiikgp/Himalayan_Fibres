/**
 * statusEngine — single source for status → label/color mappings.
 *
 * Pages and components call statusEngine.resolve(domain, status) to get a
 * typed { label, color } object — no scattered status dicts duplicated
 * across pages (which v1 had — see audit §3.6).
 */

import { configLoader } from "@/loaders/configLoader";
import type { StatusBadgeDefT } from "@/schemas/shared";

export type StatusDomain = "broadcast" | "contact" | "wa_template" | "email_send";

const FALLBACK: StatusBadgeDefT = {
  id: "unknown",
  label: "Unknown",
  color: "neutral",
};

export const statusEngine = {
  /** Resolve a status to its display def. Returns a neutral fallback if not configured. */
  resolve(domain: StatusDomain, status: string): StatusBadgeDefT {
    const cfg = configLoader.getStatusBadges();
    const domainMap = cfg.domains[domain];
    if (!domainMap) return FALLBACK;
    return domainMap[status] ?? FALLBACK;
  },

  /** Get all badges for a domain — used by filter dropdowns. */
  listForDomain(domain: StatusDomain): StatusBadgeDefT[] {
    const cfg = configLoader.getStatusBadges();
    const domainMap = cfg.domains[domain];
    if (!domainMap) return [];
    return Object.values(domainMap);
  },
};
