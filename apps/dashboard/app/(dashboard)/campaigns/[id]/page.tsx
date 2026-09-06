"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import {
  PauseIcon,
  PlayIcon,
  XIcon,
  RotateCcwIcon,
  CopyIcon,
  Trash2Icon,
  BarChart3Icon,
  Loader2Icon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { CampaignProgress } from "@/components/shared/campaign-progress";
import { MediaPreview } from "@/components/shared/media-preview";
import { DataTable } from "@/components/shared/data-table";
import { Pagination } from "@/components/shared/pagination";
import { RetryButton } from "@/components/shared/retry-button";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { StatCard } from "@/components/shared/stat-card";
import { SyncButton } from "@/components/shared/sync-button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useCampaignDetail,
  useCampaignMetrics,
  usePauseCampaign,
  useResumeCampaign,
  useCancelCampaign,
  useDeleteCampaign,
} from "@/hooks/use-campaigns";
import { usePublications, useRetryPublication, useRetryCampaignFailures } from "@/hooks/use-publications";
import { useChannels } from "@/hooks/use-channels";
import { useUsers } from "@/hooks/use-users";
import { syncCampaign } from "@/services/statistics";
import { formatDateTime, formatMetricValue } from "@/lib/format";
import { METRIC_TILE_CONFIG } from "@/lib/metric-config";
import { hasUnresolvedPublications } from "@/lib/campaign-stats";
import { ApiError } from "@/lib/api/errors";
import type { PublicationResponse } from "@/types/api";

const LIMIT = 20;

