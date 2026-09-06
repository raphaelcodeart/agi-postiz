"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import { RotateCcwIcon, ExternalLinkIcon, SendIcon, CheckCircle2Icon, LoaderIcon, XCircleIcon, BanIcon, type LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { Pagination } from "@/components/shared/pagination";
import { StatCard } from "@/components/shared/stat-card";
import { RetryButton } from "@/components/shared/retry-button";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePublications, usePublicationsSummary, useRetryPublication, useRetrySelectedPublications } from "@/hooks/use-publications";
import { useCampaigns } from "@/hooks/use-campaigns";
import { useUsers } from "@/hooks/use-users";
import { useChannels } from "@/hooks/use-channels";
import { formatDateTime } from "@/lib/format";
import { publicationStatusBuckets } from "@/lib/status-buckets";
import { ApiError } from "@/lib/api/errors";
import type { PublicationResponse, PublicationStatus } from "@/types/api";

const PUBLICATION_SUMMARY_ICONS: Record<string, LucideIcon> = {
  total: SendIcon,
  published: CheckCircle2Icon,
  active: LoaderIcon,
  failed: XCircleIcon,
  cancelled: BanIcon,
};
const PUBLICATION_SUMMARY_TONES: Record<string, "default" | "success" | "warning" | "destructive"> = {
  published: "success",
  active: "warning",
  failed: "destructive",
};

const STATUS_OPTIONS: { value: PublicationStatus; label: string }[] = [
  { value: "pending", label: "In attesa" },
  { value: "queued", label: "In coda" },
  { value: "processing", label: "In elaborazione" },
  { value: "submitted", label: "Inviato" },
  { value: "scheduled", label: "Programmato" },
  { value: "published", label: "Pubblicato" },
  { value: "retry_wait", label: "Attesa retry" },
  { value: "failed", label: "Fallito" },
  { value: "cancelled", label: "Annullato" },
  { value: "skipped", label: "Saltato" },
];

const LIMIT = 30;

