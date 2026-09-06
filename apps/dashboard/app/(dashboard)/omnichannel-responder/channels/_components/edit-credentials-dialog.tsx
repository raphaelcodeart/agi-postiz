"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { useUpdateChannelAccount } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniChannelAccountResponse } from "@/types/api";

const META_CHANNELS = ["facebook", "instagram", "whatsapp"];

const TOKEN_LABEL: Record<string, string> = {
  telegram: "Bot Token",
  facebook: "Page Access Token",
  instagram: "Page/IG Access Token",
  whatsapp: "Access Token (Cloud API)",
  gmail: "App Password",
};

/**
 * Fills in or rotates credentials on a channel created without them - e.g. a
 * WhatsApp/Meta channel created with just a name to get its webhook_secret
 * for Meta's Webhooks screen (see create-channel-dialog.tsx) before the real
 * Access Token/App Secret/Phone Number ID were even available yet.
 */
export function EditCredentialsDialog({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: OmniChannelAccountResponse;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [externalAccountId, setExternalAccountId] = useState(account.external_account_id ?? "");
  const updateChannelAccount = useUpdateChannelAccount();
  const isMeta = META_CHANNELS.includes(account.channel);
  const isGmail = account.channel === "gmail";

  function handleSubmit() {
    updateChannelAccount.mutate(
      {
        id: account.id,
        payload: {
          access_token: accessToken || undefined,
          app_secret: isMeta ? appSecret || undefined : undefined,
          external_account_id: account.channel === "whatsapp" || isGmail ? externalAccountId : undefined,
        },
      },
      {
        onSuccess: () => {
          toast.success("Credenziali aggiornate");
          onOpenChange(false);
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile aggiornare le credenziali"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Modifica credenziali — {account.name}</DialogTitle>
          <DialogDescription>
            Lascia vuoto un campo per non modificarlo. Le credenziali già salvate non vengono mai mostrate qui, per
            sicurezza.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{TOKEN_LABEL[account.channel] ?? "Access Token"}</Label>
            <PasswordInput value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="Lascia vuoto per non cambiarlo" />
          </div>
          {account.channel === "whatsapp" && (
            <div className="space-y-1.5">
              <Label>Phone Number ID</Label>
              <Input value={externalAccountId} onChange={(e) => setExternalAccountId(e.target.value)} placeholder="Da WhatsApp Manager" />
            </div>
          )}
          {isGmail && (
            <div className="space-y-1.5">
              <Label>Indirizzo Gmail</Label>
              <Input value={externalAccountId} onChange={(e) => setExternalAccountId(e.target.value)} placeholder="supporto@gmail.com" type="email" />
            </div>
          )}
          {isMeta && (
            <div className="space-y-1.5">
              <Label>App Secret</Label>
              <PasswordInput value={appSecret} onChange={(e) => setAppSecret(e.target.value)} placeholder="Lascia vuoto per non cambiarlo" />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={handleSubmit} disabled={updateChannelAccount.isPending}>Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
