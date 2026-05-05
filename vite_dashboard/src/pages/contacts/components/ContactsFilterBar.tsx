/**
 * <ContactsFilterBar> — left-column filter sidebar.
 *
 * Reads the filter spec list from the contacts page YAML
 * (filters: [segment, lifecycle, country, channel, tags, search]) and
 * resolves them via filterEngine. Choice data comes from /api/v2/segments,
 * /api/v2/contacts/countries, /api/v2/contacts/tags.
 */

import { useSegments, useContactCountries, useContactTags } from "@/api/contacts";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type ContactFilters = {
  segment: string;
  lifecycle: string;
  country: string;
  channel: "all" | "email" | "whatsapp" | "both";
  search: string;
  /**
   * Quick-toggle for the "Needs follow-up" cohort = lifecycle in
   * [contacted, interested]. Takes precedence over the single-select
   * lifecycle dropdown when on. The dropdown is disabled while active.
   */
  needsFollowup: boolean;
};

/** Multi-value lifecycle filter expanded for the "Needs follow-up" chip. */
export const NEEDS_FOLLOWUP_LIFECYCLES = ["contacted", "interested"] as const;

export const DEFAULT_FILTERS: ContactFilters = {
  segment: "all",
  lifecycle: "all",
  country: "all",
  channel: "all",
  search: "",
  needsFollowup: false,
};

const LIFECYCLES = [
  { value: "all", label: "All lifecycles" },
  { value: "new_lead", label: "New Lead" },
  { value: "contacted", label: "Contacted" },
  { value: "interested", label: "Interested" },
  { value: "customer", label: "Customer" },
  { value: "churned", label: "Churned" },
];

const CHANNELS = [
  { value: "all", label: "All channels" },
  { value: "email", label: "Email only" },
  { value: "whatsapp", label: "WhatsApp only" },
  { value: "both", label: "Both" },
];

function NativeSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const id = `filter-${label.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ContactsFilterBar({
  value,
  onChange,
}: {
  value: ContactFilters;
  onChange: (next: Partial<ContactFilters>) => void;
}) {
  const segments = useSegments();
  const countries = useContactCountries();
  // Tags fetched but not yet rendered in this iteration (multi-select needs
  // a real combobox UI; ships in a follow-up commit).
  useContactTags();

  const segmentOptions = [
    { value: "all", label: "All segments" },
    ...(segments.data?.segments.map((s) => ({
      value: s.id,
      label: `${s.name} · ${s.member_count}`,
    })) ?? []),
  ];

  const countryOptions = [
    { value: "all", label: "All countries" },
    ...(countries.data?.countries.map((c) => ({ value: c, label: c })) ?? []),
  ];

  return (
    <Card className="w-full md:w-64 md:shrink-0">
      <CardHeader>
        <CardTitle>Filters</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="filter-search" className="text-xs text-text-muted">
            Search
          </Label>
          <Input
            id="filter-search"
            placeholder="Name, company, email…"
            value={value.search}
            onChange={(e) => onChange({ search: e.target.value })}
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant={value.needsFollowup ? "default" : "outline"}
          onClick={() => onChange({ needsFollowup: !value.needsFollowup })}
          className="h-8 self-start text-xs"
          aria-pressed={value.needsFollowup}
        >
          🔥 Needs follow-up
        </Button>
        <NativeSelect
          label="Segment"
          value={value.segment}
          options={segmentOptions}
          onChange={(v) => onChange({ segment: v })}
        />
        <NativeSelect
          label={value.needsFollowup ? "Lifecycle (overridden)" : "Lifecycle"}
          value={value.needsFollowup ? "all" : value.lifecycle}
          options={LIFECYCLES}
          onChange={(v) => onChange({ lifecycle: v })}
          disabled={value.needsFollowup}
        />
        <NativeSelect
          label="Country"
          value={value.country}
          options={countryOptions}
          onChange={(v) => onChange({ country: v })}
        />
        <NativeSelect
          label="Channel"
          value={value.channel}
          options={CHANNELS}
          onChange={(v) => onChange({ channel: v as ContactFilters["channel"] })}
        />
      </CardContent>
    </Card>
  );
}
