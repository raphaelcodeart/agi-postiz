import Link from "next/link";
import { redirect } from "next/navigation";
import { MinusCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { portalFetch, type PortalCampaign, type PortalUser } from "@/lib/portal/server";

export const dynamic = "force-dynamic";

/**
 * The user's own history: every campaign they took part in, and every one they
 * were offered and declined.
 *
 * The refusals matter as much as the participations. A promoter asking "did I
 * actually opt out of that one, or did it just never reach my channels?" has no
 * other place to check - a declined campaign produces no publications at all,
 * so a table built only from published posts answers the question by omission.
 */

const STATUS_LABELS: Record<string, string> = {
  draft: "Bozza",
  announced: "In programma",
  preparing: "In preparazione",
  queued: "In coda",
  running: "In corso",
  paused: "In pausa",
  partially_completed: "Completata in parte",
  completed: "Completata",
  failed: "Non riuscita",
  cancelled: "Annullata",
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("it-IT").format(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("it-IT", { dateStyle: "medium" }).format(new Date(value));
}

/**
 * Never published to, so the row's numbers mean nothing - but why differs, and
 * the difference matters to the person reading it: "hai scelto di non
 * partecipare" must never be shown to someone an administrator took out.
 */
type NonParticipation = "declined" | "removed" | null;

function nonParticipation(campaign: PortalCampaign): NonParticipation {
  if (campaign.participation_included > 0 || campaign.channels_targeted > 0) return null;
  if (campaign.participation_withdrawn > 0) return "declined";
  if (campaign.participation_removed > 0) return "removed";
  return null;
}

export default async function PortalCampaignsPage() {
  const [user, campaigns] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalCampaign[]>("campaigns"),
  ]);

  if (!user) redirect("/portal/login");

  const list = campaigns ?? [];
  const declinedCount = list.filter((c) => nonParticipation(c) === "declined").length;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Storico campagne</h1>
          <p className="text-muted-foreground">
            Tutte le campagne di cui hai fatto parte, comprese quelle a cui hai rinunciato.
            I numeri riguardano solo i tuoi canali.
          </p>
        </div>
        <Link href="/portal/lineup" className="text-sm text-primary hover:underline">
          Campagne in programma
        </Link>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Non fai ancora parte di nessuna campagna. Collega i tuoi canali e controlla il{" "}
            <Link href="/portal/lineup" className="text-primary hover:underline">
              palinsesto
            </Link>{" "}
            per partecipare alle prossime.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[46rem] border-collapse text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-left">
                  <th className="px-4 py-3 font-medium">Campagna</th>
                  <th className="px-4 py-3 font-medium">Stato</th>
                  <th className="px-4 py-3 text-right font-medium">Canali</th>
                  <th className="px-4 py-3 text-right font-medium">Pubblicati</th>
                  <th className="px-4 py-3 text-right font-medium">In corso</th>
                  <th className="px-4 py-3 text-right font-medium">Non riusciti</th>
                  <th className="px-4 py-3 font-medium">Data</th>
                </tr>
              </thead>
              <tbody>
                {list.map((campaign) => {
                  const reason = nonParticipation(campaign);
                  const declined = reason !== null;
                  const openForChanges = campaign.status === "announced";

                  return (
                    <tr
                      key={campaign.id}
                      className={"border-b last:border-b-0 " + (declined ? "text-muted-foreground" : "")}
                    >
                      <td className="px-4 py-3 font-medium">
                        {openForChanges ? (
                          <Link
                            href={`/portal/lineup/${campaign.id}`}
                            className="hover:text-primary hover:underline"
                          >
                            {campaign.title}
                          </Link>
                        ) : (
                          campaign.title
                        )}
                        {reason && (
                          <span className="mt-0.5 flex items-center gap-1 text-xs font-normal">
                            <MinusCircleIcon className="size-3" />
                            {reason === "declined"
                              ? "hai scelto di non partecipare"
                              : "escluso da un amministratore"}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="outline">
                          {STATUS_LABELS[campaign.status] ?? campaign.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {declined ? "—" : formatNumber(campaign.channels_targeted)}
                      </td>
                      <td
                        className={
                          "px-4 py-3 text-right tabular-nums " +
                          (declined ? "" : "text-emerald-600 dark:text-emerald-400")
                        }
                      >
                        {declined ? "—" : formatNumber(campaign.published)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        {!declined && campaign.pending > 0 ? formatNumber(campaign.pending) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {!declined && campaign.failed > 0 ? (
                          <span className="text-destructive">{formatNumber(campaign.failed)}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(campaign.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {declinedCount > 0 && (
            <p className="text-sm text-muted-foreground">
              {declinedCount === 1
                ? "1 campagna a cui hai scelto di non partecipare."
                : `${declinedCount} campagne a cui hai scelto di non partecipare.`}
            </p>
          )}
        </>
      )}
    </div>
  );
}
