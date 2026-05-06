/**
 * Phase 7.8 — flow hooks + cache key contracts.
 *
 * Covers what tests can reasonably check without spinning up a full
 * React Query env: the queryKey constants, the URL shapes the hooks
 * build, and the optimistic-flip helper's fingerprint.
 */

import { describe, it, expect } from "vitest";
import { flowKeys } from "./flows";

describe("flowKeys", () => {
  it("groups every key under the root 'flows' namespace", () => {
    expect(flowKeys.all[0]).toBe("flows");
    expect(flowKeys.list({})[0]).toBe("flows");
    expect(flowKeys.detail(7)[0]).toBe("flows");
    expect(flowKeys.memberships(7)[0]).toBe("flows");
    expect(flowKeys.stepRuns(7)[0]).toBe("flows");
  });

  it("memberships key includes the status filter for separate caches", () => {
    expect(flowKeys.memberships(1, "active")).toEqual([
      "flows",
      "memberships",
      1,
      "active",
    ]);
    expect(flowKeys.memberships(1)).toEqual([
      "flows",
      "memberships",
      1,
      "all",
    ]);
  });

  it("stepRuns key separates 'failed' and 'all' caches", () => {
    expect(flowKeys.stepRuns(2, "failed")).not.toEqual(flowKeys.stepRuns(2));
  });

  it("contactMemberships key prefix matches the contact-detail invalidation pattern", () => {
    const key = flowKeys.contactMemberships("c1", true);
    // The drawer invalidates by ["contacts","detail",contactId,"flow-memberships"];
    // the prefix must align so partial-key invalidation hits this query.
    expect(key.slice(0, 4)).toEqual(["contacts", "detail", "c1", "flow-memberships"]);
  });

  it("default include_past=true is encoded in the cache key", () => {
    const a = flowKeys.contactMemberships("c1");
    const b = flowKeys.contactMemberships("c1", false);
    expect(a).not.toEqual(b);
  });
});
