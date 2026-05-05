/**
 * Dashboard endpoints — Home page data + system status.
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type HomeData = {
  emails_today: number;
  wa_today: number;
  total: number;
  wa_24h: number;
  wa_ready: number;
  opted_in: number;
  pending: number;
  email_campaigns: number;
  wa_campaigns: number;
  total_flows: number;
  active_runs: number;
  lifecycle: { id: string; label: string; icon: string; color: string; count: number }[];
  activity: {
    timestamp: string;
    kind: "email_sent" | "wa_sent" | "wa_received";
    text: string;
  }[];
};

export type SystemStatus = {
  gmail_configured: boolean;
  wa_configured: boolean;
};

export function useHomeData() {
  return useQuery({
    queryKey: ["dashboard", "home"],
    queryFn: () => apiFetch<HomeData>("/api/v2/dashboard/home"),
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["dashboard", "system_status"],
    queryFn: () => apiFetch<SystemStatus>("/api/v2/system/status"),
    staleTime: 60 * 1000,
  });
}
