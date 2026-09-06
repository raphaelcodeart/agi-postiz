"use client";

import { useEffect } from "react";
import { AlertTriangleIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="rounded-full bg-destructive/10 p-3 text-destructive">
        <AlertTriangleIcon className="size-6" />
      </div>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Si è verificato un errore imprevisto</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Riprova. Se il problema persiste, contatta l&apos;amministratore di sistema.
        </p>
      </div>
      <Button onClick={reset}>Riprova</Button>
    </div>
  );
}
