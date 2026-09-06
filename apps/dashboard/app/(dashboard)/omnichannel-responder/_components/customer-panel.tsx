"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PhoneIcon, MailIcon, TagIcon, PlusIcon, BanIcon, ShieldOffIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { useConversationDetail, useUpdateCustomer, useTags, useAddConversationTag, useRemoveConversationTag, useBlockCustomer, useUnblockCustomer } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export function CustomerPanel({ conversationId }: { conversationId: string | null }) {
  const { data: conversation, isLoading } = useConversationDetail(conversationId);
  const { data: tags } = useTags();
  const updateCustomer = useUpdateCustomer(conversationId ?? "");
  const addTag = useAddConversationTag(conversationId ?? "");
  const removeTag = useRemoveConversationTag(conversationId ?? "");
  const blockCustomer = useBlockCustomer(conversationId ?? "");
  const unblockCustomer = useUnblockCustomer(conversationId ?? "");

  const [notes, setNotes] = useState("");
  const [confirmBlockOpen, setConfirmBlockOpen] = useState(false);

  useEffect(() => {
    setNotes(conversation?.customer.notes ?? "");
  }, [conversation?.customer.id, conversation?.customer.notes]);

  if (!conversationId) return <div className="border-l p-4" />;

  if (isLoading || !conversation) {
    return (
      <div className="space-y-3 border-l p-4">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  const customer = conversation.customer;
  const availableTags = (tags ?? []).filter((t) => !conversation.tags.some((ct) => ct.id === t.id));

  function saveNotes() {
    updateCustomer.mutate(
      { customerId: customer.id, payload: { notes } },
      { onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile salvare le note") }
    );
  }

  return (
    <div className="h-full min-h-0 space-y-5 overflow-y-auto border-l p-4">
      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">{customer.name || "Cliente sconosciuto"}</p>
          {customer.is_blocked ? (
            <Button
              size="xs"
              variant="outline"
              onClick={() =>
                unblockCustomer.mutate(customer.id, {
                  onSuccess: () => toast.success("Cliente sbloccato"),
                  onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile sbloccare il cliente"),
                })
              }
              disabled={unblockCustomer.isPending}
            >
              <ShieldOffIcon /> Sblocca
            </Button>
          ) : (
            <Button size="xs" variant="outline" className="text-destructive hover:text-destructive" onClick={() => setConfirmBlockOpen(true)}>
              <BanIcon /> Blocca
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">Cliente dal {formatDateTime(customer.created_at)}</p>
        {customer.is_blocked && (
          <div className="mt-2 flex items-center gap-1.5 rounded-md bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">
            <BanIcon className="size-3.5 shrink-0" /> Cliente bloccato: i suoi nuovi messaggi non generano più bozze AI.
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmBlockOpen}
        onOpenChange={setConfirmBlockOpen}
        title="Bloccare questo cliente?"
        description="I nuovi messaggi da questo cliente verranno comunque salvati, ma non genereranno più una bozza di risposta AI e la conversazione finirà automaticamente tra le Spam. Puoi sbloccarlo in qualsiasi momento."
        confirmLabel="Blocca"
        destructive
        loading={blockCustomer.isPending}
        onConfirm={() => {
          blockCustomer.mutate(customer.id, {
            onSuccess: () => {
              toast.success("Cliente bloccato");
              setConfirmBlockOpen(false);
            },
            onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile bloccare il cliente"),
          });
        }}
      />

      <div className="space-y-2 text-sm">
        {customer.phone && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <PhoneIcon className="size-3.5" /> {customer.phone}
          </div>
        )}
        {customer.email && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <MailIcon className="size-3.5" /> {customer.email}
          </div>
        )}
      </div>

      <div>
        <p className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <TagIcon className="size-3.5" /> Tag
        </p>
        <div className="flex flex-wrap gap-1.5">
          {conversation.tags.map((tag) => (
            <Badge key={tag.id} variant="outline" className="cursor-pointer gap-1" onClick={() => removeTag.mutate(tag.id)}>
              {tag.name} ×
            </Badge>
          ))}
          {availableTags.length > 0 && (
            <Select items={availableTags.map((t) => ({ value: t.id, label: t.name }))} onValueChange={(tagId) => addTag.mutate(tagId as string)}>
              <SelectTrigger size="sm" className="h-6 gap-1 px-2 text-xs">
                <PlusIcon className="size-3" />
                <SelectValue placeholder="Aggiungi" />
              </SelectTrigger>
              <SelectContent>
                {availableTags.map((tag) => (
                  <SelectItem key={tag.id} value={tag.id}>
                    {tag.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Canali collegati</p>
        <div className="space-y-1 text-xs text-muted-foreground">
          {customer.identities.map((identity) => (
            <div key={identity.id}>
              {identity.channel}: {identity.display_name || identity.external_user_id}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground">Note</p>
          {notes !== (customer.notes ?? "") && (
            <Button size="xs" variant="ghost" onClick={saveNotes} disabled={updateCustomer.isPending}>
              Salva
            </Button>
          )}
        </div>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} placeholder="Note interne sul cliente..." />
      </div>
    </div>
  );
}
