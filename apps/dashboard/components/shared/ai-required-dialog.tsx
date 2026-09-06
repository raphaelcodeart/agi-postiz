"use client";

import { useRouter } from "next/navigation";
import { SparklesIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface AIRequiredDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Shown wherever an AI-powered action (campaign text generation, blog article
// generation/regeneration, social-preview adaptation) is attempted without an
// OpenAI key configured. See hooks/use-ai-gate.ts for the check this pairs with.
export function AIRequiredDialog({ open, onOpenChange }: AIRequiredDialogProps) {
  const router = useRouter();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SparklesIcon className="size-4" />
            Configurazione AI richiesta
          </DialogTitle>
          <DialogDescription>
            Per usare questa funzionalità devi prima configurare la API ChatGPT nelle Impostazioni.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Chiudi
          </Button>
          <Button
            onClick={() => {
              onOpenChange(false);
              router.push("/settings");
            }}
          >
            Vai alle Impostazioni
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
