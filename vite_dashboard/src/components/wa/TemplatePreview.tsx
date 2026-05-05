/**
 * <TemplatePreview> — shared green-bubble preview for WhatsApp templates.
 *
 * Used by both the inbox TemplateSheet (style="card") and the Studio
 * TemplateEditor (style="phone"). Owns:
 *   - Variables block: header inputs + body inputs (in declaration order)
 *   - Live preview bubble: header / body / footer / buttons with
 *     placeholders substituted from current variable values.
 *
 * Header media policy (AC-7.5.1, R3):
 *   When `header_format` is IMAGE/VIDEO/DOCUMENT, render a placeholder
 *   block (e.g. "IMAGE header") instead of an <img src={asset_url}>.
 *   Reason: `header_asset_url` from sync is Meta's short-lived CDN
 *   handle and would render as a broken thumbnail once it expires.
 *   Real media rendering waits for stable storage (Phase 8 candidate).
 *
 * Stateless: caller owns headerVariables / bodyVariables and passes
 * change handlers. This keeps the contact-aware prefill in TemplateSheet
 * (the only caller with a contact in scope) and the Studio's "blank +
 * placeholder hint" defaults in TemplateEditor.
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { renderPreview } from "@/lib/wa-template-vars";

type TemplateShape = {
  header_format: string | null | undefined;
  header_text: string | null | undefined;
  header_asset_url: string | null | undefined;
  body_text: string | null | undefined;
  footer_text: string | null | undefined;
  buttons: readonly unknown[] | null | undefined;
};

export type TemplatePreviewStyle = "phone" | "card";

export function TemplatePreview({
  template,
  headerVariables,
  bodyVariables,
  headerVarNames,
  bodyVarNames,
  onHeaderVarsChange,
  onBodyVarsChange,
  showInputs = true,
  style = "card",
  inputIdPrefix = "tpl",
}: {
  template: TemplateShape;
  headerVariables: Record<string, string>;
  bodyVariables: Record<string, string>;
  headerVarNames: string[];
  bodyVarNames: string[];
  onHeaderVarsChange: (next: Record<string, string>) => void;
  onBodyVarsChange: (next: Record<string, string>) => void;
  showInputs?: boolean;
  style?: TemplatePreviewStyle;
  /** Disambiguates input ids when multiple <TemplatePreview>s exist on
   * the same page (unlikely today, but cheap insurance). */
  inputIdPrefix?: string;
}) {
  const totalVars = headerVarNames.length + bodyVarNames.length;
  const isPhone = style === "phone";

  return (
    <div className="flex flex-col gap-3">
      {showInputs && totalVars > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
            Variables ({totalVars})
          </h3>
          <p className="mb-2 text-[11px] text-text-muted">
            Edit any value to override.
          </p>
          <div className="flex flex-col gap-3">
            {headerVarNames.length > 0 && (
              <VarGroup
                label="Header"
                names={headerVarNames}
                values={headerVariables}
                onChange={onHeaderVarsChange}
                idPrefix={`${inputIdPrefix}-hvar`}
              />
            )}
            {bodyVarNames.length > 0 && (
              <VarGroup
                label="Body"
                names={bodyVarNames}
                values={bodyVariables}
                onChange={onBodyVarsChange}
                idPrefix={`${inputIdPrefix}-bvar`}
              />
            )}
          </div>
        </section>
      )}

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">
          Preview
        </h3>
        {isPhone ? (
          <PhoneBubble
            template={template}
            headerVariables={headerVariables}
            bodyVariables={bodyVariables}
          />
        ) : (
          <CardBubble
            template={template}
            headerVariables={headerVariables}
            bodyVariables={bodyVariables}
          />
        )}
      </section>
    </div>
  );
}

function VarGroup({
  label,
  names,
  values,
  onChange,
  idPrefix,
}: {
  label: string;
  names: string[];
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  idPrefix: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </span>
      {names.map((name) => (
        <div key={name} className="flex flex-col gap-1">
          <Label htmlFor={`${idPrefix}-${name}`} className="text-xs text-text-muted">
            {/^\d+$/.test(name) ? `Variable ${name}` : name}
          </Label>
          <Input
            id={`${idPrefix}-${name}`}
            value={values[name] ?? ""}
            onChange={(e) => onChange({ ...values, [name]: e.target.value })}
            placeholder={`{{${name}}}`}
          />
        </div>
      ))}
    </div>
  );
}

