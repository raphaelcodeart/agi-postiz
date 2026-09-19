"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2Icon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Cancella una proposta ancora in mano al promoter (bozza o rimandata
 * indietro). Il backend rifiuta con 409 quelle consegnate o gia' diventate
 * campagne, quindi il bottone non compare nemmeno in quei casi.
 */
export function DeleteProposalButton({ proposalId }: { proposalId: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function remove() {
    setDeleting(true);
    try {
      const response = await fetch(`/api/portal/backend/proposals/${proposalId}`, {
        method: "DELETE",
      });
      if (response.ok) {
        router.push("/portal/proposals");
        router.refresh();
        return;
      }
    } finally {
      setDeleting(false);
    }
    setConfirming(false);
  }

  if (!confirming) {
    return (
      <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
        <Trash2Icon className="size-4" />
        Elimina
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">Eliminare questa proposta?</span>
      <Button variant="outline" size="sm" onClick={() => setConfirming(false)} disabled={deleting}>
        Annulla
      </Button>
      <Button variant="destructive" size="sm" onClick={remove} disabled={deleting}>
        {deleting && <Loader2Icon className="size-4 animate-spin" />}
        Elimina
      </Button>
    </div>
  );
}
