"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2Icon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

/**
 * Removes a channel the user no longer uses from their list.
 *
 * Offered only for channels already disconnected at the social network - the
 * backend enforces the same rule. Removing a live one would be a lie: the
 * provider would still hold it and the next refresh would bring it straight
 * back.
 *
 * The confirmation says what actually happens, including what is kept: the
 * publication history survives, and a user deciding whether to click deserves to
 * know that rather than fearing they are erasing their own results.
 */
export function RemoveChannelButton({ channelId, channelName }: { channelId: string; channelName: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/portal/backend/channels/${channelId}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 204) {
        const payload = await response.json().catch(() => null);
        setError(typeof payload?.detail === "string" ? payload.detail : "Rimozione non riuscita.");
        return;
      }
      router.refresh();
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AlertDialog>
      {/* Base UI composes with `render`, not Radix's `asChild` - see the
          existing components in components/ui. */}
      <AlertDialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-destructive"
            aria-label={`Rimuovi ${channelName}`}
          />
        }
      >
        <Trash2Icon className="size-4" />
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Rimuovere «{channelName}»?</AlertDialogTitle>
          <AlertDialogDescription>
            Il canale sparisce dal tuo elenco e non verrà più incluso in nessuna campagna.
            Le statistiche dei post già pubblicati restano nel tuo storico.
            {error && <span className="mt-2 block text-destructive">{error}</span>}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annulla</AlertDialogCancel>
          <AlertDialogAction onClick={remove} disabled={pending}>
            {pending && <Loader2Icon className="size-4 animate-spin" />}
            Rimuovi
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
