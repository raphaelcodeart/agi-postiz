"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { Loader2Icon, RefreshCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSyncFlow } from "@/hooks/use-statistics";
import { formatDateTime } from "@/lib/format";
import type { StatSyncDispatchResponse } from "@/types/api";

interface SyncButtonProps {
  label: string;
  dispatch: () => Promise<StatSyncDispatchResponse>;
  /** Omesso quando il chiamante non ha (ancora) un timestamp aggregato da
   * mostrare per questo scope specifico (es. il bottone sulla pagina di una
   * singola campagna) - in quel caso l'etichetta non viene renderizzata
   * invece di mostrare un fuorviante "mai" permanente. */
  lastSyncedAt?: string | null;
}

/**
 * Bottone "Sincronizza" condiviso dai 3 livelli (dashboard generale, utente,
 * campagna - vedi docs/STATISTICS.md §7): dispatcha il sync, mostra
 * progresso live (post sincronizzati/saltati/falliti) mentre il worker
 * scarica da Buffer, e l'etichetta "Ultima sincronizzazione" resta sempre
 * visibile accanto al bottone.
 */
export function SyncButton({ label, dispatch, lastSyncedAt }: SyncButtonProps) {
  const { start, run, isDispatching, isRunning, dispatchError } = useSyncFlow(dispatch);
  const notifiedRunId = useRef<string | null>(null);

  useEffect(() => {
    if (!run || run.status === "queued" || run.status === "running") return;
    if (notifiedRunId.current === run.id) return;
    notifiedRunId.current = run.id;

    if (run.status === "completed") {
      toast.success(
        run.synced_posts > 0
          ? `Sincronizzazione completata: ${run.synced_posts} post aggiornati`
          : "Tutto gia' aggiornato: nessun nuovo dato da scaricare"
      );
    } else if (run.status === "completed_with_errors") {
      toast.warning(`Sincronizzazione completata con ${run.failed_posts} errori su ${run.total_posts} post`);
    } else if (run.status === "failed") {
      toast.error(run.error_message || "Sincronizzazione non riuscita");
    }
  }, [run]);

  useEffect(() => {
    if (dispatchError) toast.error("Impossibile avviare la sincronizzazione");
  }, [dispatchError]);

  const progressLabel =
    run && (run.status === "queued" || run.status === "running")
      ? `Sincronizzazione... ${run.synced_posts + run.failed_posts + run.skipped_posts}/${run.total_posts || "?"}`
      : label;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" size="sm" disabled={isDispatching || isRunning} onClick={() => start()}>
        {isDispatching || isRunning ? (
          <Loader2Icon className="size-4 animate-spin" />
        ) : (
          <RefreshCwIcon className="size-4" />
        )}
        {progressLabel}
      </Button>
      {lastSyncedAt !== undefined && (
        <span className="text-xs text-muted-foreground">
          Ultima sincronizzazione: <span className="font-medium text-foreground">{formatDateTime(lastSyncedAt)}</span>
        </span>
      )}
    </div>
  );
}
