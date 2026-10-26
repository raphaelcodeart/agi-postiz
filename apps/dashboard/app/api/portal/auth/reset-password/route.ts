import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl } from "@/lib/env";

/**
 * Imposta la nuova password a partire dal token ricevuto per email.
 *
 * Non apre nessuna sessione di proposito: dopo un cambio password si passa dal
 * modulo di accesso, cosi' la password nuova viene usata subito almeno una
 * volta - ed e' l'unico modo per accorgersi sul momento di averla digitata
 * diversa da come si credeva.
 *
 * Token e password non vengono mai registrati (AGENTS.md regola 10).
 */
export async function POST(request: NextRequest) {
  let body: { token?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Richiesta non valida" }, { status: 400 });
  }

  if (!body.token || !body.password) {
    return NextResponse.json({ detail: "Link o password mancanti" }, { status: 400 });
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${getBackendInternalUrl()}/api/v1/portal/auth/reset-password`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: body.token, password: body.password }),
        cache: "no-store",
      }
    );
  } catch {
    return NextResponse.json({ detail: "Servizio non raggiungibile" }, { status: 502 });
  }

  const payload = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    let detail = "Non siamo riusciti a reimpostare la password";
    if (typeof payload?.detail === "string") {
      detail = payload.detail;
    } else if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) {
      detail = payload.detail[0].msg;
    }
    return NextResponse.json({ detail }, { status: backendResponse.status || 400 });
  }

  return NextResponse.json({ detail: payload?.detail ?? "Password aggiornata." });
}
