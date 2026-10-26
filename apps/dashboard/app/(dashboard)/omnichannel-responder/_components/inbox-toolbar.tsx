"use client";

import { useState } from "react";
import { InboxIcon, RefreshCwIcon, MegaphoneIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/shared/search-input";
import { FilterSelect } from "@/components/shared/filter-bar";
import { useChannelAccounts } from "@/hooks/use-omnichannel";
import { AccountSwitcher, accountSubtitle } from "./account-switcher";
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
 * the channel-account list (for the AccountSwitcher) and the broadcast
 * dialog; all conversation filter *state* is lifted to the parent page so
 * both this toolbar and ConversationList render off the same query - and
 * the page keeps the account filter in the URL (?account=) so myAGI and
 * Canali can deep-link to "the Inbox of this number only".
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
  const selectedAccount = channelAccounts?.find((a) => a.id === channelAccountFilter);

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

        <AccountSwitcher accounts={channelAccounts} value={channelAccountFilter} onChange={onChannelAccountFilterChange} />

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

      {selectedAccount && (
        <p className="text-xs text-muted-foreground">
          Stai vedendo solo le conversazioni di <span className="font-medium text-foreground">{selectedAccount.name}</span> ({accountSubtitle(selectedAccount)}).
          Le risposte partiranno da questo numero. Le altre conversazioni restano nascoste finché non torni a &quot;Tutti i canali&quot;.
        </p>
      )}

      <BroadcastDialog open={broadcastOpen} onOpenChange={setBroadcastOpen} />
    </div>
  );
}
