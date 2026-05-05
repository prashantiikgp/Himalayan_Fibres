/**
 * /api/v2/email/render-preview + /test-sends hooks (Phase 7.1).
 *
 * Lives in its own file (not email_templates.ts) because these are
 * runtime-send concerns, not template CRUD.
 */

import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "./client";

export type RenderPreviewBody = {
  template_id: number;
  variables: Record<string, string>;
  contact_id?: string | null;
  html_content_override?: string | null;
  subject_template_override?: string | null;
};

export type RenderPreviewResponse = {
  html: string;
  subject: string;
};

export function useRenderEmailPreview() {
  return useMutation({
    mutationFn: (body: RenderPreviewBody) =>
      apiFetch<RenderPreviewResponse>("/api/v2/email/render-preview", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export type SendOneEmailBody = {
  template_id: number;
  contact_id: string;
  variables: Record<string, string>;
  subject_override?: string | null;
};

export type SendOneEmailResponse = {
  success: boolean;
  message: string;
  email_send_id: number | null;
};

export function useSendOneEmail() {
  return useMutation({
    mutationFn: (body: SendOneEmailBody) =>
      apiFetch<SendOneEmailResponse>("/api/v2/email/test-sends", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
