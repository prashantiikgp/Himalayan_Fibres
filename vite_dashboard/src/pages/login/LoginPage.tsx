/**
 * Login page — Bearer auth (per STANDARDS §1).
 *
 * On success, stores the token (= APP_PASSWORD) in localStorage and redirects
 * to the user's intended destination (or /home if none).
 */

import { useState, type FormEvent } from "react";
import { useLocation, useNavigate, type Location } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setToken } from "@/lib/auth";
import { login } from "@/api/auth";
import { ApiError } from "@/lib/queryClient";
import { track } from "@/lib/analytics";
import { STRINGS } from "@/lib/strings";

type LocationState = { from?: Location } | null;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as LocationState)?.from?.pathname ?? "/home";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!password) return;
    setError(null);
    setSubmitting(true);
    try {
      const { token } = await login(password);
      setToken(token);
      track("auth_login", { success: true });
      navigate(from, { replace: true });
    } catch (err) {
      track("auth_login", { success: false });
      if (err instanceof ApiError && err.status === 401) {
        setError(STRINGS.auth.error);
      } else {
        setError(err instanceof Error ? err.message : STRINGS.errors.unknown);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{STRINGS.auth.loginTitle}</CardTitle>
          <CardDescription>{STRINGS.app.tagline}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">{STRINGS.auth.passwordLabel}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder={STRINGS.auth.passwordPlaceholder}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "login-error" : undefined}
                required
              />
            </div>
            {error && (
              <p id="login-error" role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" disabled={submitting || !password}>
              {submitting ? "…" : STRINGS.auth.submit}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
