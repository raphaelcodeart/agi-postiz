import Link from "next/link";
import { redirect } from "next/navigation";
import {
  BarChart3Icon,
  EyeIcon,
  HeartIcon,
  InfoIcon,
  Link2Icon,
  MegaphoneIcon,
  Share2Icon,
  TrendingUpIcon,
  UsersIcon,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import {
  portalFetch,
  type PortalCampaign,
  type PortalOverview,
  type PortalUser,
} from "@/lib/portal/server";
import { ActivityChart } from "./activity-chart";

export const dynamic = "force-dynamic";

const numberFormat = new Intl.NumberFormat("it-IT");
const compactFormat = new Intl.NumberFormat("it-IT", { notation: "compact", maximumFractionDigits: 1 });

function formatCompact(value: number): string {
  return value >= 10_000 ? compactFormat.format(value) : numberFormat.format(value);
}

/**
 * Headline figure. The icon is a quiet marker, not decoration: it repeats the
 * metric's meaning for someone scanning the row rather than reading it.
 */
function StatTile({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  hint?: string;
  tone?: "default" | "accent";
}) {
  return (
    <div
      className={
        "group relative overflow-hidden rounded-xl border bg-card p-4 transition-shadow hover:shadow-md " +
        (tone === "accent" ? "border-primary/30" : "")
      }
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
        <Icon
          className={
            "size-4 shrink-0 transition-transform group-hover:scale-110 " +
            (tone === "accent" ? "text-primary" : "text-muted-foreground")
          }
        />
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Top-of-page shortcuts to the sections, so the dashboard is a hub not a dead end. */
function QuickLinks({ channels, campaigns }: { channels: number; campaigns: number }) {
  const links = [
    {
      href: "/portal/channels",
      label: "I miei canali",
      count: channels,
      icon: Link2Icon,
      description: "Collega e gestisci i profili",
    },
    {
      href: "/portal/campaigns",
      label: "Le mie campagne",
      count: campaigns,
      icon: MegaphoneIcon,
      description: "Risultati per campagna",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="group flex items-center gap-4 rounded-xl border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-md"
        >
          <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground transition-transform group-hover:scale-105">
            <link.icon className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline gap-2">
              <span className="font-medium">{link.label}</span>
              <span className="text-sm text-muted-foreground tabular-nums">{link.count}</span>
            </span>
            <span className="block truncate text-sm text-muted-foreground">{link.description}</span>
          </span>
        </Link>
      ))}
    </div>
  );
}

export default async function PortalDashboardPage() {
  const [user, overview, campaigns] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalOverview>("overview"),
    portalFetch<PortalCampaign[]>("campaigns"),
  ]);

  if (!user) redirect("/portal/login");

  const stats = overview?.stats;
  const recentCampaigns = (campaigns ?? []).slice(0, 5);
  const engagement = stats ? stats.total_likes + stats.total_comments + stats.total_shares : 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Ciao {user.name.split(" ")[0]}</h1>
          <p className="text-muted-foreground">I risultati dei tuoi canali e delle tue campagne.</p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/portal/channels">
            <Link2Icon className="size-4" />
            Collega un canale
          </Link>
        </Button>
      </div>

      {/* Right after registration an account is inactive by design, so this is an
          explanation rather than an error - nothing is broken. */}
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

      <QuickLinks
        channels={stats?.channels_connected ?? 0}
        campaigns={stats?.campaigns_joined ?? 0}
      />

      {stats && stats.channels_connected === 0 && (
        <Card className="border-primary/30 bg-primary/5">
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
                Collega ora
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {stats && (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Visualizzazioni"
            value={formatCompact(stats.total_views)}
            icon={EyeIcon}
            tone="accent"
          />
          <StatTile
            label="Copertura"
            value={formatCompact(stats.total_reach)}
            icon={UsersIcon}
            hint={`${formatCompact(stats.total_impressions)} impression`}
          />
          <StatTile
            label="Interazioni"
            value={formatCompact(engagement)}
            icon={HeartIcon}
            hint={`${numberFormat.format(stats.total_shares)} condivisioni`}
          />
          <StatTile
            label="Post pubblicati"
            value={numberFormat.format(stats.posts_published)}
            icon={Share2Icon}
            hint={stats.posts_failed > 0 ? `${stats.posts_failed} non riusciti` : undefined}
          />
        </section>
      )}

      {overview && overview.timeline.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <ActivityChart data={overview.timeline} />
          </CardContent>
        </Card>
      )}

      {overview && overview.top_channels.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            <TrendingUpIcon className="size-4" />
            Canali migliori
          </h2>
          <div className="flex flex-col gap-2">
            {overview.top_channels.map((channel) => (
              <Card key={`${channel.platform}-${channel.name}`}>
                <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
                  <PlatformIcon platform={channel.platform} className="size-5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate font-medium">{channel.name}</span>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    {numberFormat.format(channel.posts)} post
                  </span>
                  <span className="text-sm tabular-nums">
                    {formatCompact(channel.impressions)}{" "}
                    <span className="text-muted-foreground">impression</span>
                  </span>
                  <span className="text-sm tabular-nums">
                    {formatCompact(channel.likes)}{" "}
                    <span className="text-muted-foreground">mi piace</span>
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            <BarChart3Icon className="size-4" />
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
            {recentCampaigns.map((campaign) => {
              const done = campaign.published + campaign.failed;
              const progress = campaign.channels_targeted
                ? Math.round((done / campaign.channels_targeted) * 100)
                : 0;
              return (
                <Card key={campaign.id} className="transition-shadow hover:shadow-md">
                  <CardContent className="flex flex-col gap-3 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="font-medium">{campaign.title}</p>
                      <div className="flex items-center gap-4 text-sm tabular-nums">
                        <span className="text-muted-foreground">
                          {campaign.channels_targeted} canali
                        </span>
                        <span className="text-emerald-600 dark:text-emerald-400">
                          {campaign.published} pubblicati
                        </span>
                        {campaign.pending > 0 && (
                          <span className="text-amber-600 dark:text-amber-400">
                            {campaign.pending} in corso
                          </span>
                        )}
                        {campaign.failed > 0 && (
                          <span className="text-destructive">{campaign.failed} non riusciti</span>
                        )}
                      </div>
                    </div>
                    {/* Progress of this user's own share of the campaign. */}
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-brand-gradient transition-[width] duration-700"
                        style={{ width: `${Math.min(100, progress)}%` }}
                      />
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
