"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2Icon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PortalAuthShell } from "../auth-shell";

const MIN_PASSWORD_LENGTH = 10; // come PortalRegisterRequest in apps/api/app/api/v1/portal.py

/**
 * Scelta della nuova password, a partire dal token nel link ricevuto per email.
 *
 * A cambio fatto si torna al modulo di accesso invece di entrare direttamente:
 * cosi' la password nuova viene usata subito almeno una volta, che e' l'unico
 * momento in cui ci si accorge di averla digitata diversa da come si credeva.
 */
function PortalResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) {
    return (
      <div className="grid gap-4 text-center">
        <p role="alert" className="pa-notice pa-notice--error">
          Questo link è incompleto. Copialo per intero dall&apos;email, oppure
          richiedine uno nuovo.
        </p>
        <Link href="/portal/forgot-password" className="pa-btn no-underline">
          Richiedi un nuovo link
        </Link>
      </div>
    );
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`La password deve avere almeno ${MIN_PASSWORD_LENGTH} caratteri.`);
      return;
    }
    if (password !== confirmation) {
      setError("Le due password non coincidono.");
      return;
    }

    setPending(true);
    try {
      const response = await fetch("/api/portal/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setError(payload?.detail ?? "Non siamo riusciti a reimpostare la password.");
        return;
      }
      router.push("/portal/login?reset=1");
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      {error && (
        <p role="alert" className="pa-notice pa-notice--error">
          {error}
        </p>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor="password">Nuova password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          autoFocus
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <p className="text-[0.79rem] text-[var(--pa-muted)]">
          Almeno {MIN_PASSWORD_LENGTH} caratteri.
        </p>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="confirmation">Ripeti la password</Label>
        <Input
          id="confirmation"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />
      </div>
      <button type="submit" className="pa-btn mt-1" disabled={pending}>
        {pending && <Loader2Icon className="size-4 animate-spin" />}
        Salva la nuova password
      </button>
    </form>
  );
}

export default function PortalResetPasswordPage() {
  return (
    <PortalAuthShell
      title="Scegli una nuova password"
      subtitle="Ancora un passaggio e torni dentro: scegli una password che non usi da altre parti."
      footer={
        <>
          Link scaduto?{" "}
          <Link href="/portal/forgot-password" className="pa-link">
            Richiedine un altro
          </Link>
        </>
      }
    >
      <Suspense>
        <PortalResetPasswordForm />
      </Suspense>
    </PortalAuthShell>
  );
}
