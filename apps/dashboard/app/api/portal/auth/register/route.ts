import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * BFF registration for end users. On success the backend returns a token, so the
 * new user is signed in straight away and lands on their dashboard rather than
 * being bounced to a login form.
 *
 * Their account starts inactive - they can connect channels and see their
 * dashboard, but are not targetable by campaigns until an administrator
 * activates them (see apps/api/app/api/v1/portal.py::register).
 */
export async function POST(request: NextRequest) {
  let body: { name?: string; email?: string; password?: string; company_name?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Richiesta non valida" }, { status: 400 });
  }

  if (!body.name || !body.email || !body.password) {
    return NextResponse.json({ detail: "Nome, email e password sono obbligatori" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getBackendInternalUrl()}/api/v1/portal/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: body.name,
        email: body.email,
        password: body.password,
        company_name: body.company_name || null,
      }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Servizio non raggiungibile" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok || !payload?.access_token) {
    // FastAPI validation errors arrive as a list of objects; flatten to the first
    // readable message so the form can show something useful.
    let detail = "Registrazione non riuscita";
    if (typeof payload?.detail === "string") {
      detail = payload.detail;
    } else if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) {
      detail = payload.detail[0].msg;
    }
    return NextResponse.json({ detail }, { status: backendResponse.status || 400 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(PORTAL_SESSION_COOKIE_NAME, payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}
