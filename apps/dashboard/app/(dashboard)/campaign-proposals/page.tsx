"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowRightIcon,
  CheckCircle2Icon,
  ClapperboardIcon,
  ClockIcon,
  LightbulbIcon,
  MegaphoneIcon,
  XCircleIcon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { MediaPreview } from "@/components/shared/media-preview";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCampaignProposals,
  useCampaignProposalsSummary,
} from "@/hooks/use-campaign-proposals";
import { formatDateTime } from "@/lib/format";
import { proposalPrefillHref } from "@/lib/campaign-proposal-prefill";
import type { CampaignProposalResponse, CampaignProposalStatus } from "@/types/api";
import { RejectProposalDialog } from "./_components/reject-proposal-dialog";

/**
 * Le proposte di campagna scritte dai promoter dal loro portale.
 *
 * Qui dentro non si pubblica niente e non si crea niente: il bottone
 * "Approva e crea campagna" porta al wizard di creazione già compilato col
 * contenuto proposto. È lo stesso wizard di sempre - destinatari, date,
 * palinsesto, lancio - perché la regola che questa funzionalità non deve
 * scalfire è che la campagna vera la lancia sempre e solo l'amministratore.
 * La proposta risulta approvata nel momento in cui la campagna viene creata,
 * nella stessa transazione (vedi apps/api/app/api/v1/campaign_proposals.py).
 *
 * Le bozze che un promoter sta ancora scrivendo non arrivano mai qui: il
 * backend non le espone affatto.
 */

const STATUS_OPTIONS: { value: CampaignProposalStatus; label: string }[] = [
  { value: "submitted", label: "Da esaminare" },
  { value: "approved", label: "Approvate" },
  { value: "rejected", label: "Rifiutate" },
];

const STATUS_BADGE: Record<
  CampaignProposalStatus,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  draft: { label: "Bozza", variant: "outline" },
  submitted: { label: "Da esaminare", variant: "default" },
  approved: { label: "Approvata", variant: "secondary" },
  rejected: { label: "Rifiutata", variant: "destructive" },
};

export default function CampaignProposalsPage() {
  const [status, setStatus] = useState<CampaignProposalStatus | "">("");
  const [rejecting, setRejecting] = useState<CampaignProposalResponse | null>(null);
  const proposalsQuery = useCampaignProposals(status ? { status } : {});
  const summaryQuery = useCampaignProposalsSummary();
  const router = useRouter();

  const counts = summaryQuery.data?.by_status ?? {};

  function approve(proposal: CampaignProposalResponse) {
    // Nessuna chiamata di approvazione: si va al wizard, e l'approvazione
    // avviene quando la campagna viene creata là in fondo.
    toast.info("Completa destinatari e date: la proposta risulterà approvata alla creazione della campagna.");
    router.push(proposalPrefillHref(proposal.id));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Proposte di campagna"
        description="Contenuti suggeriti dai promoter. Approvandone una si apre il wizard di creazione già compilato: destinatari, date e lancio restano tuoi."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Da esaminare" value={counts.submitted ?? 0} icon={ClockIcon} tone={counts.submitted ? "warning" : "default"} />
        <StatCard label="Approvate" value={counts.approved ?? 0} icon={CheckCircle2Icon} tone="success" />
        <StatCard label="Rifiutate" value={counts.rejected ?? 0} icon={XCircleIcon} />
      </div>

      <FilterBar>
        <FilterSelect
          value={status}
          onChange={(value) => setStatus(value as CampaignProposalStatus | "")}
          options={STATUS_OPTIONS}
          placeholder="Stato"
          allLabel="Tutte"
        />
      </FilterBar>

      {proposalsQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : proposalsQuery.isError ? (
        <ErrorState error={proposalsQuery.error} onRetry={() => proposalsQuery.refetch()} />
      ) : (proposalsQuery.data ?? []).length === 0 ? (
        <EmptyState
          title="Nessuna proposta"
          description="Quando un promoter invia un contenuto dal suo portale lo trovi qui."
          icon={LightbulbIcon}
        />
      ) : (
        <div className="space-y-3">
          {proposalsQuery.data!.map((proposal) => (
            <ProposalCard
              key={proposal.id}
              proposal={proposal}
              onApprove={() => approve(proposal)}
              onReject={() => setRejecting(proposal)}
            />
          ))}
        </div>
      )}

      {rejecting && (
        <RejectProposalDialog
          proposal={rejecting}
          open={!!rejecting}
          onOpenChange={(open) => !open && setRejecting(null)}
        />
      )}
    </div>
  );
}

function ProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: CampaignProposalResponse;
  onApprove: () => void;
  onReject: () => void;
}) {
  const badge = STATUS_BADGE[proposal.status];
  const pending = proposal.status === "submitted";

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold">{proposal.title}</h2>
              <Badge variant={badge.variant}>{badge.label}</Badge>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Proposta da <span className="font-medium text-foreground">{proposal.user_name ?? "—"}</span>
              {proposal.submitted_at && ` · inviata il ${formatDateTime(proposal.submitted_at)}`}
            </p>
          </div>

          {pending && (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={onReject}>
                <XCircleIcon className="size-4" />
                Rifiuta
              </Button>
              <Button size="sm" onClick={onApprove}>
                <MegaphoneIcon className="size-4" />
                Approva e crea campagna
                <ArrowRightIcon className="size-4" />
              </Button>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          {proposal.media_url && (
            <div className="w-full shrink-0 sm:w-56">
              <MediaPreview
                className="h-auto w-full"
                media={{
                  public_url: proposal.media_url,
                  mime_type: proposal.media_mime_type ?? "application/octet-stream",
                  original_filename: proposal.title,
                }}
              />
            </div>
          )}
          <div className="min-w-0 flex-1 space-y-3">
            <div>
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Testo proposto</p>
              <p className="mt-1 text-sm whitespace-pre-wrap">{proposal.default_text}</p>
            </div>

            {proposal.video_request && (
              /* Una richiesta di lavoro per il team, non testo da pubblicare:
                 in evidenza perché prima di approvare il video va prodotto. */
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3">
                <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-primary uppercase">
                  <ClapperboardIcon className="size-3.5" />
                  Richiesta video su misura
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

            {proposal.notes && (
              /* Nota per te, non testo da pubblicare: separata visivamente
                 apposta, perché finisse nel post sarebbe un errore visibile
                 su ogni canale. */
              <div className="rounded-md border border-dashed p-3">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  Nota del promoter (non viene pubblicata)
                </p>
                <p className="mt-1 text-sm whitespace-pre-wrap">{proposal.notes}</p>
              </div>
            )}

            {proposal.suggested_scheduled_at && (
              <p className="text-sm text-muted-foreground">
                Data suggerita: <span className="text-foreground">{formatDateTime(proposal.suggested_scheduled_at)}</span>{" "}
                — indicativa, la decidi tu nel wizard.
              </p>
            )}

            {proposal.status === "rejected" && proposal.review_notes && (
              <p className="text-sm text-destructive">
                Rifiutata: {proposal.review_notes}
                <span className="block text-xs text-muted-foreground">
                  Il promoter può correggerla e rimandarla.
                </span>
              </p>
            )}

            {proposal.status === "approved" && proposal.campaign_id && (
              <Link
                href={`/campaigns/${proposal.campaign_id}`}
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              >
                Vai alla campagna creata
                <ArrowRightIcon className="size-3.5" />
              </Link>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
