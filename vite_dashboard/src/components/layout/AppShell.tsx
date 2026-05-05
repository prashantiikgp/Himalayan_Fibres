/**
 * <AppShell> — sidebar + content area. Used by every authenticated route.
 *
 * Mobile (< 768px): sidebar becomes a slide-out sheet behind a hamburger button.
 * Per STANDARDS §4 a11y: skip-to-content link is in index.html (lives outside
 * React so it works even if the SPA fails to mount).
 */

import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Menu, X, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { NavSidebar } from "./NavSidebar";
import { clearToken } from "@/lib/auth";
import { track } from "@/lib/analytics";

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  function handleLogout() {
    track("auth_logout");
    clearToken();
    window.location.href = "/login";
  }

  return (
    <div className="flex min-h-screen bg-bg text-text">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">
        <NavSidebar />
      </div>

      {/* Mobile sidebar (slide-over) */}
      <div
        className={cn(
          "fixed inset-0 z-40 md:hidden",
          mobileNavOpen ? "pointer-events-auto" : "pointer-events-none",
        )}
        aria-hidden={!mobileNavOpen}
      >
        <button
          type="button"
          className={cn(
            "absolute inset-0 bg-black/50 transition-opacity",
            mobileNavOpen ? "opacity-100" : "opacity-0",
          )}
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
        />
        <div
          className={cn(
            "absolute left-0 top-0 h-full transition-transform",
            mobileNavOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <NavSidebar onNavigate={() => setMobileNavOpen(false)} />
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-card/40 px-4 py-2 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileNavOpen((v) => !v)}
            aria-label={mobileNavOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileNavOpen}
          >
            {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="Sign out">
            <LogOut className="h-5 w-5" />
          </Button>
        </header>

        <main id="main-content" className="flex-1 overflow-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
