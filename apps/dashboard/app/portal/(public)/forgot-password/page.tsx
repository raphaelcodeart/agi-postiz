"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2Icon, MailCheckIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PortalAuthShell } from "../auth-shell";

/**
 * "Ho dimenticato la password": si chiede l'indirizzo, arriva un link.
 *
 * A invio fatto la pagina dice sempre la stessa cosa, anche se quell'indirizzo
 * da noi non esiste. Non e' vaghezza: distinguere i due casi qui direbbe a
 * chiunque, senza bisogno di alcuna password, chi ha un account su AGI Post -
 * la stessa ragione per cui l'accesso non dice mai se ha sbagliato l'email o la
 * password (apps/api/app/api/v1/portal.py::forgot_password).
 */
export default function PortalForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const response = await fetch("/api/portal/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setError(payload?.detail ?? "Richiesta non riuscita");
        return;
      }
      setSent(true);
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PortalAuthShell
      title={sent ? "Controlla la posta" : "Password dimenticata"}
      subtitle={
        sent
          ? "Se esiste un account con quell'indirizzo, il link per reimpostare la password \u00e8 in arrivo."
          : "Scrivi l'indirizzo con cui ti sei registrato: ti mandiamo un link per scegliere una nuova password."
      }
      footer={
        <>
          Ti è tornata in mente?{" "}
          <Link href="/portal/login" className="pa-link">
            Torna all&apos;accesso
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="grid gap-4 text-center">
          <MailCheckIcon className="mx-auto size-10 text-[var(--pa-accent)]" aria-hidden />
          <p className="text-[0.95rem] leading-relaxed text-[var(--pa-ink-2)]">
            Il link vale un&apos;ora e si può usare una volta sola. Se non arriva entro
            qualche minuto, controlla la posta indesiderata.
          </p>
          <Link href="/portal/login" className="pa-btn mt-1 no-underline">
            Torna all&apos;accesso
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="grid gap-4">
          {error && (
            <p role="alert" className="pa-notice pa-notice--error">
              {error}
            </p>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <button type="submit" className="pa-btn mt-1" disabled={pending}>
            {pending && <Loader2Icon className="size-4 animate-spin" />}
            Mandami il link
          </button>
        </form>
      )}
    </PortalAuthShell>
  );
}
