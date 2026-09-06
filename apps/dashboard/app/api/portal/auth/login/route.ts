import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * BFF login for end users. Mirrors the admin one in app/api/auth/login, but
 * targets the portal audience and stores the token in its own httpOnly cookie:
 * the two sessions must be able to coexist in one browser, and a portal token is
 * rejected by the admin API anyway (see `typ` in apps/api/app/core/security.py).
 *
 * Never log the password or the issued token (AGENTS.md rule 10).
 */
export async function POST(request: NextRequest) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Richiesta non valida" }, { status: 400 });
  }

  if (!body.email || !body.password) {
    return NextResponse.json({ detail: "Email e password sono obbligatorie" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getBackendInternalUrl()}/api/v1/portal/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: body.email, password: body.password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Servizio non raggiungibile" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok || !payload?.access_token) {
    return NextResponse.json(
      { detail: payload?.detail ?? "Email o password non corretti" },
      { status: backendResponse.status || 401 }
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(PORTAL_SESSION_COOKIE_NAME, payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Matches ACCESS_TOKEN_EXPIRE_MINUTES default (7 days) in apps/api/app/core/config.py
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}
