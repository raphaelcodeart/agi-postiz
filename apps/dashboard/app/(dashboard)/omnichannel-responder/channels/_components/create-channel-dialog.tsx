"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCreateChannelAccount } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniChannel } from "@/types/api";

const CHANNEL_OPTIONS: { value: OmniChannel; label: string; available: boolean }[] = [
  { value: "telegram", label: "Telegram", available: true },
  { value: "facebook", label: "Facebook Messenger", available: true },
  { value: "instagram", label: "Instagram Direct", available: true },
  { value: "whatsapp", label: "WhatsApp Business (Cloud API Meta)", available: true },
  { value: "whatsapp_maytapi", label: "WhatsApp — numero personale (Maytapi)", available: true },
  { value: "gmail", label: "Gmail", available: true },
  { value: "mock", label: "Test (mock, nessun account reale)", available: true },
];

// facebook/instagram/whatsapp all need the same Access Token + App Secret
// pair (Meta's shared Graph API webhook infrastructure, see backend
// connectors/facebook.py) plus, WhatsApp only, a Phone Number ID.
const META_CHANNELS: OmniChannel[] = ["facebook", "instagram", "whatsapp"];

const META_TOKEN_LABEL: Partial<Record<OmniChannel, string>> = {
  facebook: "Page Access Token",
  instagram: "Page/IG Access Token",
  whatsapp: "Access Token (Cloud API)",
};

