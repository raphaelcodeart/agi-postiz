"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  InboxIcon,
  LogOutIcon,
  MessageCircleIcon,
  PlayIcon,
  PlusIcon,
  QrCodeIcon,
  RefreshCwIcon,
  ServerIcon,
  SmartphoneIcon,
  Trash2Icon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  useCreateMyAgiSession,
  useDeleteMyAgiSession,
  useLogoutMyAgiSession,
  useMyAgiGatewayStatus,
  useMyAgiQr,
  useMyAgiSessions,
  useRestartMyAgiSession,
  useStartMyAgiSession,
} from "@/hooks/use-myagi";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { MyAgiSessionResponse } from "@/types/api";

const SESSION_LABEL: Record<string, { label: string; tone: string }> = {
  WORKING: { label: "Collegato", tone: "bg-success/15 text-success" },
  SCAN_QR_CODE: { label: "In attesa del QR", tone: "bg-warning/15 text-warning" },
  STARTING: { label: "Avvio…", tone: "bg-muted text-muted-foreground" },
  PASSKEY_REQUIRED: { label: "Richiede passkey", tone: "bg-warning/15 text-warning" },
  STOPPED: { label: "Fermo", tone: "bg-muted text-muted-foreground" },
  FAILED: { label: "Errore", tone: "bg-destructive/15 text-destructive" },
  MISSING: { label: "Mai avviato", tone: "bg-muted text-muted-foreground" },
  UNAVAILABLE: { label: "Gateway non disponibile", tone: "bg-destructive/15 text-destructive" },
};

