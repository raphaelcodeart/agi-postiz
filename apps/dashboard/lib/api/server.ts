import "server-only";
import { cookies } from "next/headers";
import { getBackendInternalUrl, SESSION_COOKIE_NAME } from "@/lib/env";
import { ApiError, parseErrorResponse } from "@/lib/api/errors";

/**
 * Server Component / Server Action fetch helper. Calls the FastAPI backend
 * directly (no extra proxy hop) using the JWT from the httpOnly session cookie.
 * Use only in server-side code (layouts, server components, route handlers).
 */
export async function serverApiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;

  const response = await fetch(`${getBackendInternalUrl()}/api/v1${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export { ApiError };
