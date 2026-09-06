"use client";

import { useState } from "react";
import { InboxIcon, RefreshCwIcon, MegaphoneIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/shared/search-input";
import { FilterSelect } from "@/components/shared/filter-bar";
import { useChannelAccounts } from "@/hooks/use-omnichannel";
import { cn } from "@/lib/utils";
import { ChannelIcon } from "./channel-icon";
import { BroadcastDialog } from "./broadcast-dialog";
import type { OmniConversationStatus } from "@/types/api";

const STATUS_OPTIONS: { value: OmniConversationStatus; label: string }[] = [
  { value: "WAITING_APPROVAL", label: "Bozza da approvare" },
  { value: "AI_PROCESSING", label: "AI in elaborazione" },
  { value: "OPEN", label: "Aperte" },
  { value: "WAITING_CUSTOMER", label: "In attesa del cliente" },
  { value: "RESOLVED", label: "Risolte" },
  { value: "ARCHIVED", label: "Archiviate" },
];

interface InboxToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  statusFilter: OmniConversationStatus | "";
  onStatusFilterChange: (value: OmniConversationStatus | "") => void;
  channelAccountFilter: string;
  onChannelAccountFilterChange: (value: string) => void;
  isFetching: boolean;
  onRefresh: () => void;
  conversationCount: number | undefined;
}

/**
 * Page-level toolbar for the Inbox, sitting above the 3-column layout
 * (conversation list / chat / customer panel) instead of stacked inside the
 * 300px-wide conversation list column - search, status and channel filters
 * need real horizontal room, which the narrow sidebar never had. Owns only
 * the channel-account list (for the filter pills) and the broadcast dialog;
 * all conversation filter *state* is lifted to the parent page so both this
 * toolbar and ConversationList render off the same query.
 */
export function InboxToolbar({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  channelAccountFilter,
  onChannelAccountFilterChange,
  isFetching,
  onRefresh,
  conversationCount,
}: InboxToolbarProps) {
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const { data: channelAccounts } = useChannelAccounts();

  return (
    <div className="flex flex-col gap-2.5 border-b bg-muted/30 px-4 py-3">
      <div className="flex items-center gap-3">
        <div className="flex shrink-0 items-center gap-2">
          <InboxIcon className="size-4 text-muted-foreground" />
          <h1 className="text-sm font-semibold">Inbox</h1>
          {typeof conversationCount === "number" && (
            <span className="text-xs text-muted-foreground">({conversationCount})</span>
          )}
        </div>

        <SearchInput
          value={search}
          onChange={onSearchChange}
          placeholder="Cerca cliente, telefono, email..."
          className="max-w-sm flex-1"
        />

        <FilterSelect
          value={statusFilter}
          onChange={(v) => onStatusFilterChange(v as OmniConversationStatus | "")}
          options={STATUS_OPTIONS}
          placeholder="Stato"
          allLabel="Tutte"
        />

        <Button
          size="icon-sm"
          variant="outline"
          title="Aggiorna adesso (si aggiorna comunque da sola ogni pochi secondi)"
          onClick={onRefresh}
          disabled={isFetching}
        >
          <RefreshCwIcon className={isFetching ? "animate-spin" : ""} />
        </Button>
        <Button size="icon-sm" variant="outline" title="Invio multiplo" onClick={() => setBroadcastOpen(true)}>
          <MegaphoneIcon />
        </Button>
      </div>

      {channelAccounts && channelAccounts.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Canale:</span>
          <button
            type="button"
            onClick={() => onChannelAccountFilterChange("")}
            title="Tutti i canali"
            className={cn(
              "rounded-full border px-2 py-1 text-[0.7rem] font-medium transition-colors",
              channelAccountFilter === "" ? "border-primary bg-primary/10 text-primary" : "border-transparent bg-background text-muted-foreground hover:bg-muted"
            )}
          >
            Tutti
          </button>
          {channelAccounts.map((account) => (
            <button
              key={account.id}
              type="button"
              onClick={() => onChannelAccountFilterChange(channelAccountFilter === account.id ? "" : account.id)}
              title={account.name}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2 py-1 text-[0.7rem] transition-colors",
                channelAccountFilter === account.id ? "border-primary bg-primary/10 text-primary" : "border-transparent bg-background text-muted-foreground hover:bg-muted"
              )}
            >
              <ChannelIcon channel={account.channel} />
              <span className="max-w-28 truncate">{account.name}</span>
            </button>
          ))}
        </div>
      )}

      <BroadcastDialog open={broadcastOpen} onOpenChange={setBroadcastOpen} />
    </div>
  );
}
