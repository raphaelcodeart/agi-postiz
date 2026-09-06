"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Trash2Icon, ImagesIcon, PencilIcon, CheckIcon, XIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { MediaPreview } from "@/components/shared/media-preview";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { SearchInput } from "@/components/shared/search-input";
import { CardGridSkeleton } from "@/components/shared/loading-skeleton";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMediaList, useDeleteMedia, useRenameMedia } from "@/hooks/use-media";
import { useDebounce } from "@/hooks/use-debounce";
import { formatBytes, formatDateTime, formatDuration } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import type { MediaResponse } from "@/types/api";
import { UploadDropzone } from "@/components/shared/upload-dropzone";

export default function MediaPage() {
  const mediaQuery = useMediaList();
  const deleteMedia = useDeleteMedia();
  const renameMedia = useRenameMedia();
  const [deleteTarget, setDeleteTarget] = useState<MediaResponse | null>(null);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const filtered = useMemo(() => {
    const term = debouncedSearch.trim().toLowerCase();
    const all = mediaQuery.data ?? [];
    if (!term) return all;
    return all.filter((media) => media.original_filename.toLowerCase().includes(term));
  }, [mediaQuery.data, debouncedSearch]);

  function startEditing(media: MediaResponse) {
    setEditingId(media.id);
    setEditValue(media.original_filename);
  }

  function cancelEditing() {
    setEditingId(null);
    setEditValue("");
  }

  function confirmRename(media: MediaResponse) {
    const trimmed = editValue.trim();
    if (!trimmed || trimmed === media.original_filename) {
      cancelEditing();
      return;
    }
    renameMedia.mutate(
      { id: media.id, originalFilename: trimmed },
      {
        onSuccess: () => {
          toast.success("Nome aggiornato");
          cancelEditing();
        },
        onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Rinomina non riuscita"),
      }
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Media" description="Carica e gestisci le risorse multimediali per le campagne" />

      <UploadDropzone />

      <SearchInput value={search} onChange={setSearch} placeholder="Cerca per nome file..." className="sm:max-w-xs" />

      {mediaQuery.isLoading && <CardGridSkeleton count={8} />}
      {mediaQuery.isError && <ErrorState error={mediaQuery.error} onRetry={() => mediaQuery.refetch()} />}
      {mediaQuery.data && mediaQuery.data.length === 0 && (
        <EmptyState icon={ImagesIcon} title="Nessun media caricato" description="Trascina un file per iniziare." />
      )}
      {mediaQuery.data && mediaQuery.data.length > 0 && filtered.length === 0 && (
        <EmptyState icon={ImagesIcon} title="Nessun media corrisponde alla ricerca" />
      )}

      {filtered.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
          {filtered.map((media) => (
            <Card key={media.id}>
              <CardContent className="space-y-2 p-3">
                <div className="flex items-start gap-2">
                  <MediaPreview media={media} className="size-10 shrink-0" />
                  <div className="min-w-0 flex-1 space-y-0.5">
                    {editingId === media.id ? (
                      <div className="flex items-center gap-1">
                        <Input
                          autoFocus
                          value={editValue}
                          onChange={(event) => setEditValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") confirmRename(media);
                            if (event.key === "Escape") cancelEditing();
                          }}
                          className="h-6 px-1.5 text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => confirmRename(media)}
                          disabled={renameMedia.isPending}
                          className="shrink-0 text-success"
                        >
                          <CheckIcon className="size-3.5" />
                        </button>
                        <button type="button" onClick={cancelEditing} className="shrink-0 text-muted-foreground">
                          <XIcon className="size-3.5" />
                        </button>
                      </div>
                    ) : (
                      <div className="group flex items-center gap-1">
                        <p className="truncate text-xs font-medium" title={media.original_filename}>
                          {media.original_filename}
                        </p>
                        <button
                          type="button"
                          onClick={() => startEditing(media)}
                          className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground"
                          title="Rinomina"
                        >
                          <PencilIcon className="size-3" />
                        </button>
                      </div>
                    )}
                    <p className="truncate text-[10px] text-muted-foreground">{media.mime_type}</p>
                    <div className="flex flex-wrap gap-1">
                      <StatusBadge status={media.processing_status} />
                      <StatusBadge status={media.validation_status} />
                    </div>
                  </div>
                </div>
                <dl className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground">
                  <dt>Dimensione</dt>
                  <dd className="text-right text-foreground">{formatBytes(media.size_bytes)}</dd>
                  {media.width && media.height && (
                    <>
                      <dt>Risoluzione</dt>
                      <dd className="text-right text-foreground">
                        {media.width}×{media.height}
                      </dd>
                    </>
                  )}
                  {media.duration_seconds !== null && (
                    <>
                      <dt>Durata</dt>
                      <dd className="text-right text-foreground">{formatDuration(media.duration_seconds)}</dd>
                    </>
                  )}
                  <dt>Caricato</dt>
                  <dd className="text-right text-foreground">{formatDateTime(media.created_at)}</dd>
                </dl>
                {media.validation_errors && media.validation_errors.length > 0 && (
                  <p className="rounded-md bg-destructive/10 p-1.5 text-[10px] text-destructive">
                    {media.validation_errors.map((e) => e.message).join("; ")}
                  </p>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 w-full text-xs text-destructive"
                  onClick={() => setDeleteTarget(media)}
                >
                  <Trash2Icon className="size-3" />
                  Elimina
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Eliminare questo file multimediale?"
        description="Non è possibile eliminare un media collegato a una campagna attiva."
        confirmLabel="Elimina"
        destructive
        loading={deleteMedia.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteMedia.mutate(deleteTarget.id, {
            onSuccess: () => setDeleteTarget(null),
            onError: (error) => {
              toast.error(error instanceof ApiError ? error.detail : "Eliminazione non riuscita");
              setDeleteTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
