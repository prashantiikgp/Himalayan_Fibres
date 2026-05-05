/**
 * Auth endpoints. /api/v2/auth/login is the only one for now.
 */

import { apiFetch } from "./client";

export type LoginResponse = {
  token: string;
};

export async function login(password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/api/v2/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
    skipAuth: true,
  });
}
