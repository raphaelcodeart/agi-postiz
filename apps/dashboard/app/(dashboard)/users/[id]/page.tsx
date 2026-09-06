"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { PencilIcon, Trash2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useUser, useDeleteUser } from "@/hooks/use-users";
import { useBufferConnections } from "@/hooks/use-buffer-connections";
import { useChannels } from "@/hooks/use-channels";
import { formatDateTime } from "@/lib/format";
import { UserFormDialog } from "../_components/user-form-dialog";

export default function UserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const userQuery = useUser(id);
  const connectionsQuery = useBufferConnections();
  const channelsQuery = useChannels({ user_id: id });
  const deleteUser = useDeleteUser();

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const userConnections = connectionsQuery.data?.filter((c) => c.user_id === id) ?? [];

  if (userQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (userQuery.isError || !userQuery.data) {
    return <ErrorState error={userQuery.error} onRetry={() => userQuery.refetch()} />;
  }

  const user = userQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={user.name}
        description={user.email}
        actions={
          <>
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <PencilIcon className="size-4" />
              Modifica
            </Button>
            <Button variant="outline" className="text-destructive" onClick={() => setDeleteOpen(true)}>
              <Trash2Icon className="size-4" />
              Elimina
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Profilo</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Stato</span>
              <StatusBadge status={user.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Azienda</span>
              <span>{user.company_name || "—"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Creato</span>
              <span>{formatDateTime(user.created_at)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Aggiornato</span>
              <span>{formatDateTime(user.updated_at)}</span>
            </div>
            {user.notes && (
              <div className="space-y-1 border-t pt-3">
                <span className="text-muted-foreground">Note</span>
                <p>{user.notes}</p>
              </div>
            )}
            <div className="space-y-2 border-t pt-3">
              <span className="text-muted-foreground">Gruppi</span>
              <div className="flex flex-wrap gap-1.5">
                {user.groups.length > 0 ? (
                  user.groups.map((group) => <Badge key={group.id} variant="secondary">{group.name}</Badge>)
                ) : (
                  <span className="text-sm text-muted-foreground">Nessun gruppo</span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Connessioni Buffer</CardTitle>
          </CardHeader>
          <CardContent>
            {userConnections.length > 0 ? (
              <ul className="divide-y">
                {userConnections.map((connection) => (
                  <li key={connection.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div>
                      <p className="text-sm font-medium">{connection.external_account_id ?? "Account Buffer"}</p>
                      <p className="text-xs text-muted-foreground">
                        Ultima sincronizzazione: {formatDateTime(connection.last_sync_at)}
                      </p>
                    </div>
                    <StatusBadge status={connection.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Nessuna connessione Buffer" description="Questo utente non ha ancora collegato un account Buffer." />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Canali social</CardTitle>
          </CardHeader>
          <CardContent>
            {channelsQuery.data && channelsQuery.data.length > 0 ? (
              <ul className="divide-y">
                {channelsQuery.data.map((channel) => (
                  <li key={channel.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="flex items-center gap-3">
                      <PlatformBadge platform={channel.platform} />
                      <div>
                        <p className="text-sm font-medium">{channel.name}</p>
                        {channel.username && <p className="text-xs text-muted-foreground">@{channel.username}</p>}
                      </div>
                    </div>
                    <StatusBadge status={channel.publication_mode} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Nessun canale social" />
            )}
          </CardContent>
        </Card>
      </div>

      <UserFormDialog open={editOpen} onOpenChange={setEditOpen} user={user} />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Eliminare questo utente?"
        description="L'utente verrà disattivato e non sarà più visibile negli elenchi. Questa azione non elimina lo storico delle pubblicazioni."
        confirmLabel="Elimina"
        destructive
        loading={deleteUser.isPending}
        onConfirm={() =>
          deleteUser.mutate(id, {
            onSuccess: () => router.push("/users"),
          })
        }
      />
    </div>
  );
}
