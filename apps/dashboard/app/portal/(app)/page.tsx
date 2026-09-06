import Link from "next/link";
import { redirect } from "next/navigation";
import { InfoIcon, Link2Icon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  portalFetch,
  type PortalCampaign,
  type PortalStats,
  type PortalUser,
} from "@/lib/portal/server";

export const dynamic = "force-dynamic";

function formatNumber(value: number): string {
  return new Intl.NumberFormat("it-IT").format(value);
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export default async function PortalDashboardPage() {
  const [user, stats, campaigns] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalStats>("stats"),
    portalFetch<PortalCampaign[]>("campaigns"),
  ]);

  if (!user) redirect("/portal/login");

  const recentCampaigns = (campaigns ?? []).slice(0, 5);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Ciao {user.name.split(" ")[0]}</h1>
        <p className="text-muted-foreground">I risultati dei tuoi canali e delle tue campagne.</p>
      </div>

      {/* An inactive account is the normal state right after registration, so it
          gets an explanation rather than an error: nothing is broken, the
          account is simply not targetable by campaigns yet. */}
      {!user.is_active_for_campaigns && (
        <Alert>
          <InfoIcon className="size-4" />
          <AlertTitle>Account in attesa di attivazione</AlertTitle>
          <AlertDescription>
            Puoi già collegare i tuoi canali. Verrai incluso nelle campagne appena un
            amministratore attiva il tuo account.
          </AlertDescription>
        </Alert>
      )}

      {stats && stats.channels_connected === 0 && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 p-6">
            <div>
              <p className="font-medium">Non hai ancora collegato nessun canale</p>
              <p className="text-sm text-muted-foreground">
                Collega i tuoi profili social per entrare nelle campagne.
              </p>
            </div>
            <Button asChild>
              <Link href="/portal/channels">
                <Link2Icon className="size-4" />
                Collega un canale
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {stats && (
        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Riepilogo
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Canali attivi" value={formatNumber(stats.channels_connected)} />
            <StatTile label="Campagne" value={formatNumber(stats.campaigns_joined)} />
            <StatTile
              label="Post pubblicati"
              value={formatNumber(stats.posts_published)}
              hint={stats.posts_failed > 0 ? `${formatNumber(stats.posts_failed)} non riusciti` : undefined}
            />
            <StatTile label="Visualizzazioni" value={formatNumber(stats.total_views)} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Impression" value={formatNumber(stats.total_impressions)} />
            <StatTile label="Copertura" value={formatNumber(stats.total_reach)} />
            <StatTile label="Mi piace" value={formatNumber(stats.total_likes)} />
            <StatTile
              label="Commenti e condivisioni"
              value={formatNumber(stats.total_comments + stats.total_shares)}
            />
          </div>
        </section>
      )}

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Ultime campagne
          </h2>
          {recentCampaigns.length > 0 && (
            <Link href="/portal/campaigns" className="text-sm text-primary hover:underline">
              Vedi tutte
            </Link>
          )}
        </div>

        {recentCampaigns.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Non fai ancora parte di nessuna campagna.
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {recentCampaigns.map((campaign) => (
              <Card key={campaign.id}>
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 py-4">
                  <CardTitle className="text-base font-medium">{campaign.title}</CardTitle>
                  <div className="flex items-center gap-4 text-sm tabular-nums">
                    <span className="text-muted-foreground">
                      {formatNumber(campaign.channels_targeted)} canali
                    </span>
                    <span className="text-emerald-600 dark:text-emerald-400">
                      {formatNumber(campaign.published)} pubblicati
                    </span>
                    {campaign.pending > 0 && (
                      <span className="text-amber-600 dark:text-amber-400">
                        {formatNumber(campaign.pending)} in corso
                      </span>
                    )}
                    {campaign.failed > 0 && (
                      <span className="text-destructive">
                        {formatNumber(campaign.failed)} non riusciti
                      </span>
                    )}
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
