"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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

function PortalLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
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
    <Card className="w-full max-w-sm border-white/20 bg-card/80 shadow-2xl shadow-primary/10 backdrop-blur-xl">
      <CardHeader className="items-center text-center">
        <div className="glow-primary mb-1 flex size-10 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground">
          <RssIcon className="size-5" />
        </div>
        <CardTitle className="gradient-text text-xl">Agi Post</CardTitle>
        <CardDescription>Accedi al tuo profilo promoter</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="space-y-2">
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
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button type="submit" className="w-full" disabled={pending}>
            {pending && <Loader2Icon className="size-4 animate-spin" />}
            Accedi
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Non hai un account?{" "}
            <Link href="/portal/register" className="text-primary underline-offset-4 hover:underline">
              Registrati
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

export default function PortalLoginPage() {
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
      <div className="relative">
        <Suspense>
          <PortalLoginForm />
        </Suspense>
      </div>
    </div>
  );
}
