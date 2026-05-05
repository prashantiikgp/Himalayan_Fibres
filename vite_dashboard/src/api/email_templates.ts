/**
 * /api/v2/email/templates hooks (Phase 6.4).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type EmailVariableType = "text" | "textarea" | "url" | "date";

export type EmailVariableSpec = {
  name: string;
  label: string;
  type: EmailVariableType;
  placeholder: string;
  example: string;
  required: boolean;
};

export type EmailTemplateOut = {
  id: number;
  name: string;
  slug: string;
  subject_template: string;
  html_content: string;
  email_type: string;
  required_variables: string[];
  category: string;
  is_active: boolean;
  created_at: string;
  /** Phase 7.1: rich per-variable spec from the template's `.meta.yml`,
   * with a synthesized fallback for DB-only templates. May be null when
   * the backend can't determine a spec. */
  variable_spec?: EmailVariableSpec[] | null;
};

export type EmailTemplatesResponse = {
  templates: EmailTemplateOut[];
  total: number;
};

export type EmailTemplateUpsert = {
  name?: string;
  slug?: string;
  subject_template?: string;
  html_content?: string;
  email_type?: string;
  required_variables?: string[];
  category?: string;
  is_active?: boolean;
};

export type EmailTemplatesQuery = {
  active_only?: boolean;
  email_type?: string;
  category?: string;
  search?: string;
};

export function useEmailTemplates(q: EmailTemplatesQuery = {}) {
  const params = new URLSearchParams();
  if (q.active_only) params.set("active_only", "true");
  if (q.email_type) params.set("email_type", q.email_type);
  if (q.category) params.set("category", q.category);
  if (q.search) params.set("search", q.search);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: ["email_templates", q],
    queryFn: () => apiFetch<EmailTemplatesResponse>(`/api/v2/email/templates${qs}`),
    staleTime: 60 * 1000,
  });
}

export function useEmailTemplate(id: number | null) {
  return useQuery({
    queryKey: ["email_templates", "detail", id],
    enabled: id !== null,
    queryFn: () => apiFetch<EmailTemplateOut>(`/api/v2/email/templates/${id}`),
  });
}

export function useCreateEmailTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmailTemplateUpsert) =>
      apiFetch<EmailTemplateOut>("/api/v2/email/templates", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email_templates"] });
    },
  });
}

export function useSaveEmailTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: EmailTemplateUpsert }) =>
      apiFetch<EmailTemplateOut>(`/api/v2/email/templates/${id}/save`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email_templates"] });
    },
  });
}

export function useDeleteEmailTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v2/email/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email_templates"] });
    },
  });
}
