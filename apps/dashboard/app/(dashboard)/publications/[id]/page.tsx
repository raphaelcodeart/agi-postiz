"use client";

import { use } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { CheckCircle2Icon, XCircleIcon, BarChart3Icon, Loader2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { RetryButton } from "@/components/shared/retry-button";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { StatCard } from "@/components/shared/stat-card";
import { MediaLightbox } from "@/components/shared/media-lightbox";
import { LinkifiedText } from "@/components/shared/linkified-text";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  usePublicationDetail,
  usePublicationMetrics,
  useRetryPublication,
  useCancelPublication,
  useSkipPublication,
} from "@/hooks/use-publications";
import { formatDateTime, formatMetricValue } from "@/lib/format";
import { METRIC_TILE_CONFIG } from "@/lib/metric-config";
import { ApiError } from "@/lib/api/errors";

export default function PublicationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const detailQuery = usePublicationDetail(id);
  const metricsQuery = usePublicationMetrics(id);
  const retryPublication = useRetryPublication();
  const cancelPublication = useCancelPublication();
  const skipPublication = useSkipPublication();

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <ErrorState error={detailQuery.error} onRetry={() => detailQuery.refetch()} />;
  }

  const { publication: pub, attempts, resolved_text, channel_name, channel_platform, user_name, channel_external_link, media } =
    detailQuery.data;
  const canRetry = ["failed", "cancelled", "retry_wait", "queued"].includes(pub.status);
  const canCancel = ["pending", "queued", "retry_wait"].includes(pub.status);
  const canSkip = ["pending", "queued", "retry_wait", "failed"].includes(pub.status);
  const canShowStats = ["published", "scheduled"].includes(pub.status);
  const postUrl = pub.external_post_url ?? metricsQuery.data?.external_post_url ?? null;

  function notify(promise: Promise<unknown>, message: string) {
    promise
      .then(() => toast.success(message))
      .catch((error) => toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita"));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Pubblicazione su ${channel_name}`}
        description={`Campagna ${pub.campaign_id} · Utente ${user_name}`}
        actions={
          <>
            {canRetry && (
              <RetryButton
                size="default"
                loading={retryPublication.isPending}
                onRetry={() => notify(retryPublication.mutateAsync(pub.id), "Pubblicazione riaccodata")}
              />
            )}
            {canSkip && (
              <Button
                variant="outline"
                disabled={skipPublication.isPending}
                onClick={() => notify(skipPublication.mutateAsync(pub.id), "Pubblicazione saltata")}
              >
                Salta
              </Button>
            )}
            {canCancel && (
              <Button
                variant="outline"
                className="text-destructive"
                disabled={cancelPublication.isPending}
                onClick={() => notify(cancelPublication.mutateAsync(pub.id), "Pubblicazione annullata")}
              >
                Annulla
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Dettagli</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Stato</span>
              <StatusBadge status={pub.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Piattaforma</span>
              <PlatformBadge platform={channel_platform} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">ID Buffer canale</span>
              <span className="text-xs">{pub.external_channel_id}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Tentativi</span>
              <span>
                {pub.attempt_count}/{pub.max_attempts}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Campagna</span>
              <Link href={`/campaigns/${pub.campaign_id}`} className="hover:underline">
                Apri campagna
              </Link>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Inviato</span>
              <span>{formatDateTime(pub.submitted_at)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Pubblicato</span>
              <span>{formatDateTime(pub.published_at)}</span>
            </div>
            {/* metricsQuery can backfill this on-demand (Carica statistiche) before
                a page reload would otherwise pick up the saved value - see
                get_publication_metrics in publications.py. */}
            {postUrl ? (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Post pubblicato</span>
                <a
                  href={postUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-primary hover:underline"
                >
                  Visualizza online
                </a>
              </div>
            ) : (
              channel_external_link && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Post pubblicato</span>
                  <a
                    href={channel_external_link}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-primary hover:underline"
                    title="Link diretto al post non ancora disponibile da Buffer - apre il profilo del canale"
                  >
                    Vedi profilo canale
                  </a>
                </div>
              )
            )}
            {pub.error_message && (
              <div className="space-y-1 border-t pt-3">
                <span className="text-muted-foreground">Ultimo errore</span>
                <p className="text-destructive">{pub.error_message}</p>
                {pub.error_category && <p className="text-xs text-muted-foreground">Categoria: {pub.error_category}</p>}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Testo risolto</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {media && (
              <div className="overflow-hidden rounded-lg">
                <MediaLightbox media={media} className="max-h-96" />
              </div>
            )}
            <LinkifiedText text={resolved_text} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cronologia tentativi</CardTitle>
        </CardHeader>
        <CardContent>
          {attempts.length === 0 ? (
            <EmptyState title="Nessun tentativo registrato" />
          ) : (
            <ul className="divide-y">
              {attempts.map((attempt) => (
                <li key={attempt.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  {attempt.success ? (
                    <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-success" />
                  ) : (
                    <XCircleIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
                  )}
                  <div className="min-w-0 flex-1 space-y-0.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">Tentativo #{attempt.attempt_number}</span>
                      <span className="text-xs text-muted-foreground">{formatDateTime(attempt.started_at)}</span>
                      {attempt.http_status && (
                        <span className="text-xs text-muted-foreground">HTTP {attempt.http_status}</span>
                      )}
                      {attempt.duration_ms !== null && (
                        <span className="text-xs text-muted-foreground">{attempt.duration_ms}ms</span>
                      )}
                    </div>
                    {attempt.error_message && <p className="text-destructive">{attempt.error_message}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {canShowStats && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
            <div>
              <CardTitle className="text-base">Statistiche</CardTitle>
              <p className="text-xs text-muted-foreground">
                Dati da Buffer per questo singolo post. Aggiornati una volta al giorno da Buffer stesso: può
                impiegare fino a ~24h prima che compaiano i primi dati.
              </p>
            </div>
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
          </CardHeader>
          <CardContent>
            {metricsQuery.isError && (
              <ErrorState error={metricsQuery.error} onRetry={() => metricsQuery.refetch()} />
            )}

            {metricsQuery.data?.error && (
              <p className="text-sm text-destructive">{metricsQuery.data.error}</p>
            )}

            {metricsQuery.data && !metricsQuery.data.error && metricsQuery.data.metrics.length === 0 && (
              <EmptyState
                icon={BarChart3Icon}
                title="Ancora nessun dato"
                description="Le statistiche saranno disponibili entro ~24h dalla pubblicazione."
              />
            )}

            {metricsQuery.data && !metricsQuery.data.error && metricsQuery.data.metrics.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {METRIC_TILE_CONFIG.filter((m) =>
                  metricsQuery.data!.metrics.some((metric) => metric.type === m.type)
                ).map((m) => (
                  <StatCard
                    key={m.type}
                    label={m.label}
                    value={formatMetricValue(
                      m.type,
                      metricsQuery.data!.metrics.find((metric) => metric.type === m.type)!.value
                    )}
                    icon={m.icon}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
