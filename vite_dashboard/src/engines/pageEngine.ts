/**
 * pageEngine — produces a typed descriptor for each page YAML, plus the
 * page-scoped CSS variable map that feeds <PageContainer>'s style prop.
 *
 * Page styles flow:
 *   config/pages/wa_inbox.yml::styles
 *     → pageEngine.getStyleVars("wa_inbox") → { '--wa-inbox-bubble-max-width': '78%' }
 *     → <PageContainer style={vars}> → <ChatPanel className={styles.bubble}>
 *     → wa-inbox.module.css uses var(--wa-inbox-bubble-max-width)
 */

import { configLoader } from "@/loaders/configLoader";
import type { PageId } from "@/schemas/pages";

export const pageEngine = {
  /** Get the validated page config. Throws if id is invalid (compile error too). */
  getConfig<T extends PageId>(id: T) {
    return configLoader.getPage(id);
  },

  /**
   * Convert the page's `styles` block into a CSS-variable map prefixed with
   * the page id. Returned as a React.CSSProperties-compatible object so
   * components can spread it onto a root element.
   */
  getStyleVars(id: PageId): Record<string, string> {
    const cfg = configLoader.getPage(id);
    const styles = (cfg.page as { styles?: Record<string, string> }).styles ?? {};
    const prefix = `--${id.replace(/_/g, "-")}`;
    const vars: Record<string, string> = {};
    for (const [k, v] of Object.entries(styles)) {
      const kebab = k.replace(/_/g, "-");
      vars[`${prefix}-${kebab}`] = v;
    }
    return vars;
  },

  /** Page header data for <PageContainer>. */
  getMeta(id: PageId): { title: string; subtitle: string; landed_phase: number } {
    const cfg = configLoader.getPage(id);
    const page = cfg.page as { title: string; subtitle: string; landed_phase: number };
    return {
      title: page.title,
      subtitle: page.subtitle,
      landed_phase: page.landed_phase,
    };
  },
};
