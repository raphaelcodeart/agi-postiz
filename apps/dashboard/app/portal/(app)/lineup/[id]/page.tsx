import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeftIcon, CalendarClockIcon, ClockIcon, InfoIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { LinkifiedText } from "@/components/shared/linkified-text";
import { portalFetch, type PortalLineupCampaign, type PortalUser } from "@/lib/portal/server";
import { formatDateTime } from "../_lib";
import { ParticipationPanel } from "./participation-panel";

export const dynamic = "force-dynamic";

/**
 * One campaign in full, so the decision to take part is an informed one: the
 * exact text that would be posted, the media, when it goes out, and by when the
 * user has to decide.
 *
 * The text shown is the campaign's default text. Per-platform variants and the
 * personal additions (referral link, contacts, disclosure) are resolved per
 * channel at launch and are deliberately not previewed here - showing eight
 * near-identical variants would bury the thing the reader came for.
 */

export default async function PortalLineupDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [user, campaign] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalLineupCampaign>(`lineup/${id}`),
  ]);

  if (!user) redirect("/portal/login");
  if (!campaign) notFound();

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/portal/lineup"
        className="flex items-center gap-1.5 self-start text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" />
        Palinsesto
      </Link>

      <div>
        <h1 className="text-2xl font-semibold">{campaign.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <CalendarClockIcon className="size-4" />
            {campaign.scheduled_at
              ? `Pubblicazione ${formatDateTime(campaign.scheduled_at)}`
              : "Data di pubblicazione da definire"}
          </span>
          {campaign.opt_out_deadline_at && (
            <span className="flex items-center gap-1.5">
              <ClockIcon className="size-4" />
              {campaign.window_open
                ? `Decidi entro il ${formatDateTime(campaign.opt_out_deadline_at)}`
                : `Termine scaduto il ${formatDateTime(campaign.opt_out_deadline_at)}`}
            </span>
          )}
        </div>
      </div>

      {/* What the deadline means differs per campaign, and guessing wrong costs
          the user a campaign they wanted or one they did not - so it is stated. */}
      {campaign.window_open && campaign.opt_out_deadline_at && (
        <Alert>
          <InfoIcon className="size-4" />
          <AlertDescription>
            {campaign.auto_launch_at_deadline
              ? "Allo scadere del termine la campagna parte automaticamente con i canali rimasti. Dopo l'avvio non è più possibile modificare la partecipazione."
              : "Allo scadere del termine non potrai più modificare la tua partecipazione. La campagna verrà avviata da un amministratore."}
          </AlertDescription>
        </Alert>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Contenuto della campagna
        </h2>

        {campaign.media_url && (
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              {campaign.media_type === "video" ? (
                <video
                  src={campaign.media_url}
                  controls
                  preload="metadata"
                  className="max-h-[28rem] w-full bg-black object-contain"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={campaign.media_url}
                  alt=""
                  className="max-h-[28rem] w-full bg-muted object-contain"
                />
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="p-5">
            <LinkifiedText text={campaign.text} className="text-sm leading-relaxed whitespace-pre-wrap" />
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground">
          Il testo può variare leggermente sul singolo social e includere il tuo link personale,
          se lo hai impostato.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          La tua partecipazione
        </h2>
        <Card>
          <CardContent className="p-5">
            <ParticipationPanel campaign={campaign} />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
