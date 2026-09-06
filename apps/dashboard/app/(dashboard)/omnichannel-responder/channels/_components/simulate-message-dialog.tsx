"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSimulateMessage } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";

export function SimulateMessageDialog({ open, onOpenChange, channelAccountId }: { open: boolean; onOpenChange: (open: boolean) => void; channelAccountId: string }) {
  const [externalUserId, setExternalUserId] = useState("test-user-1");
  const [customerName, setCustomerName] = useState("Mario Rossi");
  const [text, setText] = useState("Buongiorno, quanto costa il vostro servizio?");
  const simulateMessage = useSimulateMessage();

  function handleSubmit() {
    simulateMessage.mutate(
      { channelAccountId, externalUserId, text, customerName },
      {
        onSuccess: () => {
          toast.success("Messaggio simulato inviato - apri l'Inbox per vedere la bozza AI");
          onOpenChange(false);
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile simulare il messaggio"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Simula messaggio in arrivo</DialogTitle>
          <DialogDescription>
            Testa l&apos;intera pipeline (ingest → bozza AI → approvazione → invio) senza credenziali reali, usando questo canale di test.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>ID cliente simulato</Label>
            <Input value={externalUserId} onChange={(e) => setExternalUserId(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Nome cliente</Label>
            <Input value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Messaggio</Label>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={handleSubmit} disabled={simulateMessage.isPending || !text.trim()}>Invia simulazione</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
