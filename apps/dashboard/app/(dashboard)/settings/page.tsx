"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ActivityIcon, DatabaseIcon, ServerIcon, SparklesIcon, Loader2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { ErrorState } from "@/components/shared/error-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  useSystemSettings,
  useUpdateSystemSettings,
  useHealth,
  useAISettings,
  useUpdateAISettings,
  useDeleteAISettings,
} from "@/hooks/use-settings";
import { settingsFormSchema, type SettingsFormValues } from "@/lib/validation/settings";
import { formatBytes, formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";

const FIELDS: {
  name: keyof SettingsFormValues;
  label: string;
  description: string;
  step?: number;
}[] = [
  {
    name: "global_concurrency_limit",
    label: "Concorrenza globale",
    description: "Numero massimo di pubblicazioni elaborate in parallelo su tutta la piattaforma.",
  },
  {
    name: "concurrent_jobs_per_connection",
    label: "Job simultanei per connessione",
    description: "Numero massimo di richieste in parallelo verso la stessa connessione Buffer.",
  },
  {
    name: "pause_between_requests_seconds",
    label: "Pausa tra richieste (secondi)",
    description: "Intervallo minimo tra due richieste consecutive verso Buffer.",
  },
  {
    name: "max_publication_attempts",
    label: "Tentativi massimi",
    description: "Numero massimo di tentativi automatici per una pubblicazione prima del fallimento definitivo.",
  },
];

function HealthTile({ icon: Icon, label, ok, statusOverride }: { icon: LucideIcon; label: string; ok: boolean; statusOverride?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-primary/[0.03]">
      <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", ok ? "bg-success/15 text-success" : "bg-destructive/10 text-destructive")}>
        <Icon className="size-4" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <StatusBadge status={statusOverride ?? (ok ? "connected" : "error")} />
      </div>
    </div>
  );
}

function AISettingsCard() {
  const aiSettingsQuery = useAISettings();
  const updateAISettings = useUpdateAISettings();
  const deleteAISettings = useDeleteAISettings();
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");

  useEffect(() => {
    if (aiSettingsQuery.data) setModel(aiSettingsQuery.data.model);
  }, [aiSettingsQuery.data]);

  function handleSave() {
    const payload: { openai_api_key?: string; openai_model?: string } = {};
    if (apiKey.trim()) payload.openai_api_key = apiKey.trim();
    if (model.trim() && model.trim() !== aiSettingsQuery.data?.model) payload.openai_model = model.trim();
    if (!payload.openai_api_key && !payload.openai_model) {
      toast.info("Nessuna modifica da salvare");
      return;
    }
    updateAISettings.mutate(payload, {
      onSuccess: () => {
        toast.success("Impostazioni AI aggiornate");
        setApiKey("");
      },
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
    });
  }

  function handleRemove() {
    deleteAISettings.mutate(undefined, {
      onSuccess: () => toast.success("Chiave API OpenAI rimossa"),
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Rimozione non riuscita"),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SparklesIcon className="size-4" />
          Generazione testo con AI
        </CardTitle>
        <CardDescription>
          Chiave API OpenAI personale usata dal pulsante &quot;Genera con AI&quot; nella creazione campagna. Non
          viene mai mostrata una volta salvata, solo se è configurata.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {aiSettingsQuery.isLoading ? (
          <Skeleton className="h-32" />
        ) : aiSettingsQuery.isError ? (
          <ErrorState error={aiSettingsQuery.error} onRetry={() => aiSettingsQuery.refetch()} />
        ) : (
          <>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Stato</span>
              <StatusBadge status={aiSettingsQuery.data?.configured ? "connected" : "disconnected"} />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="ai-api-key">
                  Chiave API OpenAI {aiSettingsQuery.data?.configured && "(lascia vuota per non modificarla)"}
                </Label>
                <Input
                  id="ai-api-key"
                  type="password"
                  autoComplete="off"
                  placeholder="sk-..."
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ai-model">Modello</Label>
                <Input id="ai-model" placeholder="gpt-4o-mini" value={model} onChange={(event) => setModel(event.target.value)} />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSave} disabled={updateAISettings.isPending}>
                {updateAISettings.isPending && <Loader2Icon className="size-4 animate-spin" />}
                Salva
              </Button>
              {aiSettingsQuery.data?.configured && (
                <Button
                  variant="outline"
                  className="text-destructive"
                  onClick={handleRemove}
                  disabled={deleteAISettings.isPending}
                >
                  Rimuovi chiave
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const settingsQuery = useSystemSettings();
  const updateSettings = useUpdateSystemSettings();
  const healthQuery = useHealth();

  const form = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsFormSchema),
    defaultValues: {
      global_concurrency_limit: 5,
      concurrent_jobs_per_connection: 1,
      pause_between_requests_seconds: 10,
      max_publication_attempts: 5,
      upload_max_size_bytes: 524288000,
    },
  });

  useEffect(() => {
    if (settingsQuery.data) {
      form.reset(settingsQuery.data);
    }
  }, [settingsQuery.data, form]);

  function onSubmit(values: SettingsFormValues) {
    updateSettings.mutate(values, {
      onSuccess: () => toast.success("Impostazioni aggiornate"),
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Impostazioni" description="Parametri operativi del motore di pubblicazione" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Stato del sistema</CardTitle>
          <CardDescription>
            Modalità integrazione Buffer:{" "}
            <span className="font-medium text-foreground">{settingsQuery.data?.buffer_integration_mode ?? "—"}</span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {healthQuery.isLoading ? (
            <Skeleton className="h-16" />
          ) : healthQuery.data ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <HealthTile icon={DatabaseIcon} label="Database" ok={healthQuery.data.database === "ok"} />
              <HealthTile icon={ServerIcon} label="Redis" ok={healthQuery.data.redis === "ok"} />
              <HealthTile
                icon={ActivityIcon}
                label="Celery worker"
                ok={healthQuery.data.celery_worker === "ok"}
                statusOverride={healthQuery.data.celery_worker === "ok" ? "connected" : healthQuery.data.celery_worker}
              />
              <p className="col-span-full text-xs text-muted-foreground">
                Ultimo controllo: {formatDateTime(healthQuery.data.timestamp)}
              </p>
            </div>
          ) : (
            <ErrorState error={healthQuery.error} onRetry={() => healthQuery.refetch()} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Concorrenza e retry</CardTitle>
          <CardDescription>
            Le modifiche vengono applicate immediatamente ai worker in background tramite Redis.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {settingsQuery.isLoading ? (
            <Skeleton className="h-64" />
          ) : settingsQuery.isError ? (
            <ErrorState error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
          ) : (
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {FIELDS.map((fieldConfig) => (
                    <FormField
                      key={fieldConfig.name}
                      control={form.control}
                      name={fieldConfig.name}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{fieldConfig.label}</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              {...field}
                              onChange={(event) => field.onChange(Number(event.target.value))}
                            />
                          </FormControl>
                          <FormDescription>{fieldConfig.description}</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                  <FormField
                    control={form.control}
                    name="upload_max_size_bytes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Dimensione massima upload</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            onChange={(event) => field.onChange(Number(event.target.value))}
                          />
                        </FormControl>
                        <FormDescription>Attualmente: {formatBytes(form.watch("upload_max_size_bytes"))}</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
                <Button type="submit" disabled={updateSettings.isPending}>
                  {updateSettings.isPending ? "Salvataggio..." : "Salva impostazioni"}
                </Button>
              </form>
            </Form>
          )}
        </CardContent>
      </Card>

      <AISettingsCard />
    </div>
  );
}
