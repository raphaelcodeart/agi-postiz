"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import type { ColumnDef } from "@tanstack/react-table";
import { PlusIcon, CopyIcon, RotateCcwIcon, ArchiveIcon, Trash2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { IconActionButton } from "@/components/shared/icon-action-button";
import { Button } from "@/components/ui/button";
import {
  useArticles,
  useArchiveArticle,
  useDeleteArticle,
  useDuplicateArticle,
  useRegenerateArticle,
} from "@/hooks/use-blog-writer";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import type { BlogArticleListItem } from "@/types/api";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";
import { useAIGate } from "@/hooks/use-ai-gate";
import { AIRequiredDialog } from "@/components/shared/ai-required-dialog";

const DRAFT_STATUSES = new Set(["generating", "draft", "ready", "publishing", "partially_published", "failed"]);

export default function DraftsPage() {
  const articlesQuery = useArticles({ limit: 100 });
  const archiveArticle = useArchiveArticle();
  const deleteArticle = useDeleteArticle();
  const duplicateArticle = useDuplicateArticle();
  const regenerateArticle = useRegenerateArticle();
  const [deleteTarget, setDeleteTarget] = useState<BlogArticleListItem | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<BlogArticleListItem | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const aiGate = useAIGate();

  const drafts = (articlesQuery.data ?? []).filter((a) => DRAFT_STATUSES.has(a.status));

  function handleRegenerate(article: BlogArticleListItem) {
    aiGate.guard(() => {
      setRegeneratingId(article.id);
      regenerateArticle.mutate(article.id, {
        onSuccess: () => {
          setRegeneratingId(null);
          toast.success("Articolo rigenerato");
        },
        onError: (error) => {
          setRegeneratingId(null);
          toast.error(error instanceof ApiError ? error.detail : "Rigenerazione non riuscita");
        },
      });
    });
  }

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
      { id: "status", header: "Stato", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
      { id: "created_at", header: "Creato", cell: ({ row }) => formatDateTime(row.original.created_at) },
      { id: "updated_at", header: "Ultima modifica", cell: ({ row }) => formatDateTime(row.original.updated_at) },
      { id: "sites_count", header: "Siti selezionati", cell: ({ row }) => row.original.sites_count },
      { id: "publications_count", header: "Pubblicazioni", cell: ({ row }) => row.original.publications_count },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/blog-writer/${row.original.id}`}>Apri</Link>
            </Button>
            <IconActionButton
              icon={CopyIcon}
              label="Duplica"
              onClick={() => duplicateArticle.mutate(row.original.id, { onSuccess: () => toast.success("Bozza duplicata") })}
            />
            <IconActionButton
              icon={RotateCcwIcon}
              label="Rigenera"
              title="Rigenera con AI"
              onClick={() => handleRegenerate(row.original)}
              disabled={regeneratingId === row.original.id}
              spinning={regeneratingId === row.original.id}
              className={cn(!aiGate.configured && "opacity-50")}
            />
            <IconActionButton icon={ArchiveIcon} label="Archivia" onClick={() => setArchiveTarget(row.original)} />
            <IconActionButton
              icon={Trash2Icon}
              label="Elimina"
              destructive
              onClick={() => setDeleteTarget(row.original)}
            />
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [regeneratingId, aiGate.configured]
  );

  return (
    <div className="space-y-4">
      <BlogWriterSubnav />
      <PageHeader
        title="Bozze"
        description="Articoli generati non ancora pubblicati (o pubblicati solo parzialmente)"
        actions={
          <Button asChild>
            <Link href="/blog-writer/new">
              <PlusIcon className="size-4" />
              Nuovo articolo
            </Link>
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={drafts}
        isLoading={articlesQuery.isLoading}
        isError={articlesQuery.isError}
        error={articlesQuery.error}
        onRetry={() => articlesQuery.refetch()}
        emptyTitle="Nessuna bozza"
        emptyDescription='Genera un nuovo articolo per iniziare.'
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Eliminare "${deleteTarget?.title}"?`}
        description="Questa azione non può essere annullata. Se l'articolo è già pubblicato su un sito, archivialo invece di eliminarlo."
        confirmLabel="Elimina"
        destructive
        loading={deleteArticle.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteArticle.mutate(deleteTarget.id, {
            onSuccess: () => {
              toast.success("Articolo eliminato");
              setDeleteTarget(null);
            },
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Eliminazione non riuscita");
              setDeleteTarget(null);
            },
          });
        }}
      />

      <ConfirmDialog
        open={!!archiveTarget}
        onOpenChange={(open) => !open && setArchiveTarget(null)}
        title={`Archiviare "${archiveTarget?.title}"?`}
        description="L'articolo verrà spostato nel Cestino - potrai recuperarlo in qualsiasi momento da lì."
        confirmLabel="Archivia"
        loading={archiveArticle.isPending}
        onConfirm={() => {
          if (!archiveTarget) return;
          archiveArticle.mutate(archiveTarget.id, {
            onSuccess: () => {
              toast.success("Articolo archiviato");
              setArchiveTarget(null);
            },
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Archiviazione non riuscita");
              setArchiveTarget(null);
            },
          });
        }}
      />

      <AIRequiredDialog open={aiGate.dialogOpen} onOpenChange={aiGate.setDialogOpen} />
    </div>
  );
}
