/**
 * <ContactsFilterBar> — left-column filter sidebar.
 *
 * Reads the filter spec list from the contacts page YAML
 * (filters: [segment, lifecycle, country, channel, tags, search]) and
 * resolves them via filterEngine. Choice data comes from /api/v2/segments,
 * /api/v2/contacts/countries, /api/v2/contacts/tags.
 */

import { useSegments, useContactCountries, useContactTags } from "@/api/contacts";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type ContactFilters = {
  segment: string;
  lifecycle: string;
  country: string;
  channel: "all" | "email" | "whatsapp" | "both";
  search: string;
};

export const DEFAULT_FILTERS: ContactFilters = {
  segment: "all",
  lifecycle: "all",
  country: "all",
  channel: "all",
  search: "",
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
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
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
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
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
        <NativeSelect
          label="Segment"
          value={value.segment}
          options={segmentOptions}
          onChange={(v) => onChange({ segment: v })}
        />
        <NativeSelect
          label="Lifecycle"
          value={value.lifecycle}
          options={LIFECYCLES}
          onChange={(v) => onChange({ lifecycle: v })}
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
