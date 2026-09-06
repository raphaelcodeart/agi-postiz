"use client";

import { use } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowLeftIcon, DownloadIcon, ExternalLinkIcon, Loader2Icon, RefreshCwIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { DataTable } from "@/components/shared/data-table";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { MetricMiniStat } from "@/components/shared/metric-mini-stat";
import { MetricTrendChart } from "../../../../_components/metric-trend-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChannelStatistics, useSyncSinglePostMutation } from "@/hooks/use-statistics";
import { channelExportUrl } from "@/services/statistics";
import { statMetricTiles } from "@/lib/metric-config";
import { formatDateTime, formatMetricValue } from "@/lib/format";
import { queryKeys } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import type { StatPostRow } from "@/types/api";

export default function ChannelStatisticsPage({
  params,
}: {
  params: Promise<{ id: string; channelId: string }>;
}) {
  const { id, channelId } = use(params);
  const channelQuery = useChannelStatistics(id, channelId);
  const syncPost = useSyncSinglePostMutation();
  const queryClient = useQueryClient();

  function refreshPost(publicationId: string) {
    syncPost.mutate(publicationId, {
      onSuccess: () => {
        toast.success("Post aggiornato");
        queryClient.invalidateQueries({ queryKey: queryKeys.statistics.channelDetail(id, channelId) });
      },
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
    });
  }

  const columns: ColumnDef<StatPostRow, unknown>[] = [
    {
      id: "campaign",
      header: "Campagna",
      cell: ({ row }) => (
        <Link href={`/campaigns/${row.original.campaign_id}`} className="hover:underline">
          {row.original.campaign_title}
        </Link>
      ),
    },
    {
      id: "published_at",
      header: "Pubblicato",
      cell: ({ row }) => formatDateTime(row.original.published_at),
    },
    {
      id: "metrics",
      header: "Statistiche",
      cell: ({ row }) => {
        if (row.original.last_sync_error) {
          return (
            <Tooltip>
              <TooltipTrigger className="text-xs text-destructive">Errore di sincronizzazione</TooltipTrigger>
              <TooltipContent className="max-w-64">{row.original.last_sync_error}</TooltipContent>
            </Tooltip>
          );
        }
        const tiles = statMetricTiles(row.original.metrics);
        if (tiles.length === 0) {
          return (
            <span className="text-xs text-muted-foreground">
              {row.original.last_synced_at ? "Nessun dato riportato" : "Non ancora sincronizzato"}
            </span>
          );
        }
        return (
          <div className="flex flex-wrap gap-1.5">
            {tiles.map((t) => (
              <MetricMiniStat key={t.type} label={t.shortLabel} value={formatMetricValue(t.type, t.value)} />
            ))}
          </div>
        );
      },
    },
    {
      id: "last_synced_at",
      header: "Ultimo sync",
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{formatDateTime(row.original.last_synced_at)}</span>,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          {row.original.external_post_url && (
            <Button variant="ghost" size="xs" render={<a href={row.original.external_post_url ?? undefined} target="_blank" rel="noreferrer" />}>
              <ExternalLinkIcon className="size-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="xs"
            disabled={syncPost.isPending}
            onClick={() => refreshPost(row.original.publication_id)}
            title="Aggiorna statistiche di questo post"
          >
            {syncPost.isPending && syncPost.variables === row.original.publication_id ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <RefreshCwIcon className="size-3.5" />
            )}
          </Button>
          <Link href={`/publications/${row.original.publication_id}`} className="text-xs text-muted-foreground hover:underline">
            Dettaglio
          </Link>
        </div>
      ),
    },
  ];

  if (channelQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (channelQuery.isError || !channelQuery.data) {
    return <ErrorState error={channelQuery.error} onRetry={() => channelQuery.refetch()} />;
  }

  const data = channelQuery.data;
  const tiles = statMetricTiles(data.totals);

  return (
    <div className="space-y-6">
      <Button variant="outline" size="sm" asChild>
        <Link href={`/statistics/users/${id}`}>
          <ArrowLeftIcon className="size-4" />
          Torna a {data.user_name}
        </Link>
      </Button>

      <PageHeader
        title={data.channel_name}
        description={`${data.username ? `@${data.username} · ` : ""}${data.user_name}`}
        actions={
          <Button variant="outline" size="sm" render={<a href={channelExportUrl(id, channelId)} />}>
            <DownloadIcon className="size-4" />
            Esporta Excel
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-3">
            <PlatformIcon platform={data.platform} />
            <span className="text-sm text-muted-foreground">{data.posts.length} post sincronizzati</span>
          </div>
          <span className="text-xs text-muted-foreground">
            Ultima sincronizzazione: <span className="font-medium text-foreground">{formatDateTime(data.last_synced_at)}</span>
          </span>
        </CardContent>
      </Card>

      {tiles.length === 0 ? (
        <EmptyState title="Nessuna statistica ancora sincronizzata per questo canale" />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {tiles.map((tile) => (
            <StatCard key={tile.type} label={tile.label} value={formatMetricValue(tile.type, tile.value)} icon={tile.icon} />
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Andamento nel tempo</CardTitle>
        </CardHeader>
        <CardContent>
          <MetricTrendChart monthly={data.timeseries_monthly} yearly={data.timeseries_yearly} />
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <DataTable columns={columns} data={data.posts} emptyTitle="Nessuna campagna ancora pubblicata su questo canale" />
        </CardContent>
      </Card>
    </div>
  );
}