export default function CampaignDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [skip, setSkip] = useState(0);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  // Was previously based on campaign.status (completed/cancelled/failed) -
  // missed "partially_completed" (kept polling forever there, harmless) but
  // more importantly didn't reflect the *publications*' real state: a manual
  // retry only flips a publication to "pending" synchronously, the actual
  // outcome lands later via a Celery task, so polling needs to track that,
  // not the campaign's own status string. Same helper used by the campaigns
  // list page's "Destinazioni" column for the same reason.
  const campaignQuery = useCampaignDetail(id, {
    refetchInterval: (query) => (query.state.data && !hasUnresolvedPublications(query.state.data.stats) ? false : 5000),
  });
  const publicationsQuery = usePublications({ campaign_id: id, skip, limit: LIMIT });
  const metricsQuery = useCampaignMetrics(id);
  const channelsQuery = useChannels({});
  const usersQuery = useUsers({ limit: 100 });

  const channelInfo = useMemo(() => {
    const map = new Map<string, { name: string; platform: string }>();
    channelsQuery.data?.forEach((c) => map.set(c.id, { name: c.name, platform: c.platform }));
    return map;
  }, [channelsQuery.data]);

  const userNames = useMemo(() => {
    const map = new Map<string, string>();
    usersQuery.data?.forEach((u) => map.set(u.id, u.name));
    return map;
  }, [usersQuery.data]);

  const pauseCampaign = usePauseCampaign(id);
  const resumeCampaign = useResumeCampaign(id);
  const cancelCampaign = useCancelCampaign(id);
  const deleteCampaign = useDeleteCampaign();
  const retryPublication = useRetryPublication();
  const retryCampaignFailures = useRetryCampaignFailures();

  function withToast(promise: Promise<unknown>, successMessage: string) {
    promise
      .then(() => toast.success(successMessage))
      .catch((error) => toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita"));
  }

  const columns = useMemo<ColumnDef<PublicationResponse, unknown>[]>(
    () => [
      {
        id: "channel",
        header: "Canale",
        cell: ({ row }) => {
          const info = channelInfo.get(row.original.social_channel_id);
          return (
            <Link href={`/publications/${row.original.id}`} className="block hover:underline">
              <div className="flex items-center gap-2">
                {info && <PlatformBadge platform={info.platform} />}
                <span>{info?.name ?? "Canale sconosciuto"}</span>
              </div>
              <span className="text-[10px] text-muted-foreground">ID Buffer: {row.original.external_channel_id}</span>
            </Link>
          );
        },
      },
      {
        id: "user",
        header: "Utente",
        cell: ({ row }) => userNames.get(row.original.user_id) ?? "—",
      },
      {
        accessorKey: "status",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        id: "attempts",
        header: "Tentativi",
        cell: ({ row }) => `${row.original.attempt_count}/${row.original.max_attempts}`,
      },
      {
        accessorKey: "error_message",
        header: "Ultimo errore",
        cell: ({ row }) =>
          row.original.error_message ? (
            <Tooltip>
              <TooltipTrigger className="max-w-56 truncate text-left text-destructive">{row.original.error_message}</TooltipTrigger>
              <TooltipContent className="max-w-64">{row.original.error_message}</TooltipContent>
            </Tooltip>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: "sent_at",
        header: "Data invio",
        cell: ({ row }) => formatDateTime(row.original.submitted_at ?? row.original.published_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          ["failed", "cancelled", "retry_wait", "queued"].includes(row.original.status) ? (
            <RetryButton
              loading={retryPublication.isPending}
              onRetry={() =>
                withToast(retryPublication.mutateAsync(row.original.id), "Pubblicazione riaccodata")
              }
            />
          ) : (
            <Link href={`/publications/${row.original.id}`} className="text-sm text-muted-foreground hover:underline">
              Dettaglio
            </Link>
          ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [retryPublication.isPending, channelInfo, userNames]
  );

  if (campaignQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (campaignQuery.isError || !campaignQuery.data) {
    return <ErrorState error={campaignQuery.error} onRetry={() => campaignQuery.refetch()} />;
  }

  const { campaign, media, stats, progress_percentage } = campaignQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={campaign.title}
        description={`Modalità: ${campaign.publishing_mode} · Destinatari: ${campaign.targeting_mode}`}
        actions={
          <>
            <Button variant="outline" onClick={() => router.push(`/campaigns/new?duplicate=${campaign.id}`)}>
              <CopyIcon className="size-4" />
              Duplica
            </Button>
            {campaign.status === "running" && (
              <Button
                variant="outline"
                disabled={pauseCampaign.isPending}
                onClick={() => withToast(pauseCampaign.mutateAsync(), "Campagna in pausa")}
              >
                <PauseIcon className="size-4" />
                Pausa
              </Button>
            )}
            {campaign.status === "paused" && (
              <Button
                variant="outline"
                disabled={resumeCampaign.isPending}
                onClick={() => withToast(resumeCampaign.mutateAsync(), "Campagna ripresa")}
              >
                <PlayIcon className="size-4" />
                Riprendi
              </Button>
            )}
            {stats.failed > 0 && (
              <Button
                variant="outline"
                disabled={retryCampaignFailures.isPending}
                onClick={() =>
                  withToast(retryCampaignFailures.mutateAsync(campaign.id), "Retry delle pubblicazioni fallite avviato")
                }
              >
                <RotateCcwIcon className="size-4" />
                Riprova falliti
              </Button>
            )}
            {!["completed", "cancelled"].includes(campaign.status) && (
              <Button
                variant="outline"
                className="text-destructive"
                disabled={cancelCampaign.isPending}
                onClick={() => withToast(cancelCampaign.mutateAsync(), "Campagna annullata")}
              >
                <XIcon className="size-4" />
                Annulla
              </Button>
            )}
            <Button variant="outline" className="text-destructive" onClick={() => setDeleteConfirmOpen(true)}>
              <Trash2Icon className="size-4" />
              Elimina
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Avanzamento</CardTitle>
          </CardHeader>
          <CardContent>
            <CampaignProgress progressPercentage={progress_percentage} stats={stats} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Dettagli</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Stato</span>
              <StatusBadge status={campaign.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Creata</span>
              <span>{formatDateTime(campaign.created_at)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Programmata</span>
              <span>{formatDateTime(campaign.scheduled_at, campaign.timezone)}</span>
            </div>
            {media && (
              <div className="flex items-center gap-2 border-t pt-3">
                <MediaPreview media={media} className="size-10" />
                <span className="truncate text-xs text-muted-foreground">{media.original_filename}</span>
              </div>
            )}
            <div className="border-t pt-3">
              <p className="mb-1 text-muted-foreground">Testo predefinito</p>
              <p className="line-clamp-4">{campaign.default_text}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pubblicazioni</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DataTable
            columns={columns}
            data={publicationsQuery.data}
            isLoading={publicationsQuery.isLoading}
            isError={publicationsQuery.isError}
            error={publicationsQuery.error}
            onRetry={() => publicationsQuery.refetch()}
            emptyTitle="Nessuna pubblicazione"
          />
          {publicationsQuery.data && (
            <Pagination skip={skip} limit={LIMIT} count={publicationsQuery.data.length} onSkipChange={setSkip} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-base">Statistiche</CardTitle>
            <p className="text-xs text-muted-foreground">
              Mi piace, visualizzazioni e nuovi iscritti da Buffer. Aggiornate una volta al giorno da Buffer stesso:
              un post appena pubblicato può impiegare fino a ~24h prima che compaiano i primi dati.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={metricsQuery.isFetching}
              onClick={() => metricsQuery.refetch()}
            >
              {metricsQuery.isFetching && <Loader2Icon className="size-4 animate-spin" />}
              <BarChart3Icon className="size-4" />
              {metricsQuery.data ? "Aggiorna statistiche" : "Carica statistiche"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="border-b pb-4">
          {/* Salva le metriche nel modulo Statistiche (dati persistiti,
              navigabili per utente/canale) - a differenza del bottone sopra,
              che le mostra solo al volo senza salvarle. Vedi docs/STATISTICS.md. */}
          <SyncButton label="Sincronizza e salva in Statistiche" dispatch={() => syncCampaign(campaign.id)} />
        </CardContent>
        <CardContent className="space-y-4">
          {metricsQuery.isError && (
            <ErrorState error={metricsQuery.error} onRetry={() => metricsQuery.refetch()} />
          )}

          {metricsQuery.data && metricsQuery.data.channels.length === 0 && (
            <EmptyState
              icon={BarChart3Icon}
              title="Nessuna pubblicazione completata"
              description="Le statistiche saranno disponibili non appena almeno un canale avrà pubblicato con successo."
            />
          )}

          {metricsQuery.data && metricsQuery.data.channels.length > 0 && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {METRIC_TILE_CONFIG.filter((m) => metricsQuery.data!.totals[m.type] !== undefined).map((m) => (
                  <StatCard
                    key={m.type}
                    label={m.label}
                    value={formatMetricValue(m.type, metricsQuery.data!.totals[m.type])}
                    icon={m.icon}
                  />
                ))}
              </div>

              <div className="space-y-2">
                {metricsQuery.data.channels.map((ch) => (
                  <div key={ch.publication_id} className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
                    <PlatformBadge platform={ch.platform} className="shrink-0" />
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{ch.channel_name}</span>
                      <span className="ml-1 text-xs text-muted-foreground">({ch.user_name})</span>
                    </span>
                    {ch.error ? (
                      <span className="text-xs text-destructive">{ch.error}</span>
                    ) : ch.metrics.length === 0 ? (
                      <span className="text-xs text-muted-foreground">Ancora nessun dato (attendi fino a 24h)</span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        {ch.metrics.map((m) => (
                          <span key={m.type}>
                            <span className="font-medium text-foreground">{formatMetricValue(m.type, m.value)}</span> {m.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteConfirmOpen}
        onOpenChange={setDeleteConfirmOpen}
        title={`Eliminare "${campaign.title}"?`}
        description="Elimina definitivamente la campagna e tutti i suoi dati: destinatari risolti, pubblicazioni e relativi tentativi - anche se è già stata pubblicata su alcuni canali. Questa azione non può essere annullata."
        confirmLabel="Elimina definitivamente"
        destructive
        loading={deleteCampaign.isPending}
        onConfirm={() => {
          deleteCampaign.mutate(id, {
            onSuccess: () => {
              toast.success("Campagna eliminata");
              router.push("/campaigns");
            },
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Eliminazione non riuscita");
              setDeleteConfirmOpen(false);
            },
          });
        }}
      />
    </div>
  );
}
