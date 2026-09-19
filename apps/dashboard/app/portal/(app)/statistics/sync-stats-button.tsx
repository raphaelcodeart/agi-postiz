"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2Icon, RefreshCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { StatSyncDispatchResponse, StatSyncRunResponse } from "@/types/api";

/**
 * "Aggiorna statistiche" nel portale del promoter.
 *
 * Fa lo stesso lavoro di components/shared/sync-button.tsx (il bottone
 * dell'amministratore) ma non lo riusa: quello e' costruito su react-query e su
 * useSyncFlow, che nel portale non esistono - queste pagine sono Server
 * Components che leggono e basta, senza cache client da tenere coerente (vedi
 * il docstring di lib/portal/server.ts). Riusarlo vorrebbe dire portare
 * react-query dentro il portale per un bottone solo; a fine sincronizzazione
 * qui basta router.refresh(), che rigenera la pagina sul server con i totali
 * nuovi.
 *
 * Lato backend il sync e' ristretto ai post di chi preme (POST
 * /portal/statistics/sync, scope="user" sul proprio id) ed eredita la guardia
 * anti-spreco: un post gia' scaricato nelle ultime 20 ore viene saltato, quindi
 * premere due volte di fila non costa chiamate al provider.
 */

const POLL_INTERVAL_MS = 2000;
// Il sync scaglia le richieste per rispettare il rate limit del provider, per
// cui un promoter con molti post puo' metterci minuti. Oltre questo limite si
// smette di interrogare e si ricarica comunque la pagina: il run prosegue sul
// worker, e i totali che nel frattempo ha scritto sono gia' quelli buoni.
const MAX_POLL_MS = 3 * 60 * 1000;
const TERMINAL_STATUSES = ["completed", "completed_with_errors", "failed"];

export function SyncStatsButton({ lastSyncedAt }: { lastSyncedAt: string | null }) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Un polling in volo non deve sopravvivere alla pagina che l'ha avviato.
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  const start = useCallback(async () => {
    setRunning(true);
    setError(null);
    setProgress(null);

    try {
      const response = await fetch("/api/portal/backend/statistics/sync", { method: "POST" });
      if (!response.ok) {
        setError("Aggiornamento non riuscito. Riprova fra poco.");
        setRunning(false);
        return;
      }
      const dispatch = (await response.json()) as StatSyncDispatchResponse;
      const startedAt = Date.now();

      while (!cancelled.current && Date.now() - startedAt < MAX_POLL_MS) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        if (cancelled.current) return;

        const runResponse = await fetch(
          `/api/portal/backend/statistics/sync/${dispatch.sync_run_id}`,
          { cache: "no-store" }
        );
        if (!runResponse.ok) break;

        const run = (await runResponse.json()) as StatSyncRunResponse;
        const done = run.synced_posts + run.failed_posts + run.skipped_posts;
        setProgress(run.total_posts > 0 ? `${done} di ${run.total_posts} post` : null);

        if (TERMINAL_STATUSES.includes(run.status)) {
          // Tutto saltato dalla guardia anti-spreco: dirlo, invece di far
          // sembrare rotto un aggiornamento che invece ha funzionato e non
          // aveva nulla da scaricare.
          if (run.total_posts > 0 && run.skipped_posts === run.total_posts) {
            setProgress("Le statistiche erano già aggiornate");
          } else if (run.failed_posts > 0) {
            setProgress(`${run.synced_posts} aggiornati, ${run.failed_posts} non riusciti`);
          } else {
            setProgress(null);
          }
          break;
        }
      }
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      if (!cancelled.current) {
        setRunning(false);
        router.refresh();
      }
    }
  }, [router]);

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button variant="outline" size="sm" onClick={start} disabled={running}>
        {running ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />}
        {running ? "Aggiornamento in corso" : "Aggiorna statistiche"}
      </Button>
      {error ? (
        <span className="text-xs text-destructive">{error}</span>
      ) : progress ? (
        <span className="text-xs text-muted-foreground">{progress}</span>
      ) : lastSyncedAt ? (
        <span className="text-xs text-muted-foreground">
          Ultimo aggiornamento:{" "}
          {new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" }).format(
            new Date(lastSyncedAt)
          )}
        </span>
      ) : null}
    </div>
  );
}
