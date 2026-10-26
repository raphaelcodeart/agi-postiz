import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl } from "@/lib/env";

/**
 * Avvia il recupero password. Non richiede sessione: e' pensata per chi non
 * riesce ad accedere.
 *
 * La risposta e' sempre la stessa, anche quando il backend fallisce: dire "non
 * conosco questo indirizzo" trasformerebbe questo modulo in un elenco di chi ha
 * un account (stessa scelta del backend, vedi portal.py::forgot_password). Un
 * errore vero lo vede solo chi legge i log.
 */
const GENERIC_ANSWER =
  "Se esiste un account con questo indirizzo, ti abbiamo inviato un'email con il link per reimpostare la password.";

export async function POST(request: NextRequest) {
  let body: { email?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Richiesta non valida" }, { status: 400 });
  }

  if (!body.email) {
    return NextResponse.json({ detail: "Inserisci la tua email" }, { status: 400 });
  }

  try {
    const backendResponse = await fetch(
      `${getBackendInternalUrl()}/api/v1/portal/auth/forgot-password`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: body.email }),
        cache: "no-store",
      }
    );
    if (!backendResponse.ok) {
      console.error(`portal/forgot-password: il backend ha risposto ${backendResponse.status}`);
    }
  } catch (error) {
    console.error("portal/forgot-password: backend irraggiungibile", error);
  }

  return NextResponse.json({ detail: GENERIC_ANSWER });
}
