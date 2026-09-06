"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2Icon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useWordpressSites, usePublishArticle } from "@/hooks/use-blog-writer";
import { ApiError } from "@/lib/api/errors";

interface PublishDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  articleId: string;
  alreadyPublishedSiteIds: string[];
}

export function PublishDialog({ open, onOpenChange, articleId, alreadyPublishedSiteIds }: PublishDialogProps) {
  const sitesQuery = useWordpressSites();
  const publishArticle = usePublishArticle();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const availableSites = (sitesQuery.data ?? []).filter((s) => s.is_active);

  function toggle(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function handlePublish() {
    if (selected.size === 0) return;
    const targets = Array.from(selected).map((wordpress_site_id) => ({ wordpress_site_id }));
    publishArticle.mutate(
      { id: articleId, targets },
      {
        onSuccess: () => {
          toast.success(`Pubblicazione avviata su ${targets.length} sito/i - controlla lo stato qui sotto`);
          setSelected(new Set());
          onOpenChange(false);
        },
        onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Pubblicazione non riuscita"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Pubblica sui blog</DialogTitle>
          <DialogDescription>
            Seleziona uno o più siti WordPress. Ogni sito viene pubblicato separatamente: se uno fallisce, gli altri
            proseguono comunque.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-72 space-y-2 overflow-y-auto rounded-md border p-3">
          {availableSites.length === 0 && (
            <p className="text-sm text-muted-foreground">Nessun sito WordPress attivo collegato.</p>
          )}
          {availableSites.map((site) => {
            const alreadyDone = alreadyPublishedSiteIds.includes(site.id);
            return (
              <label key={site.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={selected.has(site.id)}
                  onCheckedChange={(checked) => toggle(site.id, !!checked)}
                  disabled={alreadyDone}
                />
                <span className={alreadyDone ? "text-muted-foreground" : ""}>
                  {site.name} {alreadyDone && "(già pubblicato)"}
                </span>
              </label>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Annulla
          </Button>
          <Button onClick={handlePublish} disabled={selected.size === 0 || publishArticle.isPending}>
            {publishArticle.isPending && <Loader2Icon className="size-4 animate-spin" />}
            Pubblica ({selected.size})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
