/**
 * Auth guard — wraps protected routes. Redirects unauthenticated users to
 * /login while preserving their intended destination.
 */

import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { isAuthenticated } from "@/lib/auth";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
