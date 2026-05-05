/**
 * kpiEngine tests (review fix M3) — verify hydration math + lookup.
 */

import { describe, it, expect, beforeAll } from "vitest";
import { configLoader } from "@/loaders/configLoader";
import { kpiEngine } from "./kpiEngine";

beforeAll(() => {
  configLoader.bootstrap();
});

describe("kpiEngine.hydrate", () => {
  it("formats with target as 'value / target'", () => {
    const tiles = kpiEngine.hydrate(["emails_today"], { emails_today: 12 });
    expect(tiles).toHaveLength(1);
    expect(tiles[0]?.value).toBe("12 / 500");
  });

  it("formats without target as plain value", () => {
    const tiles = kpiEngine.hydrate(["total_contacts"], { total: 1574 });
    expect(tiles[0]?.value).toBe("1574");
  });

  it("treats missing data as 0", () => {
    const tiles = kpiEngine.hydrate(["opted_in"], {});
    expect(tiles[0]?.value).toBe("0");
  });

  it("returns tiles in the requested order", () => {
    const tiles = kpiEngine.hydrate(
      ["wa_today", "emails_today"],
      { emails_today: 1, wa_today: 2 },
    );
    expect(tiles.map((t) => t.id)).toEqual(["wa_today", "emails_today"]);
  });
});

describe("kpiEngine.getDefinition", () => {
  it("looks up a known KPI by id", () => {
    const def = kpiEngine.getDefinition("emails_today");
    expect(def.label).toBe("Emails Today");
    expect(def.target).toBe(500);
    expect(def.api_field).toBe("emails_today");
  });

  it("throws on unknown KPI id", () => {
    expect(() => kpiEngine.getDefinition("does_not_exist")).toThrow();
  });
});
