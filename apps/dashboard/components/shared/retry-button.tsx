"use client";

import { RotateCcwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface RetryButtonProps {
  onRetry: () => void;
  loading?: boolean;
  size?: "sm" | "xs" | "default";
  disabled?: boolean;
}

export function RetryButton({ onRetry, loading, size = "sm", disabled }: RetryButtonProps) {
  return (
    <Button
      variant="outline"
      size={size}
      disabled={loading || disabled}
      onClick={(event) => {
        event.stopPropagation();
        onRetry();
      }}
    >
      <RotateCcwIcon className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
      Riprova
    </Button>
  );
}
