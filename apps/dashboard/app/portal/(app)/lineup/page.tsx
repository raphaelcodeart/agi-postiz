import Link from "next/link";
import { redirect } from "next/navigation";
import {
  AlertTriangleIcon,
  HistoryIcon,
  SendIcon,
  CalendarClockIcon,
  CheckCircle2Icon,
  ChevronRightIcon,
  ClockIcon,
  MegaphoneIcon,
  MinusCircleIcon,
  PlayCircleIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { portalFetch, type PortalLineupCampaign, type PortalUser } from "@/lib/portal/server";
import { daysUntil, formatDateTime, lineupState, STATE_LABELS, type LineupState } from "./_lib";

export const dynamic = "force-dynamic";

/**
 * The line-up: campaigns that have been announced but not yet sent.
 *
 * Every open campaign is listed, including ones this user was not put in - that
 * is what lets someone join a campaign they would otherwise never have known
 * about. The state badge answers "am I in this?" before anything else, because
 * that is the only question the page is really asked.
 */

const STATE_STYLES: Record<LineupState, { className: string; icon: React.ComponentType<{ className?: string }> }> = {
  published: {
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    icon: SendIcon,
  },
  participating: {
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    icon: CheckCircle2Icon,
  },
  declined: {
    className: "border-muted-foreground/30 bg-muted text-muted-foreground",
    icon: MinusCircleIcon,
  },
  removed: {
    className: "border-muted-foreground/30 bg-muted text-muted-foreground",
    icon: MinusCircleIcon,
  },
  available: {
    className: "border-primary/40 bg-primary/10 text-primary",
    icon: PlayCircleIcon,
  },
  closed: {
    className: "border-muted-foreground/30 bg-muted text-muted-foreground",
    icon: ClockIcon,
  },
  no_channels: {
    className: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
    icon: AlertTriangleIcon,
  },
};

function StateBadge({ state }: { state: LineupState }) {
  const style = STATE_STYLES[state];
  const Icon = style.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${style.className}`}
    >
      <Icon className="size-3.5" />
      {STATE_LABELS[state]}
    </span>
  );
}

/**
 * The deadline is the thing that makes this page urgent, so it is stated in the
 * form a person acts on ("2 giorni") rather than only as a timestamp - and it
 * says what happens when it passes, which differs per campaign.
 */
function Deadline({ campaign }: { campaign: PortalLineupCampaign }) {
  // A campaign already gone out has no deadline left to talk about: what the
  // reader needs is when it went, not by when they could have withdrawn.
  if (campaign.phase === "launched") {
    return (
      <span className="text-muted-foreground">
        {campaign.scheduled_at
          ? `Pubblicata il ${formatDateTime(campaign.scheduled_at)}`
          : "Già pubblicata"}
      </span>
    );
  }

  if (!campaign.opt_out_deadline_at) {
    return (
      <span className="text-muted-foreground">
        Puoi modificare la tua partecipazione fino all&apos;avvio
      </span>
    );
  }

  const days = daysUntil(campaign.opt_out_deadline_at);
  const urgent = days !== null && days <= 2;

  if (!campaign.window_open) {
    return <span className="text-muted-foreground">Termine scaduto il {formatDateTime(campaign.opt_out_deadline_at)}</span>;
  }

  return (
    <span className={urgent ? "font-medium text-amber-600 dark:text-amber-400" : "text-muted-foreground"}>
      {days !== null && days <= 1 ? "Ultimo giorno" : `${days} giorni`} per decidere · entro il{" "}
      {formatDateTime(campaign.opt_out_deadline_at)}
    </span>
  );
}

export default async function PortalLineupPage() {
  const [user, lineup] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalLineupCampaign[]>("lineup"),
  ]);

  if (!user) redirect("/portal/login");

  const all = lineup ?? [];
  // Two very different things share this page: decisions with a clock on them,
  // and a record of what already went out. Keeping them in one list would bury
  // the first under the second as soon as a promoter has any history.
  const upcoming = all.filter((campaign) => campaign.phase !== "launched");
  const past = all.filter((campaign) => campaign.phase === "launched");

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Palinsesto campagne</h1>
        <p className="text-muted-foreground">
          Le campagne in programma. Puoi entrare o uscire finché il termine è aperto: dopo
          l&apos;avvio i post sono già stati inviati e non è più possibile modificarli.
        </p>
      </div>

      {upcoming.length === 0 && past.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-10 text-center">
            <MegaphoneIcon className="size-8 text-muted-foreground" />
            <p className="font-medium">Nessuna campagna in programma</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Quando verrà pubblicata una nuova campagna la troverai qui, con il testo e il
              media, prima che venga inviata.
            </p>
          </CardContent>
        </Card>
      ) : (
        <CampaignList campaigns={upcoming} />
      )}

      {past.length > 0 && (
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
              <HistoryIcon className="size-4" />
              Campagne già partite
            </h2>
            <p className="text-sm text-muted-foreground">
              Le trovi qui per consultarle. I post sono già usciti, quindi non è più possibile
              modificare la partecipazione.
            </p>
          </div>
          <CampaignList campaigns={past} />
        </section>
      )}
    </div>
  );
}

function CampaignList({ campaigns }: { campaigns: PortalLineupCampaign[] }) {
  if (campaigns.length === 0) return null;

  return (
        <div className="flex flex-col gap-3">
          {campaigns.map((campaign) => {
            const state = lineupState(campaign);
            const active = campaign.channels.filter(
              (channel) => channel.participation_status === "included"
            );

            return (
              <Link key={campaign.id} href={`/portal/lineup/${campaign.id}`} className="group">
                <Card className="transition-all group-hover:border-primary/40 group-hover:shadow-md">
                  <CardContent className="flex flex-col gap-4 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-base font-medium">{campaign.title}</p>
                        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                          {campaign.text}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StateBadge state={state} />
                        <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                      {campaign.phase !== "launched" && (
                        <span className="flex items-center gap-1.5">
                          <CalendarClockIcon className="size-4 shrink-0 text-muted-foreground" />
                          {campaign.scheduled_at ? (
                            <>Pubblicazione {formatDateTime(campaign.scheduled_at)}</>
                          ) : (
                            <span className="text-muted-foreground">Pubblicazione da definire</span>
                          )}
                        </span>
                      )}

                      <span className="flex items-center gap-1.5">
                        <ClockIcon className="size-4 shrink-0 text-muted-foreground" />
                        <Deadline campaign={campaign} />
                      </span>
                    </div>

                    {active.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-muted-foreground">Con i tuoi canali:</span>
                        {active.map((channel) => (
                          <Badge key={channel.id} variant="outline" className="gap-1.5 font-normal">
                            <PlatformIcon platform={channel.platform} className="size-3.5" />
                            {channel.name}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {state === "no_channels" && campaign.phase !== "launched" && (
                      <p className="text-sm text-amber-600 dark:text-amber-400">
                        Collega un canale per poter partecipare.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
  );
}
