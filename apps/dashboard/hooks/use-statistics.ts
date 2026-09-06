"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as statisticsService from "@/services/statistics";
import { queryKeys } from "@/lib/query/keys";
import type { StatSyncDispatchResponse, StatSyncRunResponse } from "@/types/api";

export function useStatisticsDashboard() {
  return useQuery({
    queryKey: queryKeys.statistics.dashboard(),
    queryFn: statisticsService.getDashboard,
  });
}

export function useUserStatistics(userId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.statistics.userDetail(userId ?? ""),
    queryFn: () => statisticsService.getUserStatistics(userId as string),
    enabled: !!userId,
  });
}

export function useChannelStatistics(userId: string | undefined, channelId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.statistics.channelDetail(userId ?? "", channelId ?? ""),
    queryFn: () => statisticsService.getChannelStatistics(userId as string, channelId as string),
    enabled: !!userId && !!channelId,
  });
}

// Sincronizzazione asincrona: il POST ritorna subito un sync_run_id (202), il
// progresso reale si segue con useSyncRun sotto (polling finche' non e'
// completato) - stesso spirito del polling di useCampaignDetail.
export function useSyncUserMutation() {
  return useMutation({ mutationFn: (userId: string) => statisticsService.syncUser(userId) });
}

export function useSyncCampaignMutation() {
  return useMutation({ mutationFn: (campaignId: string) => statisticsService.syncCampaign(campaignId) });
}

export function useSyncAllMutation() {
  return useMutation({ mutationFn: () => statisticsService.syncAll() });
}

const ACTIVE_SYNC_STATUSES = new Set<StatSyncRunResponse["status"]>(["queued", "running"]);

// Polling finche' lo stato non e' definitivo (completato/fallito) - il
// chiamante osserva il completamento con un useEffect su `data.status`
// (es. per invalidare la query di dettaglio e mostrare i nuovi totali).
export function useSyncRun(syncRunId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.statistics.syncRun(syncRunId ?? ""),
    queryFn: () => statisticsService.getSyncRun(syncRunId as string),
    enabled: !!syncRunId,
    refetchInterval: (query) => (query.state.data && ACTIVE_SYNC_STATUSES.has(query.state.data.status) ? 2000 : false),
    retry: false,
  });
}

export function useSyncSinglePostMutation() {
  return useMutation({ mutationFn: (publicationId: string) => statisticsService.syncSinglePost(publicationId) });
}

// Orchestrazione completa di un bottone "Sincronizza" (usata dai 3 livelli:
// utente/campagna/tutti, vedi components/shared/sync-button.tsx): dispatcha,
// esegue il polling con useSyncRun finche' non e' finita, poi invalida tutte
// le query del modulo Statistiche cosi' la pagina mostra i nuovi totali senza
// bisogno di un refresh manuale.
export function useSyncFlow(dispatch: () => Promise<StatSyncDispatchResponse>) {
  const queryClient = useQueryClient();
  const [syncRunId, setSyncRunId] = useState<string | undefined>(undefined);

  const dispatchMutation = useMutation({
    mutationFn: dispatch,
    onSuccess: (data) => setSyncRunId(data.sync_run_id),
  });

  const runQuery = useSyncRun(syncRunId);
  const run = runQuery.data;

  useEffect(() => {
    if (run && !ACTIVE_SYNC_STATUSES.has(run.status)) {
      queryClient.invalidateQueries({ queryKey: ["statistics"] });
    }
    // Si rilancia solo quando cambia lo stato/id del run, non a ogni render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status, run?.id]);

  return {
    start: () => dispatchMutation.mutate(),
    run,
    isDispatching: dispatchMutation.isPending,
    isRunning: !!syncRunId && (!run || ACTIVE_SYNC_STATUSES.has(run.status)),
    dispatchError: dispatchMutation.isError,
  };
}
