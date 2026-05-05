/**
 * Auth lifecycle (per STANDARDS §1).
 *
 * Bearer token in localStorage. Token = the Space's APP_PASSWORD.
 * No refresh; on 401 the apiFetch helper clears the token and redirects to /login.
 *
 * XSS risk is acknowledged in STANDARDS §1 — acceptable for an internal tool
 * that renders no untrusted user content.
 */

const TOKEN_KEY = "hf_dashboard_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // localStorage can throw in private-browsing modes on iOS Safari.
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch (err) {
    console.error("Failed to persist token:", err);
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}
