/**
 * Server-side origin used to reach the FastAPI backend from inside the Next.js
 * server/container (e.g. the Docker service name `http://api:8000`).
 * Falls back to NEXT_PUBLIC_API_URL for local dev where both origins are the same host.
 */
export function getBackendInternalUrl(): string {
  return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/** Secret shared with the FastAPI backend to verify admin JWTs (HS256, see app/core/security.py). */
export function getJwtSecret(): string {
  const secret = process.env.SECRET_KEY;
  if (!secret) {
    throw new Error(
      "SECRET_KEY is not set. The dashboard must share the same SECRET_KEY as the FastAPI backend to verify admin sessions."
    );
  }
  return secret;
}

export const SESSION_COOKIE_NAME = "session_token";

export function isMockApiEnabled(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCK_API === "true" && process.env.NODE_ENV !== "production";
}
