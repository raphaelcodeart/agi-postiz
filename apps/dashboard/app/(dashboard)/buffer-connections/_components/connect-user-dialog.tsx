"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUsers } from "@/hooks/use-users";
import { useBufferConnections, useCreateConnection } from "@/hooks/use-buffer-connections";
import { ApiError } from "@/lib/api/errors";

interface ConnectUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-select a user, e.g. when reconnecting an existing row. */
  preselectedUserId?: string;
}

export function ConnectUserDialog({ open, onOpenChange, preselectedUserId }: ConnectUserDialogProps) {
  const usersQuery = useUsers({ status_filter: "active", limit: 100 });
  const connectionsQuery = useBufferConnections();
  const createConnection = useCreateConnection();
  const [userId, setUserId] = useState<string>("");
  const [apiKey, setApiKey] = useState<string>("");

  useEffect(() => {
    if (open) setUserId(preselectedUserId ?? "");
    if (open) setApiKey("");
  }, [open, preselectedUserId]);

  const connectedUserIds = new Set(connectionsQuery.data?.map((c) => c.user_id));
  const availableUsers = preselectedUserId
    ? (usersQuery.data ?? [])
    : (usersQuery.data?.filter((user) => !connectedUserIds.has(user.id)) ?? []);

  function handleConnect() {
    if (!userId || !apiKey.trim()) return;
    createConnection.mutate(
      { userId, apiKey: apiKey.trim() },
      {
        onSuccess: () => {
          toast.success("Account Buffer collegato");
          onOpenChange(false);
        },
        onError: (error) => {
          toast.error(error instanceof ApiError ? error.detail : "Chiave API Buffer non valida");
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Collega account Buffer</DialogTitle>
          <DialogDescription>
            Chiedi all&apos;utente di generare una chiave API personale dal proprio account
            Buffer (Settings → API) e incollala qui sotto. Non serve nessun accesso o
            autorizzazione su Buffer da parte tua.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Utente</Label>
            <Select
              items={availableUsers.map((user) => ({ value: user.id, label: user.name }))}
              value={userId}
              onValueChange={(value) => setUserId(value ?? "")}
              disabled={!!preselectedUserId}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Seleziona utente" />
              </SelectTrigger>
              <SelectContent>
                {availableUsers.length > 0 ? (
                  availableUsers.map((user) => (
                    <SelectItem key={user.id} value={user.id}>
                      {user.name}
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="__none__" disabled>
                    Nessun utente disponibile
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="buffer-api-key">Chiave API Buffer personale</Label>
            <Input
              id="buffer-api-key"
              type="password"
              autoComplete="off"
              placeholder="Incolla qui la chiave"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button
            disabled={!userId || !apiKey.trim() || createConnection.isPending}
            onClick={handleConnect}
          >
            {createConnection.isPending ? "Collegamento..." : "Collega"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
