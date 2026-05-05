/**
 * toQueryString — covers the chip → API contract introduced in B3
 * (Needs follow-up filter). Drives `lifecycles[]` expansion + override
 * of the single-value `lifecycle` form.
 */

import { describe, it, expect } from "vitest";
import { toQueryString } from "./contacts";

describe("toQueryString", () => {
  it("emits no params for the all-defaults query", () => {
    expect(toQueryString({})).toBe("");
    expect(toQueryString({ segment: "all", lifecycle: "all", country: "all", channel: "all" }))
      .toBe("");
  });

  it("emits a single ?lifecycle=x for the legacy single-value form", () => {
    expect(toQueryString({ lifecycle: "interested" })).toBe("?lifecycle=interested");
  });

  it("expands lifecycles[] into repeated lifecycle params (Needs-follow-up chip)", () => {
    const qs = toQueryString({ lifecycles: ["contacted", "interested"] });
    // URLSearchParams keeps insertion order; assert both pairs appear.
    expect(qs).toBe("?lifecycle=contacted&lifecycle=interested");
  });

  it("lifecycles[] takes precedence over the single-value lifecycle", () => {
    const qs = toQueryString({
      lifecycle: "customer",
      lifecycles: ["contacted", "interested"],
    });
    expect(qs).toContain("lifecycle=contacted");
    expect(qs).toContain("lifecycle=interested");
    expect(qs).not.toContain("lifecycle=customer");
  });

  it("treats empty lifecycles[] as no-op (falls through to lifecycle)", () => {
    expect(toQueryString({ lifecycle: "interested", lifecycles: [] }))
      .toBe("?lifecycle=interested");
  });

  it("filters out segment=all and channel=all sentinel values", () => {
    expect(toQueryString({ segment: "all", channel: "all", lifecycle: "interested" }))
      .toBe("?lifecycle=interested");
  });

  it("repeats tags[] for multi-tag filtering", () => {
    const qs = toQueryString({ tags: ["vip", "priority"] });
    expect(qs).toContain("tags=vip");
    expect(qs).toContain("tags=priority");
  });

  it("URL-encodes search terms with special characters", () => {
    expect(toQueryString({ search: "M&S" })).toBe("?search=M%26S");
  });

  it("emits page=0 explicitly when set, since 0 is meaningful", () => {
    expect(toQueryString({ page: 0 })).toBe("?page=0");
  });
});
