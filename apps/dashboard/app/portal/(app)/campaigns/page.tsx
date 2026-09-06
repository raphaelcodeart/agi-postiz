import { redirect } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { portalFetch, type PortalCampaign, type PortalUser } from "@/lib/portal/server";

export const dynamic = "force-dynamic";

const STATUS_LABELS: Record<string, string> = {
  draft: "Bozza",
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

export default async function PortalCampaignsPage() {
  const [user, campaigns] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalCampaign[]>("campaigns"),
  ]);

  if (!user) redirect("/portal/login");

  const list = campaigns ?? [];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Le tue campagne</h1>
        <p className="text-muted-foreground">
          I numeri riguardano solo i tuoi canali, non l&apos;intera campagna.
        </p>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Non fai ancora parte di nessuna campagna. Collega i tuoi canali per essere incluso
            nelle prossime.
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[42rem] border-collapse text-sm">
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
              {list.map((campaign) => (
                <tr key={campaign.id} className="border-b last:border-b-0">
                  <td className="px-4 py-3 font-medium">{campaign.title}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">
                      {STATUS_LABELS[campaign.status] ?? campaign.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatNumber(campaign.channels_targeted)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                    {formatNumber(campaign.published)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                    {campaign.pending > 0 ? formatNumber(campaign.pending) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {campaign.failed > 0 ? (
                      <span className="text-destructive">{formatNumber(campaign.failed)}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDate(campaign.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
