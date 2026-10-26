"use client";

import { useState } from "react";
import { toast } from "sonner";
import { DatabaseIcon, KeyRoundIcon, Loader2Icon, ShieldCheckIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";
import { useCheckCrmKey, useUpdateAIAgentConfig } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniAIAgentConfigResponse, OmniCrmKeyCheckResponse } from "@/types/api";

const DEFAULT_BASE_URL = "https://mamify.app/m/api/plugins/mamify/rag/";

const CHECK_TONE: Record<OmniCrmKeyCheckResponse["status"], string> = {
  ok: "border-success/40 bg-success/10 text-success",
  invalid: "border-destructive/40 bg-destructive/10 text-destructive",
  no_permission: "border-warning/40 bg-warning/10 text-warning",
  unavailable: "border-warning/40 bg-warning/10 text-warning",
  error: "border-destructive/40 bg-destructive/10 text-destructive",
  not_configured: "border-border bg-muted/40 text-muted-foreground",
};

/**
 * Integrazione CRM Mamify: la chiave entra qui e non esce piu'. L'API dice solo
 * se e' impostata (e se viene da questa pagina o dall'ambiente), quindi il
 * campo e' sempre vuoto e scrivere qualcosa vuol dire sostituirla.
 *
 * Salva per conto suo (non col "Salva" in alto): accendere l'accesso ai dati
 * personali dei clienti e' un gesto a parte, con una conferma, come
 * l'autorisponditore.
 */
