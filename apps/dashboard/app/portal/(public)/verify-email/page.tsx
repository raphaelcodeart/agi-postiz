"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2Icon, Loader2Icon, TriangleAlertIcon } from "lucide-react";
import { PortalAuthShell } from "../auth-shell";

/**
 * Pagina di atterraggio del link nell'email di benvenuto.
 *
 * Conferma l'indirizzo e, in un colpo solo, apre la sessione: chi ha appena
 * dimostrato di leggere quella casella non deve reinserire la password, tanto
 * piu' che spesso apre la posta da un dispositivo diverso da quello su cui si e'
 * registrato (il backend spiega perche' il token basti come prova:
 * apps/api/app/api/v1/portal.py::verify_email).
 *
 * La chiamata e' un POST e non un GET dentro il link, di proposito: i client di
 * posta e gli antivirus aprono i link in anticipo per controllarli, e un GET che
 * consuma il token lo brucerebbe prima che l'utente lo veda. Cosi' il token si
 * consuma solo quando la pagina e' davvero aperta da un browser.
 */
type Phase = "verifying" | "done" | "failed";

function PortalVerifyEmailInner() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [phase, setPhase] = useState<Phase>(token ? "verifying" : "failed");
  const [message, setMessage] = useState(
    token ? "" : "Questo link è incompleto. Copialo per intero dall'email."
  );
  // React in sviluppo monta i componenti due volte; senza questa guardia la
  // seconda chiamata troverebbe il token gia' bruciato dalla prima e mostrerebbe
  // un errore su una conferma perfettamente riuscita.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;

    (async () => {
      try {
        const response = await fetch("/api/portal/auth/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          setMessage(payload?.detail ?? "Link non valido o scaduto.");
          setPhase("failed");
          return;
        }
        setPhase("done");
        // Un attimo per far leggere la conferma, poi dentro. Navigazione piena
        // e non router.push: la sessione e' appena nata in un cookie, e il
        // layout del portale va rivalutato dal server con quel cookie in mano.
        setTimeout(() => {
          window.location.href = "/portal";
        }, 1400);
      } catch {
        setMessage("Servizio non raggiungibile. Riprova fra poco.");
        setPhase("failed");
      }
    })();
  }, [token, router]);

  if (phase === "verifying") {
    return (
      <div className="grid justify-items-center gap-3 py-2 text-center">
        <Loader2Icon className="size-8 animate-spin text-[var(--pa-accent)]" aria-hidden />
        <p className="text-[0.95rem] text-[var(--pa-muted)]">Stiamo confermando il tuo indirizzo…</p>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div className="grid justify-items-center gap-3 py-2 text-center">
        <CheckCircle2Icon className="size-10 text-[var(--pa-accent)]" aria-hidden />
        <p className="text-[0.95rem] leading-relaxed text-[var(--pa-ink-2)]">
          Indirizzo confermato. Ti stiamo portando nella tua area…
        </p>
        <Link href="/portal" className="pa-link">
          Vai subito
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-4 text-center">
      <TriangleAlertIcon className="mx-auto size-10 text-[var(--pa-muted)]" aria-hidden />
      <p role="alert" className="pa-notice pa-notice--error">
        {message}
      </p>
      <p className="text-[0.9rem] leading-relaxed text-[var(--pa-muted)]">
        Accedi con le tue credenziali: da dentro puoi farti rimandare subito una nuova
        email di conferma.
      </p>
      <Link href="/portal/login" className="pa-btn no-underline">
        Vai all&apos;accesso
      </Link>
    </div>
  );
}

export default function PortalVerifyEmailPage() {
  return (
    <PortalAuthShell
      title="Conferma indirizzo"
      subtitle="Ancora un istante e il tuo account è attivo."
      footer={
        <>
          Problemi?{" "}
          <Link href="/portal/login" className="pa-link">
            Accedi e richiedi un nuovo link
          </Link>
        </>
      }
    >
      <Suspense>
        <PortalVerifyEmailInner />
      </Suspense>
    </PortalAuthShell>
  );
}