export function CreateChannelDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [channel, setChannel] = useState<OmniChannel>("telegram");
  const [name, setName] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [gmailAddress, setGmailAddress] = useState("");
  const [productId, setProductId] = useState("");
  const [phoneId, setPhoneId] = useState("");
  const createChannelAccount = useCreateChannelAccount();
  const isMeta = META_CHANNELS.includes(channel);
  const isGmail = channel === "gmail";
  const isMaytapi = channel === "whatsapp_maytapi";

  function reset() {
    setChannel("telegram");
    setName("");
    setAccessToken("");
    setAppSecret("");
    setPhoneNumberId("");
    setGmailAddress("");
    setProductId("");
    setPhoneId("");
  }

  function handleSubmit() {
    if (!name.trim()) {
      toast.error("Inserisci un nome per il canale");
      return;
    }
    if (isGmail && (!gmailAddress.trim() || !accessToken.trim())) {
      toast.error("Inserisci indirizzo Gmail e App Password");
      return;
    }
    // Maytapi, a differenza dei canali Meta, non ha il problema di dover
    // esistere prima di poter recuperare le credenziali: Product ID, Phone ID e
    // token stanno tutti sulla stessa pagina della console, prima di venire
    // qui. Quindi si chiedono subito, e il canale nasce già funzionante.
    if (isMaytapi && (!productId.trim() || !phoneId.trim() || !accessToken.trim())) {
      toast.error("Inserisci Product ID, Phone ID e API Token di Maytapi");
      return;
    }
    // Credentials are optional at creation time for Meta channels (Facebook/
    // Instagram/WhatsApp) on purpose: Meta's own Webhooks screen needs this
    // channel's webhook_secret to exist before you can even reach the screen
    // where you'd get the real Access Token/App Secret/Phone Number ID from
    // Meta's API Setup - not having one shouldn't block having the other.
    // Fill them in later via "Modifica credenziali" on the channel row. Gmail
    // has no such bootstrap problem (no webhook to register at all - it's
    // polled, see docs/OMNICHANNEL_RESPONDER.md), so both fields are required
    // upfront instead.
    createChannelAccount.mutate(
      {
        channel,
        name,
        access_token: accessToken || undefined,
        app_secret: isMeta ? appSecret : undefined,
        external_account_id: channel === "whatsapp" ? phoneNumberId : isGmail ? gmailAddress : undefined,
        // Product ID e Phone ID non sono segreti (indirizzano quale istanza e
        // quale numero usare, come il Phone Number ID della Cloud API) quindi
        // vanno in `config`, in chiaro, e non nel blob cifrato col token.
        config: isMaytapi ? { product_id: productId.trim(), phone_id: phoneId.trim() } : undefined,
      },
      {
        onSuccess: () => {
          const missingCreds = isMeta && (!accessToken.trim() || !appSecret.trim() || (channel === "whatsapp" && !phoneNumberId.trim()));
          toast.success(
            missingCreds
              ? "Canale creato — apri ℹ️ \"Info webhook\" per il Verify Token, poi torna qui a completare le credenziali con \"Modifica credenziali\""
              : "Canale creato"
          );
          reset();
          onOpenChange(false);
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile creare il canale"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { onOpenChange(next); if (!next) reset(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuovo canale</DialogTitle>
          <DialogDescription>Collega un canale di messaggistica al tuo inbox unificato.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Canale</Label>
            <Select items={CHANNEL_OPTIONS} value={channel} onValueChange={(v) => setChannel(v as OmniChannel)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CHANNEL_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} disabled={!opt.available}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Nome</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Es. Bot assistenza clienti" />
          </div>

          {channel === "telegram" && (
            <div className="space-y-1.5">
              <Label>Bot Token</Label>
              <PasswordInput value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="123456:ABC-DEF..." />
              <p className="text-xs text-muted-foreground">
                Crealo con @BotFather su Telegram. Dopo la creazione, registra il webhook dalla lista canali.
              </p>
            </div>
          )}

          {isMaytapi && (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Product ID</Label>
                  <Input value={productId} onChange={(e) => setProductId(e.target.value)} placeholder="es. 1a2b3c4d-..." />
                </div>
                <div className="space-y-1.5">
                  <Label>Phone ID</Label>
                  <Input value={phoneId} onChange={(e) => setPhoneId(e.target.value)} placeholder="es. 12345" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>API Token</Label>
                <PasswordInput value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="Token Maytapi" />
              </div>
              <p className="text-xs text-muted-foreground">
                Tutti e tre si trovano in console.maytapi.com → Settings → Token. Il numero va prima
                collegato via QR code dalla console, come si fa con WhatsApp Web. Dopo aver creato il
                canale, premi <span className="font-medium">Registra webhook</span> nella lista per far
                arrivare qui i messaggi.
              </p>
              <p className="text-xs text-muted-foreground">
                A differenza di WhatsApp Business (Cloud API), qui il numero è uno normale e non ci sono
                né verifica aziendale né template approvati: si risponde liberamente, anche oltre le 24 ore.
              </p>
            </div>
          )}

          {isGmail && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Indirizzo Gmail</Label>
                <Input value={gmailAddress} onChange={(e) => setGmailAddress(e.target.value)} placeholder="supporto@gmail.com" type="email" />
              </div>
              <div className="space-y-1.5">
                <Label>App Password</Label>
                <PasswordInput value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="xxxx xxxx xxxx xxxx" />
                <p className="text-xs text-muted-foreground">
                  Non la password normale dell&apos;account. Richiede la verifica in due passaggi attiva: Account Google → Sicurezza → Password per le app.
                  I messaggi vengono controllati ogni pochi minuti (polling IMAP), non in tempo reale.
                </p>
              </div>
            </div>
          )}

          {isMeta && (
            <>
              <div className="space-y-1.5">
                <Label>{META_TOKEN_LABEL[channel]}</Label>
                <PasswordInput value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="EAAxxxxx..." />
              </div>
              {channel === "whatsapp" && (
                <div className="space-y-1.5">
                  <Label>Phone Number ID</Label>
                  <Input value={phoneNumberId} onChange={(e) => setPhoneNumberId(e.target.value)} placeholder="Da WhatsApp Manager" />
                </div>
              )}
              <div className="space-y-1.5">
                <Label>App Secret</Label>
                <PasswordInput value={appSecret} onChange={(e) => setAppSecret(e.target.value)} placeholder="App Dashboard → Impostazioni → Basic" />
              </div>
              <p className="text-xs text-muted-foreground">
                Si trovano nell&apos;app Meta collegata (developers.facebook.com). Dopo la creazione, apri &quot;Info webhook&quot; dalla lista canali per l&apos;URL e il token da incollare nelle impostazioni webhook dell&apos;app.
              </p>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={handleSubmit} disabled={createChannelAccount.isPending}>Crea canale</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
