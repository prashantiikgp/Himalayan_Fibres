/**
 * Display-formatting helpers — dates, numbers, durations, etc.
 *
 * Centralized so locale changes (per STANDARDS §7 — i18n deferred but
 * structured for an easy future swap) only touch one file.
 */

import { format, formatDistanceToNow, isValid, parseISO } from "date-fns";

/** Format an ISO date string or Date as "Mar 12, 14:32". */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(d)) return "—";
  return format(d, "MMM d, HH:mm");
}

/** "5 minutes ago" / "2 hours ago" / "—" for null. */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? parseISO(value) : value;
  if (!isValid(d)) return "—";
  return formatDistanceToNow(d, { addSuffix: true });
}

/** "1,234" — locale-aware integer separator. */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-IN");
}

/** "₹12,500" — INR with locale separator. */
export function formatCurrency(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);
}

/** "23h 45m" / "2m 10s" / "<1s" — for durations in seconds. */
export function formatDuration(seconds: number): string {
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM ? `${h}h ${remM}m` : `${h}h`;
}

/** Truncate to N characters with ellipsis. Used in chat previews and table cells. */
export function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1).trimEnd()}…`;
}
