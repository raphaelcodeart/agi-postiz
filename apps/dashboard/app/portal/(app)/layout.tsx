import Link from "next/link";
import { redirect } from "next/navigation";
import { RssIcon } from "lucide-react";
import {
  portalFetch,
  type PortalLineupCampaign,
  type PortalUser,
} from "@/lib/portal/server";
import { PortalLogoutButton } from "./logout-button";
import { PortalSidebar, PortalTabBar } from "./portal-nav";

/**
 * Shell for the signed-in portal.
 *
 * The guard lives here rather than in each page: /portal/me is the single call
 * that decides whether a session is real, and any page inside this group is
 * unreachable without it. Login and registration sit in the sibling (public)
 * group and are untouched by it.
 *
 * Navigation is a left rail on desktop and a bottom bar on a phone. The header
 * keeps only identity - logo, name, sign out - so the sections stay in one
 * place instead of being a row of links that grows until it wraps.
 */
export default async function PortalAppLayout({ children }: { children: React.ReactNode }) {
  const user = await portalFetch<PortalUser>("me");
  if (!user) {
    redirect("/portal/login");
  }

  // Only campaigns still open for a decision are counted. A badge that includes
  // ones the user has already handled trains them to ignore it.
  const lineup = await portalFetch<PortalLineupCampaign[]>("lineup");
  const pendingDecisions = (lineup ?? []).filter(
    (campaign) => campaign.window_open && campaign.included_count === 0 && campaign.withdrawn_count === 0
  ).length;
  const badges = pendingDecisions > 0 ? { "/portal/lineup": pendingDecisions } : undefined;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-30 border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-4 py-3">
          <Link href="/portal" className="flex items-center gap-2">
            <span className="glow-primary flex size-8 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground">
              <RssIcon className="size-4" />
            </span>
            <span className="gradient-text text-base font-semibold">Agi Post</span>
          </Link>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-muted-foreground sm:inline">{user.name}</span>
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

      <PortalTabBar badges={badges} />
    </div>
  );
}
