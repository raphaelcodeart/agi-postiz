"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckIcon, ClapperboardIcon, Loader2Icon, SendIcon, SaveIcon, UploadIcon, XIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PlatformIcon, platformLabel } from "@/components/shared/platform-badge";
import { PROPOSAL_PLATFORMS } from "@/lib/proposal-platforms";
import { cn } from "@/lib/utils";
import type { CampaignProposalResponse } from "@/types/api";

/**
 * Il modulo con cui un promoter scrive una proposta di campagna.
 *
 * Due bottoni e non uno: "Salva bozza" tiene la proposta in mano a chi la
 * scrive - modificabile, cancellabile, e l'amministratore non la vede nemmeno -
 * mentre "Invia" la consegna e da quel momento la congela. Sono due intenzioni
 * diverse, e un solo bottone costringerebbe a scegliere quale delle due
 * penalizzare: o si consegna per sbaglio un testo a metà, o non c'è modo di
 * interrompere e riprendere dopo.
 *
 * Il video si carica prima, a sé (POST /portal/proposals/media): l'upload di un
 * file da telefono può durare minuti, e tenerlo dentro il salvataggio del
 * modulo significherebbe perdere tutto il testo scritto se la rete cade a metà.
 */

const MAX_TEXT = 5000;
const MAX_NOTES = 2000;
const MAX_VIDEO_REQUEST = 2000;

type UploadedMedia = { id: string; url: string; mimeType: string; name: string };

