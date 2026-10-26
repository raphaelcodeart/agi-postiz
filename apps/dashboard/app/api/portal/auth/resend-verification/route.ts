import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * Rimanda l'email di conferma all'utente collegato.
 *
 * Il destinatario lo decide il backend a partire dal token di sessione, non
 * questa rotta e non il browser: nessun indirizzo viaggia nel corpo, quindi non
 * c'e' modo di usarla per far arrivare posta a caselle altrui.
 */
export async function POST(request: NextRequest) {
  const token = request.cookies.get(PORTAL_SESSION_COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sessione scaduta. Accedi di nuovo." }, { status: 401 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${getBackendInternalUrl()}/api/v1/portal/auth/resend-verification`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      }
    );
  } catch {
    return NextResponse.json({ detail: "Servizio non raggiungibile" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(
      {
        detail:
          typeof payload?.detail === "string"
            ? payload.detail
            : "Non siamo riusciti a inviare l'email. Riprova fra poco.",
      },
      { status: backendResponse.status || 400 }
    );
  }

  return NextResponse.json({ detail: payload?.detail ?? "Email inviata." });
}
