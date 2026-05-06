/**
 * Phase 8.2 — pure filter helpers for the WaTemplatePicker.
 */

import { describe, it, expect } from "vitest";
import type { TemplateRegistryEntry, WATemplateOut } from "@/api/wa";
import {
  joinWithRegistry,
  filterByCategory,
  filterByIntent,
  filterBySearch,
  availableIntents,
} from "./wa-template-filters";

function tpl(over: Partial<WATemplateOut>): WATemplateOut {
  return {
    id: 1,
    name: "x",
    language: "en_US",
    category: "MARKETING",
    status: "APPROVED",
    body_text: "",
    header_format: null,
    header_asset_url: null,
    header_text: null,
    footer_text: null,
    variables: [],
    is_draft: false,
    tier: "company",
    rejection_reason: "",
    submitted_at: null,
    quality_score: null,
    buttons: [],
    ...over,
  };
}

function reg(name: string, use_case: string, intent_label: string, display_name = name): TemplateRegistryEntry {
  return { name, display_name, description: "", use_case, intent_label, category: "", notes: "" };
}

describe("joinWithRegistry", () => {
  it("attaches intent_label and display_name from the registry", () => {
    const out = joinWithRegistry(
      [tpl({ id: 1, name: "welcome_message", body_text: "Hi" })],
      [reg("welcome_message", "onboarding", "Intro", "Welcome Message")],
    );
    expect(out).toHaveLength(1);
    expect(out[0]?.intent_label).toBe("Intro");
    expect(out[0]?.display_name).toBe("Welcome Message");
  });

  it("falls back to 'Other' and the raw name when the template is missing from registry", () => {
    const out = joinWithRegistry([tpl({ id: 2, name: "rogue_template" })], []);
    expect(out).toHaveLength(1);
    expect(out[0]?.intent_label).toBe("Other");
    expect(out[0]?.display_name).toBe("rogue_template");
  });
});

describe("filterByCategory", () => {
  const rows = [
    tpl({ id: 1, category: "MARKETING" }),
    tpl({ id: 2, category: "UTILITY" }),
    tpl({ id: 3, category: null }),
  ];
  it("ALL returns everything", () => {
    expect(filterByCategory(rows, "ALL")).toHaveLength(3);
  });
  it("filters by exact uppercased value", () => {
    expect(filterByCategory(rows, "MARKETING").map((r) => r.id)).toEqual([1]);
    expect(filterByCategory(rows, "UTILITY").map((r) => r.id)).toEqual([2]);
  });
  it("treats null category as not matching", () => {
    expect(filterByCategory(rows, "MARKETING")).toHaveLength(1);
  });
});

describe("filterByIntent", () => {
  const rows = [
    { id: 1, intent_label: "Intro" },
    { id: 2, intent_label: "Order" },
    { id: 3, intent_label: "Other" },
  ];
  it("ALL returns everything", () => {
    expect(filterByIntent(rows, "ALL")).toHaveLength(3);
  });
  it("matches exact label", () => {
    expect(filterByIntent(rows, "Order").map((r) => r.id)).toEqual([2]);
  });
});

describe("filterBySearch", () => {
  const rows = [
    tpl({ id: 1, name: "welcome_message", body_text: "Hello there" }),
    tpl({ id: 2, name: "order_confirmation", body_text: "Your order is ready" }),
    tpl({ id: 3, name: "b2b_intro", body_text: "Reaching out about fibre" }),
  ];
  it("empty search returns everything", () => {
    expect(filterBySearch(rows, "")).toHaveLength(3);
    expect(filterBySearch(rows, "   ")).toHaveLength(3);
  });
  it("matches against name", () => {
    expect(filterBySearch(rows, "welcome").map((r) => r.id)).toEqual([1]);
  });
  it("matches against body_text", () => {
    expect(filterBySearch(rows, "fibre").map((r) => r.id)).toEqual([3]);
  });
  it("is case-insensitive", () => {
    expect(filterBySearch(rows, "ORDER")).toHaveLength(1);
  });
});

describe("availableIntents", () => {
  it("returns labels in canonical order", () => {
    const rows = [
      { intent_label: "Other" },
      { intent_label: "Order" },
      { intent_label: "Intro" },
    ];
    expect(availableIntents(rows)).toEqual(["Intro", "Order", "Other"]);
  });
  it("dedupes", () => {
    const rows = [
      { intent_label: "Intro" },
      { intent_label: "Intro" },
    ];
    expect(availableIntents(rows)).toEqual(["Intro"]);
  });
  it("returns empty when no rows", () => {
    expect(availableIntents([])).toEqual([]);
  });
});
