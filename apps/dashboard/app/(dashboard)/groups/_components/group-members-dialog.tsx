"use client";

import Link from "next/link";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/shared/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useGroupUsers } from "@/hooks/use-users";
import type { GroupResponse } from "@/types/api";

interface GroupMembersDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: GroupResponse;
}

export function GroupMembersDialog({ open, onOpenChange, group }: GroupMembersDialogProps) {
  const usersQuery = useGroupUsers(open ? group.id : undefined);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Utenti in &quot;{group.name}&quot;</DialogTitle>
          <DialogDescription>
            {group.user_count} {group.user_count === 1 ? "utente iscritto a questo gruppo" : "utenti iscritti a questo gruppo"}.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-1 overflow-y-auto">
          {usersQuery.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          )}

          {usersQuery.isError && <p className="text-sm text-destructive">Impossibile caricare gli utenti del gruppo.</p>}

          {usersQuery.data && usersQuery.data.length === 0 && (
            <p className="text-sm text-muted-foreground">Nessun utente iscritto a questo gruppo.</p>
          )}

          {usersQuery.data?.map((user) => (
            <Link
              key={user.id}
              href={`/users/${user.id}`}
              onClick={() => onOpenChange(false)}
              className="flex items-center justify-between gap-3 rounded-md px-2 py-2 text-sm hover:bg-accent"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-foreground">{user.name}</p>
                <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              </div>
              <StatusBadge status={user.status} />
            </Link>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
