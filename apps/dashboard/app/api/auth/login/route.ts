import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * BFF login endpoint. Exchanges credentials for a FastAPI JWT and stores it in an
 * httpOnly cookie so the access token never reaches client-side JavaScript.
 * Never log the password or the issued token (AGENTS.md rule 10).
 */
export async function POST(request: NextRequest) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request body" }, { status: 400 });
  }

  if (!body.email || !body.password) {
    return NextResponse.json({ detail: "Email and password are required" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getBackendInternalUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: body.email, password: body.password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Backend service is unreachable" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok || !payload?.access_token) {
    return NextResponse.json(
      { detail: payload?.detail ?? "Invalid credentials" },
      { status: backendResponse.status || 401 }
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Matches ACCESS_TOKEN_EXPIRE_MINUTES default (7 days) in apps/api/app/core/config.py
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}
