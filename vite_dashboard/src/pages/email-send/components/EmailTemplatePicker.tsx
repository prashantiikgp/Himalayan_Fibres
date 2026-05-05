/**
 * <EmailTemplatePicker> — `<select>` over active email templates.
 *
 * Same shape as the WA Inbox TemplateSheet picker but for email templates.
 * Phase 7.1 (Day_4_improvememt/PLAN_email.md).
 */

import { Label } from "@/components/ui/label";
import {
  useEmailTemplates,
  type EmailTemplateOut,
} from "@/api/email_templates";

export function EmailTemplatePicker({
  value,
  onChange,
  id = "email-template-picker",
  label = "Template",
}: {
  value: number | null;
  onChange: (id: number | null, tpl: EmailTemplateOut | null) => void;
  id?: string;
  label?: string;
}) {
  const { data, isLoading, error } = useEmailTemplates({ active_only: true });
  const templates = data?.templates ?? [];

  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          if (!v) {
            onChange(null, null);
            return;
          }
          const num = Number(v);
          const tpl = templates.find((t) => t.id === num) ?? null;
          onChange(num, tpl);
        }}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text"
        disabled={isLoading || !!error}
      >
        <option value="">
          {isLoading
            ? "Loading templates…"
            : error
              ? "Failed to load templates"
              : "— Pick a template —"}
        </option>
        {templates.map((t) => {
          const varCount = t.required_variables.length;
          return (
            <option key={t.id} value={t.id}>
              {t.name} ({t.email_type}, {varCount} var{varCount === 1 ? "" : "s"})
            </option>
          );
        })}
      </select>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error.message}
        </p>
      )}
    </div>
  );
}
