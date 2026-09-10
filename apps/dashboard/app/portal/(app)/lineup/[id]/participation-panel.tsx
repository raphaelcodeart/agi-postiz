"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckIcon, Loader2Icon, MinusCircleIcon, UndoIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { PlatformIcon } from "@/components/shared/platform-badge";
import type { PortalLineupCampaign, PortalLineupChannel } from "@/lib/portal/server";

/**
 * Where the user actually decides.
 *
 * Two rules shape the interface:
 *
 * 1. **Leaving is one click.** Withdrawing is the action this feature exists to
 *    make possible, and burying it behind a channel selection would be the
 *    interface quietly discouraging it. Per-channel control is there for anyone
 *    who wants it, but "Non partecipo" acts on everything.
 * 2. **Nothing is irreversible while the window is open.** Both directions stay
 *    available, so a decision taken quickly is not a decision regretted - which
 *    is also what keeps the one-click withdrawal safe to offer.
 */

/**
 * FastAPI returns a plain string for our own errors and an ARRAY of objects for
 * validation failures. Rendering the array as a React child crashes the page
 * into an error boundary - see the same note in channels/connect-panel.tsx.
 */
function errorMessage(payload: unknown, fallback: string): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

type Action = "join" | "withdraw";

export function ParticipationPanel({ campaign }: { campaign: PortalLineupCampaign }) {
  const router = useRouter();
  const [pending, setPending] = useState<Action | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [showReason, setShowReason] = useState(false);

  const active = campaign.channels.filter((c) => c.participation_status === "included");
  const joinable = campaign.channels.filter(
    (c) => c.participation_status === null || c.can_rejoin
  );
  const removed = campaign.channels.filter((c) => c.participation_status === "removed");

  async function send(action: Action, channelIds: string[] | null, withReason?: string) {
    setPending(action);
    try {
      const response = await fetch(`/api/portal/backend/lineup/${campaign.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_ids: channelIds ?? [],
          reason: withReason || null,
        }),
      });
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        toast.error(errorMessage(payload, "Operazione non riuscita."));
        return;
      }

      const result = payload as { message?: string; warnings?: string[] } | null;
      toast.success(result?.message ?? "Fatto.");
      result?.warnings?.forEach((warning) => toast.warning(warning));

      setSelected([]);
      setShowReason(false);
      setReason("");
      // The page is a server component reading the backend: refreshing is what
      // makes the new state visible, rather than mirroring it in local state and
      // risking the two disagreeing.
      router.refresh();
    } catch {
      toast.error("Servizio non raggiungibile. Riprova.");
    } finally {
      setPending(null);
    }
  }

  if (!campaign.window_open) {
    return (
      <Alert>
        <AlertDescription>
          {active.length > 0
            ? "Il termine per modificare la partecipazione è scaduto: i tuoi canali sono confermati per questa campagna."
            : "Il termine per partecipare a questa campagna è scaduto."}
        </AlertDescription>
      </Alert>
    );
  }

  if (campaign.channels.length === 0) {
    return (
      <Alert>
        <AlertDescription>
          Non hai canali collegati. Collega un canale per poter partecipare alle campagne.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {active.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <p className="font-medium">Partecipi con {active.length === 1 ? "questo canale" : "questi canali"}</p>
            <p className="text-sm text-muted-foreground">
              Se non vuoi far parte di questa campagna puoi toglierti adesso. Non serve fare
              nulla per confermare.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            {active.map((channel) => (
              <ChannelRow key={channel.id} channel={channel}>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={pending !== null}
                  onClick={() => send("withdraw", [channel.id])}
                >
                  Togli
                </Button>
              </ChannelRow>
            ))}
          </div>

          {showReason ? (
            <div className="flex flex-col gap-2 rounded-lg border p-3">
              <label htmlFor="withdraw-reason" className="text-sm font-medium">
                Vuoi dirci perché? (facoltativo)
              </label>
              <Textarea
                id="withdraw-reason"
                value={reason}
                maxLength={500}
                rows={2}
                placeholder="Es. non è in linea con il mio pubblico"
                onChange={(event) => setReason(event.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="destructive"
                  disabled={pending !== null}
                  onClick={() => send("withdraw", null, reason)}
                >
                  {pending === "withdraw" ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <MinusCircleIcon className="size-4" />
                  )}
                  Conferma: non partecipo
                </Button>
                <Button variant="ghost" disabled={pending !== null} onClick={() => setShowReason(false)}>
                  Annulla
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              className="self-start border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={pending !== null}
              onClick={() => setShowReason(true)}
            >
              <MinusCircleIcon className="size-4" />
              Non partecipo a questa campagna
            </Button>
          )}
        </div>
      )}

      {joinable.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <p className="font-medium">
              {active.length > 0 ? "Aggiungi altri canali" : "Partecipa a questa campagna"}
            </p>
            <p className="text-sm text-muted-foreground">
              {active.length > 0
                ? "Seleziona i canali su cui vuoi pubblicare anche."
                : "Seleziona i canali su cui vuoi pubblicare questa campagna."}
            </p>
          </div>

          <div className="flex flex-col gap-2">
            {joinable.map((channel) => {
              const checked = selected.includes(channel.id);
              return (
                <label
                  key={channel.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(value) =>
                      setSelected((current) =>
                        value === true
                          ? [...current, channel.id]
                          : current.filter((id) => id !== channel.id)
                      )
                    }
                  />
                  <PlatformIcon platform={channel.platform} className="size-5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">
                    {channel.name}
                    {channel.username && (
                      <span className="text-muted-foreground"> · @{channel.username}</span>
                    )}
                  </span>
                  {channel.participation_status === "withdrawn" && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <UndoIcon className="size-3" />
                      avevi rinunciato
                    </span>
                  )}
                </label>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              disabled={pending !== null || selected.length === 0}
              onClick={() => send("join", selected)}
            >
              {pending === "join" ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <CheckIcon className="size-4" />
              )}
              {selected.length > 1 ? `Partecipa con ${selected.length} canali` : "Partecipa"}
            </Button>
            {joinable.length > 1 && (
              <Button
                variant="outline"
                disabled={pending !== null}
                onClick={() => send("join", joinable.map((c) => c.id))}
              >
                Partecipa con tutti
              </Button>
            )}
          </div>
        </div>
      )}

      {removed.length > 0 && (
        <Alert>
          <AlertDescription>
            {removed.length === 1
              ? `Il canale ${removed[0].name} è stato escluso da questa campagna da un amministratore.`
              : `${removed.length} dei tuoi canali sono stati esclusi da questa campagna da un amministratore.`}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function ChannelRow({
  channel,
  children,
}: {
  channel: PortalLineupChannel;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border p-3">
      <PlatformIcon platform={channel.platform} className="size-5 shrink-0" />
      <span className="min-w-0 flex-1 truncate">
        {channel.name}
        {channel.username && <span className="text-muted-foreground"> · @{channel.username}</span>}
      </span>
      {channel.joined_by_me && (
        <span className="hidden text-xs text-muted-foreground sm:inline">aggiunto da te</span>
      )}
      {children}
    </div>
  );
}
