import { apiClient } from "@/lib/api/client";
import type { AdminResponse } from "@/types/api";

export async function login(email: string, password: string): Promise<void> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Invalid credentials");
  }
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST" });
}

export function getMe(): Promise<AdminResponse> {
  return apiClient.get<AdminResponse>("/auth/me");
}
