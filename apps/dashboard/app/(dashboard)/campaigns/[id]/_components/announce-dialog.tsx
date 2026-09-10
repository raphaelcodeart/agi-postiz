"use client";

import { useState } from "react";
import { CalendarClockIcon, Loader2Icon, MegaphoneIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAnnounceCampaign } from "@/hooks/use-campaigns";
import { ApiError } from "@/lib/api/errors";
import type { CampaignResponse } from "@/types/api";

/**
 * Puts an existing campaign into the line-up.
 *
 * Until this existed, announcing could only happen inside the creation wizard,
 * at the one moment the administrator had to remember to pick it. Anything else
 * - a campaign saved as a draft to finish later, a duplicate of an old one, an
 * announce that failed on a bad targeting selection - left a campaign that could
 * never be announced at all, only recreated from scratch. Since a failed
 * announce leaves exactly that (a draft), the gap was also what made the failure
 * unrecoverable rather than merely annoying.
 */
export function AnnounceDialog({
  campaign,
  open,
  onOpenChange,
}: {
  campaign: CampaignResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const announce = useAnnounceCampaign();
  const [deadline, setDeadline] = useState("");
  const [autoLaunch, setAutoLaunch] = useState(false);

  // The deadline must precede the publishing date, or the window closes after
  // the posts have already gone out. Mirrors the backend's own check.
  const scheduledAt = campaign.scheduled_at ? new Date(campaign.scheduled_at) : null;
  const deadlineDate = deadline ? new Date(deadline) : null;
  const deadlineTooLate = Boolean(scheduledAt && deadlineDate && deadlineDate >= scheduledAt);
  const autoLaunchNeedsDeadline = autoLaunch && !deadline;

  function submit() {
    announce.mutate(
      {
        campaignId: campaign.id,
        payload: {
          // The targeting selection made at creation, re-used as-is: announcing
          // is not the moment to change who the campaign is for.
          targeting_params: (campaign.metadata_json ?? {}) as Record<string, unknown>,
          opt_out_deadline_at: deadline ? new Date(deadline).toISOString() : null,
          auto_launch_at_deadline: autoLaunch,
        },
      },
      {
        onSuccess: (lineup) => {
          toast.success(
            `Campagna in palinsesto: ${lineup.included_count} canali coinvolti. Nessun post è stato inviato.`
          );
          onOpenChange(false);
        },
        onError: (error) =>
          toast.error(
            error instanceof ApiError ? error.detail : "Impossibile mettere la campagna in palinsesto"
          ),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MegaphoneIcon className="size-4" />
            Metti in palinsesto
          </DialogTitle>
          <DialogDescription>
            I destinatari vedranno la campagna nel loro portale e potranno togliersi. Nessun
            post viene inviato finché non la lanci.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="announce-deadline" className="flex items-center gap-2">
              <CalendarClockIcon className="size-4" />
              Termine per ritirarsi
            </Label>
            <Input
              id="announce-deadline"
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Lascia vuoto per tenere aperto fino al lancio.
            </p>
          </div>

          <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
            <div className="space-y-0.5">
              <Label>Avvia automaticamente alla scadenza</Label>
              <p className="text-xs text-muted-foreground">
                {autoLaunch
                  ? "Allo scadere del termine la campagna parte da sola con i canali rimasti."
                  : "La campagna resta ferma alla scadenza: la lanci tu."}
              </p>
            </div>
            <Switch checked={autoLaunch} onCheckedChange={setAutoLaunch} />
          </div>

          {autoLaunchNeedsDeadline && (
            <Alert variant="destructive">
              <AlertDescription>
                Per avviare la campagna automaticamente serve un termine: senza scadenza non
                c&apos;è un momento in cui partire.
              </AlertDescription>
            </Alert>
          )}

          {deadlineTooLate && (
            <Alert variant="destructive">
              <AlertDescription>
                Il termine deve precedere la data di pubblicazione della campagna.
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button
            disabled={announce.isPending || autoLaunchNeedsDeadline || deadlineTooLate}
            onClick={submit}
          >
            {announce.isPending && <Loader2Icon className="size-4 animate-spin" />}
            Metti in palinsesto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
