"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2Icon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PortalAuthShell } from "../auth-shell";

function PortalLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Arriva da /portal/reset-password: la password e' appena stata cambiata e
  // questo e' il primo accesso con quella nuova.
  const justReset = searchParams.get("reset") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const response = await fetch("/api/portal/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setError(payload?.detail ?? "Accesso non riuscito");
        return;
      }
      router.push(searchParams.get("next") || "/portal");
      router.refresh();
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      {justReset && !error && (
        <p className="pa-notice pa-notice--ok">
          Password aggiornata. Accedi con quella nuova.
        </p>
      )}
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
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <div className="flex items-baseline justify-between gap-3">
          <Label htmlFor="password">Password</Label>
          <Link
            href="/portal/forgot-password"
            className="text-[0.82rem] text-[var(--pa-muted)] hover:text-[var(--pa-accent)]"
          >
            Hai dimenticato la password?
          </Link>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      <button type="submit" className="pa-btn mt-1" disabled={pending}>
        {pending && <Loader2Icon className="size-4 animate-spin" />}
        Accedi
      </button>
    </form>
  );
}

export default function PortalLoginPage() {
  return (
    <PortalAuthShell
      title="Bentornato"
      subtitle="Accedi al tuo profilo promoter: i tuoi canali, le campagne e i numeri che stanno facendo."
      footer={
        <>
          Non hai ancora un account?{" "}
          <Link href="/portal/register" className="pa-link">
            Registrati
          </Link>
        </>
      }
    >
      <Suspense>
        <PortalLoginForm />
      </Suspense>
    </PortalAuthShell>
  );
}
