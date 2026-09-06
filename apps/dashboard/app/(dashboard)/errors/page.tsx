"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { RetryButton } from "@/components/shared/retry-button";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePublications, useRetryPublication } from "@/hooks/use-publications";
import { useCampaigns } from "@/hooks/use-campaigns";
import { useUsers } from "@/hooks/use-users";
import { useChannels } from "@/hooks/use-channels";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import type { PublicationResponse } from "@/types/api";

const RETRYABLE_CATEGORIES = new Set(["rate_limit", "network_error", "server_error"]);
const LIMIT = 100;

export default function ErrorsPage() {
  const [campaignId, setCampaignId] = useState("");
  const [userId, setUserId] = useState("");
  const [platform, setPlatform] = useState("");
  const [category, setCategory] = useState("");
  const [retryable, setRetryable] = useState("");
  const [fromDate, setFromDate] = useState("");

  const publicationsQuery = usePublications({ status_filter: "failed", limit: LIMIT });
  const campaignsQuery = useCampaigns({ limit: 100 });
  const usersQuery = useUsers({ limit: 100 });
  const channelsQuery = useChannels({});
  const retryPublication = useRetryPublication();

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
    const map = new Map<string, { name: string; platform: string }>();
    channelsQuery.data?.forEach((c) => map.set(c.id, { name: c.name, platform: c.platform }));
    return map;
  }, [channelsQuery.data]);

  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    publicationsQuery.data?.forEach((p) => p.error_category && set.add(p.error_category));
    return Array.from(set).map((value) => ({ value, label: value }));
  }, [publicationsQuery.data]);

  const filtered = useMemo(() => {
    const all = publicationsQuery.data ?? [];
    return all.filter((pub) => {
      if (campaignId && pub.campaign_id !== campaignId) return false;
      if (userId && pub.user_id !== userId) return false;
      if (platform && channelInfo.get(pub.social_channel_id)?.platform !== platform) return false;
      if (category && pub.error_category !== category) return false;
      if (retryable) {
        const isRetryable = pub.error_category ? RETRYABLE_CATEGORIES.has(pub.error_category) : false;
        if (retryable === "yes" && !isRetryable) return false;
        if (retryable === "no" && isRetryable) return false;
      }
      if (fromDate && new Date(pub.updated_at) < new Date(fromDate)) return false;
      return true;
    });
  }, [publicationsQuery.data, campaignId, userId, platform, category, retryable, fromDate, channelInfo]);

  const columns = useMemo<ColumnDef<PublicationResponse, unknown>[]>(
    () => [
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
        id: "platform",
        header: "Piattaforma",
        cell: ({ row }) => {
          const info = channelInfo.get(row.original.social_channel_id);
          return info ? <PlatformBadge platform={info.platform} /> : "—";
        },
      },
      {
        accessorKey: "error_category",
        header: "Categoria",
        cell: ({ row }) => row.original.error_category ?? "—",
      },
      {
        id: "retryable",
        header: "Retryable",
        cell: ({ row }) =>
          row.original.error_category ? (
            RETRYABLE_CATEGORIES.has(row.original.error_category) ? "Sì" : "No"
          ) : (
            "—"
          ),
      },
      {
        accessorKey: "error_message",
        header: "Messaggio",
        cell: ({ row }) =>
          row.original.error_message ? (
            <Tooltip>
              <TooltipTrigger className="max-w-64 truncate text-left text-destructive">{row.original.error_message}</TooltipTrigger>
              <TooltipContent className="max-w-64">{row.original.error_message}</TooltipContent>
            </Tooltip>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: "date",
        header: "Data",
        cell: ({ row }) => formatDateTime(row.original.updated_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <RetryButton
            loading={retryPublication.isPending}
            onRetry={() =>
              retryPublication.mutate(row.original.id, {
                onSuccess: () => toast.success("Pubblicazione riaccodata"),
                onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Retry non riuscito"),
              })
            }
          />
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [campaignTitles, userNames, channelInfo, retryPublication.isPending]
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Centro errori" description="Pubblicazioni fallite filtrabili per campagna, utente, piattaforma e categoria" />

      <div className="flex flex-wrap items-end gap-3">
        <FilterBar>
          <FilterSelect
            value={campaignId}
            onChange={setCampaignId}
            placeholder="Campagna"
            options={Array.from(campaignTitles.entries()).map(([value, label]) => ({ value, label }))}
          />
          <FilterSelect
            value={userId}
            onChange={setUserId}
            placeholder="Utente"
            options={Array.from(userNames.entries()).map(([value, label]) => ({ value, label }))}
          />
          <FilterSelect
            value={platform}
            onChange={setPlatform}
            placeholder="Piattaforma"
            options={[
              { value: "instagram", label: "Instagram" },
              { value: "facebook", label: "Facebook" },
              { value: "linkedin", label: "LinkedIn" },
              { value: "tiktok", label: "TikTok" },
              { value: "youtube", label: "YouTube" },
              { value: "twitter", label: "X" },
              { value: "threads", label: "Threads" },
            ]}
          />
          <FilterSelect value={category} onChange={setCategory} placeholder="Categoria" options={categoryOptions} />
          <FilterSelect
            value={retryable}
            onChange={setRetryable}
            placeholder="Retryable"
            options={[
              { value: "yes", label: "Sì" },
              { value: "no", label: "No" },
            ]}
          />
        </FilterBar>
        <div className="flex flex-col gap-1">
          <Label htmlFor="from-date" className="text-xs text-muted-foreground">
            Dal
          </Label>
          <Input
            id="from-date"
            type="date"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
            className="w-40"
          />
        </div>
      </div>

      <DataTable
        columns={columns}
        data={filtered}
        isLoading={publicationsQuery.isLoading}
        isError={publicationsQuery.isError}
        error={publicationsQuery.error}
        onRetry={() => publicationsQuery.refetch()}
        emptyTitle="Nessun errore trovato"
        emptyDescription="Ottimo! Non ci sono pubblicazioni fallite che corrispondono ai filtri selezionati."
      />
    </div>
  );
}
