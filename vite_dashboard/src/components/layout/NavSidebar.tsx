/**
 * <NavSidebar> — production sidebar driven by config/dashboard/sidebar.yml
 * via navigationEngine. No hardcoded nav array.
 *
 * Mobile: collapses to a hamburger menu via the parent <AppShell>'s state.
 */

import { NavLink } from "react-router-dom";
import * as Lucide from "lucide-react";
import { cn } from "@/lib/utils";
import { navigationEngine } from "@/engines/navigationEngine";
import { configLoader } from "@/loaders/configLoader";

function ResolvedIcon({ name }: { name: string }) {
  const Icon = (Lucide as unknown as Record<string, Lucide.LucideIcon | undefined>)[name];
  if (!Icon) {
    return <Lucide.Circle className="h-4 w-4" aria-hidden />;
  }
  return <Icon className="h-4 w-4" aria-hidden />;
}

export function NavSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const groups = navigationEngine.getGroups();
  const dashboard = configLoader.getDashboard();

  return (
    <aside
      className="flex h-full w-56 flex-col gap-2 border-r border-border bg-card/40 px-3 py-4"
      aria-label="Primary navigation"
    >
      <div className="px-2 pb-2">
        <div className="text-sm font-semibold text-text">{dashboard.title}</div>
        {dashboard.subtitle && (
          <div className="text-xs text-text-muted">{dashboard.subtitle}</div>
        )}
      </div>
      <nav className="flex flex-col gap-3" role="navigation">
        {groups.map((group) => (
          <div key={group.id} className="flex flex-col gap-0.5">
            {group.label && (
              <div className="px-2 pt-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                {group.label}
              </div>
            )}
            {group.routes.map((route) => (
              <NavLink
                key={route.id}
                to={route.path}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-text-muted transition-colors",
                    "hover:bg-card hover:text-text",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                    isActive && "bg-primary/10 text-primary",
                  )
                }
              >
                <ResolvedIcon name={route.icon} />
                <span>{route.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
