"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegisterChannelWebhook } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";

export function RegisterWebhookDialog({ open, onOpenChange, channelAccountId }: { open: boolean; onOpenChange: (open: boolean) => void; channelAccountId: string }) {
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const registerWebhook = useRegisterChannelWebhook();

  function handleSubmit() {
    registerWebhook.mutate(
      { id: channelAccountId, publicBaseUrl },
      {
        onSuccess: () => {
          toast.success("Webhook Telegram registrato");
          onOpenChange(false);
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile registrare il webhook"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Registra webhook Telegram</DialogTitle>
          <DialogDescription>
            Inserisci l&apos;URL pubblico HTTPS di questa API (es. quello del vhost api.* configurato in nginx) - Telegram invierà lì i messaggi in arrivo.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label>URL pubblico dell&apos;API</Label>
          <Input value={publicBaseUrl} onChange={(e) => setPublicBaseUrl(e.target.value)} placeholder="https://api.tuodominio.it" />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={handleSubmit} disabled={registerWebhook.isPending || !publicBaseUrl.trim()}>Registra</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
