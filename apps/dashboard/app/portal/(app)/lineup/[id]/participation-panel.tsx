"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  BanIcon,
  CalendarClockIcon,
  CheckIcon,
  CircleCheckBigIcon,
  Loader2Icon,
  PlusIcon,
  ShieldAlertIcon,
  UndoIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { PlatformIcon, platformLabel } from "@/components/shared/platform-badge";
import type { PortalLineupCampaign, PortalLineupChannel } from "@/lib/portal/server";

/**
 * Where the user actually decides.
 *
 * Three rules shape the interface:
 *
 * 1. **Nothing has to be confirmed.** Taking part is the default; the only
 *    action is leaving. The panel says so in words, because a screen full of
 *    buttons otherwise reads as "you must do something" and the commonest
 *    outcome - do nothing, stay in - would look like an unfinished task.
 * 2. **Leaving is never a guess.** The button names the consequence ("Non
 *    pubblicare qui") rather than the mechanism ("Togli"), and the destructive
 *    styling is reserved for it, so nothing else on the page competes with it.
 * 3. **Nothing is irreversible while the window is open.** Both directions stay
 *    available, which is what makes a one-click withdrawal safe to offer.
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

/** Avatar with the platform mark tucked into its corner - reads at a glance. */
function ChannelAvatar({ channel }: { channel: PortalLineupChannel }) {
  return (
    <span className="relative shrink-0">
      <Avatar className="size-11">
        <AvatarImage src={channel.avatar_url ?? undefined} alt="" />
        <AvatarFallback className="text-xs font-medium">
          {channel.name.slice(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>
      <PlatformIcon
        platform={channel.platform}
        className="absolute -right-1 -bottom-1 size-5 ring-2 ring-card"
      />
    </span>
  );
}

function ChannelIdentity({ channel }: { channel: PortalLineupChannel }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate font-medium">{channel.name}</span>
      <span className="block truncate text-sm text-muted-foreground">
        {channel.username ? `@${channel.username}` : platformLabel(channel.platform)}
      </span>
    </span>
  );
}

export function ParticipationPanel({ campaign }: { campaign: PortalLineupCampaign }) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState<"all" | string | null>(null);

  const active = campaign.channels.filter((c) => c.participation_status === "included");
  const joinable = campaign.channels.filter(
    (c) => c.participation_status === null || c.can_rejoin
  );
  const removed = campaign.channels.filter((c) => c.participation_status === "removed");

  async function send(action: Action, channelIds: string[] | null, key: string, withReason?: string) {
    setPending(key);
    try {
      const response = await fetch(`/api/portal/backend/lineup/${campaign.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_ids: channelIds ?? [], reason: withReason || null }),
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
      setConfirming(null);
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
        <CalendarClockIcon className="size-4" />
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

  const busy = pending !== null;

  return (
    <div className="flex flex-col gap-6">
      {active.length > 0 && (
        <section className="flex flex-col gap-4">
          {/* States the default out loud: taking part requires no action. Without
              this the panel reads as a form waiting to be filled in. */}
          <div className="flex gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
            <CircleCheckBigIcon className="mt-0.5 size-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <div className="min-w-0 space-y-1">
              <p className="font-medium text-emerald-900 dark:text-emerald-200">
                {active.length === 1
                  ? "Partecipi a questa campagna"
                  : `Partecipi con ${active.length} canali`}
              </p>
              <p className="text-sm text-emerald-800/80 dark:text-emerald-300/80">
                Non devi confermare nulla: il post uscirà automaticamente. Se preferisci non
                farne parte, puoi togliere i tuoi canali finché il termine è aperto.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            {active.map((channel) => {
              const isConfirming = confirming === channel.id;
              return (
                <div
                  key={channel.id}
                  className={
                    "rounded-xl border transition-colors " +
                    (isConfirming ? "border-destructive/40 bg-destructive/5" : "bg-card")
                  }
                >
                  <div className="flex flex-wrap items-center gap-3 p-3">
                    <ChannelAvatar channel={channel} />
                    <ChannelIdentity channel={channel} />

                    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                      <CheckIcon className="size-3.5" />
                      Confermato
                    </span>

                    {/* Only offered per channel when there is a choice to make.
                        With a single channel it is the same decision as the one
                        below, and two buttons doing one thing is a hesitation. */}
                    {active.length > 1 && !isConfirming && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        className="border-destructive/30 text-destructive hover:border-destructive/50 hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => setConfirming(channel.id)}
                      >
                        <BanIcon className="size-4" />
                        Non pubblicare qui
                      </Button>
                    )}
                  </div>

                  {isConfirming && (
                    <div className="flex flex-wrap items-center gap-2 border-t border-destructive/20 px-3 py-3">
                      <p className="mr-auto text-sm">
                        Togliere <span className="font-medium">{channel.name}</span> da questa
                        campagna?
                      </p>
                      <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirming(null)}>
                        Annulla
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={busy}
                        onClick={() => send("withdraw", [channel.id], channel.id)}
                      >
                        {pending === channel.id ? (
                          <Loader2Icon className="size-4 animate-spin" />
                        ) : (
                          <BanIcon className="size-4" />
                        )}
                        Sì, togli questo canale
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {confirming === "all" ? (
            <div className="flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
              <div className="flex gap-3">
                <ShieldAlertIcon className="mt-0.5 size-5 shrink-0 text-destructive" />
                <div className="space-y-1">
                  <p className="font-medium">
                    {active.length === 1
                      ? "Confermi di non voler partecipare?"
                      : `Confermi di togliere tutti e ${active.length} i tuoi canali?`}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    La campagna non uscirà sui tuoi canali. Puoi rientrare finché il termine
                    è aperto.
                  </p>
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="withdraw-reason" className="text-sm font-medium">
                  Vuoi dirci perché?{" "}
                  <span className="font-normal text-muted-foreground">(facoltativo)</span>
                </label>
                <Textarea
                  id="withdraw-reason"
                  value={reason}
                  maxLength={500}
                  rows={2}
                  placeholder="Es. non è in linea con il mio pubblico"
                  onChange={(event) => setReason(event.target.value)}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="destructive"
                  disabled={busy}
                  onClick={() => send("withdraw", null, "all", reason)}
                >
                  {pending === "all" ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <BanIcon className="size-4" />
                  )}
                  Sì, non partecipo
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => setConfirming(null)}>
                  Annulla, resto nella campagna
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              // h-auto + whitespace-normal override the variant's fixed height and
              // its base `whitespace-nowrap`: without both, a two-line label runs
              // off the side of the button on a phone, which is where most
              // promoters read this.
              className="h-auto w-full justify-start gap-3 border-destructive/30 px-4 py-3 text-left whitespace-normal hover:border-destructive/50 hover:bg-destructive/5"
              disabled={busy}
              onClick={() => setConfirming("all")}
            >
              <BanIcon className="size-5 shrink-0 text-destructive" />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="font-medium text-destructive">
                  Non voglio partecipare a questa campagna
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {active.length === 1
                    ? "Il post non uscirà sul tuo canale"
                    : "Il post non uscirà su nessuno dei tuoi canali"}
                </span>
              </span>
            </Button>
          )}
        </section>
      )}

      {joinable.length > 0 && (
        <section className="flex flex-col gap-3">
          {active.length > 0 && <div className="border-t" />}

          <div className="space-y-1">
            <p className="font-medium">
              {active.length > 0 ? "Aggiungi altri canali" : "Vuoi partecipare?"}
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
                  className={
                    "flex cursor-pointer flex-wrap items-center gap-3 rounded-xl border p-3 transition-colors " +
                    (checked ? "border-primary/50 bg-primary/5" : "hover:bg-muted/40")
                  }
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
                  <ChannelAvatar channel={channel} />
                  <ChannelIdentity channel={channel} />
                  {channel.participation_status === "withdrawn" && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                      <UndoIcon className="size-3.5" />
                      avevi rinunciato
                    </span>
                  )}
                </label>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || selected.length === 0} onClick={() => send("join", selected, "join")}>
              {pending === "join" ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <PlusIcon className="size-4" />
              )}
              {selected.length > 1
                ? `Partecipa con ${selected.length} canali`
                : "Partecipa a questa campagna"}
            </Button>
            {joinable.length > 1 && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => send("join", joinable.map((c) => c.id), "join")}
              >
                Partecipa con tutti
              </Button>
            )}
          </div>
        </section>
      )}

      {removed.length > 0 && (
        <Alert>
          <ShieldAlertIcon className="size-4" />
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
