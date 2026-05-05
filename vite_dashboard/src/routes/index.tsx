/**
 * Route definitions — built from the YAML-driven sidebar via navigationEngine.
 *
 * As of Phase 5.0 every page from PHASES.md has a real component
 * mounted; the MigrationPage placeholder is no longer referenced in
 * any route, so the import has been dropped.
 */

import { Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "./ProtectedRoute";
import { LoginPage } from "@/pages/login/LoginPage";
import { HomePage } from "@/pages/home/HomePage";
import { ContactsPage } from "@/pages/contacts/ContactsPage";
import { WAInboxPage } from "@/pages/wa-inbox/WAInboxPage";
import { BroadcastsPage } from "@/pages/broadcasts/BroadcastsPage";
import { WATemplatesPage } from "@/pages/wa-templates/WATemplatesPage";
import { FlowsPage } from "@/pages/flows/FlowsPage";
import { navigationEngine } from "@/engines/navigationEngine";

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
        { path: "wa-inbox", element: <WAInboxPage /> },
        { path: "broadcasts", element: <BroadcastsPage /> },
        { path: "wa-templates", element: <WATemplatesPage /> },
        { path: "flows", element: <FlowsPage /> },
      ],
    },
    { path: "*", element: <Navigate to={defaultPath} replace /> },
  ];
}
