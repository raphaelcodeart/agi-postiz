"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRejectCampaignProposal } from "@/hooks/use-campaign-proposals";
import { ApiError } from "@/lib/api/errors";
import type { CampaignProposalResponse } from "@/types/api";

/**
 * Il motivo è obbligatorio, e non per formalità: la proposta torna modificabile
 * per il promoter, che lo legge così com'è scritto. Un rifiuto senza motivo non
 * gli dice cosa cambiare, e la cosa più probabile che succede dopo è che
 * ripresenti la stessa identica proposta.
 */
export function RejectProposalDialog({
  proposal,
  open,
  onOpenChange,
}: {
  proposal: CampaignProposalResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const reject = useRejectCampaignProposal();

  function handleSubmit() {
    reject.mutate(
      { id: proposal.id, reviewNotes: reason.trim() },
      {
        onSuccess: () => {
          toast.success("Proposta rifiutata: il promoter può correggerla e rimandarla");
          setReason("");
          onOpenChange(false);
        },
        onError: (err) =>
          toast.error(err instanceof ApiError ? err.message : "Impossibile rifiutare la proposta"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rifiuta «{proposal.title}»</DialogTitle>
          <DialogDescription>
            Spiega cosa non va: {proposal.user_name ?? "il promoter"} lo legge nel suo portale e può
            correggere la proposta e rimandarla.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label>Motivo</Label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
            maxLength={2000}
            placeholder="Es. Il video è troppo lungo per Instagram: sotto i 60 secondi andrebbe bene."
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            disabled={reject.isPending || !reason.trim()}
          >
            Rifiuta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
