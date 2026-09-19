import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeftIcon, CheckCircle2Icon, ClapperboardIcon, ClockIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { portalFetch } from "@/lib/portal/server";
import type { CampaignProposalResponse } from "@/types/api";
import { ProposalForm } from "../proposal-form";
import { DeleteProposalButton } from "./delete-proposal-button";

export const dynamic = "force-dynamic";

const dateTimeFormat = new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" });

/**
 * Una proposta del promoter.
 *
 * La pagina ha due facce a seconda dello stato, e la scelta non e' estetica:
 * finche' la proposta e' in mano a chi l'ha scritta (bozza, o rimandata
 * indietro) e' un modulo modificabile; una volta consegnata diventa di sola
 * lettura, perche' e' esattamente il testo che l'amministratore sta leggendo e
 * cambiarlo sotto i suoi occhi significherebbe fargli approvare altro.
 */
export default async function PortalProposalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const proposal = await portalFetch<CampaignProposalResponse>(`proposals/${id}`);
  if (!proposal) notFound();

  const editable = proposal.status === "draft" || proposal.status === "rejected";

  return (
    <div className="flex flex-col gap-6">
      <Button variant="outline" size="sm" asChild className="self-start">
        <Link href="/portal/proposals">
          <ArrowLeftIcon className="size-4" />
          Torna alle proposte
        </Link>
      </Button>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold">{proposal.title}</h1>
          <p className="text-muted-foreground">
            Creata il {dateTimeFormat.format(new Date(proposal.created_at))}
          </p>
        </div>
        {editable && <DeleteProposalButton proposalId={proposal.id} />}
      </div>

      {proposal.status === "submitted" && (
        <Alert>
          <ClockIcon className="size-4" />
          <AlertTitle>In attesa di risposta</AlertTitle>
          <AlertDescription>
            L&apos;amministratore la sta esaminando. Finché non risponde non puoi modificarla: è il
            testo che ha davanti.
          </AlertDescription>
        </Alert>
      )}

      {proposal.status === "approved" && (
        <Alert>
          <CheckCircle2Icon className="size-4" />
          <AlertTitle>Proposta accettata</AlertTitle>
          <AlertDescription>
            È diventata una campagna. La trovi nel{" "}
            <Link href="/portal/lineup" className="text-primary hover:underline">
              palinsesto
            </Link>{" "}
            insieme alle altre, e come per ogni campagna puoi scegliere su quali dei tuoi canali
            farla uscire.
          </AlertDescription>
        </Alert>
      )}

      {editable ? (
        <ProposalForm proposal={proposal} />
      ) : (
        <ReadOnlyProposal proposal={proposal} />
      )}
    </div>
  );
}

function ReadOnlyProposal({ proposal }: { proposal: CampaignProposalResponse }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-5 p-5">
        {proposal.media_url && (
          <div>
            {proposal.media_mime_type?.startsWith("video/") ? (
              <video src={proposal.media_url} className="w-full max-w-md rounded-lg" controls playsInline />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={proposal.media_url} alt="" className="w-full max-w-md rounded-lg" />
            )}
          </div>
        )}

        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Testo proposto
          </p>
          <p className="mt-1 text-sm whitespace-pre-wrap">{proposal.default_text}</p>
        </div>

        {proposal.notes && (
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              La tua nota per l&apos;amministratore
            </p>
            <p className="mt-1 text-sm whitespace-pre-wrap">{proposal.notes}</p>
          </div>
        )}

        {proposal.video_request && (
          <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
            <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-primary uppercase">
              <ClapperboardIcon className="size-3.5" />
              Video su misura richiesto
            </p>
            <p className="mt-1 text-sm whitespace-pre-wrap">{proposal.video_request}</p>
          </div>
        )}

        {proposal.target_platforms.length > 0 && (
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Social desiderati
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {proposal.target_platforms.map((platform) => (
                <PlatformBadge key={platform} platform={platform} />
              ))}
            </div>
          </div>
        )}

        {proposal.suggested_scheduled_at && (
          <p className="text-sm text-muted-foreground">
            Data suggerita:{" "}
            <span className="text-foreground">
              {dateTimeFormat.format(new Date(proposal.suggested_scheduled_at))}
            </span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
