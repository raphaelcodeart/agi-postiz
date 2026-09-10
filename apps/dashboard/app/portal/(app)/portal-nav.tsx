"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarClockIcon,
  HistoryIcon,
  LayoutDashboardIcon,
  Link2Icon,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The portal's sections, in one place: the desktop rail and the mobile bar are
 * two renderings of this list, not two lists that have to be kept in step.
 *
 * Ordered by how often a promoter needs them, not by how the system is built.
 * "Palinsesto" sits second because it is the only section with a deadline
 * attached - miss it and a decision is made for you.
 */
export const PORTAL_SECTIONS: {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
}[] = [
  { href: "/portal", label: "Riepilogo", icon: LayoutDashboardIcon, description: "I tuoi risultati" },
  { href: "/portal/lineup", label: "Palinsesto", icon: CalendarClockIcon, description: "Campagne in programma" },
  { href: "/portal/channels", label: "Canali", icon: Link2Icon, description: "Profili collegati" },
  { href: "/portal/campaigns", label: "Storico", icon: HistoryIcon, description: "Campagne passate" },
];

/**
 * "/portal" would otherwise light up on every page, since every route starts
 * with it. Exact match for the index, prefix match for the rest.
 */
function isActive(pathname: string, href: string): boolean {
  return href === "/portal" ? pathname === "/portal" : pathname.startsWith(href);
}

/** Vertical rail, desktop only. */
export function PortalSidebar({ badges }: { badges?: Record<string, number> }) {
  const pathname = usePathname();

  return (
    <nav className="sticky top-20 hidden w-52 shrink-0 flex-col gap-1 lg:flex" aria-label="Sezioni">
      {PORTAL_SECTIONS.map((section) => {
        const active = isActive(pathname, section.href);
        const badge = badges?.[section.href];
        return (
          <Link
            key={section.href}
            href={section.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
              active
                ? "bg-primary/10 font-medium text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <section.icon className="size-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">{section.label}</span>
            {badge ? (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[0.7rem] leading-none font-medium tabular-nums",
                  active ? "bg-primary/20 text-primary" : "bg-muted-foreground/15"
                )}
              >
                {badge}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Horizontal card strip, shown where the rail is not: below the header on
 * tablet, and pinned to the bottom of the screen on a phone - which is where a
 * thumb actually reaches, and where every app a promoter already uses puts it.
 */
export function PortalTabBar({ badges }: { badges?: Record<string, number> }) {
  const pathname = usePathname();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-card/95 backdrop-blur lg:hidden"
      aria-label="Sezioni"
    >
      <div className="mx-auto flex w-full max-w-5xl">
        {PORTAL_SECTIONS.map((section) => {
          const active = isActive(pathname, section.href);
          const badge = badges?.[section.href];
          return (
            <Link
              key={section.href}
              href={section.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex flex-1 flex-col items-center gap-1 px-1 py-2.5 text-[0.7rem] transition-colors",
                active ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <span className="relative">
                <section.icon className="size-5" />
                {badge ? (
                  <span className="absolute -top-1.5 -right-2 min-w-4 rounded-full bg-primary px-1 text-[0.6rem] leading-4 font-medium text-primary-foreground tabular-nums">
                    {badge}
                  </span>
                ) : null}
              </span>
              <span className="truncate">{section.label}</span>
              {active && (
                <span className="absolute inset-x-4 top-0 h-0.5 rounded-full bg-primary" />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
