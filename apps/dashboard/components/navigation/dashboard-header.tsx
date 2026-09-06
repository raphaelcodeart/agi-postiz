"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { BreadcrumbNav } from "@/components/navigation/breadcrumb-nav";
import { ThemeToggle } from "@/components/navigation/theme-toggle";
import { UserMenu } from "@/components/navigation/user-menu";
import { useMe } from "@/hooks/use-auth";

export function DashboardHeader() {
  const { data: admin } = useMe();

  return (
    <header className="glass-surface sticky top-0 z-40 flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-4" />
      <BreadcrumbNav />
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <UserMenu admin={admin} />
      </div>
    </header>
  );
}
