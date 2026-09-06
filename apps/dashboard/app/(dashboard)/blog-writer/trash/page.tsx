"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import type { ColumnDef } from "@tanstack/react-table";
import { Trash2Icon, RotateCcwIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Button } from "@/components/ui/button";
import { useArticles, useRestoreArticle, useDeleteArticle } from "@/hooks/use-blog-writer";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import type { BlogArticleListItem } from "@/types/api";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";

export default function BlogWriterTrashPage() {
  const articlesQuery = useArticles({ status: "archived", limit: 100 });
  const restoreArticle = useRestoreArticle();
  const deleteArticle = useDeleteArticle();
  const [deleteTarget, setDeleteTarget] = useState<BlogArticleListItem | null>(null);

  const columns = useMemo<ColumnDef<BlogArticleListItem, unknown>[]>(
    () => [
      {
        id: "title",
        header: "Titolo",
        cell: ({ row }) => (
          <Link href={`/blog-writer/${row.original.id}`} className="font-medium hover:underline">
            {row.original.title || "(senza titolo)"}
          </Link>
        ),
      },
      { id: "language", header: "Lingua", cell: ({ row }) => row.original.language },
      { id: "status", header: "Stato", cell: () => <StatusBadge status="archived" /> },
      { id: "updated_at", header: "Archiviato il", cell: ({ row }) => formatDateTime(row.original.updated_at) },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                restoreArticle.mutate(row.original.id, {
                  onSuccess: () => toast.success("Articolo ripristinato in Bozze"),
                  onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Ripristino non riuscito"),
                })
              }
              disabled={restoreArticle.isPending}
            >
              <RotateCcwIcon className="size-3.5" />
              Recupera
            </Button>
            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteTarget(row.original)}>
              <Trash2Icon className="size-3.5" />
              Elimina definitivamente
            </Button>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [restoreArticle.isPending]
  );

  return (
    <div className="space-y-4">
      <BlogWriterSubnav />
      <PageHeader title="Cestino articoli" description="Articoli archiviati: recuperali in Bozze o eliminali definitivamente" />

      <DataTable
        columns={columns}
        data={articlesQuery.data}
        isLoading={articlesQuery.isLoading}
        isError={articlesQuery.isError}
        error={articlesQuery.error}
        onRetry={() => articlesQuery.refetch()}
        emptyTitle="Il cestino è vuoto"
        emptyDescription="Gli articoli archiviati compariranno qui."
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Eliminare definitivamente "${deleteTarget?.title}"?`}
        description="Questa azione non può essere annullata. Se l'articolo è già pubblicato su un sito WordPress, l'eliminazione viene rifiutata."
        confirmLabel="Elimina definitivamente"
        destructive
        loading={deleteArticle.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteArticle.mutate(deleteTarget.id, {
            onSuccess: () => {
              toast.success("Articolo eliminato definitivamente");
              setDeleteTarget(null);
            },
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Eliminazione non riuscita");
              setDeleteTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