function errorMessage(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

/**
 * myAGI: i numeri WhatsApp collegati al nostro gateway (WAHA in
 * docker-compose). Fa il lavoro della console Maytapi: creare un numero,
 * mostrare il QR, dire se il telefono e' collegato, scollegarlo. Il numero
 * e' gia' un canale dell'Omnichannel Responder: i messaggi arrivano
 * nell'Inbox come da ogni altro canale.
 */
export default function MyAgiPage() {
  const { data: gateway, isLoading: gatewayLoading } = useMyAgiGatewayStatus();
  const [qrAccountId, setQrAccountId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<MyAgiSessionResponse | null>(null);

  const { data: sessions, isLoading } = useMyAgiSessions(qrAccountId !== null);
  const startSession = useStartMyAgiSession();
  const restartSession = useRestartMyAgiSession();
  const logoutSession = useLogoutMyAgiSession();
  const deleteSession = useDeleteMyAgiSession();

  const gatewayOk = !!gateway?.configured && !!gateway?.reachable;

  return (
    <div className="space-y-6">
      <PageHeader
        title="myAGI"
        description="I numeri WhatsApp collegati al gateway di questa installazione. Ogni numero è un canale dell'Omnichannel Responder."
        actions={
          <Button onClick={() => setCreateOpen(true)} disabled={!gatewayOk}>
            <PlusIcon /> Nuovo numero
          </Button>
        }
      />

      {/* Stato del gateway: senza, niente funziona e va detto per primo. */}
      <div className={cn("flex items-start gap-3 rounded-lg border p-4", gatewayOk ? "border-border bg-muted/30" : "border-destructive/40 bg-destructive/5")}>
        <ServerIcon className={cn("mt-0.5 size-5 shrink-0", gatewayOk ? "text-muted-foreground" : "text-destructive")} />
        <div className="text-sm">
          {gatewayLoading ? (
            <Skeleton className="h-4 w-48" />
          ) : gatewayOk ? (
            <>
              <p className="font-medium">Gateway attivo</p>
              <p className="text-muted-foreground">
                WAHA {gateway?.version} · motore {gateway?.engine}. Il client WhatsApp gira su questo server, non da un fornitore esterno:
                stesso meccanismo di Maytapi (numero normale collegato come dispositivo), nessun canone.
              </p>
            </>
          ) : (
            <>
              <p className="font-medium text-destructive">{gateway?.configured ? "Gateway non raggiungibile" : "Gateway non configurato"}</p>
              <p className="text-muted-foreground">
                {gateway?.detail ?? "Imposta MYAGI_WA_URL e MYAGI_WA_API_KEY e avvia il servizio myagi_wa (docs/OMNICHANNEL_RESPONDER.md)."}
              </p>
            </>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : !sessions || sessions.length === 0 ? (
        <EmptyState
          icon={SmartphoneIcon}
          title="Nessun numero collegato"
          description="Crea un numero, premi Avvia e scansiona il QR da WhatsApp → Dispositivi collegati. Da quel momento i messaggi arrivano nell'Inbox."
          action={
            <Button onClick={() => setCreateOpen(true)} disabled={!gatewayOk}>
              <PlusIcon /> Nuovo numero
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3">
          {sessions.map((session) => {
            const meta = SESSION_LABEL[session.session_status] ?? { label: session.session_status, tone: "bg-muted text-muted-foreground" };
            const canShowQr = session.session_status === "SCAN_QR_CODE";
            const needsStart = ["MISSING", "STOPPED", "FAILED"].includes(session.session_status);
            return (
              <div key={session.channel_account_id} className="flex flex-wrap items-center gap-4 rounded-lg border p-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-lime-500/15 text-lime-700 dark:text-lime-400">
                  <MessageCircleIcon className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">{session.name}</p>
                    <Badge className={cn("border-transparent", meta.tone)}>{meta.label}</Badge>
                    {session.account_status === "disabled" && <Badge variant="outline">Ricezione sospesa</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {session.phone_number ? (
                      <>
                        +{session.phone_number}
                        {session.push_name ? ` · ${session.push_name}` : ""}
                      </>
                    ) : (
                      "Nessun telefono collegato"
                    )}
                    {" · "}
                    {session.conversation_count} conversazioni
                  </p>
                  {session.detail && <p className="mt-1 text-xs text-muted-foreground">{session.detail}</p>}
                </div>
                <div className="flex flex-wrap gap-1">
                  {/* Porta all'Inbox gia' filtrata su questo numero (vedi
                      omnichannel-responder/page.tsx, parametro ?account=). */}
                  <Button size="sm" variant="outline" asChild>
                    <Link href={`/omnichannel-responder?account=${session.channel_account_id}`} title="Apri l'Inbox con le sole conversazioni di questo numero">
                      <InboxIcon /> Inbox
                      {session.conversation_count > 0 && (
                        <span className="rounded-full bg-muted px-1.5 text-[0.65rem] tabular-nums text-muted-foreground">{session.conversation_count}</span>
                      )}
                    </Link>
                  </Button>
                  {canShowQr && (
                    <Button size="sm" onClick={() => setQrAccountId(session.channel_account_id)}>
                      <QrCodeIcon /> Mostra QR
                    </Button>
                  )}
                  {needsStart && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={startSession.isPending || !gatewayOk}
                      onClick={() =>
                        startSession.mutate(session.channel_account_id, {
                          onSuccess: (updated) => {
                            if (updated.session_status === "SCAN_QR_CODE") setQrAccountId(updated.channel_account_id);
                          },
                          onError: (err) => toast.error(errorMessage(err, "Impossibile avviare la sessione")),
                        })
                      }
                    >
                      <PlayIcon /> Avvia
                    </Button>
                  )}
                  {!needsStart && session.session_status !== "UNAVAILABLE" && (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      title="Riavvia la sessione"
                      disabled={restartSession.isPending}
                      onClick={() =>
                        restartSession.mutate(session.channel_account_id, {
                          onSuccess: () => toast.success("Sessione riavviata"),
                          onError: (err) => toast.error(errorMessage(err, "Impossibile riavviare")),
                        })
                      }
                    >
                      <RefreshCwIcon />
                    </Button>
                  )}
                  {session.session_status === "WORKING" && (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      title="Scollega il telefono (servirà un nuovo QR)"
                      disabled={logoutSession.isPending}
                      onClick={() =>
                        logoutSession.mutate(session.channel_account_id, {
                          onSuccess: () => toast.success("Telefono scollegato"),
                          onError: (err) => toast.error(errorMessage(err, "Impossibile scollegare")),
                        })
                      }
                    >
                      <LogOutIcon />
                    </Button>
                  )}
                  <Button size="icon-sm" variant="ghost" className="text-destructive hover:text-destructive" title="Elimina il numero" onClick={() => setDeleteTarget(session)}>
                    <Trash2Icon />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        I numeri compaiono anche in{" "}
        <Link href="/omnichannel-responder/channels" className="underline">Omnichannel → Canali</Link> come tipo &quot;WhatsApp (myAGI)&quot;, dove si può sospendere la ricezione.
        Il telefono deve restare acceso e connesso a internet almeno ogni due settimane, come per WhatsApp Web. Il numero usato da un client non ufficiale può essere limitato da WhatsApp: usa un numero dedicato, non quello del titolare.
      </p>

      <CreateNumberDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={(created) => { if (created.session_status === "SCAN_QR_CODE") setQrAccountId(created.channel_account_id); }} />
      <QrDialog accountId={qrAccountId} session={sessions?.find((s) => s.channel_account_id === qrAccountId) ?? null} onClose={() => setQrAccountId(null)} />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Eliminare "${deleteTarget?.name}"?`}
        description="Il numero viene scollegato dal gateway e il canale eliminato con tutte le sue conversazioni, messaggi e bozze. Per cambiare solo telefono usa invece Scollega."
        confirmLabel="Elimina"
        destructive
        loading={deleteSession.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteSession.mutate(deleteTarget.channel_account_id, {
            onSuccess: () => {
              toast.success("Numero eliminato");
              setDeleteTarget(null);
            },
            onError: (err) => toast.error(errorMessage(err, "Impossibile eliminare il numero")),
          });
        }}
      />
    </div>
  );
}

function CreateNumberDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (session: MyAgiSessionResponse) => void }) {
  const [name, setName] = useState("");
  const createSession = useCreateMyAgiSession();

  function submit() {
    if (!name.trim()) {
      toast.error("Dai un nome al numero (es. Assistenza clienti)");
      return;
    }
    createSession.mutate(name.trim(), {
      onSuccess: (created) => {
        toast.success("Numero creato: scansiona il QR per collegare il telefono");
        setName("");
        onOpenChange(false);
        onCreated(created);
      },
      onError: (err) => toast.error(errorMessage(err, "Impossibile creare il numero")),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuovo numero WhatsApp</DialogTitle>
          <DialogDescription>
            Viene creato un canale &quot;WhatsApp (myAGI)&quot; nell&apos;Omnichannel e avviata una sessione sul gateway. Subito dopo compare il QR da scansionare.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label>Nome</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Es. Assistenza clienti" autoFocus />
          <p className="text-xs text-muted-foreground">È il nome che vedrai nell&apos;Inbox accanto a ogni conversazione di questo numero.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button onClick={submit} disabled={createSession.isPending}>Crea e mostra QR</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function QrDialog({ accountId, session, onClose }: { accountId: string | null; session: MyAgiSessionResponse | null; onClose: () => void }) {
  const open = accountId !== null;
  const waiting = session?.session_status === "SCAN_QR_CODE";
  const { data: qr, isLoading, error } = useMyAgiQr(accountId, open && (waiting || !session));
  const connected = session?.session_status === "WORKING";

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{connected ? "Telefono collegato" : "Collega il telefono"}</DialogTitle>
          <DialogDescription>
            {connected
              ? `${session?.name} è collegato${session?.phone_number ? ` al numero +${session.phone_number}` : ""}. Puoi chiudere questa finestra.`
              : "Su WhatsApp: Impostazioni → Dispositivi collegati → Collega un dispositivo, poi inquadra il codice. Si rinnova da solo ogni pochi secondi."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-72 items-center justify-center rounded-lg border bg-white p-4">
          {connected ? (
            <div className="text-center text-sm text-muted-foreground">
              <MessageCircleIcon className="mx-auto mb-2 size-10 text-success" />
              Collegato. I messaggi arrivano nell&apos;Inbox.
            </div>
          ) : qr?.data ? (
            // Base64 dal gateway, non un URL: nessun'immagine passa da fuori.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`data:${qr.mimetype ?? "image/png"};base64,${qr.data}`} alt="QR code WhatsApp" className="size-64" />
          ) : isLoading ? (
            <Skeleton className="size-64" />
          ) : error ? (
            <p className="text-sm text-destructive">{errorMessage(error, "Impossibile leggere il QR dal gateway")}</p>
          ) : (
            <p className="max-w-xs text-center text-sm text-muted-foreground">
              {session?.session_status === "STARTING" ? "La sessione sta partendo, il QR arriva tra qualche secondo…" : session?.detail ?? "Nessun QR disponibile in questo stato: prova Avvia o Riavvia."}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Chiudi</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
