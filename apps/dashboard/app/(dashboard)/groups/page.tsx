"use client";

import { useState } from "react";
import { PlusIcon, PencilIcon, UsersRoundIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { CardGridSkeleton } from "@/components/shared/loading-skeleton";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useGroups } from "@/hooks/use-users";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GroupResponse } from "@/types/api";
import { GroupFormDialog } from "./_components/group-form-dialog";
import { GroupMembersDialog } from "./_components/group-members-dialog";

const GROUP_TONES = [
  "bg-chart-1/12 text-chart-1",
  "bg-chart-2/12 text-chart-2",
  "bg-chart-3/12 text-chart-3",
  "bg-chart-4/12 text-chart-4",
  "bg-chart-5/12 text-chart-5",
];

export default function GroupsPage() {
  const groupsQuery = useGroups();
  const [formOpen, setFormOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<GroupResponse | undefined>(undefined);
  const [membersGroup, setMembersGroup] = useState<GroupResponse | undefined>(undefined);

  function openCreate() {
    setEditingGroup(undefined);
    setFormOpen(true);
  }

  function openEdit(group: GroupResponse) {
    setEditingGroup(group);
    setFormOpen(true);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Gruppi"
        description="Organizza gli utenti in gruppi per indirizzare le campagne"
        actions={
          <Button onClick={openCreate}>
            <PlusIcon className="size-4" />
            Nuovo gruppo
          </Button>
        }
      />

      {groupsQuery.isLoading && <CardGridSkeleton count={6} />}

      {groupsQuery.isError && <ErrorState error={groupsQuery.error} onRetry={() => groupsQuery.refetch()} />}

      {groupsQuery.data && groupsQuery.data.length === 0 && (
        <EmptyState
          icon={UsersRoundIcon}
          title="Nessun gruppo creato"
          description="Crea un gruppo per iniziare a segmentare i tuoi utenti."
        />
      )}

      {groupsQuery.data && groupsQuery.data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {groupsQuery.data.map((group, index) => (
            <Card key={group.id} className="animate-in fade-in slide-in-from-bottom-1 duration-500">
              <CardHeader>
                <div
                  className={cn(
                    "mb-1 flex size-10 items-center justify-center rounded-xl",
                    GROUP_TONES[index % GROUP_TONES.length]
                  )}
                >
                  <UsersRoundIcon className="size-5" />
                </div>
                <CardTitle className="text-base">{group.name}</CardTitle>
                <CardAction>
                  <Button variant="ghost" size="icon-sm" aria-label="Modifica gruppo" onClick={() => openEdit(group)}>
                    <PencilIcon className="size-3.5" />
                  </Button>
                </CardAction>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{group.description || "Nessuna descrizione"}</p>
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary">
                    {group.user_count} {group.user_count === 1 ? "utente" : "utenti"}
                  </Badge>
                  <Button variant="outline" size="sm" onClick={() => setMembersGroup(group)}>
                    <UsersRoundIcon className="size-3.5" />
                    Vedi utenti
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">Creato il {formatDateTime(group.created_at)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <GroupFormDialog open={formOpen} onOpenChange={setFormOpen} group={editingGroup} />
      {membersGroup && (
        <GroupMembersDialog
          open={!!membersGroup}
          onOpenChange={(open) => !open && setMembersGroup(undefined)}
          group={membersGroup}
        />
      )}
    </div>
  );
}
