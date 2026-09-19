"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2Icon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PortalAuthShell } from "../auth-shell";

const MIN_PASSWORD_LENGTH = 10; // matches PortalRegisterRequest in apps/api/app/api/v1/portal.py

export default function PortalRegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", company_name: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function update(field: keyof typeof form) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (form.password.length < MIN_PASSWORD_LENGTH) {
      setError(`La password deve avere almeno ${MIN_PASSWORD_LENGTH} caratteri.`);
      return;
    }

    setPending(true);
    try {
      const response = await fetch("/api/portal/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setError(payload?.detail ?? "Registrazione non riuscita");
        return;
      }
      router.push("/portal");
      router.refresh();
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <PortalAuthShell
      title="Entra nella rete"
      subtitle="Colleghi i tuoi account social, pubblichi da un posto solo e vedi i numeri veri. L'autorizzazione la dai tu e la revochi quando vuoi."
      footer={
        <>
          Hai già un account?{" "}
          <Link href="/portal/login" className="pa-link">
            Accedi
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="grid gap-4">
        {error && (
          <p role="alert" className="pa-notice pa-notice--error">
            {error}
          </p>
        )}
        <div className="grid gap-1.5">
          <Label htmlFor="name">Nome e cognome</Label>
          <Input id="name" required minLength={2} value={form.name} onChange={update("name")} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={form.email}
            onChange={update("email")}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="company_name">
            Azienda <span className="font-normal text-[var(--pa-muted)]">(facoltativo)</span>
          </Label>
          <Input id="company_name" value={form.company_name} onChange={update("company_name")} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={form.password}
            onChange={update("password")}
          />
          <p className="text-[0.79rem] text-[var(--pa-muted)]">
            Almeno {MIN_PASSWORD_LENGTH} caratteri.
          </p>
        </div>
        <button type="submit" className="pa-btn mt-1" disabled={pending}>
          {pending && <Loader2Icon className="size-4 animate-spin" />}
          Crea il mio account
        </button>
      </form>
    </PortalAuthShell>
  );
}
