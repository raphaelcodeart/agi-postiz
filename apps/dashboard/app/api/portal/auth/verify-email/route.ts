import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * Conferma l'indirizzo con il token del link ricevuto per email e apre la
 * sessione, cosi' chi clicca si ritrova dentro al portale invece che davanti a
 * un modulo di accesso (il backend spiega perche' il token vale come prova:
 * portal.py::verify_email).
 *
 * Il cookie e' lo stesso dell'accesso normale - httpOnly, mai leggibile dal
 * browser - percio' chi conferma da un dispositivo diverso da quello della
 * registrazione resta collegato proprio li'.
 */
export async function POST(request: NextRequest) {
  let body: { token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Richiesta non valida" }, { status: 400 });
  }

  if (!body.token) {
    return NextResponse.json({ detail: "Link di conferma incompleto" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getBackendInternalUrl()}/api/v1/portal/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: body.token }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Servizio non raggiungibile" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok || !payload?.access_token) {
    return NextResponse.json(
      {
        detail:
          typeof payload?.detail === "string"
            ? payload.detail
            : "Link non valido o scaduto. Accedi e chiedine uno nuovo.",
      },
      { status: backendResponse.status || 400 }
    );
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