export function ProposalForm({ proposal }: { proposal?: CampaignProposalResponse }) {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState(proposal?.title ?? "");
  const [text, setText] = useState(proposal?.default_text ?? "");
  const [notes, setNotes] = useState(proposal?.notes ?? "");
  const [videoRequest, setVideoRequest] = useState(proposal?.video_request ?? "");
  const [platforms, setPlatforms] = useState<string[]>(proposal?.target_platforms ?? []);
  const [suggestedAt, setSuggestedAt] = useState(
    proposal?.suggested_scheduled_at ? proposal.suggested_scheduled_at.slice(0, 16) : ""
  );
  const [media, setMedia] = useState<UploadedMedia | null>(
    proposal?.media_file_id && proposal.media_url
      ? {
          id: proposal.media_file_id,
          url: proposal.media_url,
          mimeType: proposal.media_mime_type ?? "",
          name: "Allegato",
        }
      : null
  );

  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState<"draft" | "submit" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function uploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/portal/backend/proposals/media", { method: "POST", body });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        setError(typeof payload?.detail === "string" ? payload.detail : "Caricamento non riuscito.");
        return;
      }
      setMedia({
        id: payload.id,
        url: payload.public_url,
        mimeType: payload.mime_type,
        name: payload.original_filename,
      });
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function togglePlatform(platform: string) {
    setPlatforms((current) =>
      current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform]
    );
  }

  async function save(mode: "draft" | "submit") {
    if (!title.trim() || title.trim().length < 3) {
      setError("Dai un titolo alla proposta (almeno 3 caratteri).");
      return;
    }
    if (!text.trim()) {
      setError("Scrivi il testo del post che proponi.");
      return;
    }

    setSaving(mode);
    setError(null);

    const payload = {
      title: title.trim(),
      default_text: text,
      notes: notes.trim() || null,
      video_request: videoRequest.trim() || null,
      target_platforms: platforms,
      media_file_id: media?.id ?? null,
      // datetime-local non porta fuso: viene interpretato come ora locale del
      // browser e mandato in UTC, come ovunque altro nel prodotto.
      suggested_scheduled_at: suggestedAt ? new Date(suggestedAt).toISOString() : null,
    };

    try {
      let proposalId = proposal?.id;

      if (proposalId) {
        const response = await fetch(`/api/portal/backend/proposals/${proposalId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          setError(typeof detail?.detail === "string" ? detail.detail : "Salvataggio non riuscito.");
          return;
        }
      } else {
        const response = await fetch("/api/portal/backend/proposals", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, submit: mode === "submit" }),
        });
        const created = await response.json().catch(() => null);
        if (!response.ok) {
          setError(typeof created?.detail === "string" ? created.detail : "Salvataggio non riuscito.");
          return;
        }
        // Creata già consegnata: l'invio è avvenuto nella stessa chiamata, non
        // serve il passaggio esplicito qui sotto.
        proposalId = created.id;
        if (mode === "submit") {
          router.push("/portal/proposals");
          router.refresh();
          return;
        }
      }

      if (mode === "submit") {
        const response = await fetch(`/api/portal/backend/proposals/${proposalId}/submit`, {
          method: "POST",
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          setError(typeof detail?.detail === "string" ? detail.detail : "Invio non riuscito.");
          return;
        }
      }

      router.push("/portal/proposals");
      router.refresh();
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setSaving(null);
    }
  }

  const busy = saving !== null || uploading;

  return (
    <div className="flex flex-col gap-5">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {proposal?.status === "rejected" && proposal.review_notes && (
        <Alert>
          <AlertDescription>
            <span className="font-medium">L&apos;amministratore ha chiesto una modifica:</span>{" "}
            {proposal.review_notes}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="flex flex-col gap-5 p-5">
          <div className="space-y-1.5">
            <Label>Titolo</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={255}
              placeholder="Es. Video unboxing del prodotto nuovo"
            />
            <p className="text-xs text-muted-foreground">
              Serve solo a riconoscere la proposta: non viene pubblicato.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Testo del post</Label>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_TEXT))}
              rows={7}
              placeholder="Scrivi il post come lo pubblicheresti."
            />
            <p className="text-xs text-muted-foreground">
              {text.length}/{MAX_TEXT} caratteri. L&apos;amministratore può adattarlo alle singole
              piattaforme prima di pubblicarlo.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Video o immagine</Label>
            {media ? (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
                {media.mimeType.startsWith("video/") ? (
                  <video src={media.url} className="h-20 w-32 rounded object-cover" muted preload="metadata" playsInline />
                ) : (
                  // Media servito dal backend su un host non prevedibile:
                  // next/image richiederebbe di elencarli tutti.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={media.url} alt={media.name} className="h-20 w-32 rounded object-cover" />
                )}
                <span className="min-w-0 flex-1 truncate text-sm">{media.name}</span>
                <Button variant="ghost" size="sm" onClick={() => setMedia(null)} disabled={busy}>
                  <XIcon className="size-4" />
                  Togli
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <input
                  ref={fileInput}
                  type="file"
                  accept="video/*,image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void uploadFile(file);
                  }}
                />
                <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
                  {uploading ? <Loader2Icon className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}
                  {uploading ? "Caricamento..." : "Carica un file"}
                </Button>
                <span className="text-xs text-muted-foreground">Facoltativo.</span>
              </div>
            )}
          </div>

          {/* Per chi il video non sa o non può farlo: lo chiede a noi. È un
              riquadro a sé, non un campo in più fra gli altri, perché è una
              richiesta di lavoro per AGI Post e non un pezzo del post. */}
          <div className="space-y-2 rounded-xl border border-primary/25 bg-primary/5 p-4">
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <ClapperboardIcon className="size-4" />
              </span>
              <div>
                <Label htmlFor="video-request">Vuoi che il video lo creiamo noi?</Label>
                <p className="text-xs text-muted-foreground">
                  Facoltativo. Se non hai un video o non sai come farlo, descrivi cosa vorresti: lo
                  realizza il team di AGI Post.
                </p>
              </div>
            </div>
            <Textarea
              id="video-request"
              value={videoRequest}
              onChange={(e) => setVideoRequest(e.target.value.slice(0, MAX_VIDEO_REQUEST))}
              rows={4}
              className="bg-card"
              placeholder="Es. Un reel verticale di 20-30 secondi che mostri il prodotto in uso, tono ironico, con sottotitoli e musica allegra..."
            />
            <p className="text-xs text-muted-foreground">
              {videoRequest.length}/{MAX_VIDEO_REQUEST} caratteri. Più dettagli dai (durata, stile,
              cosa mostrare, testi) più il video sarà come lo immagini.
            </p>
          </div>

          <div className="space-y-2">
            <Label>Su quali social vorresti pubblicarla</Label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Social desiderati">
              {PROPOSAL_PLATFORMS.map((platform) => {
                const selected = platforms.includes(platform);
                return (
                  <button
                    key={platform}
                    type="button"
                    onClick={() => togglePlatform(platform)}
                    aria-pressed={selected}
                    disabled={busy}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border py-1 pr-3.5 pl-1 text-sm font-medium shadow-xs transition-colors focus-visible:ring-3 focus-visible:ring-primary/30 focus-visible:outline-none disabled:opacity-50",
                      selected
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-card-foreground hover:border-primary/40 hover:bg-primary/5"
                    )}
                  >
                    <PlatformIcon platform={platform} className="size-7" />
                    {platformLabel(platform)}
                    {selected && <CheckIcon className="size-4" />}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Facoltativo. Serve all&apos;amministratore per configurare la campagna sui social giusti.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Quando ti piacerebbe uscisse</Label>
            <Input
              type="datetime-local"
              value={suggestedAt}
              onChange={(e) => setSuggestedAt(e.target.value)}
              className="max-w-xs"
            />
            <p className="text-xs text-muted-foreground">
              Facoltativo e non vincolante: la data la decide l&apos;amministratore.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Nota per l&apos;amministratore</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value.slice(0, MAX_NOTES))}
              rows={3}
              placeholder="Perché secondo te funziona, a chi si rivolge, cosa c'è nel video..."
            />
            <p className="text-xs text-muted-foreground">Non viene pubblicata da nessuna parte.</p>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save("submit")} disabled={busy}>
          {saving === "submit" ? <Loader2Icon className="size-4 animate-spin" /> : <SendIcon className="size-4" />}
          Invia all&apos;amministratore
        </Button>
        <Button variant="outline" onClick={() => save("draft")} disabled={busy}>
          {saving === "draft" ? <Loader2Icon className="size-4 animate-spin" /> : <SaveIcon className="size-4" />}
          Salva bozza
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Una volta inviata non potrai più modificarla, finché l&apos;amministratore non ti chiede una
        correzione.
      </p>
    </div>
  );
}