export default function PublicationsPage() {
  const [statusFilter, setStatusFilter] = useState<PublicationStatus | "">("");
  const [skip, setSkip] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const publicationsQuery = usePublications({ status_filter: statusFilter || undefined, skip, limit: LIMIT });
  const summaryQuery = usePublicationsSummary();
  const summaryBuckets = summaryQuery.data
    ? publicationStatusBuckets(summaryQuery.data.total, summaryQuery.data.by_status)
    : [];
  const campaignsQuery = useCampaigns({ limit: 100 });
  const usersQuery = useUsers({ limit: 100 });
  const channelsQuery = useChannels({});

  const retryPublication = useRetryPublication();
  const retrySelected = useRetrySelectedPublications();

  const campaignTitles = useMemo(() => {
    const map = new Map<string, string>();
    campaignsQuery.data?.forEach((c) => map.set(c.id, c.title));
    return map;
  }, [campaignsQuery.data]);

  const userNames = useMemo(() => {
    const map = new Map<string, string>();
    usersQuery.data?.forEach((u) => map.set(u.id, u.name));
    return map;
  }, [usersQuery.data]);

  const channelInfo = useMemo(() => {
    const map = new Map<string, { name: string; platform: string; external_link: string | null }>();
    channelsQuery.data?.forEach((c) => map.set(c.id, { name: c.name, platform: c.platform, external_link: c.external_link }));
    return map;
  }, [channelsQuery.data]);

  function toggleSelected(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function handleRetrySelected() {
    retrySelected.mutate(Array.from(selected), {
      onSuccess: (data) => {
        toast.success(data.message);
        setSelected(new Set());
      },
      onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Retry non riuscito"),
    });
  }

  const columns = useMemo<ColumnDef<PublicationResponse, unknown>[]>(
    () => [
      {
        id: "select",
        header: "",
        cell: ({ row }) =>
          ["failed", "cancelled", "retry_wait", "queued"].includes(row.original.status) ? (
            <Checkbox
              checked={selected.has(row.original.id)}
              onCheckedChange={(checked) => toggleSelected(row.original.id, !!checked)}
            />
          ) : null,
      },
      {
        id: "campaign",
        header: "Campagna",
        cell: ({ row }) => (
          <Link href={`/campaigns/${row.original.campaign_id}`} className="hover:underline">
            {campaignTitles.get(row.original.campaign_id) ?? "—"}
          </Link>
        ),
      },
      {
        id: "user",
        header: "Utente",
        cell: ({ row }) => userNames.get(row.original.user_id) ?? "—",
      },
      {
        id: "channel",
        header: "Canale",
        cell: ({ row }) => {
          const info = channelInfo.get(row.original.social_channel_id);
          return (
            <div>
              {info ? (
                <div className="flex items-center gap-2">
                  <PlatformBadge platform={info.platform} />
                  <span>{info.name}</span>
                </div>
              ) : (
                "—"
              )}
              <span className="text-[10px] text-muted-foreground">ID Buffer: {row.original.external_channel_id}</span>
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        id: "attempts",
        header: "Tentativi",
        cell: ({ row }) => `${row.original.attempt_count}/${row.original.max_attempts}`,
      },
      {
        accessorKey: "error_message",
        header: "Ultimo errore",
        cell: ({ row }) =>
          row.original.error_message ? (
            <Tooltip>
              <TooltipTrigger className="max-w-56 truncate text-left text-destructive">{row.original.error_message}</TooltipTrigger>
              <TooltipContent className="max-w-64">{row.original.error_message}</TooltipContent>
            </Tooltip>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: "sent_at",
        header: "Data invio",
        cell: ({ row }) => formatDateTime(row.original.submitted_at ?? row.original.published_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const postUrl = row.original.external_post_url ?? channelInfo.get(row.original.social_channel_id)?.external_link;
          return (
            <div className="flex justify-end gap-1">
              {["failed", "cancelled", "retry_wait", "queued"].includes(row.original.status) && (
                <RetryButton
                  loading={retryPublication.isPending}
                  onRetry={() =>
                    retryPublication.mutate(row.original.id, {
                      onSuccess: () => toast.success("Pubblicazione riaccodata"),
                      onError: (error) =>
                        toast.error(error instanceof ApiError ? error.detail : "Retry non riuscito"),
                    })
                  }
                />
              )}
              {postUrl && (
                <Button variant="ghost" size="icon-sm" asChild aria-label="Vedi online" title="Vedi online">
                  <a href={postUrl} target="_blank" rel="noreferrer">
                    <ExternalLinkIcon className="size-3.5" />
                  </a>
                </Button>
              )}
              <Button variant="ghost" size="sm" asChild>
                <Link href={`/publications/${row.original.id}`}>Dettaglio</Link>
              </Button>
            </div>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [campaignTitles, userNames, channelInfo, selected, retryPublication.isPending]
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Pubblicazioni" description="Storico delle pubblicazioni verso i canali social" />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        {(summaryQuery.isLoading
          ? Object.keys(PUBLICATION_SUMMARY_ICONS).map((key) => ({ key, label: "", value: 0 }))
          : summaryBuckets
        ).map((bucket) => (
          <StatCard
            key={bucket.key}
            label={bucket.label}
            value={bucket.value}
            icon={PUBLICATION_SUMMARY_ICONS[bucket.key]}
            tone={PUBLICATION_SUMMARY_TONES[bucket.key] ?? "default"}
            loading={summaryQuery.isLoading}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterBar>
          <FilterSelect
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value as PublicationStatus | "");
              setSkip(0);
            }}
            placeholder="Stato"
            options={STATUS_OPTIONS}
          />
        </FilterBar>
        {selected.size > 0 && (
          <Button variant="outline" onClick={handleRetrySelected} disabled={retrySelected.isPending}>
            <RotateCcwIcon className="size-4" />
            Riprova selezionate ({selected.size})
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        data={publicationsQuery.data}
        isLoading={publicationsQuery.isLoading}
        isError={publicationsQuery.isError}
        error={publicationsQuery.error}
        onRetry={() => publicationsQuery.refetch()}
        emptyTitle="Nessuna pubblicazione trovata"
      />

      {publicationsQuery.data && (
        <Pagination skip={skip} limit={LIMIT} count={publicationsQuery.data.length} onSkipChange={setSkip} />
      )}
    </div>
  );
}
