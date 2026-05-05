/**
 * <EmailVariablesForm> — typed input list driven by EmailTemplateOut.variable_spec.
 *
 * Modes:
 *   - "single"    — Send Email page. Auto-prefilled from the picked contact
 *                   (handled server-side by build_send_variables); auto-resolved
 *                   names are NOT hidden because the founder may want to tweak
 *                   them per send.
 *   - "broadcast" — ComposeTab email branch. Per-recipient AUTO_RESOLVED names
 *                   are filtered out — they vary per recipient and the server
 *                   resolves them from the contact in build_send_variables.
 *   - "studio"    — EmailTemplateEditor. No contact context; defaults come from
 *                   YAML `example` values so the preview reads naturally.
 *
 * Phase 7.1 (Day_4_improvememt/PLAN_email.md).
 */

import { useEffect, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { EmailVariableSpec } from "@/api/email_templates";

export type EmailVariablesFormMode = "single" | "broadcast" | "studio";

export const AUTO_RESOLVED_VAR_NAMES = [
  "first_name",
  "last_name",
  "name",
  "email",
  "contact_company",
] as const;

function isAutoResolved(name: string): boolean {
  return (AUTO_RESOLVED_VAR_NAMES as readonly string[]).includes(name);
}

function defaultValueFor(spec: EmailVariableSpec, mode: EmailVariablesFormMode): string {
  // In broadcast mode AUTO_RESOLVED vars are stripped; in single+studio we
  // surface example values so the preview pane has something to render.
  if (mode === "broadcast" && isAutoResolved(spec.name)) return "";
  return spec.example || "";
}

export function visibleVariables(
  spec: EmailVariableSpec[] | null | undefined,
  mode: EmailVariablesFormMode,
): EmailVariableSpec[] {
  if (!spec) return [];
  if (mode === "broadcast") {
    return spec.filter((s) => !isAutoResolved(s.name));
  }
  return spec;
}

export function requiredVariableNames(
  spec: EmailVariableSpec[] | null | undefined,
  mode: EmailVariablesFormMode,
): string[] {
  return visibleVariables(spec, mode)
    .filter((s) => s.required)
    .map((s) => s.name);
}

export function buildDefaultValues(
  spec: EmailVariableSpec[] | null | undefined,
  mode: EmailVariablesFormMode,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of visibleVariables(spec, mode)) {
    out[s.name] = defaultValueFor(s, mode);
  }
  return out;
}

export function EmailVariablesForm({
  spec,
  values,
  onChange,
  mode,
  disabled,
}: {
  spec: EmailVariableSpec[] | null | undefined;
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  mode: EmailVariablesFormMode;
  disabled?: boolean;
}) {
  const visible = useMemo(() => visibleVariables(spec, mode), [spec, mode]);

  // Seed defaults whenever the spec or mode changes (template switched).
  // We only fill in values for vars the parent hasn't set; existing keys
  // stay so the user's edits aren't clobbered.
  useEffect(() => {
    if (visible.length === 0) return;
    const defaults = buildDefaultValues(spec, mode);
    let mutated = false;
    const merged = { ...values };
    for (const [k, v] of Object.entries(defaults)) {
      if (!(k in merged) || merged[k] === undefined) {
        merged[k] = v;
        mutated = true;
      }
    }
    if (mutated) onChange(merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, mode]);

  if (!spec) {
    return (
      <p className="text-xs text-text-muted">Loading variable spec…</p>
    );
  }
  if (visible.length === 0) {
    return (
      <p className="text-xs text-text-muted">
        (no declared variables — preview will use empty values)
      </p>
    );
  }

  function set(name: string, v: string) {
    onChange({ ...values, [name]: v });
  }

  return (
    <div className="flex flex-col gap-3">
      {visible.map((v) => {
        const id = `email-var-${v.name}`;
        const value = values[v.name] ?? "";
        const label = v.label || v.name;
        return (
          <div key={v.name} className="flex flex-col gap-1">
            <Label htmlFor={id} className="text-xs text-text-muted">
              {label}
              {v.required && (
                <span className="ml-1 text-danger" aria-hidden="true">
                  *
                </span>
              )}
              <span className="ml-2 font-mono text-[10px] text-text-muted/70">
                {`{{${v.name}}}`}
              </span>
            </Label>
            {v.type === "textarea" ? (
              <textarea
                id={id}
                value={value}
                onChange={(e) => set(v.name, e.target.value)}
                placeholder={v.placeholder}
                rows={3}
                disabled={disabled}
                className="rounded-md border border-border bg-card p-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
              />
            ) : (
              <Input
                id={id}
                type={v.type === "date" ? "date" : v.type === "url" ? "url" : "text"}
                value={value}
                onChange={(e) => set(v.name, e.target.value)}
                placeholder={v.placeholder}
                disabled={disabled}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
