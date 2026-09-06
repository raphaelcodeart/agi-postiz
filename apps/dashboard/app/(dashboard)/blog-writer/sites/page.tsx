"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import type { ColumnDef } from "@tanstack/react-table";
import { PlusIcon, PencilIcon, Trash2Icon, RefreshCwIcon, ExternalLinkIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { IconActionButton } from "@/components/shared/icon-action-button";
import { Button } from "@/components/ui/button";
import { useWordpressSites, useDeleteWordpressSite, useTestWordpressSiteConnection } from "@/hooks/use-blog-writer";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import type { WordpressSiteResponse } from "@/types/api";
import { SiteDialog } from "./_components/site-dialog";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";

export default function WordpressSitesPage() {
  const sitesQuery = useWordpressSites();
  const deleteSite = useDeleteWordpressSite();
  const testConnection = useTestWordpressSiteConnection();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<WordpressSiteResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WordpressSiteResponse | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  function handleTest(site: WordpressSiteResponse) {
    setTestingId(site.id);
    testConnection.mutate(site.id, {
      onSuccess: (result) => {
        setTestingId(null);
        if (result.success) toast.success(`Connessione riuscita (${result.wp_user_name ?? site.username})`);
        else toast.error(result.message);
      },
      onError: (error) => {
        setTestingId(null);
        toast.error(error instanceof ApiError ? error.detail : "Test non riuscito");
      },
    });
  }

  const columns = useMemo<ColumnDef<WordpressSiteResponse, unknown>[]>(
    () => [
      {
        id: "name",
        header: "Sito",
        cell: ({ row }) => (
          <div>
            <a
              href={row.original.site_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium hover:underline"
            >
              {row.original.name}
              <ExternalLinkIcon className="size-3 text-muted-foreground" />
            </a>
            <p className="text-xs text-muted-foreground">{row.original.site_url}</p>
          </div>
        ),
      },
      {
        id: "connection_status",
        header: "Connessione",
        cell: ({ row }) => <StatusBadge status={row.original.connection_status} />,
      },
      {
        id: "is_active",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.is_active ? "active" : "inactive"} />,
      },
      {
        id: "default_status",
        header: "Pubblicazione predefinita",
        cell: ({ row }) => row.original.default_status,
      },
      {
        id: "language",
        header: "Lingua",
        cell: ({ row }) => row.original.language,
      },
      {
        id: "last_connection_test_at",
        header: "Ultimo test",
        cell: ({ row }) => formatDateTime(row.original.last_connection_test_at),
      },
      {
        id: "last_published_at",
        header: "Ultima pubblicazione",
        cell: ({ row }) => formatDateTime(row.original.last_published_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <IconActionButton
              icon={RefreshCwIcon}
              label="Testa"
              onClick={() => handleTest(row.original)}
              disabled={testingId === row.original.id}
              spinning={testingId === row.original.id}
            />
            <IconActionButton
              icon={PencilIcon}
              label="Modifica"
              onClick={() => {
                setEditTarget(row.original);
                setDialogOpen(true);
              }}
            />
            <IconActionButton
              icon={Trash2Icon}
              label="Scollega"
              destructive
              onClick={() => setDeleteTarget(row.original)}
            />
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [testingId]
  );

  return (
    <div className="space-y-4">
      <BlogWriterSubnav />
      <PageHeader
        title="Siti WordPress"
        description="Connetti i siti su cui Blog Writer AI può pubblicare articoli"
        actions={
          <Button
            onClick={() => {
              setEditTarget(null);
              setDialogOpen(true);
            }}
          >
            <PlusIcon className="size-4" />
            Connetti sito web
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={sitesQuery.data}
        isLoading={sitesQuery.isLoading}
        isError={sitesQuery.isError}
        error={sitesQuery.error}
        onRetry={() => sitesQuery.refetch()}
        emptyTitle="Nessun sito WordPress collegato"
        emptyDescription='Clicca "Connetti sito web" per aggiungere il primo sito.'
      />

      <SiteDialog open={dialogOpen} onOpenChange={setDialogOpen} site={editTarget} />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Scollegare "${deleteTarget?.name}"?`}
        description="Il sito verrà rimosso dai siti disponibili per la pubblicazione. Gli articoli già pubblicati restano su WordPress, non vengono cancellati."
        confirmLabel="Scollega"
        destructive
        loading={deleteSite.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteSite.mutate(deleteTarget.id, {
            onSuccess: () => {
              toast.success("Sito scollegato");
              setDeleteTarget(null);
            },
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Rimozione non riuscita");
              setDeleteTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
