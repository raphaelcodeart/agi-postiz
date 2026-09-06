"use client";

import { useState } from "react";
import { XIcon, ZoomInIcon } from "lucide-react";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { MediaResponse } from "@/types/api";

/**
 * Full-size media preview with click-to-zoom for images (videos already have
 * their own native fullscreen via <video controls>, so they render plain).
 * Shared by the Bacheca feed cards and the publication detail page's "Testo
 * risolto" card, so the lightbox behavior/styling stays in one place.
 */
export function MediaLightbox({
  media,
  className = "max-h-[32rem]",
}: {
  media: Pick<MediaResponse, "mime_type" | "public_url">;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const isImage = media.mime_type.startsWith("image/");
  const isVideo = media.mime_type.startsWith("video/");

  if (isVideo) {
    return <video src={media.public_url} className={`w-full bg-black ${className}`} controls preload="metadata" playsInline />;
  }

  if (!isImage) return null;

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="group relative block w-full cursor-zoom-in" title="Ingrandisci">
        {/* Backend-hosted asset with an unpredictable origin/path, same
            reason components/shared/media-preview.tsx uses a plain <img> too. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={media.public_url} alt="" className={`w-full object-cover ${className}`} />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all duration-150 group-hover:bg-black/20 group-hover:opacity-100">
          <ZoomInIcon className="size-8 text-white drop-shadow" />
        </span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent showCloseButton={false} className="max-w-[92vw] border-none bg-transparent p-0 shadow-none sm:max-w-[92vw]">
          <DialogTitle className="sr-only">Immagine ingrandita</DialogTitle>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={media.public_url} alt="" className="mx-auto max-h-[90vh] w-auto rounded-lg object-contain" />
          <DialogClose className="absolute top-3 right-3 flex size-9 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80">
            <XIcon className="size-5" />
            <span className="sr-only">Chiudi</span>
          </DialogClose>
        </DialogContent>
      </Dialog>
    </>
  );
}
