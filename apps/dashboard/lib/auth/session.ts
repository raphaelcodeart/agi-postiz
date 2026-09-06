import "server-only";
import { jwtVerify } from "jose";
import { getJwtSecret } from "@/lib/env";

export interface SessionPayload {
  adminId: string;
  expiresAt: number;
}

/**
 * Verifies the admin JWT issued by FastAPI's SecurityService.create_access_token
 * (HS256, subject = administrator id). Mirrors apps/api/app/core/security.py exactly.
 */
export async function verifySessionToken(token: string): Promise<SessionPayload | null> {
  try {
    const secret = new TextEncoder().encode(getJwtSecret());
    const { payload } = await jwtVerify(token, secret, { algorithms: ["HS256"] });
    if (!payload.sub || typeof payload.exp !== "number") {
      return null;
    }
    return { adminId: payload.sub, expiresAt: payload.exp };
  } catch {
    return null;
  }
}
