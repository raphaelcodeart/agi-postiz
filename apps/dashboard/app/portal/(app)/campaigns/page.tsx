import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { portalFetch, type PortalCampaign, type PortalUser } from "@/lib/portal/server";
import { PortalCampaignsBrowser } from "./campaigns-browser";

export const dynamic = "force-dynamic";

/**
 * The user's own history: every campaign they took part in, and every one they
 * were offered and declined.
 *
 * The refusals matter as much as the participations. A promoter asking "did I
 * actually opt out of that one, or did it just never reach my channels?" has no
 * other place to check - a declined campaign produces no publications at all,
 * so a table built only from published posts answers the question by omission.
 *
 * Ricerca, filtri e ordinamento vivono nel componente client accanto: la lista
 * arriva gia' completa da una sola chiamata, quindi filtrarla e' lavoro del
 * browser, non un altro giro di rete (vedi campaigns-browser.tsx).
 */
export default async function PortalCampaignsPage() {
  const [user, campaigns] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalCampaign[]>("campaigns"),
  ]);

  if (!user) redirect("/portal/login");

  const list = campaigns ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Storico campagne</h1>
          <p className="text-muted-foreground">
            Tutte le campagne di cui hai fatto parte, comprese quelle a cui hai rinunciato. I numeri
            riguardano solo i tuoi canali.
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
        <PortalCampaignsBrowser campaigns={list} />
      )}
    </div>
  );
}
