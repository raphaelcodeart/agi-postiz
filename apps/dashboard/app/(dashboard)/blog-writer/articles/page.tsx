"use client";

import { useMemo } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { useArticles } from "@/hooks/use-blog-writer";
import { formatDateTime } from "@/lib/format";
import type { BlogArticleListItem } from "@/types/api";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";

export default function PublishedArticlesPage() {
  const articlesQuery = useArticles({ limit: 100 });
  const published = (articlesQuery.data ?? []).filter((a) => a.status === "published" || a.status === "partially_published");

  const columns = useMemo<ColumnDef<BlogArticleListItem, unknown>[]>(
    () => [
      {
        id: "title",
        header: "Titolo",
        cell: ({ row }) => (
          <Link href={`/blog-writer/${row.original.id}`} className="font-medium hover:underline">
            {row.original.title}
          </Link>
        ),
      },
      { id: "status", header: "Stato", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
      { id: "sites_count", header: "Siti", cell: ({ row }) => row.original.sites_count },
      { id: "updated_at", header: "Ultima sincronizzazione", cell: ({ row }) => formatDateTime(row.original.updated_at) },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/blog-writer/${row.original.id}`}>Apri articolo</Link>
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <BlogWriterSubnav />
      <PageHeader title="Articoli pubblicati" description="Articoli usciti su almeno un sito WordPress" />

      <DataTable
        columns={columns}
        data={published}
        isLoading={articlesQuery.isLoading}
        isError={articlesQuery.isError}
        error={articlesQuery.error}
        onRetry={() => articlesQuery.refetch()}
        emptyTitle="Nessun articolo pubblicato"
      />
    </div>
  );
}
