import Link from "next/link";
import { redirect } from "next/navigation";
import { RssIcon } from "lucide-react";
import { portalFetch, type PortalUser } from "@/lib/portal/server";
import { PortalLogoutButton } from "./logout-button";

/**
 * Shell for the signed-in portal.
 *
 * The guard lives here rather than in each page: /portal/me is the single call
 * that decides whether a session is real, and any page inside this group is
 * unreachable without it. Login and registration sit in the sibling (public)
 * group and are untouched by it.
 */
export default async function PortalAppLayout({ children }: { children: React.ReactNode }) {
  const user = await portalFetch<PortalUser>("me");
  if (!user) {
    redirect("/portal/login");
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="border-b bg-card/60 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <Link href="/portal" className="flex items-center gap-2">
            <span className="glow-primary flex size-8 items-center justify-center rounded-lg bg-brand-gradient text-primary-foreground">
              <RssIcon className="size-4" />
            </span>
            <span className="gradient-text text-base font-semibold">Agi Post</span>
          </Link>

          <nav className="flex items-center gap-4 text-sm">
            <Link href="/portal" className="text-muted-foreground transition-colors hover:text-foreground">
              Riepilogo
            </Link>
            <Link
              href="/portal/channels"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Canali
            </Link>
            <Link
              href="/portal/campaigns"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Campagne
            </Link>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-muted-foreground sm:inline">{user.name}</span>
            <PortalLogoutButton />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
