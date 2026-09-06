"use client";

import Link from "next/link";
import { FileTextIcon, CheckCircle2Icon, XCircleIcon, GlobeIcon, AlertTriangleIcon, MegaphoneIcon, PlusIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBlogWriterDashboard } from "@/hooks/use-blog-writer";
import { formatDateTime } from "@/lib/format";
import { BlogWriterSubnav } from "./_components/blog-writer-subnav";

export default function BlogWriterDashboardPage() {
  const dashboardQuery = useBlogWriterDashboard();

  return (
    <div className="space-y-6">
      <BlogWriterSubnav />
      <PageHeader
        title="Blog Writer AI"
        description="Genera, gestisci e pubblica articoli di blog assistiti da AI"
        actions={
          <Button asChild>
            <Link href="/blog-writer/new">
              <PlusIcon className="size-4" />
              Nuovo articolo
            </Link>
          </Button>
        }
      />

      {dashboardQuery.isLoading && <Skeleton className="h-40" />}
      {dashboardQuery.isError && <ErrorState error={dashboardQuery.error} onRetry={() => dashboardQuery.refetch()} />}

      {dashboardQuery.data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StatCard label="Bozze" value={dashboardQuery.data.draft_count} icon={FileTextIcon} />
            <StatCard label="Articoli pubblicati" value={dashboardQuery.data.published_count} icon={CheckCircle2Icon} tone="success" />
            <StatCard label="Pubblicazioni fallite" value={dashboardQuery.data.failed_publications_count} icon={XCircleIcon} tone="destructive" />
            <StatCard label="Siti WordPress collegati" value={dashboardQuery.data.sites_count} icon={GlobeIcon} />
            <StatCard label="Siti con errore" value={dashboardQuery.data.sites_error_count} icon={AlertTriangleIcon} tone="warning" />
            <StatCard label="Campagne social create" value={dashboardQuery.data.social_campaigns_count} icon={MegaphoneIcon} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ultimi articoli modificati</CardTitle>
              </CardHeader>
              <CardContent>
                {dashboardQuery.data.recent_articles.length === 0 ? (
                  <EmptyState icon={FileTextIcon} title="Nessun articolo ancora" />
                ) : (
                  <ul className="divide-y">
                    {dashboardQuery.data.recent_articles.map((a) => (
                      <li key={a.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                        <Link href={`/blog-writer/${a.id}`} className="min-w-0 flex-1 truncate hover:underline">
                          {a.title || "(senza titolo)"}
                        </Link>
                        <StatusBadge status={a.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ultime pubblicazioni / errori recenti</CardTitle>
              </CardHeader>
              <CardContent>
                {dashboardQuery.data.recent_publications.length === 0 ? (
                  <EmptyState icon={GlobeIcon} title="Nessuna pubblicazione ancora" />
                ) : (
                  <ul className="divide-y">
                    {dashboardQuery.data.recent_publications.map((p) => (
                      <li key={p.id} className="space-y-0.5 py-2 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="truncate font-medium">{p.wordpress_site_name}</span>
                          <StatusBadge status={p.publication_status} />
                        </div>
                        {p.error_message && <p className="text-xs text-destructive">{p.error_message}</p>}
                        <p className="text-xs text-muted-foreground">{formatDateTime(p.published_at ?? p.created_at)}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
