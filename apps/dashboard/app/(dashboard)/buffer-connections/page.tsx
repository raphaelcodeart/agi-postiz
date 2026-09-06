"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { LinkIcon, PlugZapIcon, RefreshCwIcon, Unlink2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUsers } from "@/hooks/use-users";
import {
  useBufferConnections,
  useDisconnectConnection,
  useSyncConnection,
} from "@/hooks/use-buffer-connections";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import { toast } from "sonner";
import type { BufferConnectionResponse } from "@/types/api";
import { ChannelCountCell } from "./_components/channel-count-cell";
import { ConnectUserDialog } from "./_components/connect-user-dialog";

export default function BufferConnectionsPage() {
  const connectionsQuery = useBufferConnections();
  const usersQuery = useUsers({ limit: 100 });
  const syncConnection = useSyncConnection();
  const disconnectConnection = useDisconnectConnection();

  const [connectOpen, setConnectOpen] = useState(false);
  const [reconnectUserId, setReconnectUserId] = useState<string | undefined>(undefined);
  const [disconnectTarget, setDisconnectTarget] = useState<BufferConnectionResponse | null>(null);

  const usersById = useMemo(() => {
    const map = new Map<string, string>();
    usersQuery.data?.forEach((user) => map.set(user.id, user.name));
    return map;
  }, [usersQuery.data]);

  function handleReconnect(connection: BufferConnectionResponse) {
    setReconnectUserId(connection.user_id);
    setConnectOpen(true);
  }

  function handleSync(connection: BufferConnectionResponse) {
    syncConnection.mutate(connection.id, {
      onSuccess: () => toast.success("Sincronizzazione avviata"),
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Sincronizzazione non riuscita"),
    });
  }

  const columns = useMemo<ColumnDef<BufferConnectionResponse, unknown>[]>(
    () => [
      {
        id: "user",
        header: "Utente",
        cell: ({ row }) => (
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <PlugZapIcon className="size-4" />
            </span>
            <div>
              <span>{usersById.get(row.original.user_id) ?? row.original.user_id}</span>
              <span className="block text-[10px] text-muted-foreground">
                ID Buffer: {row.original.external_account_id ?? "—"}
              </span>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Stato connessione",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "last_sync_at",
        header: "Ultima sincronizzazione",
        cell: ({ row }) => formatDateTime(row.original.last_sync_at),
      },
      {
        id: "channels",
        header: "Canali",
        cell: ({ row }) => <ChannelCountCell userId={row.original.user_id} />,
      },
      {
        accessorKey: "last_error",
        header: "Ultimo errore",
        cell: ({ row }) =>
          row.original.last_error ? (
            <Tooltip>
              <TooltipTrigger className="max-w-48 truncate text-left text-destructive">
                {row.original.last_error}
              </TooltipTrigger>
              <TooltipContent className="max-w-64">{row.original.last_error}</TooltipContent>
            </Tooltip>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => handleSync(row.original)}>
              <RefreshCwIcon className="size-3.5" />
              Sincronizza
            </Button>
            <Button variant="ghost" size="sm" onClick={() => handleReconnect(row.original)}>
              <LinkIcon className="size-3.5" />
              Ricollega
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={() => setDisconnectTarget(row.original)}
            >
              <Unlink2Icon className="size-3.5" />
              Disconnetti
            </Button>
          </div>
        ),
      },
    ],
    [usersById]
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Connessioni Buffer"
        description="Account Buffer collegati per la pubblicazione sui canali social"
        actions={
          <Button
            onClick={() => {
              setReconnectUserId(undefined);
              setConnectOpen(true);
            }}
          >
            <LinkIcon className="size-4" />
            Collega account
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={connectionsQuery.data}
        isLoading={connectionsQuery.isLoading}
        isError={connectionsQuery.isError}
        error={connectionsQuery.error}
        onRetry={() => connectionsQuery.refetch()}
        emptyTitle="Nessuna connessione Buffer"
        emptyDescription="Collega un account Buffer per iniziare a pubblicare sui canali social."
      />

      <ConnectUserDialog open={connectOpen} onOpenChange={setConnectOpen} preselectedUserId={reconnectUserId} />

      <ConfirmDialog
        open={!!disconnectTarget}
        onOpenChange={(open) => !open && setDisconnectTarget(null)}
        title="Disconnettere questo account Buffer?"
        description="I canali social collegati non saranno più raggiungibili per la pubblicazione finché non si ricollega l'account."
        confirmLabel="Disconnetti"
        destructive
        loading={disconnectConnection.isPending}
        onConfirm={() => {
          if (!disconnectTarget) return;
          disconnectConnection.mutate(disconnectTarget.id, {
            onSuccess: () => setDisconnectTarget(null),
          });
        }}
      />
    </div>
  );
}
