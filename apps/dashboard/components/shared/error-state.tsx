"use client";

import { AlertTriangleIcon, RefreshCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";

interface ErrorStateProps {
  error?: unknown;
  title?: string;
  onRetry?: () => void;
}

export function ErrorState({ error, title = "Impossibile caricare i dati", onRetry }: ErrorStateProps) {
  const detail = error instanceof ApiError ? error.detail : error instanceof Error ? error.message : null;

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 py-16 text-center">
      <div className="rounded-full bg-destructive/10 p-3 text-destructive">
        <AlertTriangleIcon className="size-5" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {detail && <p className="max-w-sm text-sm text-muted-foreground">{detail}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCwIcon className="size-3.5" />
          Riprova
        </Button>
      )}
    </div>
  );
}
