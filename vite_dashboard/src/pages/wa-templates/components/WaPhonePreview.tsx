/**
 * <WaPhonePreview> — minimal phone-style render of a WA template.
 *
 * Mirrors the chat bubble layout of the WhatsApp app: header (text or
 * media placeholder) → body → footer → buttons. Variables are shown
 * as `{{name}}` literals; the variables form previews substitution
 * separately. Phase 4.1b will add live substitution with the form
 * values bubbling into this preview.
 */

import type { WATemplateOut } from "@/api/wa";

export function WaPhonePreview({
  template,
}: {
  template: Pick<
    WATemplateOut,
    "header_format" | "header_text" | "header_asset_url" | "body_text" | "footer_text" | "buttons"
  >;
}) {
  return (
    <div className="mx-auto flex max-w-[320px] flex-col gap-2 rounded-2xl border border-border bg-[#0b141a] p-3 shadow-lg">
      <div className="flex items-center gap-2 text-xs text-text-subtle">
        <span className="inline-block h-6 w-6 rounded-full bg-success" />
        <span>WhatsApp preview</span>
      </div>
      <div className="rounded-lg rounded-bl-none bg-[#005c4b] p-3 text-sm text-white shadow">
        {template.header_format === "TEXT" && template.header_text && (
          <p className="mb-1 font-bold">{template.header_text}</p>
        )}
        {(template.header_format === "IMAGE" ||
          template.header_format === "DOCUMENT" ||
          template.header_format === "VIDEO") && (
          <div className="mb-2 flex h-24 items-center justify-center rounded-md bg-black/40 text-[10px] uppercase tracking-widest">
            {template.header_format} header
          </div>
        )}
        {template.body_text ? (
          <p className="whitespace-pre-wrap break-words leading-snug">{template.body_text}</p>
        ) : (
          <p className="italic text-white/60">(empty body)</p>
        )}
        {template.footer_text && (
          <p className="mt-2 text-[11px] italic text-white/70">{template.footer_text}</p>
        )}
      </div>
      {Array.isArray(template.buttons) && template.buttons.length > 0 && (
        <ul className="flex flex-col gap-1">
          {template.buttons.map((btn, i) => {
            const b = btn as { type?: string; text?: string; url?: string };
            return (
              <li
                key={i}
                className="rounded-md border border-border bg-[#1f2c33] px-3 py-1.5 text-center text-xs text-[#53bdeb]"
              >
                {b.text || `Button ${i + 1}`}
                {b.type === "URL" && b.url && (
                  <span className="ml-1 text-white/40">↗</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
