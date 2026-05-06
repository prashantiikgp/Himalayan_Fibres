/**
 * <ButtonsEditor> — UI for adding/removing template buttons in the
 * Studio editor (Phase 10.4).
 *
 * Meta supports four button types we expose:
 *   URL          — link with optional {{1}} placeholder
 *   PHONE_NUMBER — tap-to-call
 *   QUICK_REPLY  — sends a predefined reply text back to us
 *   CATALOG      — opens the linked WhatsApp commerce catalog
 *
 * Meta caps (enforced visually, not blocking — Meta will also enforce
 * server-side at template submission):
 *   - max 10 buttons total
 *   - max 3 QUICK_REPLY
 *   - max 2 CTA (URL + PHONE_NUMBER + CATALOG combined)
 *
 * Presets are pre-populated buttons the operator can add with one click.
 * Customised after add by editing the row.
 */

import { useMemo } from "react";
import { Plus, Trash2, Globe, MessageSquare, Phone, ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type ButtonType = "URL" | "PHONE_NUMBER" | "QUICK_REPLY" | "CATALOG";

export type WAButton = {
  type: ButtonType;
  text: string;
  url?: string;
  phone_number?: string;
};

const QUICK_REPLY_MAX = 3;
const CTA_MAX = 2;
const TOTAL_MAX = 10;

type Preset = {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  build: () => WAButton;
};

const FOUNDER_PHONE = "+918582952074";

const PRESETS: Preset[] = [
  {
    key: "website",
    label: "Website",
    icon: Globe,
    build: () => ({
      type: "URL",
      text: "Visit website",
      url: "https://www.himalayanfibres.com/",
    }),
  },
  {
    key: "url-with-var",
    label: "Specific page (with variable)",
    icon: Globe,
    build: () => ({
      type: "URL",
      text: "View product",
      url: "https://www.himalayanfibres.com/{{1}}",
    }),
  },
  {
    key: "samples",
    label: "Send samples",
    icon: MessageSquare,
    build: () => ({ type: "QUICK_REPLY", text: "Send me samples" }),
  },
  {
    key: "more-info",
    label: "Tell me more",
    icon: MessageSquare,
    build: () => ({ type: "QUICK_REPLY", text: "Tell me more" }),
  },
  {
    key: "not-interested",
    label: "Not interested",
    icon: MessageSquare,
    build: () => ({ type: "QUICK_REPLY", text: "Not interested" }),
  },
  {
    key: "catalog",
    label: "View catalog",
    icon: ShoppingBag,
    build: () => ({ type: "CATALOG", text: "View our catalog" }),
  },
  {
    key: "call-founder",
    label: "Call founder",
    icon: Phone,
    build: () => ({
      type: "PHONE_NUMBER",
      text: "Call us",
      phone_number: FOUNDER_PHONE,
    }),
  },
];

export function ButtonsEditor({
  buttons,
  onChange,
}: {
  buttons: readonly WAButton[];
  onChange: (next: WAButton[]) => void;
}) {
  const counts = useMemo(() => countByType(buttons), [buttons]);
  const ctaCount = counts.URL + counts.PHONE_NUMBER + counts.CATALOG;
  const atTotalCap = buttons.length >= TOTAL_MAX;
  const atQuickReplyCap = counts.QUICK_REPLY >= QUICK_REPLY_MAX;
  const atCtaCap = ctaCount >= CTA_MAX;

  function add(button: WAButton) {
    onChange([...buttons, button]);
  }

  function update(index: number, patch: Partial<WAButton>) {
    onChange(buttons.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  }

  function remove(index: number) {
    onChange(buttons.filter((_, i) => i !== index));
  }

  function presetDisabled(p: Preset): boolean {
    if (atTotalCap) return true;
    const sample = p.build();
    if (sample.type === "QUICK_REPLY" && atQuickReplyCap) return true;
    if (sample.type !== "QUICK_REPLY" && atCtaCap) return true;
    // CATALOG is a one-of-a-kind button — disable preset if one already added.
    if (sample.type === "CATALOG" && counts.CATALOG > 0) return true;
    return false;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <Label className="text-xs text-text-muted">
          Buttons ({buttons.length}/{TOTAL_MAX})
        </Label>
        <span className="text-[10px] text-text-subtle">
          QR {counts.QUICK_REPLY}/{QUICK_REPLY_MAX} · CTA {ctaCount}/{CTA_MAX}
        </span>
      </div>

      {/* Preset row */}
      <div className="flex flex-wrap gap-1.5 rounded-md border border-border bg-card/40 p-2">
        <span className="self-center text-[10px] uppercase tracking-wider text-text-muted">
          Add preset:
        </span>
        {PRESETS.map((p) => {
          const Icon = p.icon;
          const disabled = presetDisabled(p);
          return (
            <button
              key={p.key}
              type="button"
              disabled={disabled}
              onClick={() => add(p.build())}
              title={disabled ? "Limit reached for this button type" : `Add: ${p.label}`}
              className={cn(
                "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-[11px] transition-colors",
                "border-border bg-card text-text hover:bg-card/60",
                "disabled:cursor-not-allowed disabled:opacity-40",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
              )}
            >
              <Icon className="h-3 w-3" />
              {p.label}
            </button>
          );
        })}
      </div>

      {/* Buttons list */}
      {buttons.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-3 text-center text-xs text-text-muted">
          No buttons. Click a preset above or "Add custom" below.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {buttons.map((b, i) => (
            <ButtonRow
              key={i}
              button={b}
              onChange={(patch) => update(i, patch)}
              onRemove={() => remove(i)}
            />
          ))}
        </ul>
      )}

      {/* Add-custom row */}
      <div className="flex flex-wrap gap-1.5">
        <CustomAddBtn
          label="+ Custom URL"
          disabled={atTotalCap || atCtaCap}
          onClick={() => add({ type: "URL", text: "", url: "" })}
        />
        <CustomAddBtn
          label="+ Custom Quick Reply"
          disabled={atTotalCap || atQuickReplyCap}
          onClick={() => add({ type: "QUICK_REPLY", text: "" })}
        />
        <CustomAddBtn
          label="+ Custom Phone"
          disabled={atTotalCap || atCtaCap}
          onClick={() => add({ type: "PHONE_NUMBER", text: "", phone_number: "" })}
        />
      </div>
    </div>
  );
}

function CustomAddBtn({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={onClick}
      disabled={disabled}
      className="text-xs"
    >
      <Plus className="mr-1 h-3 w-3" />
      {label.replace("+ ", "")}
    </Button>
  );
}

function ButtonRow({
  button,
  onChange,
  onRemove,
}: {
  button: WAButton;
  onChange: (patch: Partial<WAButton>) => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border bg-card/40 p-2 sm:flex-row sm:items-end">
      <div className="flex flex-1 flex-col gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          {button.type}
        </span>
        <Input
          value={button.text}
          onChange={(e) => onChange({ text: e.target.value })}
          placeholder="Button label"
          maxLength={25}
          className="h-8 text-xs"
        />
      </div>
      {button.type === "URL" && (
        <div className="flex flex-1 flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            URL
          </span>
          <Input
            value={button.url ?? ""}
            onChange={(e) => onChange({ url: e.target.value })}
            placeholder="https://… (use {{1}} for a variable)"
            className="h-8 text-xs"
          />
        </div>
      )}
      {button.type === "PHONE_NUMBER" && (
        <div className="flex flex-1 flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            Phone
          </span>
          <Input
            value={button.phone_number ?? ""}
            onChange={(e) => onChange({ phone_number: e.target.value })}
            placeholder="+919999999999"
            className="h-8 text-xs"
          />
        </div>
      )}
      {button.type === "CATALOG" && (
        <div className="flex flex-1 items-center text-[11px] text-text-muted">
          Opens the linked WhatsApp catalog automatically.
        </div>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={onRemove}
        className="self-start sm:self-end"
        title="Remove button"
      >
        <Trash2 className="h-3 w-3" />
      </Button>
    </li>
  );
}

function countByType(buttons: readonly WAButton[]): Record<ButtonType, number> {
  const out: Record<ButtonType, number> = {
    URL: 0,
    PHONE_NUMBER: 0,
    QUICK_REPLY: 0,
    CATALOG: 0,
  };
  for (const b of buttons) {
    if (b.type in out) out[b.type] += 1;
  }
  return out;
}
