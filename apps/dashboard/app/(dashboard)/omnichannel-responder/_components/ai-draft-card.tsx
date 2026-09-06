"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { SparklesIcon, CheckIcon, RefreshCwIcon, XIcon, CopyIcon, ShieldAlertIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { useApproveDraft, useEditDraft, useRegenerateDraft, useRejectDraft } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniAIDraftResponse } from "@/types/api";

const SENSITIVE_LABELS: Record<string, string> = {
  refund: "Rimborso",
  legal: "Questione legale",
  medical: "Argomento medico",
  complaint: "Reclamo",
  pricing_exception: "Eccezione di prezzo",
  discount: "Sconto",
  contract: "Contratto",
  payment_problem: "Problema di pagamento",
};

export function AIDraftCard({ conversationId, draft }: { conversationId: string; draft: OmniAIDraftResponse }) {
  const [text, setText] = useState(draft.edited_text ?? draft.original_ai_text ?? "");
  const editDraft = useEditDraft(conversationId);
  const approveDraft = useApproveDraft(conversationId);
  const regenerateDraft = useRegenerateDraft(conversationId);
  const rejectDraft = useRejectDraft(conversationId);

  useEffect(() => {
    setText(draft.edited_text ?? draft.original_ai_text ?? "");
  }, [draft.id, draft.edited_text, draft.original_ai_text]);

  const isBusy = approveDraft.isPending || regenerateDraft.isPending || rejectDraft.isPending || editDraft.isPending;
  const isGenerating = draft.status === "GENERATING";
  const isFailed = draft.status === "FAILED";
  const isTerminal = ["SENT", "REJECTED"].includes(draft.status);
  const isDirty = text !== (draft.edited_text ?? draft.original_ai_text ?? "");

  function handleApprove() {
    const run = async () => {
      if (isDirty) {
        await editDraft.mutateAsync({ draftId: draft.id, editedText: text });
      }
      await approveDraft.mutateAsync(draft.id);
    };
    run()
      .then(() => toast.success("Risposta approvata e inviata"))
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Impossibile inviare la risposta"));
  }

  function handleRegenerate() {
    regenerateDraft.mutate(draft.id, {
      onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile rigenerare la bozza"),
    });
  }

  function handleReject() {
    rejectDraft.mutate(draft.id, {
      onError: (err) => toast.error(err instanceof ApiError ? err.message : "Impossibile scartare la bozza"),
    });
  }

  function handleCopy() {
    navigator.clipboard.writeText(text);
    toast.success("Testo copiato");
  }

  if (isTerminal) return null;

  return (
    <Card className="border-primary/30 bg-primary/[0.03]">
      <CardHeader className="flex-row items-center gap-2 space-y-0 py-3">
        <SparklesIcon className="size-4 text-primary" />
        <span className="text-sm font-semibold">
          {isGenerating ? "L'AI sta generando una risposta..." : "Proposta di risposta AI"}
        </span>
      </CardHeader>

      {draft.sensitive_category && (
        <div className="mx-(--card-spacing) mb-2 flex items-center gap-2 rounded-md bg-warning/15 px-3 py-2 text-xs text-warning-foreground dark:text-warning">
          <ShieldAlertIcon className="size-3.5 shrink-0" />
          Argomento sensibile rilevato ({SENSITIVE_LABELS[draft.sensitive_category] ?? draft.sensitive_category}): revisiona con attenzione prima di inviare.
        </div>
      )}
      {isFailed && (
        <div className="mx-(--card-spacing) mb-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          Generazione fallita: {draft.failure_reason || "errore sconosciuto"}
        </div>
      )}

      <CardContent>
        {isGenerating ? (
          <div className="h-20 animate-pulse rounded-md bg-muted" />
        ) : !isFailed ? (
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} disabled={isBusy} />
        ) : null}
      </CardContent>

      {!isGenerating && (
        <CardFooter className="flex flex-wrap gap-2">
          {!isFailed && (
            <>
              <Button size="sm" onClick={handleApprove} disabled={isBusy || !text.trim()}>
                <CheckIcon /> Approva e invia
              </Button>
              <Button size="sm" variant="outline" onClick={handleCopy} disabled={isBusy}>
                <CopyIcon /> Copia
              </Button>
            </>
          )}
          <Button size="sm" variant="outline" onClick={handleRegenerate} disabled={isBusy}>
            <RefreshCwIcon className={regenerateDraft.isPending ? "animate-spin" : ""} /> Rigenera
          </Button>
          {!isFailed && (
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={handleReject} disabled={isBusy}>
              <XIcon /> Scarta
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  );
}
