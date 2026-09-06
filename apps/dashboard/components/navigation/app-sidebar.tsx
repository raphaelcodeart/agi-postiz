"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Rss, LogOutIcon } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import { useLogout } from "@/hooks/use-auth";
import { usePendingCount } from "@/hooks/use-omnichannel";
import {
  BOARD_NAV_ITEM,
  MAIN_NAV_ITEMS,
  BUFFER_NAV_ITEMS,
  BLOG_WRITER_NAV_ITEMS,
  OMNICHANNEL_RESPONDER_NAV_ITEMS,
  SETTINGS_NAV_ITEM,
  type NavItem,
} from "@/lib/navigation";

// Keyed by href - a small red dot on the item's icon, "pending count" shown
// in the tooltip. Currently only the Omnichannel Responder inbox uses this
// (new messages / drafts to approve), but any nav item can opt in this way.
function NavItems({ items, pathname, badgeCounts }: { items: NavItem[]; pathname: string; badgeCounts?: Record<string, number> }) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const badgeCount = badgeCounts?.[item.href] ?? 0;
        const tooltip = badgeCount > 0 ? `${item.label} (${badgeCount} da gestire)` : item.label;
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton isActive={isActive} tooltip={tooltip} render={<Link href={item.href} />}>
              <span className="relative inline-flex">
                <item.icon />
                {badgeCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-destructive ring-1 ring-sidebar" />
                )}
              </span>
              <span>{item.label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const logout = useLogout();
  const isSettingsActive = pathname.startsWith(SETTINGS_NAV_ITEM.href);
  const { data: pendingCount } = usePendingCount();
  const omnichannelBadges = { "/omnichannel-responder": pendingCount?.count ?? 0 };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="glow-primary flex size-7 shrink-0 items-center justify-center rounded-md bg-brand-gradient text-primary-foreground">
            <Rss className="size-4" />
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <p className="gradient-text truncate text-sm font-semibold">Social Publisher Buffer</p>
            <p className="truncate text-xs text-muted-foreground">Admin Console</p>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <NavItems items={[BOARD_NAV_ITEM]} pathname={pathname} />
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        {/* One single block - Dashboard/Utenti/Gruppi/Connessioni Buffer/
            Canali social/Media, then Campagne/Pubblicazioni/Centro errori
            appended right after Media, no separator between the two - under
            one "Campagne Buffer" label for the whole group (same style as
            "Omnichannel Responder"/"Blog Writer AI" below), not just the
            three Buffer items. */}
        <SidebarGroup>
          <SidebarGroupLabel>Campagne Buffer</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavItems items={[...MAIN_NAV_ITEMS, ...BUFFER_NAV_ITEMS]} pathname={pathname} />
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Omnichannel Responder</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavItems items={OMNICHANNEL_RESPONDER_NAV_ITEMS} pathname={pathname} badgeCounts={omnichannelBadges} />
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Blog Writer AI</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavItems items={BLOG_WRITER_NAV_ITEMS} pathname={pathname} />
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarSeparator />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={isSettingsActive}
              tooltip={SETTINGS_NAV_ITEM.label}
              render={<Link href={SETTINGS_NAV_ITEM.href} />}
            >
              <SETTINGS_NAV_ITEM.icon />
              <span>{SETTINGS_NAV_ITEM.label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="Esci"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="text-destructive hover:text-destructive"
            >
              <LogOutIcon />
              <span>Esci</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
