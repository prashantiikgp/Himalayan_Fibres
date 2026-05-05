/**
 * format helpers — pure-function tests (review fix M3).
 */

import { describe, it, expect } from "vitest";
import {
  formatCurrency,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatRelative,
  truncate,
} from "./format";

describe("formatNumber", () => {
  it("formats integers with locale separator", () => {
    expect(formatNumber(1574)).toBe("1,574");
    expect(formatNumber(1000000)).toMatch(/[1].*0.*0.*0.*0.*0.*0/);
  });

  it("returns em-dash for nullish", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
  });
});

describe("formatCurrency", () => {
  it("formats INR with locale separator", () => {
    expect(formatCurrency(12500)).toContain("12,500");
    expect(formatCurrency(12500)).toContain("₹");
  });

  it("returns em-dash for nullish", () => {
    expect(formatCurrency(null)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("handles sub-second", () => {
    expect(formatDuration(0.5)).toBe("<1s");
  });
  it("handles seconds", () => {
    expect(formatDuration(45)).toBe("45s");
  });
  it("handles minutes", () => {
    expect(formatDuration(125)).toBe("2m 5s");
    expect(formatDuration(120)).toBe("2m");
  });
  it("handles hours", () => {
    expect(formatDuration(3600)).toBe("1h");
    expect(formatDuration(3661)).toBe("1h 1m");
  });
});

describe("truncate", () => {
  it("leaves short strings alone", () => {
    expect(truncate("hi", 10)).toBe("hi");
  });
  it("ellipsizes long strings", () => {
    const out = truncate("hello world from here", 10);
    expect(out.length).toBe(10);
    expect(out).toContain("…");
  });
});

describe("formatDateTime / formatRelative", () => {
  it("formatDateTime returns em-dash for nullish", () => {
    expect(formatDateTime(null)).toBe("—");
  });
  it("formatRelative returns em-dash for nullish", () => {
    expect(formatRelative(null)).toBe("—");
  });
});
