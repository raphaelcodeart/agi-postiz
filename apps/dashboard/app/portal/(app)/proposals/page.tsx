import Link from "next/link";
import { redirect } from "next/navigation";
import {
  CheckCircle2Icon,
  ClockIcon,
  FileEditIcon,
  LightbulbIcon,
  PlusIcon,
  XCircleIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { portalFetch, type PortalUser } from "@/lib/portal/server";
import type { CampaignProposalResponse, CampaignProposalStatus } from "@/types/api";

export const dynamic = "force-dynamic";

/**
 * Le proposte di campagna del promoter.
 *
 * Qui non si pubblica niente: si suggerisce. Una proposta accettata diventa una
 * campagna vera creata dall'amministratore, e da quel momento segue la strada di
 * sempre - palinsesto, finestra di rinuncia, lancio. La pagina lo dice in chiaro
 * in cima, perché l'unico equivoco possibile su questa funzionalità è credere di
 * aver pubblicato qualcosa.
 */

const STATUS_META: Record<
  CampaignProposalStatus,
  {
    label: string;
    hint: string;
    variant: "default" | "secondary" | "outline" | "destructive";
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  draft: {
    label: "Bozza",
    hint: "Non ancora inviata: puoi modificarla quando vuoi.",
    variant: "outline",
    icon: FileEditIcon,
  },
  submitted: {
    label: "In attesa",
    hint: "L'amministratore la sta esaminando.",
    variant: "default",
    icon: ClockIcon,
  },
  approved: {
    label: "Accettata",
    hint: "È diventata una campagna: la trovi nel palinsesto.",
    variant: "secondary",
    icon: CheckCircle2Icon,
  },
  rejected: {
    label: "Da correggere",
    hint: "L'amministratore ha chiesto una modifica.",
    variant: "destructive",
    icon: XCircleIcon,
  },
};

const dateFormat = new Intl.DateTimeFormat("it-IT", { dateStyle: "medium" });

export default async function PortalProposalsPage() {
  const [user, proposals] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<CampaignProposalResponse[]>("proposals"),
  ]);

  if (!user) redirect("/portal/login");

  const list = proposals ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Le tue proposte</h1>
          <p className="text-muted-foreground">
            Proponi un contenuto: testo, video e quando ti piacerebbe uscisse. Se
            l&apos;amministratore lo accetta diventa una campagna vera.
          </p>
        </div>
        <Button asChild>
          <Link href="/portal/proposals/new">
            <PlusIcon className="size-4" />
            Nuova proposta
          </Link>
        </Button>
      </div>

      {list.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-6">
            <LightbulbIcon className="size-6 text-primary" />
            <div>
              <p className="font-medium">Non hai ancora proposto niente</p>
              <p className="text-sm text-muted-foreground">
                Hai girato un video che secondo te funziona? Proponilo. Se viene accettato entra nel
                palinsesto come qualunque altra campagna, e ogni promoter potrà scegliere se
                parteciparvi.
              </p>
            </div>
            <Button asChild variant="outline">
              <Link href="/portal/proposals/new">Scrivi la prima proposta</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {list.map((proposal) => {
            const meta = STATUS_META[proposal.status];
            const Icon = meta.icon;
            return (
              <Card key={proposal.id} className="transition-shadow hover:shadow-md">
                <Link href={`/portal/proposals/${proposal.id}`} className="block">
                  <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
                    {proposal.media_url && proposal.media_mime_type?.startsWith("video/") ? (
                      <video
                        src={proposal.media_url}
                        className="h-14 w-20 shrink-0 rounded object-cover"
                        muted
                        preload="metadata"
                        playsInline
                      />
                    ) : proposal.media_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={proposal.media_url}
                        alt=""
                        className="h-14 w-20 shrink-0 rounded object-cover"
                      />
                    ) : (
                      <span className="flex h-14 w-20 shrink-0 items-center justify-center rounded bg-muted">
                        <Icon className="size-5 text-muted-foreground" />
                      </span>
                    )}

                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{proposal.title}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {meta.hint} · {dateFormat.format(new Date(proposal.created_at))}
                      </p>
                    </div>

                    <Badge variant={meta.variant}>{meta.label}</Badge>
                  </CardContent>
                </Link>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
