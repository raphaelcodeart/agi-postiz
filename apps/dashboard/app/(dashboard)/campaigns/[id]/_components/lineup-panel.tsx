"use client";

import { useState } from "react";
import {
  ClockIcon,
  Loader2Icon,
  MinusCircleIcon,
  RocketIcon,
  UserPlusIcon,
  UsersIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { useCampaignLineup, useRemoveCampaignParticipant } from "@/hooks/use-campaigns";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import type { CampaignParticipant, CampaignResponse } from "@/types/api";

/**
 * Who is in an announced campaign, and what happens next.
 *
 * The panel answers the two questions an administrator has while a campaign is
 * sitting in the line-up: how many channels will actually go out, and has
 * anybody pulled out. Both are invisible from the progress card above, which is
 * built from publications - and an announced campaign has none yet.
 */

const STATUS_META: Record<
  CampaignParticipant["status"],
  { label: string; className: string }
> = {
  included: {
    label: "Partecipa",
    className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  withdrawn: {
    label: "Ritirato",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  removed: {
    label: "Escluso",
    className: "border-muted-foreground/30 bg-muted text-muted-foreground",
  },
};

export function LineupPanel({
  campaign,
  onLaunch,
  launching,
}: {
  campaign: CampaignResponse;
  onLaunch: () => void;
  launching: boolean;
}) {
  const lineupQuery = useCampaignLineup(campaign.id, campaign.participation_mode === "opt_out");
  const removeParticipant = useRemoveCampaignParticipant(campaign.id);
  const [removingId, setRemovingId] = useState<string | null>(null);

  if (campaign.participation_mode !== "opt_out") return null;

  const lineup = lineupQuery.data;

  async function handleRemove(participant: CampaignParticipant) {
    setRemovingId(participant.id);
    try {
      await removeParticipant.mutateAsync({ participantId: participant.id });
      toast.success(`${participant.channel_name} escluso dalla campagna`);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita");
    } finally {
      setRemovingId(null);
    }
  }

  const included = lineup?.participants.filter((p) => p.status === "included") ?? [];
  const gone = lineup?.participants.filter((p) => p.status !== "included") ?? [];
  const selfJoined = included.filter((p) => p.added_by === "user").length;
  const launched = campaign.status !== "announced" && campaign.status !== "draft";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <UsersIcon className="size-4" />
          Palinsesto e partecipanti
        </CardTitle>
        {lineup && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="outline" className={STATUS_META.included.className}>
              {lineup.included_count} partecipano
            </Badge>
            {lineup.withdrawn_count > 0 && (
              <Badge variant="outline" className={STATUS_META.withdrawn.className}>
                {lineup.withdrawn_count} ritirati
              </Badge>
            )}
            {lineup.removed_count > 0 && (
              <Badge variant="outline" className={STATUS_META.removed.className}>
                {lineup.removed_count} esclusi
              </Badge>
            )}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {lineupQuery.isLoading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Caricamento partecipanti...
          </p>
        )}

        {lineup && !launched && (
          <Alert>
            <ClockIcon className="size-4" />
            <AlertDescription>
              {lineup.opt_out_deadline_at ? (
                <>
                  {lineup.window_open ? "I destinatari possono ritirarsi fino al " : "Termine scaduto il "}
                  <strong>{formatDateTime(lineup.opt_out_deadline_at)}</strong>.{" "}
                  {lineup.auto_launch_at_deadline
                    ? "Alla scadenza la campagna parte automaticamente."
                    : "Alla scadenza la campagna resta ferma: avviala tu."}
                </>
              ) : (
                <>
                  Nessun termine impostato: i destinatari possono ritirarsi fino al lancio.
                  Nessun post è ancora stato inviato.
                </>
              )}
            </AlertDescription>
          </Alert>
        )}

        {selfJoined > 0 && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <UserPlusIcon className="size-4" />
            {selfJoined === 1
              ? "1 canale si è aggiunto autonomamente dal portale."
              : `${selfJoined} canali si sono aggiunti autonomamente dal portale.`}
          </p>
        )}

        {lineup && lineup.participants.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nessun partecipante. Rimetti la campagna in palinsesto per ricalcolare i destinatari.
          </p>
        )}

        {included.length > 0 && (
          <ParticipantTable
            participants={included}
            removable={!launched}
            removingId={removingId}
            onRemove={handleRemove}
          />
        )}

        {gone.length > 0 && (
          <details className="rounded-lg border">
            <summary className="cursor-pointer px-4 py-2 text-sm font-medium">
              Non partecipano ({gone.length})
            </summary>
            <div className="border-t">
              <ParticipantTable participants={gone} removable={false} removingId={null} onRemove={handleRemove} />
            </div>
          </details>
        )}

        {!launched && lineup && lineup.included_count > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-t pt-4">
            <Button disabled={launching} onClick={onLaunch}>
              {launching ? <Loader2Icon className="size-4 animate-spin" /> : <RocketIcon className="size-4" />}
              Lancia ora ({lineup.included_count} canali)
            </Button>
            <p className="text-xs text-muted-foreground">
              Il lancio invia i post al provider: da quel momento i destinatari non possono più
              ritirarsi.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ParticipantTable({
  participants,
  removable,
  removingId,
  onRemove,
}: {
  participants: CampaignParticipant[];
  removable: boolean;
  removingId: string | null;
  onRemove: (participant: CampaignParticipant) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[38rem] border-collapse text-sm">
        <tbody>
          {participants.map((participant) => (
            <tr key={participant.id} className="border-b last:border-b-0">
              <td className="py-2 pr-3 pl-4">
                <div className="flex items-center gap-2">
                  <PlatformIcon platform={participant.platform} className="size-4 shrink-0" />
                  <span className="truncate">{participant.channel_name}</span>
                </div>
              </td>
              <td className="px-3 py-2 text-muted-foreground">{participant.user_name}</td>
              <td className="px-3 py-2">
                <Badge variant="outline" className={STATUS_META[participant.status].className}>
                  {STATUS_META[participant.status].label}
                </Badge>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {participant.added_by === "user" && participant.status === "included" && "aggiunto da sé"}
                {participant.status !== "included" && participant.decided_reason}
                {participant.status !== "included" &&
                  !participant.decided_reason &&
                  participant.decided_at &&
                  formatDateTime(participant.decided_at)}
              </td>
              <td className="py-2 pr-4 pl-3 text-right">
                {removable && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={removingId !== null}
                    onClick={() => onRemove(participant)}
                  >
                    {removingId === participant.id ? (
                      <Loader2Icon className="size-4 animate-spin" />
                    ) : (
                      <MinusCircleIcon className="size-4" />
                    )}
                    Escludi
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