function CardBubble({
  template,
  headerVariables,
  bodyVariables,
}: {
  template: TemplateShape;
  headerVariables: Record<string, string>;
  bodyVariables: Record<string, string>;
}) {
  const hasHeaderText = template.header_format === "TEXT" && template.header_text;
  const hasMediaHeader =
    template.header_format === "IMAGE" ||
    template.header_format === "VIDEO" ||
    template.header_format === "DOCUMENT";
  return (
    <div className="rounded-md border border-success/30 bg-success/5 p-3 text-sm text-text whitespace-pre-wrap">
      {hasMediaHeader && <MediaHeaderPlaceholder format={template.header_format} />}
      {hasHeaderText && (
        <div className="mb-2 font-semibold">
          {renderPreview(template.header_text, headerVariables)}
        </div>
      )}
      {template.body_text ? (
        <div>{renderPreview(template.body_text, bodyVariables)}</div>
      ) : (
        <div className="italic text-text-muted">(empty body)</div>
      )}
      {template.footer_text && (
        <div className="mt-2 text-xs italic text-text-muted">
          {template.footer_text}
        </div>
      )}
      <ButtonsList buttons={template.buttons} />
    </div>
  );
}

function PhoneBubble({
  template,
  headerVariables,
  bodyVariables,
}: {
  template: TemplateShape;
  headerVariables: Record<string, string>;
  bodyVariables: Record<string, string>;
}) {
  const hasHeaderText = template.header_format === "TEXT" && template.header_text;
  const hasMediaHeader =
    template.header_format === "IMAGE" ||
    template.header_format === "VIDEO" ||
    template.header_format === "DOCUMENT";
  return (
    <div className="mx-auto flex max-w-[320px] flex-col gap-2 rounded-2xl border border-border bg-[#0b141a] p-3 shadow-lg">
      <div className="flex items-center gap-2 text-xs text-text-subtle">
        <span className="inline-block h-6 w-6 rounded-full bg-success" />
        <span>WhatsApp preview</span>
      </div>
      <div className="rounded-lg rounded-bl-none bg-[#005c4b] p-3 text-sm text-white shadow">
        {hasHeaderText && (
          <p className="mb-1 font-bold">
            {renderPreview(template.header_text, headerVariables)}
          </p>
        )}
        {hasMediaHeader && <MediaHeaderPlaceholder format={template.header_format} />}
        {template.body_text ? (
          <p className="whitespace-pre-wrap break-words leading-snug">
            {renderPreview(template.body_text, bodyVariables)}
          </p>
        ) : (
          <p className="italic text-white/60">(empty body)</p>
        )}
        {template.footer_text && (
          <p className="mt-2 text-[11px] italic text-white/70">{template.footer_text}</p>
        )}
      </div>
      <ButtonsList buttons={template.buttons} variant="phone" />
    </div>
  );
}

function MediaHeaderPlaceholder({ format }: { format: string | null | undefined }) {
  return (
    <div className="mb-2 flex h-24 items-center justify-center rounded-md bg-black/40 text-[10px] uppercase tracking-widest text-white/70">
      {format} header
    </div>
  );
}

function ButtonsList({
  buttons,
  variant = "card",
}: {
  buttons: readonly unknown[] | null | undefined;
  variant?: "card" | "phone";
}) {
  if (!Array.isArray(buttons) || buttons.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1 mt-2">
      {buttons.map((btn, i) => {
        const b = btn as { type?: string; text?: string; url?: string };
        return (
          <li
            key={i}
            className={
              variant === "phone"
                ? "rounded-md border border-border bg-[#1f2c33] px-3 py-1.5 text-center text-xs text-[#53bdeb]"
                : "rounded-md border border-border bg-card/40 px-3 py-1.5 text-center text-xs text-primary"
            }
          >
            {b.text || `Button ${i + 1}`}
            {b.type === "URL" && b.url && (
              <span className="ml-1 opacity-50">↗</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
