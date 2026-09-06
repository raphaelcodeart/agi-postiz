import "server-only";
import { jwtVerify } from "jose";
import { getJwtSecret } from "@/lib/env";

export interface SessionPayload {
  adminId: string;
  expiresAt: number;
}

export interface PortalSessionPayload {
  userId: string;
  expiresAt: number;
}

/**
 * Token audiences, mirroring TOKEN_TYPE_* in apps/api/app/core/security.py.
 *
 * Checking this here is not redundant with the backend checking it. Without it,
 * a portal JWT dropped into the admin cookie would satisfy the middleware - the
 * signature is valid, only the audience differs - and the admin interface would
 * render. Every API call behind it would still fail 401, so no data would leak,
 * but a user would be looking at an administrative UI, and the gap would be one
 * loose endpoint away from being a real one.
 */
const TOKEN_TYPE_ADMIN = "admin";
const TOKEN_TYPE_PORTAL_USER = "portal_user";

async function verify(token: string, expectedType: string) {
  try {
    const secret = new TextEncoder().encode(getJwtSecret());
    const { payload } = await jwtVerify(token, secret, { algorithms: ["HS256"] });
    if (!payload.sub || typeof payload.exp !== "number") {
      return null;
    }
    // Tokens minted before the claim existed are admin tokens, which is what
    // they were - open sessions survive the change. Portal tokens always carry
    // the claim, so they can never be read as admin ones.
    const tokenType = typeof payload.typ === "string" ? payload.typ : TOKEN_TYPE_ADMIN;
    if (tokenType !== expectedType) {
      return null;
    }
    return { sub: payload.sub, exp: payload.exp };
  } catch {
    return null;
  }
}

/**
 * Verifies the admin JWT issued by FastAPI's SecurityService.create_access_token
 * (HS256, subject = administrator id). Mirrors apps/api/app/core/security.py exactly.
 */
export async function verifySessionToken(token: string): Promise<SessionPayload | null> {
  const payload = await verify(token, TOKEN_TYPE_ADMIN);
  return payload ? { adminId: payload.sub, expiresAt: payload.exp } : null;
}

/** Verifies an end-user portal JWT (subject = user id). */
export async function verifyPortalSessionToken(token: string): Promise<PortalSessionPayload | null> {
  const payload = await verify(token, TOKEN_TYPE_PORTAL_USER);
  return payload ? { userId: payload.sub, expiresAt: payload.exp } : null;
}
