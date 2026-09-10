import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowRightIcon,
  EyeIcon,
  HeartIcon,
  InfoIcon,
  Link2Icon,
  SendIcon,
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
  type PortalLineupCampaign,
  type PortalOverview,
  type PortalUser,
} from "@/lib/portal/server";
import { ActivityChart } from "./activity-chart";
import { LineupSpotlight } from "./lineup-spotlight";

export const dynamic = "force-dynamic";

/**
 * The promoter's home.
 *
 * Ordered by what is time-sensitive, not by what is impressive. Campaigns open
 * for a decision come first: they are the only thing here with a clock running
 * against them, and a promoter who does not see them in time has been opted in
 * by inattention. Results come after - they are always there tomorrow.
 *
 * Section shortcuts used to live here as cards; they moved into the shell's own
 * navigation (portal-nav.tsx), where they are reachable from every page rather
 * than only this one.
 */

const numberFormat = new Intl.NumberFormat("it-IT");
const compactFormat = new Intl.NumberFormat("it-IT", { notation: "compact", maximumFractionDigits: 1 });

function formatCompact(value: number): string {
  return value >= 10_000 ? compactFormat.format(value) : numberFormat.format(value);
}

/**
 * Headline figure. The icon repeats the metric's meaning for someone scanning
 * the row rather than reading it.
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

function SectionHeading({
  icon: Icon,
  children,
  href,
  linkLabel,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
        <Icon className="size-4" />
        {children}
      </h2>
      {href && (
        <Link href={href} className="flex items-center gap-1 text-sm text-primary hover:underline">
          {linkLabel}
          <ArrowRightIcon className="size-3.5" />
        </Link>
      )}
    </div>
  );
}

export default async function PortalDashboardPage() {
  const [user, overview, campaigns, lineup] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalOverview>("overview"),
    portalFetch<PortalCampaign[]>("campaigns"),
    portalFetch<PortalLineupCampaign[]>("lineup"),
  ]);

  if (!user) redirect("/portal/login");

  const stats = overview?.stats;
  const recentCampaigns = (campaigns ?? []).slice(0, 4);
  const engagement = stats ? stats.total_likes + stats.total_comments + stats.total_shares : 0;
  const hasResults = Boolean(stats && stats.posts_published > 0);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Ciao {user.name.split(" ")[0]}</h1>
          <p className="text-muted-foreground">
            {stats && stats.channels_connected > 0
              ? `${stats.channels_connected} ${stats.channels_connected === 1 ? "canale collegato" : "canali collegati"} · ${stats.campaigns_joined} ${stats.campaigns_joined === 1 ? "campagna" : "campagne"}`
              : "Collega i tuoi canali per iniziare."}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/portal/channels">
            <Link2Icon className="size-4" />
            Collega un canale
          </Link>
        </Button>
      </div>

      {/* Only reachable now when an operator has switched automatic activation
          off, or the account was suspended - so it says what actually unblocks
          it rather than "wait". */}
      {!user.is_active_for_campaigns && (
        <Alert>
          <InfoIcon className="size-4" />
          <AlertTitle>Account non ancora attivo per le campagne</AlertTitle>
          <AlertDescription>
            Puoi già collegare i tuoi canali: collegandone uno il tuo account si attiva
            automaticamente. Se hai già collegato dei canali, contatta l&apos;amministratore.
          </AlertDescription>
        </Alert>
      )}

      {/* First, always: the only thing on this page with a deadline. */}
      <LineupSpotlight campaigns={lineup ?? []} />

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
        <section className="flex flex-col gap-3">
          <SectionHeading icon={TrendingUpIcon}>I tuoi risultati</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
              icon={SendIcon}
              hint={stats.posts_failed > 0 ? `${stats.posts_failed} non riusciti` : undefined}
            />
          </div>
          {/* Says why the numbers are what they are, instead of leaving a wall of
              zeroes looking like something is broken. */}
          {!hasResults && (
            <p className="text-xs text-muted-foreground">
              I numeri compaiono dopo le prime pubblicazioni: i social li rendono disponibili
              nelle ore successive al post.
            </p>
          )}
        </section>
      )}

      {overview && overview.timeline.length > 0 && hasResults && (
        <Card>
          <CardContent className="p-5">
            <ActivityChart data={overview.timeline} />
          </CardContent>
        </Card>
      )}

      {overview && overview.top_channels.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeading icon={TrendingUpIcon} href="/portal/channels" linkLabel="Tutti i canali">
            Canali migliori
          </SectionHeading>
          <div className="flex flex-col gap-2">
            {overview.top_channels.map((channel) => (
              <Card key={`${channel.platform}-${channel.name}`}>
                <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
                  <PlatformIcon platform={channel.platform} className="size-8 shrink-0" />
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
        <SectionHeading
          icon={SendIcon}
          href={recentCampaigns.length > 0 ? "/portal/campaigns" : undefined}
          linkLabel="Vedi tutte"
        >
          Ultime campagne
        </SectionHeading>

        {recentCampaigns.length === 0 ? (
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-6">
              <p className="text-sm text-muted-foreground">
                Non fai ancora parte di nessuna campagna.
              </p>
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/lineup">Vedi il palinsesto</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {recentCampaigns.map((campaign) => {
              const done = campaign.published + campaign.failed;
              const progress = campaign.channels_targeted
                ? Math.round((done / campaign.channels_targeted) * 100)
                : 0;
              const declined =
                campaign.channels_targeted === 0 &&
                (campaign.participation_withdrawn > 0 || campaign.participation_removed > 0);

              return (
                <Card key={campaign.id} className="transition-shadow hover:shadow-md">
                  <CardContent className="flex flex-col gap-3 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className={"font-medium " + (declined ? "text-muted-foreground" : "")}>
                        {campaign.title}
                      </p>
                      {declined ? (
                        <span className="text-sm text-muted-foreground">
                          {campaign.participation_withdrawn > 0
                            ? "non hai partecipato"
                            : "escluso dall'amministratore"}
                        </span>
                      ) : (
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
                      )}
                    </div>
                    {!declined && (
                      /* Progress of this user's own share of the campaign. */
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-brand-gradient transition-[width] duration-700"
                          style={{ width: `${Math.min(100, progress)}%` }}
                        />
                      </div>
                    )}
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
