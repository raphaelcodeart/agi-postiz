import Link from "next/link";
import { CalendarClockIcon, CheckCircle2Icon, ClockIcon, MegaphoneIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import type { PortalLineupCampaign } from "@/lib/portal/server";
import { daysUntil, formatDateTime, lineupState } from "./lineup/_lib";

/**
 * The open campaigns, at the top of the user's dashboard.
 *
 * This is the one thing on the page with a clock running against it: a campaign
 * announced on Monday and launched on Friday is only refusable in between, and a
 * promoter who does not open the portal in those days has effectively been
 * opted in by inattention. So it leads, it states the deadline in days, and it
 * makes the two decisions reachable in one click from here.
 */
export function LineupSpotlight({ campaigns }: { campaigns: PortalLineupCampaign[] }) {
  const open = campaigns.filter((campaign) => campaign.window_open);
  if (open.length === 0) return null;

  // Soonest deadline first: that is the order in which they stop being decisions.
  const sorted = [...open].sort((a, b) => {
    const left = a.opt_out_deadline_at ? new Date(a.opt_out_deadline_at).getTime() : Infinity;
    const right = b.opt_out_deadline_at ? new Date(b.opt_out_deadline_at).getTime() : Infinity;
    return left - right;
  });

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          <MegaphoneIcon className="size-4" />
          Campagne in programma
        </h2>
        <Link href="/portal/lineup" className="text-sm text-primary hover:underline">
          Vedi il palinsesto
        </Link>
      </div>

      <div className="flex flex-col gap-2">
        {sorted.slice(0, 3).map((campaign) => {
          const state = lineupState(campaign);
          const participating = state === "participating";
          const days = daysUntil(campaign.opt_out_deadline_at);
          const urgent = days !== null && days <= 2;
          const active = campaign.channels.filter((c) => c.participation_status === "included");

          return (
            <Card
              key={campaign.id}
              className={
                "transition-shadow hover:shadow-md " +
                (urgent ? "border-amber-500/40" : participating ? "border-emerald-500/30" : "border-primary/30")
              }
            >
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{campaign.title}</p>
                    <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">
                      {campaign.text}
                    </p>
                  </div>
                  {participating ? (
                    <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                      <CheckCircle2Icon className="size-3.5" />
                      Partecipi
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                      Puoi partecipare
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <CalendarClockIcon className="size-4" />
                    {campaign.scheduled_at
                      ? formatDateTime(campaign.scheduled_at)
                      : "Data da definire"}
                  </span>
                  {campaign.opt_out_deadline_at && (
                    <span
                      className={
                        "flex items-center gap-1.5 " +
                        (urgent
                          ? "font-medium text-amber-600 dark:text-amber-400"
                          : "text-muted-foreground")
                      }
                    >
                      <ClockIcon className="size-4" />
                      {days !== null && days <= 1
                        ? "Ultimo giorno per decidere"
                        : `${days} giorni per decidere`}
                    </span>
                  )}
                  {active.length > 0 && (
                    <span className="flex items-center gap-1.5">
                      {active.slice(0, 4).map((channel) => (
                        <PlatformIcon
                          key={channel.id}
                          platform={channel.platform}
                          className="size-4"
                        />
                      ))}
                    </span>
                  )}
                </div>

                <Button asChild size="sm" variant={participating ? "outline" : "default"} className="self-start">
                  <Link href={`/portal/lineup/${campaign.id}`}>
                    {participating ? "Vedi dettagli o rinuncia" : "Vedi e partecipa"}
                  </Link>
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
