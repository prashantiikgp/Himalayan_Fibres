/**
 * Route definitions — built from the YAML-driven sidebar via navigationEngine.
 *
 * Phase 0 ships /home as fully functional. The other 5 routes render
 * <MigrationPage>, which shows <MigrationStatusCard> with a working v1
 * deep-link. As each page lands in its phase, swap its route's element to
 * the real component.
 */

import { Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "./ProtectedRoute";
import { LoginPage } from "@/pages/login/LoginPage";
import { HomePage } from "@/pages/home/HomePage";
import { ContactsPage } from "@/pages/contacts/ContactsPage";
import { MigrationPage } from "@/pages/migration/MigrationPage";
import { navigationEngine } from "@/engines/navigationEngine";
import type { PageId } from "@/schemas/pages";

export function buildRoutes(): RouteObject[] {
  const defaultPath = navigationEngine.getDefaultPath();

  return [
    { path: "/login", element: <LoginPage /> },
    {
      path: "/",
      element: (
        <ProtectedRoute>
          <AppShell />
        </ProtectedRoute>
      ),
      children: [
        { index: true, element: <Navigate to={defaultPath} replace /> },
        { path: "home", element: <HomePage /> },
        // Phases 1-5: replace <MigrationPage /> with the real page component
        // when it ships.
        { path: "contacts", element: <ContactsPage /> },
        { path: "wa-inbox", element: <MigrationPage pageId={"wa_inbox" as PageId} /> },
        { path: "broadcasts", element: <MigrationPage pageId={"broadcasts" as PageId} /> },
        { path: "wa-templates", element: <MigrationPage pageId={"wa_templates" as PageId} /> },
        { path: "flows", element: <MigrationPage pageId={"flows" as PageId} /> },
      ],
    },
    { path: "*", element: <Navigate to={defaultPath} replace /> },
  ];
}
