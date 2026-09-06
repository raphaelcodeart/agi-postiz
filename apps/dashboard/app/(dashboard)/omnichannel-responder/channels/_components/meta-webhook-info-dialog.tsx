"use client";

import { useState } from "react";
import { toast } from "sonner";
import { CopyIcon } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { OmniChannel } from "@/types/api";

function CopyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex gap-2">
        <Input value={value} readOnly onFocus={(e) => e.target.select()} className="font-mono text-xs" />
        <Button
          type="button"
          size="icon"
          variant="outline"
          onClick={() => {
            navigator.clipboard.writeText(value);
            toast.success("Copiato");
          }}
        >
          <CopyIcon />
        </Button>
      </div>
    </div>
  );
}

const META_CHANNEL_LABEL: Partial<Record<OmniChannel, string>> = {
  facebook: "Facebook",
  instagram: "Instagram",
  whatsapp: "WhatsApp",
};

const META_SUBSCRIBE_FIELD: Partial<Record<OmniChannel, string>> = {
  facebook: "messages",
  instagram: "messages",
  whatsapp: "messages",
};

/**
 * Shared across facebook/instagram/whatsapp - all three run on Meta's same
 * webhook subscription mechanics (see backend api/v1/omnichannel_webhooks.py
 * ::_meta_webhook_verify), only the URL path segment and dashboard location
 * for pasting these values differ.
 */
export function MetaWebhookInfoDialog({
  open,
  onOpenChange,
  channel,
  channelAccountId,
  verifyToken,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channel: OmniChannel;
  channelAccountId: string;
  verifyToken: string;
}) {
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const webhookUrl = publicBaseUrl
    ? `${publicBaseUrl.replace(/\/$/, "")}/api/v1/omnichannel-responder/webhooks/${channel}/${channelAccountId}`
    : "";
  const label = META_CHANNEL_LABEL[channel] ?? channel;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Info webhook {label}</DialogTitle>
          <DialogDescription>
            A differenza di Telegram, qui non c&apos;è una registrazione automatica: incolla questi due valori tu stesso nella sezione Webhooks dell&apos;app Meta collegata.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>URL pubblico HTTPS di questa API</Label>
            <Input value={publicBaseUrl} onChange={(e) => setPublicBaseUrl(e.target.value)} placeholder="https://api.tuodominio.it" />
          </div>

          {webhookUrl && <CopyField label="URL di callback" value={webhookUrl} />}
          <CopyField label="Verify Token" value={verifyToken} />

          <p className="text-xs text-muted-foreground">
            Dopo aver salvato in Meta, iscrivi l&apos;app agli eventi <code>{META_SUBSCRIBE_FIELD[channel] ?? "messages"}</code> nella stessa schermata — senza quello, i messaggi non arriveranno mai qui anche se il webhook risulta verificato.
          </p>
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Chiudi</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
