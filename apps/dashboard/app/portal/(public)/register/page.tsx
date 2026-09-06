"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2Icon, RssIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -left-32 size-96 rounded-full bg-brand-from/30 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-32 -bottom-32 size-96 rounded-full bg-brand-to/30 blur-3xl"
      />
      <Card className="relative w-full max-w-sm border-white/20 bg-card/80 shadow-2xl shadow-primary/10 backdrop-blur-xl">
        <CardHeader className="items-center text-center">
          <div className="glow-primary mb-1 flex size-10 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground">
            <RssIcon className="size-5" />
          </div>
          <CardTitle className="gradient-text text-xl">Crea il tuo account</CardTitle>
          <CardDescription>
            Collega i tuoi canali social e segui i risultati delle campagne
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Label htmlFor="name">Nome e cognome</Label>
              <Input id="name" required minLength={2} value={form.name} onChange={update("name")} />
            </div>
            <div className="space-y-2">
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
            <div className="space-y-2">
              <Label htmlFor="company_name">
                Azienda <span className="text-muted-foreground">(facoltativo)</span>
              </Label>
              <Input id="company_name" value={form.company_name} onChange={update("company_name")} />
            </div>
            <div className="space-y-2">
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
              <p className="text-xs text-muted-foreground">
                Almeno {MIN_PASSWORD_LENGTH} caratteri.
              </p>
            </div>
            <Button type="submit" className="w-full" disabled={pending}>
              {pending && <Loader2Icon className="size-4 animate-spin" />}
              Registrati
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Hai già un account?{" "}
              <Link href="/portal/login" className="text-primary underline-offset-4 hover:underline">
                Accedi
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
