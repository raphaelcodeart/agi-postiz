"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Loader2Icon, RssIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { loginSchema, type LoginFormValues } from "@/lib/validation/auth";
import { useLogin } from "@/hooks/use-auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  function onSubmit(values: LoginFormValues) {
    setServerError(null);
    login.mutate(values, {
      onSuccess: () => {
        const next = searchParams.get("next") || "/";
        router.push(next);
        router.refresh();
      },
      onError: (error) => {
        setServerError(error instanceof Error ? error.message : "Accesso non riuscito");
      },
    });
  }

  return (
    <Card className="w-full max-w-sm animate-in fade-in zoom-in-95 border-white/20 bg-card/80 shadow-2xl shadow-primary/10 backdrop-blur-xl duration-700">
      <CardHeader className="items-center text-center">
        <div className="glow-primary animate-float mb-1 flex size-10 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground">
          <RssIcon className="size-5" />
        </div>
        <CardTitle className="gradient-text text-xl">Social Publisher</CardTitle>
        <CardDescription>Accedi alla dashboard amministrativa</CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {serverError && (
              <Alert variant="destructive">
                <AlertDescription>{serverError}</AlertDescription>
              </Alert>
            )}
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="admin@example.com" autoComplete="username" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Password</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending && <Loader2Icon className="size-4 animate-spin" />}
              Accedi
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
      <div
        aria-hidden
        className="animate-float pointer-events-none absolute -top-32 -left-32 size-96 rounded-full bg-brand-from/30 blur-3xl"
      />
      <div
        aria-hidden
        className="animate-float pointer-events-none absolute -right-32 -bottom-32 size-96 rounded-full bg-brand-to/30 blur-3xl [animation-delay:-3s]"
      />
      <div className="relative">
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
