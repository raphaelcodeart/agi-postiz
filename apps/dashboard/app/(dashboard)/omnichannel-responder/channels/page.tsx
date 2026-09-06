"use client";

import { useState } from "react";
import { toast } from "sonner";
import { PlusIcon, Trash2Icon, WebhookIcon, InfoIcon, PlayIcon, RadioIcon, KeyIcon, RefreshCwIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/shared/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useChannelAccounts, useCheckChannelAccountStatus, useDeleteChannelAccount, useToggleChannelAccount } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { ChannelIcon, channelLabel } from "../_components/channel-icon";
import { CreateChannelDialog } from "./_components/create-channel-dialog";
import { RegisterWebhookDialog } from "./_components/register-webhook-dialog";
import { SimulateMessageDialog } from "./_components/simulate-message-dialog";
import { MetaWebhookInfoDialog } from "./_components/meta-webhook-info-dialog";
import { EditCredentialsDialog } from "./_components/edit-credentials-dialog";
import type { OmniChannel } from "@/types/api";

const META_CHANNELS: OmniChannel[] = ["facebook", "instagram", "whatsapp"];

export default function OmnichannelChannelsPage() {
  const { data: accounts, isLoading } = useChannelAccounts();
  const deleteChannelAccount = useDeleteChannelAccount();
  const toggleChannelAccount = useToggleChannelAccount();
  const checkChannelAccountStatus = useCheckChannelAccountStatus();

  const [createOpen, setCreateOpen] = useState(false);
  const [webhookAccountId, setWebhookAccountId] = useState<string | null>(null);
  const [metaInfoAccountId, setMetaInfoAccountId] = useState<string | null>(null);
  const [simulateAccountId, setSimulateAccountId] = useState<string | null>(null);
  const [deleteAccountId, setDeleteAccountId] = useState<string | null>(null);
  const [editCredentialsAccountId, setEditCredentialsAccountId] = useState<string | null>(null);
  const metaInfoAccount = accounts?.find((a) => a.id === metaInfoAccountId);
  const editCredentialsAccount = accounts?.find((a) => a.id === editCredentialsAccountId);

  return (
    <div>
      <PageHeader
        title="Canali collegati"
        description="Gestisci gli account WhatsApp, Instagram, Facebook, Telegram e Gmail collegati al tuo inbox."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <PlusIcon /> Nuovo canale
          </Button>
        }
      />

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : !accounts || accounts.length === 0 ? (
        <EmptyState
          icon={RadioIcon}
          title="Nessun canale collegato"
          description="Collega Telegram o crea un canale di test per iniziare a ricevere messaggi."
          action={<Button onClick={() => setCreateOpen(true)}><PlusIcon /> Nuovo canale</Button>}
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Canale</TableHead>
                <TableHead>Nome</TableHead>
                <TableHead>Stato</TableHead>
                <TableHead>Ricezione</TableHead>
                <TableHead>Conversazioni</TableHead>
                <TableHead>Creato</TableHead>
                <TableHead className="text-right">Azioni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {accounts.map((account) => (
                <TableRow key={account.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <ChannelIcon channel={account.channel} />
                      {channelLabel(account.channel)}
                    </div>
                  </TableCell>
                  <TableCell>{account.name}</TableCell>
                  <TableCell><StatusBadge status={account.status} /></TableCell>
                  <TableCell>
                    {account.channel !== "mock" && (
                      <Switch
                        checked={account.status !== "disabled"}
                        disabled={toggleChannelAccount.isPending}
                        title={account.status === "disabled" ? "Riattiva la ricezione messaggi" : "Sospendi la ricezione messaggi"}
                        onCheckedChange={() =>
                          toggleChannelAccount.mutate(account.id, {
                            onSuccess: (updated) =>
                              toast.success(updated.status === "disabled" ? `${updated.name}: ricezione sospesa` : `${updated.name}: ricezione riattivata`),
                            onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile cambiare lo stato del canale"),
                          })
                        }
                      />
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{account.conversation_count}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDateTime(account.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      {account.channel === "telegram" && (
                        <Button size="icon-sm" variant="ghost" title="Registra webhook" onClick={() => setWebhookAccountId(account.id)}>
                          <WebhookIcon />
                        </Button>
                      )}
                      {META_CHANNELS.includes(account.channel) && (
                        <Button size="icon-sm" variant="ghost" title="Info webhook" onClick={() => setMetaInfoAccountId(account.id)}>
                          <InfoIcon />
                        </Button>
                      )}
                      {account.channel === "mock" && (
                        <Button size="icon-sm" variant="ghost" title="Simula messaggio" onClick={() => setSimulateAccountId(account.id)}>
                          <PlayIcon />
                        </Button>
                      )}
                      {account.channel !== "mock" && (
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          title="Verifica connessione"
                          disabled={checkChannelAccountStatus.isPending}
                          onClick={() =>
                            checkChannelAccountStatus.mutate(account.id, {
                              onSuccess: (result) =>
                                result.status === "connected"
                                  ? toast.success(`${account.name}: connesso`)
                                  : toast.error(`${account.name}: ${typeof result.detail === "string" ? result.detail : "errore di connessione"}`),
                              onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile verificare la connessione"),
                            })
                          }
                        >
                          <RefreshCwIcon />
                        </Button>
                      )}
                      {account.channel !== "mock" && (
                        <Button size="icon-sm" variant="ghost" title="Modifica credenziali" onClick={() => setEditCredentialsAccountId(account.id)}>
                          <KeyIcon />
                        </Button>
                      )}
                      <Button size="icon-sm" variant="ghost" className="text-destructive hover:text-destructive" title="Elimina" onClick={() => setDeleteAccountId(account.id)}>
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CreateChannelDialog open={createOpen} onOpenChange={setCreateOpen} />
      {webhookAccountId && (
        <RegisterWebhookDialog open={!!webhookAccountId} onOpenChange={(open) => !open && setWebhookAccountId(null)} channelAccountId={webhookAccountId} />
      )}
      {simulateAccountId && (
        <SimulateMessageDialog open={!!simulateAccountId} onOpenChange={(open) => !open && setSimulateAccountId(null)} channelAccountId={simulateAccountId} />
      )}
      {metaInfoAccount && (
        <MetaWebhookInfoDialog
          open={!!metaInfoAccountId}
          onOpenChange={(open) => !open && setMetaInfoAccountId(null)}
          channel={metaInfoAccount.channel}
          channelAccountId={metaInfoAccount.id}
          verifyToken={metaInfoAccount.webhook_secret}
        />
      )}
      {editCredentialsAccount && (
        <EditCredentialsDialog
          open={!!editCredentialsAccountId}
          onOpenChange={(open) => !open && setEditCredentialsAccountId(null)}
          account={editCredentialsAccount}
        />
      )}
      <ConfirmDialog
        open={!!deleteAccountId}
        onOpenChange={(open) => !open && setDeleteAccountId(null)}
        title="Eliminare questo canale?"
        description="Le conversazioni collegate resteranno visibili nello storico, ma non riceverai più nuovi messaggi da questo canale."
        confirmLabel="Elimina"
        destructive
        loading={deleteChannelAccount.isPending}
        onConfirm={() => {
          if (!deleteAccountId) return;
          deleteChannelAccount.mutate(deleteAccountId, {
            onSuccess: () => setDeleteAccountId(null),
            onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile eliminare il canale"),
          });
        }}
      />
    </div>
  );
}
