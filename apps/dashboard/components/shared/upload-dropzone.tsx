"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { UploadCloudIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUploadMedia } from "@/hooks/use-media";
import { ApiError } from "@/lib/api/errors";
import { Progress } from "@/components/ui/progress";

export function UploadDropzone() {
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState<Record<string, { name: string; percent: number }>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadMedia = useUploadMedia();

  const uploadFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      Array.from(files).forEach((file) => {
        const uploadId = `${file.name}-${crypto.randomUUID()}`;
        setUploads((prev) => ({ ...prev, [uploadId]: { name: file.name, percent: 0 } }));

        uploadMedia.mutate(
          {
            file,
            onProgress: (percent) =>
              setUploads((prev) => (prev[uploadId] ? { ...prev, [uploadId]: { ...prev[uploadId], percent } } : prev)),
          },
          {
            onSuccess: () => toast.success(`${file.name} caricato`),
            onError: (error) =>
              toast.error(
                `${file.name}: ${error instanceof ApiError ? error.detail : "caricamento non riuscito"}`
              ),
            onSettled: () =>
              setUploads((prev) =>
                Object.fromEntries(Object.entries(prev).filter(([id]) => id !== uploadId))
              ),
          }
        );
      });
    },
    [uploadMedia]
  );

  const activeUploads = Object.entries(uploads);

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          uploadFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors",
          isDragging ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"
        )}
      >
        <UploadCloudIcon className="size-6 text-muted-foreground" />
        <p className="text-sm font-medium text-foreground">
          Trascina i file qui oppure clicca per selezionarli
        </p>
        <p className="text-xs text-muted-foreground">Immagini, video e audio supportati dalla piattaforma</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => uploadFiles(event.target.files)}
        />
      </div>

      {activeUploads.length > 0 && (
        <div className="space-y-2">
          {activeUploads.map(([uploadId, upload]) => (
            <div key={uploadId} className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="truncate">{upload.name}</span>
                <span className="tabular-nums">{upload.percent}%</span>
              </div>
              <Progress value={upload.percent} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
