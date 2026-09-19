import Link from "next/link";
import { redirect } from "next/navigation";
import { BarChart3Icon, ChevronRightIcon, DownloadIcon, InfoIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { MetricMiniStat } from "@/components/shared/metric-mini-stat";
import { MetricTrendChart } from "@/components/shared/metric-trend-chart";
import { ROW_SUMMARY_METRIC_KEYS, shortLabelForMetric, statMetricTiles } from "@/lib/metric-config";
import { portalFetch, type PortalUser } from "@/lib/portal/server";
import type { StatUserDetailResponse } from "@/types/api";
import { StatTile, formatExact, formatMetric, formatMetricByType } from "../../_shared/stat-tile";
import { SyncStatsButton } from "./sync-stats-button";

export const dynamic = "force-dynamic";

/**
 * Le statistiche complete del promoter: la stessa sezione che l'amministratore
 * ha su /statistics/users/{id}, ristretta a chi e' collegato.
 *
 * Non ricalcola niente: GET /portal/statistics passa per gli stessi
 * statistics_service.build_user_detail che alimentano la pagina admin, quindi i
 * numeri che il promoter legge qui e quelli che l'amministratore legge per lui
 * sono per costruzione gli stessi.
 *
 * Il livello "classifica dei promoter" della dashboard admin qui non esiste, ed
 * e' voluto: mostra chi rende piu' di chi, cioe' esattamente l'unica cosa di
 * quel modulo che un promoter non deve vedere degli altri.
 */
export default async function PortalStatisticsPage() {
  const data = await portalFetch<StatUserDetailResponse>("statistics");

  // portalFetch restituisce null sia senza sessione sia quando il backend non
  // risponde, e le due cose vanno trattate diversamente: la prima e' un rientro
  // al login, la seconda un guasto momentaneo da dire e basta. Il layout ha gia'
  // verificato la sessione, quindi qui si ricontrolla solo in questo ramo.
  if (!data) {
    const user = await portalFetch<PortalUser>("me");
    if (!user) redirect("/portal/login");
    return (
      <Alert>
        <InfoIcon className="size-4" />
        <AlertDescription>
          Le statistiche non sono raggiungibili in questo momento. Riprova fra poco.
        </AlertDescription>
      </Alert>
    );
  }

  const tiles = statMetricTiles(data.totals);
  const postCount = data.channels.reduce((sum, channel) => sum + channel.post_count, 0);
  const hasData = tiles.length > 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Le tue statistiche</h1>
          <p className="text-muted-foreground">
            {postCount > 0
              ? `${formatExact(postCount)} post su ${data.channels.length} ${data.channels.length === 1 ? "canale" : "canali"}`
              : "Ancora nessun post pubblicato."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {hasData && (
            <Button variant="outline" size="sm" asChild>
              {/* Link normale e non fetch via JS: il proxy BFF sta sullo stesso
                  dominio e inoltra il content-disposition, quindi il cookie di
                  sessione viaggia da solo e il download parte come una
                  navigazione qualsiasi. */}
              <a href="/api/portal/backend/statistics/export.xlsx">
                <DownloadIcon className="size-4" />
                Esporta Excel
              </a>
            </Button>
          )}
          <SyncStatsButton lastSyncedAt={data.last_synced_at} />
        </div>
      </div>

      {!hasData ? (
        <Card>
          <CardContent className="flex flex-col gap-2 p-6">
            <p className="font-medium">Nessuna statistica disponibile</p>
            <p className="text-sm text-muted-foreground">
              I numeri compaiono dopo le prime pubblicazioni. I social li calcolano una volta al
              giorno, quindi un post appena uscito resta a zero per qualche ora: non è un errore.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {tiles.map((tile, index) => (
              <StatTile
                key={tile.type}
                label={tile.label}
                value={formatMetricByType(tile.type, tile.value)}
                icon={tile.icon}
                tone={index === 0 ? "accent" : "default"}
              />
            ))}
          </div>

          <Card>
            <CardContent className="p-5">
              <MetricTrendChart monthly={data.timeseries_monthly} yearly={data.timeseries_yearly} />
            </CardContent>
          </Card>
        </>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          <BarChart3Icon className="size-4" />
          I tuoi canali
        </h2>

        {data.channels.length === 0 ? (
          <Alert>
            <InfoIcon className="size-4" />
            <AlertDescription>
              Nessun canale ha ancora pubblicato. Collega i tuoi profili e partecipa a una campagna
              per vedere qui i risultati, canale per canale.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-col gap-2">
            {data.channels.map((channel) => (
              <Card key={channel.social_channel_id} className="transition-shadow hover:shadow-md">
                <Link
                  href={`/portal/statistics/channels/${channel.social_channel_id}`}
                  className="block"
                >
                  <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-3 p-4">
                    <PlatformIcon platform={channel.platform} className="size-8 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{channel.channel_name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {channel.username ? `@${channel.username} · ` : ""}
                        {formatExact(channel.post_count)} post
                      </p>
                    </div>
                    {/* Le stesse 4 metriche per riga delle liste admin
                        (ROW_SUMMARY_METRIC_KEYS): il totale del canale si legge
                        senza doverlo aprire. */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {ROW_SUMMARY_METRIC_KEYS.map((key) => {
                        const value = channel.totals[key];
                        return (
                          <MetricMiniStat
                            key={key}
                            label={shortLabelForMetric(key)}
                            value={value === null ? "—" : formatMetric(key, value)}
                          />
                        );
                      })}
                    </div>
                    <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground" />
                  </CardContent>
                </Link>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
