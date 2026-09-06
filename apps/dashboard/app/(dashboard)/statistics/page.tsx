"use client";

import Link from "next/link";
import { ChevronRightIcon, DownloadIcon, TrophyIcon, UsersIcon, Share2Icon, SendIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PlatformDistributionChart } from "@/components/shared/platform-distribution-chart";
import { MetricMiniStat } from "@/components/shared/metric-mini-stat";
import { MetricTrendChart } from "./_components/metric-trend-chart";
import { SyncButton } from "@/components/shared/sync-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatisticsDashboard, useSyncAllMutation } from "@/hooks/use-statistics";
import { dashboardExportUrl } from "@/services/statistics";
import { ROW_SUMMARY_METRIC_KEYS, shortLabelForMetric, statMetricTiles } from "@/lib/metric-config";
import { formatDateTime, formatMetricValue } from "@/lib/format";

export default function StatisticsDashboardPage() {
  const dashboardQuery = useStatisticsDashboard();
  const syncAll = useSyncAllMutation();

  if (dashboardQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (dashboardQuery.isError || !dashboardQuery.data) {
    return <ErrorState error={dashboardQuery.error} onRetry={() => dashboardQuery.refetch()} />;
  }

  const data = dashboardQuery.data;
  const tiles = statMetricTiles(data.totals);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Statistiche"
        description="Il valore che i tuoi promoter portano alle campagne: views, interazioni e nuovi iscritti generati sui social, canale per canale."
        actions={
          <Button variant="outline" size="sm" render={<a href={dashboardExportUrl()} />}>
            <DownloadIcon className="size-4" />
            Esporta Excel
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <UsersIcon className="size-4" /> {data.user_count} utenti
            </span>
            <span className="flex items-center gap-1.5">
              <Share2Icon className="size-4" /> {data.channel_count} canali
            </span>
            <span className="flex items-center gap-1.5">
              <SendIcon className="size-4" /> {data.post_count} post sincronizzati
            </span>
          </div>
          <SyncButton label="Sincronizza tutto" dispatch={() => syncAll.mutateAsync()} lastSyncedAt={data.last_synced_at} />
        </CardContent>
      </Card>

      {tiles.length === 0 ? (
        <EmptyState
          icon={TrophyIcon}
          title="Nessuna statistica ancora sincronizzata"
          description='Premi "Sincronizza tutto" per scaricare da Buffer le metriche di tutti i post pubblicati finora.'
        />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {tiles.map((tile) => (
            <StatCard
              key={tile.type}
              label={tile.label}
              value={formatMetricValue(tile.type, tile.value)}
              icon={tile.icon}
            />
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Distribuzione per piattaforma</CardTitle>
          </CardHeader>
          <CardContent>
            <PlatformDistributionChart distribution={data.platform_distribution} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrophyIcon className="size-4 text-primary" /> Classifica promoter
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {data.users.length === 0 ? (
              <div className="px-6 pb-6">
                <EmptyState title="Nessun utente con dati sincronizzati" />
              </div>
            ) : (
              <ul className="divide-y">
                {data.users.map((user, index) => (
                  <li key={user.user_id}>
                    <Link
                      href={`/statistics/users/${user.user_id}`}
                      className="flex items-center gap-3 px-6 py-3 transition-colors hover:bg-muted/50"
                    >
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{user.user_name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {user.company_name || "—"} · {user.channel_count} canali · {user.post_count} post
                        </p>
                      </div>
                      <div className="hidden shrink-0 items-center gap-1.5 lg:flex">
                        {ROW_SUMMARY_METRIC_KEYS.map((key) => {
                          const value = user.totals[key];
                          return (
                            <MetricMiniStat
                              key={key}
                              label={shortLabelForMetric(key)}
                              value={value === null ? "—" : formatMetricValue(key, value)}
                            />
                          );
                        })}
                      </div>
                      <span className="hidden text-xs text-muted-foreground xl:block">
                        Sync: {formatDateTime(user.last_synced_at)}
                      </span>
                      <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
