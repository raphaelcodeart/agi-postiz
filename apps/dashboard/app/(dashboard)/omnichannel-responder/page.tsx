"use client";

import { useState } from "react";
import { useConversations } from "@/hooks/use-omnichannel";
import { useDebounce } from "@/hooks/use-debounce";
import { InboxToolbar } from "./_components/inbox-toolbar";
import { ConversationList } from "./_components/conversation-list";
import { ChatPanel } from "./_components/chat-panel";
import { CustomerPanel } from "./_components/customer-panel";
import type { OmniConversationStatus } from "@/types/api";

export default function OmnichannelResponderPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OmniConversationStatus | "">("");
  // Filters by specific connected account (e.g. one particular Telegram bot),
  // not just by channel type - two bots of the same type would otherwise be
  // indistinguishable (see conv.channel_account_name in conversation-list.tsx).
  const [channelAccountFilter, setChannelAccountFilter] = useState("");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);

  const { data: conversations, isLoading, isFetching, refetch } = useConversations({
    status: statusFilter,
    channel_account_id: channelAccountFilter || undefined,
    search: debouncedSearch || undefined,
  });

  return (
    <div className="-m-4 flex h-[calc(100vh-4rem)] flex-col overflow-hidden rounded-lg border bg-background sm:-m-6">
      <InboxToolbar
        search={search}
        onSearchChange={setSearch}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        channelAccountFilter={channelAccountFilter}
        onChannelAccountFilterChange={setChannelAccountFilter}
        isFetching={isFetching}
        onRefresh={() => refetch()}
        conversationCount={conversations?.length}
      />
      <div className="grid min-h-0 flex-1 grid-cols-[300px_1fr_280px] overflow-hidden">
        <ConversationList conversations={conversations} isLoading={isLoading} selectedId={selectedId} onSelect={setSelectedId} />
        <ChatPanel conversationId={selectedId} onDeleted={() => setSelectedId(null)} />
        <CustomerPanel conversationId={selectedId} />
      </div>
    </div>
  );
}
