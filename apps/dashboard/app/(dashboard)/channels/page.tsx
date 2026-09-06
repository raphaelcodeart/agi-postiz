"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import { RefreshCwIcon, ExternalLinkIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { PlatformBadge, PlatformIcon } from "@/components/shared/platform-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { SearchInput } from "@/components/shared/search-input";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { Pagination } from "@/components/shared/pagination";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useChannels, useUpdateChannelMode } from "@/hooks/use-channels";
import { useUsers } from "@/hooks/use-users";
import { useBufferConnections } from "@/hooks/use-buffer-connections";
import { useDebounce } from "@/hooks/use-debounce";
import { syncConnection } from "@/services/buffer-connections";
import { queryKeys } from "@/lib/query/keys";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import type { PublicationMode, SocialChannelResponse } from "@/types/api";

const PLATFORM_OPTIONS = [
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube" },
  { value: "twitter", label: "X" },
  { value: "threads", label: "Threads" },
];

const MODE_OPTIONS: { value: PublicationMode; label: string }[] = [
  { value: "automatic", label: "Automatico" },
  { value: "notification", label: "Notifica" },
  { value: "approval", label: "Approvazione" },
  { value: "disabled", label: "Disabilitato" },
];

const PAGE_SIZE = 25;

export default function ChannelsPage() {
  const [platform, setPlatform] = useState("");
  const [publicationMode, setPublicationMode] = useState("");
  const [search, setSearch] = useState("");
  const [skip, setSkip] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const queryClient = useQueryClient();
  const debouncedSearch = useDebounce(search, 300);
  const channelsQuery = useChannels({
    platform: platform || undefined,
    publication_mode: (publicationMode as PublicationMode) || undefined,
  });
  const updateMode = useUpdateChannelMode();
  const connectionsQuery = useBufferConnections();
  const usersQuery = useUsers({ limit: 100 });

  const userNames = useMemo(() => {
    const map = new Map<string, string>();
    usersQuery.data?.forEach((u) => map.set(u.id, u.name));
    return map;
  }, [usersQuery.data]);

  // Buffer only tells us about a newly-added social profile once we ask it to
  // (POST /connections/{id}/sync per connection) - there's no push/webhook, so
  // "refresh channels" here means fanning that out across every connected account.
  async function handleRefreshAll() {
    const connections = connectionsQuery.data ?? [];
    if (connections.length === 0) {
      toast.info("Nessuna connessione Buffer da sincronizzare");
      return;
    }

    setIsRefreshing(true);
    const results = await Promise.allSettled(connections.map((conn) => syncConnection(conn.id)));
    const failed = results.filter((r) => r.status === "rejected").length;

    // Sync runs in the background worker, not synchronously in this request, so
    // give it a moment before refetching or the list would still show stale data.
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["channels", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.bufferConnections.list() });
      setIsRefreshing(false);
    }, 2500);

    if (failed > 0) {
      toast.warning(`Sincronizzazione avviata: ${failed} connessione/i non ha risposto subito`);
    } else {
      toast.success(`Sincronizzazione avviata su ${connections.length} connessione/i, i nuovi canali appariranno a breve`);
    }
  }

  // The /buffer/channels endpoint has no server-side pagination, so filtering by
  // name/username and paging through results happens client-side over the full set.
  const filtered = useMemo(() => {
    const term = debouncedSearch.trim().toLowerCase();
    const all = channelsQuery.data ?? [];
    if (!term) return all;
    return all.filter(
      (channel) =>
        channel.name.toLowerCase().includes(term) || channel.username?.toLowerCase().includes(term)
    );
  }, [channelsQuery.data, debouncedSearch]);

  const page = filtered.slice(skip, skip + PAGE_SIZE);

  function handleModeChange(channelId: string, mode: PublicationMode) {
    updateMode.mutate(
      { channelId, mode },
      {
        onSuccess: () => toast.success("Modalità di pubblicazione aggiornata"),
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
      }
    );
  }

  const columns = useMemo<ColumnDef<SocialChannelResponse, unknown>[]>(
    () => [
      {
        id: "platform_icon",
        header: "",
        cell: ({ row }) => <PlatformIcon platform={row.original.platform} />,
      },
      {
        accessorKey: "name",
        header: "Canale",
        cell: ({ row }) => (
          <div>
            {row.original.external_link ? (
              <a
                href={row.original.external_link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-medium text-foreground hover:underline"
              >
                {row.original.name}
                <ExternalLinkIcon className="size-3 text-muted-foreground" />
              </a>
            ) : (
              <p className="font-medium text-foreground">{row.original.name}</p>
            )}
            {row.original.username && (
              <p className="text-xs text-muted-foreground">@{row.original.username}</p>
            )}
          </div>
        ),
      },
      {
        accessorKey: "platform",
        header: "Piattaforma",
        cell: ({ row }) => <PlatformBadge platform={row.original.platform} />,
      },
      {
        id: "user",
        header: "Utente",
        cell: ({ row }) => userNames.get(row.original.user_id) ?? "—",
      },
      {
        accessorKey: "is_active",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.is_active ? "active" : "inactive"} />,
      },
      {
        id: "publication_mode",
        header: "Modalità pubblicazione",
        cell: ({ row }) => (
          <Select
            items={MODE_OPTIONS}
            value={row.original.publication_mode}
            onValueChange={(value) => handleModeChange(row.original.id, value as PublicationMode)}
          >
            <SelectTrigger size="sm" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
      },
      {
        accessorKey: "last_sync_at",
        header: "Ultima sincronizzazione",
        cell: ({ row }) => formatDateTime(row.original.last_sync_at),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [userNames]
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Canali social"
        description="Profili social collegati tramite Buffer e modalità di pubblicazione"
        actions={
          <Button variant="outline" onClick={handleRefreshAll} disabled={isRefreshing}>
            <RefreshCwIcon className={isRefreshing ? "size-4 animate-spin" : "size-4"} />
            Aggiorna canali
          </Button>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            setSkip(0);
          }}
          placeholder="Cerca canale o username..."
          className="sm:max-w-xs"
        />
        <FilterBar>
          <FilterSelect
            value={platform}
            onChange={(value) => {
              setPlatform(value);
              setSkip(0);
            }}
            placeholder="Piattaforma"
            options={PLATFORM_OPTIONS}
          />
          <FilterSelect
            value={publicationMode}
            onChange={(value) => {
              setPublicationMode(value);
              setSkip(0);
            }}
            placeholder="Modalità"
            options={MODE_OPTIONS}
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        data={page}
        isLoading={channelsQuery.isLoading}
        isError={channelsQuery.isError}
        error={channelsQuery.error}
        onRetry={() => channelsQuery.refetch()}
        emptyTitle="Nessun canale trovato"
      />

      <Pagination skip={skip} limit={PAGE_SIZE} count={page.length} onSkipChange={setSkip} />
    </div>
  );
}
