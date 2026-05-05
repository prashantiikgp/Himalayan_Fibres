/**
 * themeEngine tests (review fix M3) — verify CSS variable emission.
 */

import { describe, it, expect, beforeAll } from "vitest";
import { configLoader } from "@/loaders/configLoader";
import { themeEngine } from "./themeEngine";

beforeAll(() => {
  configLoader.bootstrap();
});

describe("themeEngine", () => {
  it("resolveVars emits a flat CSS-var map", () => {
    const vars = themeEngine.resolveVars();
    expect(vars["--color-primary"]).toBeDefined();
    expect(vars["--color-text-muted"]).toBeDefined();
    expect(vars["--font-md"]).toBeDefined();
    expect(vars["--radius-card"]).toBeDefined();
    expect(vars["--spacing-section"]).toBeDefined();
  });

  it("resolveVars emits component-scoped vars from components.yml", () => {
    const vars = themeEngine.resolveVars();
    expect(vars["--data-table-row-height"]).toBeDefined();
    expect(vars["--kpi-card-padding"]).toBeDefined();
    expect(vars["--status-badge-radius"]).toBeDefined();
  });

  it("applyToDocument writes vars onto document.documentElement", () => {
    themeEngine.applyToDocument();
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--color-primary")).toMatch(/^#[0-9a-fA-F]/);
    expect(root.style.getPropertyValue("--data-table-row-height")).toBe("44px");
  });

  it("snake_case YAML keys become kebab-case CSS vars", () => {
    const vars = themeEngine.resolveVars();
    // YAML key "card_bg" → "--color-card-bg"
    expect(vars["--color-card-bg"]).toBeDefined();
    expect(vars["--color-card_bg"]).toBeUndefined();
  });
});
