import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Tone = "success" | "warning" | "destructive" | "info" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  success: "border-transparent bg-success/15 text-success dark:bg-success/20",
  warning: "border-transparent bg-warning/15 text-warning-foreground dark:bg-warning/25 dark:text-warning",
  destructive: "border-transparent bg-destructive/10 text-destructive",
  info: "border-transparent bg-primary/10 text-primary",
  neutral: "border-transparent bg-muted text-muted-foreground",
};

const STATUS_TONE: Record<string, Tone> = {
  // Users
  active: "success",
  inactive: "neutral",
  suspended: "destructive",
  // Buffer connections
  connected: "success",
  pending: "warning",
  expired: "warning",
  revoked: "destructive",
  error: "destructive",
  disconnected: "neutral",
  // Channels / publication mode
  automatic: "success",
  notification: "info",
  approval: "warning",
  disabled: "neutral",
  // Media
  uploaded: "info",
  inspecting: "info",
  processing: "info",
  ready: "success",
  failed: "destructive",
  valid: "success",
  warning: "warning",
  invalid: "destructive",
  // Campaigns
  draft: "neutral",
  preparing: "info",
  queued: "info",
  running: "info",
  paused: "warning",
  partially_completed: "warning",
  completed: "success",
  cancelled: "neutral",
  // Publications
  submitted: "info",
  scheduled: "info",
  published: "success",
  retry_wait: "warning",
  skipped: "neutral",
  unknown: "neutral",
  // Blog Writer AI (ready/failed/draft/published reuse the tones defined above)
  untested: "neutral",
  generating: "info",
  publishing: "info",
  partially_published: "warning",
  archived: "neutral",
  retrying: "warning",
  removed: "neutral",
  updated: "success",
  // Omnichannel Responder conversations
  new: "info",
  ai_processing: "info",
  waiting_approval: "warning",
  waiting_customer: "info",
  resolved: "success",
  spam: "destructive",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Attivo",
  inactive: "Inattivo",
  suspended: "Sospeso",
  connected: "Connesso",
  pending: "In attesa",
  expired: "Scaduto",
  revoked: "Revocato",
  error: "Errore",
  disconnected: "Disconnesso",
  automatic: "Automatico",
  notification: "Notifica",
  approval: "Approvazione",
  disabled: "Disabilitato",
  uploaded: "Caricato",
  inspecting: "Analisi",
  processing: "Elaborazione",
  ready: "Pronto",
  failed: "Fallito",
  valid: "Valido",
  warning: "Attenzione",
  invalid: "Non valido",
  draft: "Bozza",
  preparing: "Preparazione",
  queued: "In coda",
  running: "In corso",
  paused: "In pausa",
  partially_completed: "Parziale",
  completed: "Completata",
  cancelled: "Annullata",
  submitted: "Inviato",
  scheduled: "Programmato",
  published: "Pubblicato",
  retry_wait: "Attesa retry",
  skipped: "Saltato",
  unknown: "Sconosciuto",
  // Blog Writer AI
  untested: "Non testata",
  generating: "Generazione...",
  publishing: "Pubblicazione...",
  partially_published: "Parziale",
  archived: "Archiviato",
  retrying: "Nuovo tentativo",
  removed: "Rimosso",
  updated: "Aggiornato",
  // Omnichannel Responder conversations
  new: "Nuova",
  ai_processing: "AI in elaborazione",
  waiting_approval: "Da approvare",
  waiting_customer: "Attesa cliente",
  resolved: "Risolta",
  spam: "Spam",
};

const LIVE_STATUSES = new Set([
  "processing",
  "running",
  "queued",
  "preparing",
  "retry_wait",
  "inspecting",
  "generating",
  "publishing",
  "retrying",
  "ai_processing",
]);

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const tone = STATUS_TONE[status] ?? "neutral";
  const label = STATUS_LABELS[status] ?? status;
  const isLive = LIVE_STATUSES.has(status);

  return (
    <Badge variant="outline" className={cn("gap-1.5", TONE_CLASSES[tone], className)}>
      {isLive && <span className="status-dot-live size-1.5 shrink-0 rounded-full bg-current" />}
      {label}
    </Badge>
  );
}
