"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { SaveIcon, ZapIcon, ShieldCheckIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { cn } from "@/lib/utils";
import { useAIAgentConfig, useUpdateAIAgentConfig } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniAIAgentConfigResponse } from "@/types/api";

const TONE_OPTIONS = [
  { value: "professionale", label: "Professionale" },
  { value: "amichevole", label: "Amichevole" },
  { value: "formale", label: "Formale" },
  { value: "informale", label: "Informale" },
];

const LANGUAGE_OPTIONS = [
  { value: "auto", label: "Automatica (segue il cliente)" },
  { value: "it", label: "Italiano" },
  { value: "en", label: "Inglese" },
];

const SENSITIVE_CATEGORY_OPTIONS = [
  { value: "refund", label: "Rimborso" },
  { value: "legal", label: "Questione legale" },
  { value: "medical", label: "Argomento medico" },
  { value: "complaint", label: "Reclamo" },
  { value: "pricing_exception", label: "Eccezione di prezzo" },
  { value: "discount", label: "Sconto" },
  { value: "contract", label: "Contratto" },
  { value: "payment_problem", label: "Problema di pagamento" },
];

function toCsv(values: string[] | null): string {
  return (values ?? []).join(", ");
}
function fromCsv(text: string): string[] {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

export default function OmnichannelSettingsPage() {
  const { data: config, isLoading } = useAIAgentConfig();
  const updateConfig = useUpdateAIAgentConfig();

  const [form, setForm] = useState<{
    name: string; description: string; system_prompt: string; language: string; tone: string;
    temperature: number; company_description: string; allowed_topics: string; forbidden_topics: string;
    signature: string; max_context_messages: number; knowledge_base_enabled: boolean;
    automatic_language_detection: boolean; sensitive_categories: string[];
    auto_generate_draft: boolean;
    response_mode: OmniAIAgentConfigResponse["response_mode"];
  } | null>(null);
  const [confirmAutoReplyOpen, setConfirmAutoReplyOpen] = useState(false);

  useEffect(() => {
    if (!config) return;
    setForm({
      name: config.name,
      description: config.description ?? "",
      system_prompt: config.system_prompt ?? "",
      language: config.language,
      tone: config.tone,
      temperature: config.temperature,
      company_description: config.company_description ?? "",
      allowed_topics: toCsv(config.allowed_topics),
      forbidden_topics: toCsv(config.forbidden_topics),
      signature: config.signature ?? "",
      max_context_messages: config.max_context_messages,
      knowledge_base_enabled: config.knowledge_base_enabled,
      automatic_language_detection: config.automatic_language_detection,
      sensitive_categories: config.sensitive_categories ?? [],
      auto_generate_draft: config.auto_generate_draft,
      response_mode: config.response_mode,
    });
  }, [config?.id]);

  if (isLoading || !form) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  function toggleCategory(value: string) {
    setForm((prev) => prev && ({
      ...prev,
      sensitive_categories: prev.sensitive_categories.includes(value)
        ? prev.sensitive_categories.filter((c) => c !== value)
        : [...prev.sensitive_categories, value],
    }));
  }

  function persistResponseMode(mode: OmniAIAgentConfigResponse["response_mode"]) {
    updateConfig.mutate(
      { response_mode: mode },
      {
        onSuccess: () => {
          setForm((prev) => prev && { ...prev, response_mode: mode });
          toast.success(mode === "AUTO_REPLY" ? "Autorisponditore automatico attivato" : "Autorisponditore automatico disattivato: le risposte torneranno in bozza");
        },
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile aggiornare la modalità di risposta"),
      }
    );
  }

  function handleToggleAutoReply(next: boolean) {
    if (next) {
      setConfirmAutoReplyOpen(true);
    } else {
      persistResponseMode("APPROVAL_REQUIRED");
    }
  }

  function handleSave() {
    if (!form) return;
    updateConfig.mutate(
      {
        name: form.name,
        description: form.description || undefined,
        system_prompt: form.system_prompt || undefined,
        language: form.language,
        tone: form.tone,
        temperature: form.temperature,
        company_description: form.company_description || undefined,
        allowed_topics: fromCsv(form.allowed_topics),
        forbidden_topics: fromCsv(form.forbidden_topics),
        signature: form.signature || undefined,
        max_context_messages: form.max_context_messages,
        knowledge_base_enabled: form.knowledge_base_enabled,
        automatic_language_detection: form.automatic_language_detection,
        auto_generate_draft: form.auto_generate_draft,
        sensitive_categories: form.sensitive_categories,
      },
      {
        onSuccess: () => toast.success("Configurazione salvata"),
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile salvare la configurazione"),
      }
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        title="AI Agent"
        description="Configura come l'assistente AI genera le proposte di risposta."
        actions={<Button onClick={handleSave} disabled={updateConfig.isPending}><SaveIcon /> Salva</Button>}
      />

      <div
        className={cn(
          "flex items-center justify-between gap-4 rounded-lg border-2 p-4 transition-colors",
          form.response_mode === "AUTO_REPLY" ? "border-warning bg-warning/10" : "border-border bg-muted/30"
        )}
      >
        <div className="flex items-start gap-3">
          {form.response_mode === "AUTO_REPLY" ? (
            <ZapIcon className="mt-0.5 size-5 shrink-0 text-warning" />
          ) : (
            <ShieldCheckIcon className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
          )}
          <div>
            <p className="text-base font-semibold">
              Autorisponditore automatico: {form.response_mode === "AUTO_REPLY" ? "ACCESO" : "SPENTO"}
            </p>
            <p className="text-sm text-muted-foreground">
              {form.response_mode === "AUTO_REPLY"
                ? "L'AI invia le risposte da sola, senza attendere la tua approvazione."
                : "Ogni risposta dell'AI resta in bozza finché non la approvi tu, dall'Inbox."}
              {" "}Gli argomenti sensibili (sotto) richiedono comunque sempre revisione umana, in entrambi i casi.
            </p>
          </div>
        </div>
        <Switch checked={form.response_mode === "AUTO_REPLY"} onCheckedChange={handleToggleAutoReply} disabled={updateConfig.isPending} />
      </div>

      <ConfirmDialog
        open={confirmAutoReplyOpen}
        onOpenChange={setConfirmAutoReplyOpen}
        title="Accendere l'autorisponditore automatico?"
        description="Da questo momento l'AI invierà le risposte ai clienti da sola, senza che tu debba approvarle una per una. Gli argomenti sensibili (rimborso, legale, medico...) continueranno a restare in bozza per la tua revisione. Puoi spegnerlo in qualsiasi momento."
        confirmLabel="Sì, accendi"
        loading={updateConfig.isPending}
        onConfirm={() => {
          persistResponseMode("AUTO_REPLY");
          setConfirmAutoReplyOpen(false);
        }}
      />

      <div className="space-y-4 rounded-lg border p-4">
        <div className="space-y-1.5">
          <Label>Nome assistente</Label>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Descrizione dell&apos;azienda</Label>
          <Textarea value={form.company_description} onChange={(e) => setForm({ ...form, company_description: e.target.value })} rows={3} placeholder="Cosa fa la tua azienda, prodotti/servizi principali..." />
        </div>
        <div className="space-y-1.5">
          <Label>Istruzioni di sistema (system prompt)</Label>
          <Textarea
            value={form.system_prompt}
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
            rows={8}
            className="field-sizing-fixed h-56 resize-y overflow-y-auto"
            placeholder="Sei l'assistente clienti di..."
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label>Tono di voce</Label>
            <Select items={TONE_OPTIONS} value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v as string })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TONE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Lingua di risposta</Label>
            <Select items={LANGUAGE_OPTIONS} value={form.language} onValueChange={(v) => setForm({ ...form, language: v as string })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {LANGUAGE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label>Firma (opzionale)</Label>
            <Input value={form.signature} onChange={(e) => setForm({ ...form, signature: e.target.value })} placeholder="Il team di..." />
          </div>
          <div className="space-y-1.5">
            <Label>Messaggi di contesto (storico)</Label>
            <Input type="number" min={1} max={100} value={form.max_context_messages} onChange={(e) => setForm({ ...form, max_context_messages: Number(e.target.value) })} />
          </div>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Creatività (temperatura)</Label>
            <span className="text-xs text-muted-foreground">{form.temperature.toFixed(1)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1.5}
            step={0.1}
            value={form.temperature}
            onChange={(e) => setForm({ ...form, temperature: Number(e.target.value) })}
            className="w-full accent-primary"
          />
          <p className="text-xs text-muted-foreground">
            Più bassa (0-0.3) = risposte più letterali e ripetibili, utile se hai istruzioni precise nel prompt da seguire alla lettera. Più alta (0.8+) = risposte più varie e naturali, meno prevedibili.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label>Argomenti consentiti (separati da virgola)</Label>
          <Input value={form.allowed_topics} onChange={(e) => setForm({ ...form, allowed_topics: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Argomenti vietati (separati da virgola)</Label>
          <Input value={form.forbidden_topics} onChange={(e) => setForm({ ...form, forbidden_topics: e.target.value })} />
        </div>

        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">Generazione automatica della bozza AI</p>
            <p className="text-xs text-muted-foreground">
              {form.auto_generate_draft
                ? "Ogni messaggio in arrivo genera subito una proposta di risposta."
                : "Nessuna proposta automatica: nell'Inbox potrai scrivere tu o generarla con un click quando vuoi (utile per non consumare chiamate AI su conversazioni a cui rispondi sempre a mano)."}
            </p>
          </div>
          <Switch checked={form.auto_generate_draft} onCheckedChange={(v) => setForm({ ...form, auto_generate_draft: v })} />
        </div>

        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">Usa la Knowledge Base</p>
            <p className="text-xs text-muted-foreground">Cerca informazioni pertinenti tra i documenti caricati prima di rispondere.</p>
          </div>
          <Switch checked={form.knowledge_base_enabled} onCheckedChange={(v) => setForm({ ...form, knowledge_base_enabled: v })} />
        </div>
        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">Rilevamento automatico della lingua</p>
            <p className="text-xs text-muted-foreground">Rispondi sempre nella lingua usata dal cliente (ignorato se hai impostato una lingua fissa sopra).</p>
          </div>
          <Switch checked={form.automatic_language_detection} onCheckedChange={(v) => setForm({ ...form, automatic_language_detection: v })} />
        </div>

        <div className="space-y-1.5">
          <Label>Argomenti sensibili - richiedono sempre revisione umana</Label>
          <div className="flex flex-wrap gap-2">
            {SENSITIVE_CATEGORY_OPTIONS.map((opt) => {
              const active = form.sensitive_categories.includes(opt.value);
              return (
                <Badge
                  key={opt.value}
                  variant={active ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleCategory(opt.value)}
                >
                  {opt.label}
                </Badge>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}
