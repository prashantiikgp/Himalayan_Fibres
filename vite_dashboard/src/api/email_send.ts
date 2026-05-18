/**
 * /api/v2/email/render-preview + /test-sends hooks (Phase 7.1).
 *
 * Lives in its own file (not email_templates.ts) because these are
 * runtime-send concerns, not template CRUD.
 */

import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { getToken } from "@/lib/auth";
import { apiBase } from "@/lib/env";
import { ApiError } from "@/lib/queryClient";

export type AttachmentRef = {
  url: string;
  file_name: string;
  content_type: string;
  kind: string;
  size: number;
};

/** Multipart upload — bypasses apiFetch (which forces JSON content-type);
 * the browser sets the multipart boundary itself. */
export function useUploadAttachment() {
  return useMutation({
    mutationFn: async (args: { file: File; kind: string }) => {
      const fd = new FormData();
      fd.append("file", args.file);
      fd.append("kind", args.kind);
      const token = getToken();
      const res = await fetch(`${apiBase()}/api/v2/email/attachments`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new ApiError(res.status, body, "/api/v2/email/attachments");
      }
      return (await res.json()) as AttachmentRef;
    },
  });
}

export type RenderPreviewBody = {
  template_id: number;
  variables: Record<string, string>;
  contact_id?: string | null;
  html_content_override?: string | null;
  subject_template_override?: string | null;
  attachments?: AttachmentRef[];
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
  attachments?: AttachmentRef[];
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
