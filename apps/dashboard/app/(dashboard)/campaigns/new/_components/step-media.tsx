import { useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { MediaPreview } from "@/components/shared/media-preview";
import { EmptyState } from "@/components/shared/empty-state";
import { CardGridSkeleton } from "@/components/shared/loading-skeleton";
import { UploadDropzone } from "@/components/shared/upload-dropzone";
import { MediaTypeFilter, filterMediaByType, type MediaTypeFilterValue } from "@/components/shared/media-type-filter";
import { useMediaList } from "@/hooks/use-media";
import type { CampaignWizardValues } from "@/lib/validation/campaigns";

export function StepMedia({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const mediaQuery = useMediaList();
  const selectedId = form.watch("media_file_id");
  const [typeFilter, setTypeFilter] = useState<MediaTypeFilterValue>("all");

  const readyMedia = filterMediaByType(mediaQuery.data?.filter((m) => m.processing_status === "ready") ?? [], typeFilter);
  const processingCount =
    mediaQuery.data?.filter((m) => m.processing_status !== "ready" && m.processing_status !== "failed").length ?? 0;

  return (
    <div className="space-y-4">
      <UploadDropzone />
      {processingCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {processingCount} file in elaborazione — comparirà qui appena pronto (di solito pochi secondi).
        </p>
      )}

      <button
        type="button"
        onClick={() => form.setValue("media_file_id", null)}
        className={cn(
          "flex w-full items-center justify-between rounded-lg border p-3 text-left text-sm",
          !selectedId && "border-primary bg-primary/5"
        )}
      >
        <span>Nessun media per questa campagna (solo testo)</span>
        {!selectedId && <CheckIcon className="size-4 text-primary" />}
      </button>

      {!mediaQuery.isLoading && (mediaQuery.data?.length ?? 0) > 0 && (
        <MediaTypeFilter value={typeFilter} onChange={setTypeFilter} />
      )}

      {mediaQuery.isLoading ? (
        <CardGridSkeleton count={4} />
      ) : readyMedia.length === 0 ? (
        <EmptyState
          title="Nessun media pronto"
          description={
            typeFilter === "all"
              ? "Carica un file qui sopra oppure prosegui senza allegato."
              : "Nessun media di questo tipo. Prova un altro filtro o caricane uno nuovo."
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {readyMedia.map((media) => {
            const isSelected = selectedId === media.id;
            return (
              <button
                type="button"
                key={media.id}
                onClick={() => form.setValue("media_file_id", media.id)}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-lg border p-3 text-center",
                  isSelected && "border-primary bg-primary/5"
                )}
              >
                <MediaPreview media={media} className="size-16" />
                <span className="line-clamp-2 text-xs" title={media.original_filename}>
                  {media.original_filename}
                </span>
                {isSelected && <CheckIcon className="size-4 text-primary" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
