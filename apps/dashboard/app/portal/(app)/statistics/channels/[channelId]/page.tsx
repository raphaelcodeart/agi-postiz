import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeftIcon, DownloadIcon, ExternalLinkIcon, SendIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { MetricMiniStat } from "@/components/shared/metric-mini-stat";
import { MetricTrendChart } from "@/components/shared/metric-trend-chart";
import { statMetricTiles } from "@/lib/metric-config";
import { portalFetch } from "@/lib/portal/server";
import type { StatChannelDetailResponse, StatPostRow } from "@/types/api";
import { StatTile, formatExact, formatMetricByType } from "../../../../_shared/stat-tile";

export const dynamic = "force-dynamic";

const dateFormat = new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" });

function formatDate(iso: string | null): string {
  return iso ? dateFormat.format(new Date(iso)) : "—";
}

/**
 * Un canale del promoter, post per post.
 *
 * L'equivalente di /statistics/users/{id}/channels/{channelId} lato
 * amministratore, con due differenze volute:
 *
 * - i post sono schede e non una tabella. La tabella admin vive su uno schermo
 *   largo; questa pagina si apre soprattutto dal telefono (il portale ha la
 *   barra di navigazione in basso proprio per quello), e una tabella a 5 colonne
 *   li' si legge solo scorrendo di lato.
 * - nessun bottone "aggiorna" per singolo post. Quello dell'amministratore
 *   scavalca la guardia anti-spreco di proposito; moltiplicato per ogni
 *   promoter e ogni riga diventerebbe il modo piu' facile di bruciare la quota
 *   API del cliente. L'aggiornamento qui e' uno solo, quello della pagina
 *   precedente, che sincronizza tutti i post rispettando la guardia.
 */
export default async function PortalChannelStatisticsPage({
  params,
}: {
  params: Promise<{ channelId: string }>;
}) {
  const { channelId } = await params;
  const data = await portalFetch<StatChannelDetailResponse>(`statistics/channels/${channelId}`);
  // Il backend risponde 404 sia per un canale inesistente sia per uno di un
  // altro promoter, e sono indistinguibili di proposito.
  if (!data) notFound();

  const tiles = statMetricTiles(data.totals);

  return (
    <div className="flex flex-col gap-6">
      <Button variant="outline" size="sm" asChild className="self-start">
        <Link href="/portal/statistics">
          <ArrowLeftIcon className="size-4" />
          Torna alle statistiche
        </Link>
      </Button>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <PlatformIcon platform={data.platform} className="size-10 shrink-0" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold">{data.channel_name}</h1>
            <p className="truncate text-muted-foreground">
              {data.username ? `@${data.username} · ` : ""}
              {formatExact(data.posts.length)} {data.posts.length === 1 ? "post" : "post"}
            </p>
          </div>
        </div>
        {data.posts.length > 0 && (
          <Button variant="outline" size="sm" asChild>
            <a href={`/api/portal/backend/statistics/channels/${channelId}/export.xlsx`}>
              <DownloadIcon className="size-4" />
              Esporta Excel
            </a>
          </Button>
        )}
      </div>

      {tiles.length > 0 && (
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
      )}

      {data.timeseries_monthly.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <MetricTrendChart monthly={data.timeseries_monthly} yearly={data.timeseries_yearly} />
          </CardContent>
        </Card>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          <SendIcon className="size-4" />
          I post di questo canale
        </h2>

        {data.posts.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <p className="text-sm text-muted-foreground">
                Nessun post pubblicato su questo canale.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {data.posts.map((post) => (
              <PostCard key={post.publication_id} post={post} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function PostCard({ post }: { post: StatPostRow }) {
  const tiles = statMetricTiles(post.metrics);

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <p className="min-w-0 flex-1 truncate font-medium">{post.campaign_title}</p>
          <span className="text-xs text-muted-foreground">{formatDate(post.published_at)}</span>
        </div>

        {post.last_sync_error ? (
          /* Il messaggio arriva dal provider e dice gia' di cosa si tratta -
             canale scollegato, post mai uscito su quella piattaforma (vedi
             docs/STATISTICS.md). Nasconderlo dietro un generico "errore"
             toglierebbe al promoter l'unica cosa su cui puo' agire. */
          <p className="text-xs text-destructive">{post.last_sync_error}</p>
        ) : tiles.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {post.last_synced_at
              ? "Nessun dato riportato dal social per questo post."
              : "Statistiche non ancora scaricate."}
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {tiles.map((tile) => (
              <MetricMiniStat
                key={tile.type}
                label={tile.shortLabel}
                value={formatMetricByType(tile.type, tile.value)}
              />
            ))}
          </div>
        )}

        {post.external_post_url && (
          <a
            href={post.external_post_url}
            target="_blank"
            rel="noreferrer"
            className="flex w-fit items-center gap-1 text-xs text-primary hover:underline"
          >
            Vedi il post sul social
            <ExternalLinkIcon className="size-3" />
          </a>
        )}
      </CardContent>
    </Card>
  );
}
