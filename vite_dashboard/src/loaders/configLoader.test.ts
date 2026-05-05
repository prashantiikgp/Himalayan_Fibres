/**
 * configLoader fail-loud tests (review fix M3).
 *
 * Verifies the production-readiness principle: bad YAML throws
 * ConfigValidationError with a useful message; bootstrap is idempotent.
 */

import { describe, it, expect } from "vitest";
import { ZodError } from "zod";
import { ThemeConfig } from "@/schemas/theme";
import { SidebarConfig } from "@/schemas/sidebar";
import { HomePageConfig, ContactsPageConfig } from "@/schemas/pages";
import { configLoader } from "./configLoader";

describe("configLoader", () => {
  it("bootstrap() succeeds and is idempotent", () => {
    expect(() => configLoader.bootstrap()).not.toThrow();
    // Second call is a no-op; mustn't re-validate or throw
    expect(() => configLoader.bootstrap()).not.toThrow();
  });

  it("getTheme() returns a fully-typed theme after bootstrap", () => {
    configLoader.bootstrap();
    const theme = configLoader.getTheme();
    expect(theme.name).toBe("hf-dashboard-dark");
    expect(theme.colors.primary).toMatch(/^#[0-9a-fA-F]{3,8}$/);
    expect(theme.fonts.md).toMatch(/^\d+px$/);
  });

  it("getSidebar() returns the grouped nav (B11 fix)", () => {
    configLoader.bootstrap();
    const sidebar = configLoader.getSidebar();
    const groupIds = sidebar.sidebar.groups.map((g) => g.id);
    expect(groupIds).toContain("whatsapp");
    expect(groupIds).toContain("top");
  });

  it("getPage('home') has the structure HomePage expects", () => {
    configLoader.bootstrap();
    const home = configLoader.getPage("home");
    expect(home.page.sections.kpi_rows).toHaveLength(2);
    expect(home.page.sections.kpi_rows[0]?.ids.length).toBeGreaterThan(0);
  });
});

describe("Zod schemas — fail-loud on bad YAML", () => {
  it("ThemeConfig rejects missing required field", () => {
    const bad = { name: "x", colors: { primary: "#fff" } }; // missing rest
    expect(() => ThemeConfig.parse(bad)).toThrow(ZodError);
  });

  it("ThemeConfig rejects extra fields (extra: 'forbid')", () => {
    const bad = {
      name: "x",
      colors: {
        primary: "#fff",
        primary_foreground: "#000",
        secondary: "#fff",
        secondary_foreground: "#000",
        success: "#0f0",
        success_foreground: "#000",
        warning: "#ff0",
        warning_foreground: "#000",
        error: "#f00",
        error_foreground: "#000",
        bg: "#000",
        card_bg: "#111",
        border: "#222",
        text: "#fff",
        text_muted: "#aaa",
        text_subtle: "#bbb",
        bonus_undocumented: "#abc", // ← unknown
      },
      fonts: { xs: "1px", sm: "2px", md: "3px", lg: "4px", xl: "5px" },
      radii: { sm: "1px", md: "2px", card: "3px", pill: "4px" },
      spacing: { card: "1px", section: "2px" },
    };
    expect(() => ThemeConfig.parse(bad)).toThrow(ZodError);
  });

  it("SidebarConfig requires non-empty groups", () => {
    expect(() => SidebarConfig.parse({ sidebar: { groups: [] } })).toThrow(ZodError);
  });

  it("HomePageConfig requires landed_phase as a number 0-5", () => {
    const bad = {
      page: {
        title: "Home",
        landed_phase: 99,
        sections: {
          status_strip: { enabled: true },
          kpi_rows: [{ ids: ["x"] }],
          lifecycle: { title: "L" },
          activity: { title: "A" },
        },
      },
    };
    expect(() => HomePageConfig.parse(bad)).toThrow(ZodError);
  });

  it("ContactsPageConfig requires at least one column", () => {
    const bad = {
      page: {
        title: "Contacts",
        landed_phase: 1,
        table: { columns: [] },
      },
    };
    expect(() => ContactsPageConfig.parse(bad)).toThrow(ZodError);
  });
});
