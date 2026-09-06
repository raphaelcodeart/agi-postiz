"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboardIcon, SparklesIcon, FileTextIcon, BookOpenCheckIcon, GlobeIcon, Trash2Icon } from "lucide-react";
import { cn } from "@/lib/utils";

// Blog Writer only has one entry in the main sidebar (see app-sidebar.tsx) -
// this in-page bar is how the admin moves between its sub-pages instead.
const TABS = [
  { href: "/blog-writer", label: "Dashboard BWA", icon: LayoutDashboardIcon },
  { href: "/blog-writer/new", label: "Nuovo articolo", icon: SparklesIcon },
  { href: "/blog-writer/drafts", label: "Bozze", icon: FileTextIcon },
  { href: "/blog-writer/articles", label: "Pubblicati", icon: BookOpenCheckIcon },
  { href: "/blog-writer/sites", label: "Siti WordPress", icon: GlobeIcon },
  { href: "/blog-writer/trash", label: "Cestino", icon: Trash2Icon },
];

export function BlogWriterSubnav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-1 border-b pb-3">
      {TABS.map((tab) => {
        const isActive = tab.href === "/blog-writer" ? pathname === "/blog-writer" : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "bg-primary/10 font-medium text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <tab.icon className="size-4" />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
