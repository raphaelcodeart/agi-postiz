import { ImageIcon, MusicIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MediaResponse } from "@/types/api";

interface MediaPreviewProps {
  media: Pick<MediaResponse, "mime_type" | "public_url" | "original_filename">;
  className?: string;
}

export function MediaPreview({ media, className }: MediaPreviewProps) {
  const isImage = media.mime_type.startsWith("image/");
  const isVideo = media.mime_type.startsWith("video/");
  const isAudio = media.mime_type.startsWith("audio/");

  return (
    <div
      className={cn(
        "flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted",
        className
      )}
    >
      {isImage ? (
        // Backend-hosted media asset with an unpredictable origin/path; next/image
        // would require allowlisting every possible host, so a plain <img> is used.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={media.public_url} alt={media.original_filename} className="size-full object-cover" />
      ) : isVideo ? (
        // preload="metadata" fetches just enough to paint the first frame as a
        // preview thumbnail, without downloading the whole file.
        <video src={media.public_url} className="size-full object-cover" muted preload="metadata" playsInline />
      ) : isAudio ? (
        <MusicIcon className="size-5 text-muted-foreground" />
      ) : (
        <ImageIcon className="size-5 text-muted-foreground" />
      )}
    </div>
  );
}
