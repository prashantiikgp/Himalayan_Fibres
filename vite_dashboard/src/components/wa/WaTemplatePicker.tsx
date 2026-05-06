/**
 * <WaTemplatePicker> — shared template picker for the WA inbox sheet
 * AND the broadcast Compose tab (Phase 8.2).
 *
 * Two pill rows (Type / Intent) + debounced search + a clickable list.
 * Pure-state component: caller owns `value` and `onChange`. Internal
 * state is filter UI only.
 *
 * Density:
 *   - "list"    → spacious rows with body preview (broadcasts page)
 *   - "compact" → 48px rows, no body preview (inbox sheet, narrow)
 *
 * Selection rules (per plan D4):
 *   - Click a pill that hides the current selection → keep selection,
 *     show "current selection is hidden" hint above the list.
 *   - Click the already-selected row → onChange(null) (re-click clears).
 */

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useWaTemplates, useTemplateRegistry } from "@/api/wa";
import {
  joinWithRegistry,
  filterByCategory,
  filterByIntent,
  filterBySearch,
  availableIntents,
  type CategoryFilter,
  type EnrichedTemplate,
} from "@/lib/wa-template-filters";

type Density = "list" | "compact";
type StatusFilter = "APPROVED" | "PENDING" | "ALL";

export function WaTemplatePicker({
  value,
  onChange,
  status = "APPROVED",
  density = "list",
  excludePrefixes,
}: {
  value: string | null;
  onChange: (name: string | null) => void;
  status?: StatusFilter;
  density?: Density;
  excludePrefixes?: readonly string[];
}) {
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("ALL");
  const [intentFilter, setIntentFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 200);

  const { data: tplData, isLoading: tplLoading, error: tplError } = useWaTemplates({
    status: status === "ALL" ? undefined : status,
  });
  const { data: regData } = useTemplateRegistry();

  const enriched: EnrichedTemplate[] = useMemo(() => {
    const rows = joinWithRegistry(tplData?.templates ?? [], regData?.entries ?? []);
    if (!excludePrefixes || excludePrefixes.length === 0) return rows;
    return rows.filter((r) => !excludePrefixes.some((p) => r.name.startsWith(p)));
  }, [tplData, regData, excludePrefixes]);

  // After Type filter: drives both Intent-pill availability AND the list.
  const afterCategory = useMemo(
    () => filterByCategory(enriched, categoryFilter),
    [enriched, categoryFilter],
  );
  const intentLabels = useMemo(() => availableIntents(afterCategory), [afterCategory]);
  const afterIntent = useMemo(
    () => filterByIntent(afterCategory, intentFilter),
    [afterCategory, intentFilter],
  );
  const visible = useMemo(
    () => filterBySearch(afterIntent, debouncedSearch),
    [afterIntent, debouncedSearch],
  );

  // Has the selection been filtered out? (Selection is preserved per D4.)
  const selectionHidden = useMemo(() => {
    if (!value) return false;
    return !visible.some((t) => t.name === value);
  }, [value, visible]);

  const showAuthCategory = useMemo(
    () => enriched.some((t) => (t.category ?? "").toUpperCase() === "AUTHENTICATION"),
    [enriched],
  );

  function clearAllFilters() {
    setCategoryFilter("ALL");
    setIntentFilter("ALL");
    setSearch("");
  }

  return (
    <div className="flex flex-col gap-2">
      <PillRow label="Type">
        <Pill active={categoryFilter === "ALL"} onClick={() => setCategoryFilter("ALL")}>
          All
        </Pill>
        <Pill active={categoryFilter === "MARKETING"} onClick={() => setCategoryFilter("MARKETING")}>
          Marketing
        </Pill>
        <Pill active={categoryFilter === "UTILITY"} onClick={() => setCategoryFilter("UTILITY")}>
          Utility
        </Pill>
        {showAuthCategory && (
          <Pill
            active={categoryFilter === "AUTHENTICATION"}
            onClick={() => setCategoryFilter("AUTHENTICATION")}
          >
            Auth
          </Pill>
        )}
      </PillRow>

      {intentLabels.length > 0 && (
        <PillRow label="Intent">
          <Pill active={intentFilter === "ALL"} onClick={() => setIntentFilter("ALL")}>
            All
          </Pill>
          {intentLabels.map((label) => (
            <Pill
              key={label}
              active={intentFilter === label}
              onClick={() => setIntentFilter(label)}
            >
              {label}
            </Pill>
          ))}
        </PillRow>
      )}

      <div className="relative">
        <Search className="absolute left-2 top-2.5 h-4 w-4 text-text-muted" aria-hidden="true" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search templates by name or body…"
          className="pl-8"
          aria-label="Search templates"
        />
      </div>

      {selectionHidden && (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-2 py-1 text-[11px] text-warning">
          Current selection is hidden by filters.{" "}
          <button
            type="button"
            onClick={clearAllFilters}
            className="underline underline-offset-2 hover:text-warning/80"
          >
            Clear filters
          </button>
        </div>
      )}

      <ul
        role="listbox"
        aria-label="Templates"
        className="flex max-h-[60vh] flex-col overflow-auto rounded-md border border-border bg-card/40"
      >
        {tplLoading && (
          <li className="p-card text-sm text-text-muted">Loading templates…</li>
        )}
        {tplError && (
          <li className="p-card text-sm text-danger" role="alert">
            {tplError instanceof Error ? tplError.message : "Failed to load templates"}
          </li>
        )}
        {!tplLoading && !tplError && visible.length === 0 && (
          <li className="p-card text-sm text-text-muted">
            No templates match. Try clearing filters.
          </li>
        )}
        {visible.map((t) => (
          <TemplatePickerRow
            key={t.id}
            template={t}
            selected={t.name === value}
            density={density}
            onPick={() => onChange(t.name === value ? null : t.name)}
          />
        ))}
      </ul>
    </div>
  );
}

function PillRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-pill border px-2.5 py-0.5 text-xs font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        active
          ? "border-primary bg-primary text-white"
          : "border-border bg-card text-text hover:bg-card/60",
      )}
    >
      {children}
    </button>
  );
}

function TemplatePickerRow({
  template,
  selected,
  density,
  onPick,
}: {
  template: EnrichedTemplate;
  selected: boolean;
  density: Density;
  onPick: () => void;
}) {
  const compact = density === "compact";
  const cat = (template.category ?? "?").toUpperCase();
  const catBadge = cat === "MARKETING" ? "MKT" : cat === "UTILITY" ? "UTL" : cat.slice(0, 3);
  const varCount = template.variables?.length ?? 0;
  const bodyPreview = (template.body_text || "").trim().replace(/\s+/g, " ");

  return (
    <li
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onClick={onPick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick();
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-0.5 border-b border-border/40 px-card transition-colors",
        compact ? "py-2" : "py-3",
        selected ? "bg-primary/10 ring-1 ring-inset ring-primary" : "hover:bg-card/60",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-text">
          {template.display_name}
          {template.display_name !== template.name && (
            <span className="ml-1 text-[10px] font-normal text-text-subtle">
              ({template.name})
            </span>
          )}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Badge tone="neutral">{catBadge}</Badge>
          <Badge tone="info">{template.intent_label}</Badge>
          <Badge tone="subtle">{varCount} var{varCount === 1 ? "" : "s"}</Badge>
        </div>
      </div>
      {!compact && bodyPreview && (
        <span className="truncate text-xs text-text-subtle">
          {bodyPreview.slice(0, 80)}
          {bodyPreview.length > 80 ? "…" : ""}
        </span>
      )}
    </li>
  );
}

function Badge({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "neutral" | "info" | "subtle";
}) {
  const palette = {
    neutral: "bg-card text-text-muted",
    info: "bg-primary/15 text-primary",
    subtle: "bg-card/60 text-text-subtle",
  }[tone];
  return (
    <span className={cn("rounded-pill px-1.5 py-0.5 text-[10px]", palette)}>
      {children}
    </span>
  );
}
