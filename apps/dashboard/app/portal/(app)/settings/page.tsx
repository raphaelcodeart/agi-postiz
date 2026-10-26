import { redirect } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { portalFetch, type PortalGroup, type PortalUser } from "@/lib/portal/server";
import { ProfileSettingsForm } from "./profile-settings-form";

export const dynamic = "force-dynamic";

/**
 * Impostazioni del promoter: dove scrive e a quali gruppi partecipa.
 *
 * Sono gli stessi tre dati chiesti dal popup del primo accesso. Il popup li
 * raccoglie una volta; questa pagina permette di correggerli quando si cambia
 * citta' o si vuole entrare (o uscire) da un gruppo, senza dover scrivere a
 * chi amministra. Nome ed email restano in sola lettura: cambiano per altre
 * vie e con altre garanzie (l'indirizzo e' quello confermato).
 */
export default async function PortalSettingsPage() {
  const [user, groups] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalGroup[]>("groups"),
  ]);

  if (!user) redirect("/portal/login");

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Impostazioni</h1>
        <p className="text-muted-foreground">Il tuo profilo e i gruppi a cui partecipi.</p>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">Account</h2>
        <Card>
          <CardContent className="grid gap-4 p-5 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase">Nome</p>
              <p className="mt-0.5 font-medium">{user.name}</p>
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase">Email</p>
              <p className="mt-0.5 truncate font-medium">{user.email}</p>
            </div>
            {user.company_name && (
              <div className="sm:col-span-2">
                <p className="text-xs font-medium text-muted-foreground uppercase">Azienda</p>
                <p className="mt-0.5 font-medium">{user.company_name}</p>
              </div>
            )}
            <p className="text-sm text-muted-foreground sm:col-span-2">
              Per cambiare nome o indirizzo email scrivi a chi gestisce il progetto.
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">Zona e gruppi</h2>
        <Card>
          <CardContent className="p-5">
            <ProfileSettingsForm
              groups={groups ?? []}
              initialCity={user.city}
              initialPostalCode={user.postal_code}
              initialGroupIds={user.group_ids}
            />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
