"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertTriangleIcon, CheckIcon, XIcon } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useConversations, useSendBroadcast } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import { ChannelIcon, channelLabel } from "./channel-icon";
import type { OmniBroadcastResult } from "@/types/api";

const ACTIVE_STATUSES_ONLY = (status: string) => status !== "ARCHIVED" && status !== "SPAM";

export function BroadcastDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { data: allConversations } = useConversations({});
  const sendBroadcast = useSendBroadcast();
  const conversations = (allConversations ?? []).filter((c) => ACTIVE_STATUSES_ONLY(c.status));

  const [step, setStep] = useState<1 | 2>(1);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"all" | "select">("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<OmniBroadcastResult | null>(null);

  function reset() {
    setStep(1);
    setText("");
    setMode("all");
    setSelectedIds(new Set());
    setResult(null);
  }

  // Single close path used everywhere (the dialog's own X, "Annulla",
  // "Chiudi") so the form always resets - a button that called
  // onOpenChange(false) directly would close the dialog without resetting,
  // reopening later still showing the previous send's result screen.
  function handleClose() {
    onOpenChange(false);
    reset();
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const targetCount = mode === "all" ? conversations.length : selectedIds.size;

  function handleSend() {
    if (mode === "select" && selectedIds.size === 0) {
      toast.error("Seleziona almeno un destinatario");
      return;
    }
    sendBroadcast.mutate(
      { text, conversation_ids: mode === "select" ? Array.from(selectedIds) : undefined },
      {
        onSuccess: (res) => setResult(res),
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile inviare il messaggio multiplo"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(next) : handleClose())}>
      <DialogContent className="max-w-lg">
        {result ? (
          <>
            <DialogHeader>
              <DialogTitle>Invio completato</DialogTitle>
              <DialogDescription>
                {result.sent} inviati su {result.total_targeted} destinatari{result.failed > 0 ? `, ${result.failed} falliti` : ""}.
              </DialogDescription>
            </DialogHeader>
            {result.failures.length > 0 && (
              <div className="max-h-64 space-y-1.5 overflow-y-auto rounded-md border p-2">
                {result.failures.map((f) => (
                  <div key={f.conversation_id} className="flex items-start gap-2 rounded-md bg-destructive/5 px-2 py-1.5 text-xs">
                    <XIcon className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                    <div>
                      <span className="font-medium">{f.customer_name || "Cliente sconosciuto"}</span> ({channelLabel(f.channel)}): {f.error}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <DialogFooter>
              <Button onClick={handleClose}>Chiudi</Button>
            </DialogFooter>
          </>
        ) : step === 1 ? (
          <>
            <DialogHeader>
              <DialogTitle>Messaggio multiplo</DialogTitle>
              <DialogDescription>Scrivi il messaggio da inviare a più contatti dell&apos;Inbox in un colpo solo.</DialogDescription>
            </DialogHeader>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} placeholder="Scrivi qui il messaggio..." />
            <div className="flex items-start gap-2 rounded-md bg-warning/10 px-3 py-2 text-xs text-warning-foreground dark:text-warning">
              <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
              Per WhatsApp, Facebook e Instagram, Meta accetta messaggi liberi solo entro 24 ore dall&apos;ultimo messaggio del contatto — a chi ti ha scritto da più tempo l&apos;invio potrebbe essere rifiutato (lo vedrai chiaramente nel riepilogo finale). Su Telegram non c&apos;è questo limite.
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>Annulla</Button>
              <Button onClick={() => setStep(2)} disabled={!text.trim()}>Avanti</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Scegli i destinatari</DialogTitle>
              <DialogDescription>I contatti bloccati sono sempre esclusi, anche se selezionati.</DialogDescription>
            </DialogHeader>

            <div className="flex gap-2 text-xs">
              <button
                type="button"
                onClick={() => setMode("all")}
                className={`flex-1 rounded-md border px-3 py-2 text-left ${mode === "all" ? "border-primary bg-primary/10" : "border-border"}`}
              >
                <p className="font-medium">Tutti in Inbox</p>
                <p className="text-muted-foreground">{conversations.length} contatti</p>
              </button>
              <button
                type="button"
                onClick={() => setMode("select")}
                className={`flex-1 rounded-md border px-3 py-2 text-left ${mode === "select" ? "border-primary bg-primary/10" : "border-border"}`}
              >
                <p className="font-medium">Seleziona</p>
                <p className="text-muted-foreground">{selectedIds.size} selezionati</p>
              </button>
            </div>

            {mode === "select" && (
              <div className="max-h-72 space-y-1 overflow-y-auto rounded-md border p-2">
                {conversations.map((conv) => (
                  <label key={conv.id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50">
                    <Checkbox checked={selectedIds.has(conv.id)} onCheckedChange={() => toggleSelected(conv.id)} />
                    <Avatar size="sm">
                      <AvatarFallback>{(conv.customer.name || "?")[0]?.toUpperCase()}</AvatarFallback>
                    </Avatar>
                    <ChannelIcon channel={conv.channel} />
                    <span className="min-w-0 flex-1 truncate text-sm">{conv.customer.name || "Cliente sconosciuto"}</span>
                  </label>
                ))}
                {conversations.length === 0 && <p className="p-2 text-xs text-muted-foreground">Nessuna conversazione disponibile.</p>}
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep(1)}>Indietro</Button>
              <Button onClick={handleSend} disabled={sendBroadcast.isPending || targetCount === 0}>
                <CheckIcon /> Invia a {targetCount} {targetCount === 1 ? "contatto" : "contatti"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
