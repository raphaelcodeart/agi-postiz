import Link from "next/link";
import { redirect } from "next/navigation";
import { SettingsIcon } from "lucide-react";
import {
  portalFetch,
  type PortalGroup,
  type PortalLineupCampaign,
  type PortalUser,
} from "@/lib/portal/server";
import { BrandMark, portalFont } from "../_shared/brand";
import { PortalLogoutButton } from "./logout-button";
import { PortalEmailGate } from "./email-gate";
import { PortalProfileGate } from "./profile-gate";
import { PortalLegalFooter } from "../_shared/legal";
import { PortalSidebar, PortalTabBar } from "./portal-nav";

/**
 * Shell for the signed-in portal.
 *
 * The guard lives here rather than in each page: /portal/me is the single call
 * that decides whether a session is real, and any page inside this group is
 * unreachable without it. Login and registration sit in the sibling (public)
 * group and are untouched by it.
 *
 * Una seconda guardia segue la prima: chi non ha ancora confermato l'indirizzo
 * vede la testata e la finestra di attesa, e nient'altro. Il contenuto non
 * viene proprio reso - non e' nascosto sotto un velo - cosi' non c'e' niente da
 * scoprire togliendo un elemento dal DOM. Il blocco che conta resta comunque
 * quello dell'API (get_verified_portal_user in apps/api/app/api/v1/portal.py):
 * questo serve a spiegare all'utente cosa manca, non a difendere i dati.
 *
 * Navigation is a left rail on desktop and a bottom bar on a phone. The header
 * keeps only identity - logo, name, sign out - so the sections stay in one
 * place instead of being a row of links that grows until it wraps.
 *
 * The whole group carries .portal-skin: the promoter's side of the product
 * wears the public landing's design system (see the block of that name in
 * app/globals.css), not the admin dashboard's. The pages below were already
 * written against semantic tokens - bg-card, text-muted-foreground, text-primary
 * - so re-pointing those tokens here restyles them without touching each one.
 */
export default async function PortalAppLayout({ children }: { children: React.ReactNode }) {
  const user = await portalFetch<PortalUser>("me");
  if (!user) {
    redirect("/portal/login");
  }

  // Entrambe: il reset della password conferma l'indirizzo ma non la privacy,
  // e l'API (get_verified_portal_user) chiude il portale finche' manca una
  // delle due. Subito dopo viene la terza guardia, il profilo del primo
  // accesso: stessa cornice, finestra diversa.
  const gate = !user.email_verified || !user.privacy_accepted ? "email" : !user.profile_completed ? "profile" : null;
  if (gate) {
    const groups = gate === "profile" ? ((await portalFetch<PortalGroup[]>("groups")) ?? []) : [];
    return (
      <div className={`portal-skin ${portalFont.variable} flex min-h-screen flex-col`}>
        <header className="pa-header sticky top-0 z-30">
          <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-4 py-3">
            <span className="pa-brand !text-[1.05rem]">
              <BrandMark size={26} />
              AGI Post
            </span>
            <div className="ml-auto flex items-center gap-3">
              <span className="hidden text-sm text-muted-foreground sm:inline">{user.name}</span>
              <PortalLogoutButton />
            </div>
          </div>
        </header>

        {/* Sfondo decorativo: da' alla finestra qualcosa su cui posarsi senza
            mostrare nulla di reale. */}
        <div aria-hidden className="pa-deco flex-1">
          <span className="pa-shape pa-shape--a" />
          <span className="pa-shape pa-shape--b" />
          <span className="pa-shape pa-shape--c" />
        </div>

        <div className="relative z-10 px-4 pb-6">
          <PortalLegalFooter compact />
        </div>

        {gate === "email" ? (
          <PortalEmailGate email={user.email} alreadySent={user.verification_email_sent} />
        ) : (
          <PortalProfileGate
            userName={user.name}
            groups={groups}
            initialCity={user.city}
            initialPostalCode={user.postal_code}
            initialGroupIds={user.group_ids}
          />
        )}
      </div>
    );
  }

  // Only campaigns still open for a decision are counted. A badge that includes
  // ones the user has already handled trains them to ignore it.
  const lineup = await portalFetch<PortalLineupCampaign[]>("lineup");
  const pendingDecisions = (lineup ?? []).filter(
    (campaign) => campaign.window_open && campaign.included_count === 0 && campaign.withdrawn_count === 0
  ).length;
  const badges = pendingDecisions > 0 ? { "/portal/lineup": pendingDecisions } : undefined;

  return (
    <div className={`portal-skin ${portalFont.variable} flex min-h-screen flex-col`}>
      <header className="pa-header sticky top-0 z-30">
        <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-4 py-3">
          <Link href="/portal" className="pa-brand !text-[1.05rem]">
            <BrandMark size={26} />
            AGI Post
          </Link>

          <div className="ml-auto flex items-center gap-1 sm:gap-3">
            {/* Il nome porta alle Impostazioni: e' la convenzione che chiunque
                conosce, e tiene la testata a sola identita' senza aggiungere
                una settima voce alla barra delle sezioni. */}
            <Link
              href="/portal/settings"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
              aria-label="Impostazioni"
            >
              <SettingsIcon className="size-4" />
              <span className="hidden sm:inline">{user.name}</span>
            </Link>
            <PortalLogoutButton />
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-1 gap-8 px-4 py-6">
        <PortalSidebar badges={badges} />
        {/* min-w-0 so a wide table inside a page scrolls itself instead of
            stretching the flex row and pushing the rail off screen. */}
        <main className="min-w-0 flex-1 pb-24 lg:pb-8">{children}</main>
      </div>

      <div className="mx-auto w-full max-w-5xl px-4 pb-24 lg:pb-8">
        <PortalLegalFooter />
      </div>

      <PortalTabBar badges={badges} />
    </div>
  );
}