export function CrmSection({ config }: { config: OmniAIAgentConfigResponse }) {
  const updateConfig = useUpdateAIAgentConfig();
  const checkKey = useCheckCrmKey();
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(config.crm_base_url ?? "");
  const [showAdvanced, setShowAdvanced] = useState(!!config.crm_base_url);
  const [confirmEnableOpen, setConfirmEnableOpen] = useState(false);
  const [lastCheck, setLastCheck] = useState<OmniCrmKeyCheckResponse | null>(null);

  const dirty = apiKey.trim().length > 0 || (baseUrl.trim() || "") !== (config.crm_base_url ?? "");

  function saveCredentials() {
    const payload: Parameters<typeof updateConfig.mutate>[0] = {};
    if (apiKey.trim()) payload.crm_api_key = apiKey.trim();
    if ((baseUrl.trim() || "") !== (config.crm_base_url ?? "")) payload.crm_base_url = baseUrl.trim() || null;
    updateConfig.mutate(payload, {
      onSuccess: () => {
        setApiKey("");
        setLastCheck(null);
        toast.success("Credenziali CRM salvate");
      },
      onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile salvare le credenziali"),
    });
  }

  function removeKey() {
    updateConfig.mutate(
      { crm_api_key: "", crm_enabled: false },
      {
        onSuccess: () => {
          setLastCheck(null);
          toast.success("Chiave CRM rimossa e integrazione spenta");
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile rimuovere la chiave"),
      }
    );
  }

  function setEnabled(enabled: boolean) {
    updateConfig.mutate(
      { crm_enabled: enabled },
      {
        onSuccess: () => toast.success(enabled ? "Accesso al CRM attivato: l'AI può consultare i dati del cliente che scrive" : "Accesso al CRM disattivato"),
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile aggiornare l'integrazione"),
      }
    );
  }

  function runCheck() {
    checkKey.mutate(undefined, {
      onSuccess: setLastCheck,
      onError: (err) => toast.error(err instanceof ApiError ? err.message : "Verifica non riuscita"),
    });
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <DatabaseIcon className={cn("mt-0.5 size-5 shrink-0", config.crm_enabled ? "text-primary" : "text-muted-foreground")} />
          <div>
            <p className="text-base font-semibold">
              CRM Mamify: {config.crm_enabled ? "ATTIVO" : "SPENTO"}
            </p>
            <p className="text-sm text-muted-foreground">
              Con il CRM attivo l&apos;AI può rispondere con i dati del cliente che scrive: saldi Mamix e MamiCash, movimenti, ordini e rete di invitati, oltre a prodotti e gift card del catalogo.
            </p>
          </div>
        </div>
        <Switch
          checked={config.crm_enabled}
          disabled={updateConfig.isPending || (!config.crm_enabled && !config.crm_api_key_set)}
          onCheckedChange={(next) => (next ? setConfirmEnableOpen(true) : setEnabled(false))}
        />
      </div>

      <ConfirmDialog
        open={confirmEnableOpen}
        onOpenChange={setConfirmEnableOpen}
        title="Attivare l'accesso al CRM?"
        description="L'AI potrà leggere dal CRM Mamify i dati dell'account del cliente che sta scrivendo e usarli nelle risposte. Il cliente viene identificato solo dal numero WhatsApp da cui scrive (o dai contatti che inserisci tu nella sua scheda), mai da ciò che scrive in chat: nessuno può chiedere dati di un'altra persona. Su Telegram, Instagram e Facebook, dove il numero non c'è, l'AI non fornirà dati di account."
        confirmLabel="Sì, attiva"
        loading={updateConfig.isPending}
        onConfirm={() => {
          setEnabled(true);
          setConfirmEnableOpen(false);
        }}
      />

      <div className="rounded-md border border-dashed bg-muted/30 p-3 text-xs text-muted-foreground">
        <p className="flex items-center gap-1.5 font-medium text-foreground">
          <ShieldCheckIcon className="size-3.5" /> Come funziona la privacy
        </p>
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          <li>Il cliente è identificato dal <strong>numero WhatsApp del mittente</strong>, o da telefono/email che l&apos;operatore scrive nella scheda cliente. Mai da email, codici o numeri scritti dal cliente in chat.</li>
          <li>Se un numero corrisponde a più account, l&apos;AI chiede l&apos;email e la usa solo <em>insieme</em> al numero per distinguere, mai da sola.</li>
          <li>Senza identità verificabile (Telegram, Instagram, Facebook, numero non in anagrafica) l&apos;AI non fornisce saldi, ordini o rete: restano solo prodotti e gift card.</li>
          <li>Ogni consultazione finisce nell&apos;audit della bozza (quale strumento, con che esito), senza dati personali.</li>
        </ul>
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <Label className="flex items-center gap-1.5"><KeyRoundIcon className="size-3.5" /> Chiave API (X-Fw360-Key)</Label>
          <Input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config.crm_api_key_set ? "•••••••• chiave impostata: scrivi qui per sostituirla" : "Incolla la chiave creata in Sviluppatori > API > Chiavi API"}
          />
          <p className="text-xs text-muted-foreground">
            {config.crm_api_key_set ? (
              <>
                <Badge variant="outline" className="mr-1.5">{config.crm_api_key_source === "env" ? "dall'ambiente del server" : "impostata"}</Badge>
                La chiave è cifrata e non viene mai mostrata. Sulla chiave vanno spuntati gli endpoint del gruppo <em>Plugins › Mamify › Rag</em>.
              </>
            ) : (
              <>Dal pannello Mamify: <em>Sviluppatori › API › Chiavi API</em>, nuova chiave, poi spunta nel gruppo <em>Plugins › Mamify › Rag</em> gli endpoint che servono.</>
            )}
          </p>
        </div>
        <div className="flex items-start gap-2 pt-6">
          <Button variant="outline" onClick={runCheck} disabled={checkKey.isPending || !config.crm_api_key_set || dirty} title={dirty ? "Salva prima le modifiche" : undefined}>
            {checkKey.isPending ? <Loader2Icon className="animate-spin" /> : <ShieldCheckIcon />} Verifica chiave
          </Button>
        </div>
      </div>

      {lastCheck && (
        <div className={cn("rounded-md border px-3 py-2 text-sm", CHECK_TONE[lastCheck.status])}>
          {lastCheck.message}
        </div>
      )}

      <div className="space-y-2">
        <button type="button" className="text-xs text-muted-foreground underline" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "Nascondi impostazioni avanzate" : "Impostazioni avanzate"}
        </button>
        {showAdvanced && (
          <div className="space-y-1.5">
            <Label>Indirizzo base delle API</Label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={DEFAULT_BASE_URL} />
            <p className="text-xs text-muted-foreground">Lascia vuoto per usare l&apos;indirizzo di produzione. Solo https.</p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button onClick={saveCredentials} disabled={!dirty || updateConfig.isPending}>
          {updateConfig.isPending ? <Loader2Icon className="animate-spin" /> : <KeyRoundIcon />} Salva credenziali CRM
        </Button>
        {config.crm_api_key_set && config.crm_api_key_source === "config" && (
          <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={removeKey} disabled={updateConfig.isPending}>
            Rimuovi chiave
          </Button>
        )}
      </div>
    </div>
  );
}
