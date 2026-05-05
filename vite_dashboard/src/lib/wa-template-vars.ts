/**
 * Pure helpers for WhatsApp template placeholder handling. Shared by
 * the inbox TemplateSheet and the Studio TemplatePreview so the regex,
 * preview substitution, and contact-aware prefill logic don't drift.
 *
 * Framework-agnostic — no React imports — so tests can call them
 * directly.
 */

const PLACEHOLDER_RE = /\{\{\s*([\w]+)\s*\}\}/g;

/**
 * Return the placeholder names found in `text`, in first-appearance
 * order, deduplicated. Matches `{{1}}`, `{{name}}`, `{{ first_name }}`.
 */
export function extractPlaceholders(text: string | null | undefined): string[] {
  if (!text) return [];
  const found: string[] = [];
  // Reset lastIndex defensively — PLACEHOLDER_RE is module-scoped + /g.
  PLACEHOLDER_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = PLACEHOLDER_RE.exec(text)) !== null) {
    const name = m[1];
    if (name && !found.includes(name)) found.push(name);
  }
  return found;
}

/**
 * Substitute `{{varName}}` placeholders in `text` with values from
 * `vars`. Empty/whitespace values fall back to the literal `{{varName}}`
 * so the operator can see what's still unfilled.
 */
export function renderPreview(
  text: string | null | undefined,
  vars: Record<string, string>,
): string {
  if (!text) return "";
  return text.replace(/\{\{\s*([\w]+)\s*\}\}/g, (_match, name: string) => {
    const v = (vars[name] ?? "").trim();
    return v || `{{${name}}}`;
  });
}

/**
 * Mirror of hf_dashboard/services/broadcast_engine.py::_resolve_wa_variable
 * — picks the value the broadcast engine would inject for a given
 * placeholder name, given a contact context. Used to pre-fill variable
 * inputs in the TemplateSheet so the operator only edits overrides.
 *
 * Studio editor passes `contact = null` (no contact in scope) and
 * receives an empty string for every name, which the input renders as
 * a `{{varName}}` placeholder.
 */
export function resolveVariableForContact(
  varName: string,
  contact: { contact_name?: string; contact_company?: string | null } | null,
): string {
  const fullName = (contact?.contact_name || "").trim();
  const company = (contact?.contact_company || "").trim();
  const firstName = fullName.split(/\s+/)[0] || "";
  const map: Record<string, string> = {
    customer_name: fullName || company || "Customer",
    first_name: firstName || fullName || "Customer",
    name: fullName || "Customer",
    company_name: company || fullName || "your company",
    "1": fullName || firstName || "Customer",
    "2": company || "—",
  };
  return map[varName] ?? "";
}
