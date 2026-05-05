/**
 * Contacts endpoints — Phase 1.
 */

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type ContactRow = {
  id: string;
  first_name: string;
  last_name: string;
  company: string;
  email: string;
  phone: string;
  wa_id: string | null;
  lifecycle: string;
  customer_type: string;
  consent_status: string;
  country: string;
  tags: string[];
  segments: string[];
  channels: ("email" | "whatsapp")[];
};

export type ContactListResponse = {
  contacts: ContactRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type ContactsQuery = {
  segment?: string;
  lifecycle?: string;
  country?: string;
  channel?: "all" | "email" | "whatsapp" | "both";
  tags?: string[];
  search?: string;
  page?: number;
  page_size?: number;
};

function toQueryString(q: ContactsQuery): string {
  const sp = new URLSearchParams();
  if (q.segment && q.segment !== "all") sp.set("segment", q.segment);
  if (q.lifecycle && q.lifecycle !== "all") sp.set("lifecycle", q.lifecycle);
  if (q.country && q.country !== "all") sp.set("country", q.country);
  if (q.channel && q.channel !== "all") sp.set("channel", q.channel);
  if (q.search) sp.set("search", q.search);
  if (q.page !== undefined) sp.set("page", String(q.page));
  if (q.page_size !== undefined) sp.set("page_size", String(q.page_size));
  for (const t of q.tags ?? []) sp.append("tags", t);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export function useContacts(q: ContactsQuery) {
  return useQuery({
    queryKey: ["contacts", q],
    queryFn: () => apiFetch<ContactListResponse>(`/api/v2/contacts${toQueryString(q)}`),
    placeholderData: keepPreviousData,
  });
}

export type ContactNoteOut = {
  id: number;
  body: string;
  author: string | null;
  created_at: string;
};

export type ContactInteractionOut = {
  id: number;
  kind: string;
  summary: string;
  actor: string | null;
  created_at: string;
};

export type ContactDetail = ContactRow & {
  customer_subtype: string;
  geography: string;
  legacy_notes: string;
  threaded_notes: ContactNoteOut[];
  activity: ContactInteractionOut[];
  matched_segments: SegmentSummary[];
};

export function useContactDetail(contactId: string | null) {
  return useQuery({
    queryKey: ["contacts", "detail", contactId],
    enabled: contactId !== null,
    queryFn: () => apiFetch<ContactDetail>(`/api/v2/contacts/${contactId}`),
  });
}

export type ContactCreate = {
  first_name: string;
  last_name?: string;
  phone: string;
  email?: string;
  company?: string;
  country?: string;
  customer_type?: string;
  lifecycle?: string;
  tags?: string[];
};

export type ContactUpdate = {
  first_name?: string;
  last_name?: string;
  phone?: string;
  email?: string;
  company?: string;
  country?: string;
  lifecycle?: string;
  consent_status?: string;
  tags?: string[];
  notes?: string;
};

export async function createContact(body: ContactCreate): Promise<ContactRow> {
  return apiFetch<ContactRow>("/api/v2/contacts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateContact(id: string, body: ContactUpdate): Promise<ContactRow> {
  return apiFetch<ContactRow>(`/api/v2/contacts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function addContactNote(id: string, body: string): Promise<ContactNoteOut> {
  return apiFetch<ContactNoteOut>(`/api/v2/contacts/${id}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export type ImportResponse = {
  imported: number;
  skipped: number;
  errors: string[];
};

export async function importContacts(file: File): Promise<ImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const { apiBase } = await import("@/lib/env");
  const { getToken, clearToken } = await import("@/lib/auth");
  const { ApiError } = await import("@/lib/queryClient");
  const token = getToken();
  const res = await fetch(`${apiBase()}/api/v2/contacts/import`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "Unauthenticated", "/api/v2/contacts/import");
  }
  if (!res.ok) {
    throw new ApiError(res.status, await res.text().catch(() => ""), "/api/v2/contacts/import");
  }
  return (await res.json()) as ImportResponse;
}

export type SegmentSummary = {
  id: string;
  name: string;
  color: string | null;
  description: string | null;
  member_count: number;
};

export function useSegments() {
  return useQuery({
    queryKey: ["segments"],
    queryFn: () => apiFetch<{ segments: SegmentSummary[] }>("/api/v2/segments"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useContactCountries() {
  return useQuery({
    queryKey: ["contacts", "countries"],
    queryFn: () => apiFetch<{ countries: string[] }>("/api/v2/contacts/countries"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useContactTags() {
  return useQuery({
    queryKey: ["contacts", "tags"],
    queryFn: () => apiFetch<{ tags: string[] }>("/api/v2/contacts/tags"),
    staleTime: 60 * 1000,
  });
}
