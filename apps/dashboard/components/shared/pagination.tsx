"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PaginationProps {
  skip: number;
  limit: number;
  count: number;
  onSkipChange: (skip: number) => void;
}

export function Pagination({ skip, limit, count, onSkipChange }: PaginationProps) {
  const page = Math.floor(skip / limit) + 1;
  const hasPrevious = skip > 0;
  const hasNext = count >= limit;

  return (
    <div className="flex items-center justify-between gap-4 pt-3">
      <p className="text-sm text-muted-foreground">
        Pagina {page} &middot; {count} risultat{count === 1 ? "o" : "i"} in questa pagina
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrevious}
          onClick={() => onSkipChange(Math.max(0, skip - limit))}
        >
          <ChevronLeftIcon className="size-3.5" />
          Precedente
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={() => onSkipChange(skip + limit)}
        >
          Successiva
          <ChevronRightIcon className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
