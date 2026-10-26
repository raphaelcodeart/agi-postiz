"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useConversations } from "@/hooks/use-omnichannel";
import { useDebounce } from "@/hooks/use-debounce";
import { InboxToolbar } from "./_components/inbox-toolbar";
import { ConversationList } from "./_components/conversation-list";
import { ChatPanel } from "./_components/chat-panel";
import { CustomerPanel } from "./_components/customer-panel";
import type { OmniConversationStatus } from "@/types/api";

// Ultimo numero scelto, per riaprire l'Inbox dove la si era lasciata. E' una
// comodita' per singolo browser, non uno stato condiviso: l'URL (?account=)
// resta la fonte di verita' e vince sempre quando c'e'.
const LAST_ACCOUNT_KEY = "omni.inbox.account";

function readLastAccount(): string {
  try {
    return window.localStorage.getItem(LAST_ACCOUNT_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeLastAccount(value: string) {
  try {
    if (value) window.localStorage.setItem(LAST_ACCOUNT_KEY, value);
    else window.localStorage.removeItem(LAST_ACCOUNT_KEY);
  } catch {
    // storage non disponibile (navigazione privata, dati bloccati): si lavora senza memoria
  }
}

function InboxPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Filtra per account collegato (uno specifico numero WhatsApp, un
  // particolare bot Telegram), non per tipo di canale: due numeri dello
  // stesso tipo sarebbero altrimenti indistinguibili. Vive nell'URL cosi'
  // myAGI e Canali possono portare qui "le conversazioni di questo numero".
  const channelAccountFilter = searchParams.get("account") ?? "";

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OmniConversationStatus | "">("");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);

  const setChannelAccountFilter = useCallback(
    (value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) params.set("account", value);
      else params.delete("account");
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
      writeLastAccount(value);
      // La conversazione aperta puo' appartenere a un altro numero: si chiude
      // per non mostrare una chat che la lista a sinistra non contiene piu'.
      setSelectedId(null);
    },
    [pathname, router, searchParams]
  );

  // Prima apertura senza ?account=: si riparte dall'ultimo numero usato.
  useEffect(() => {
    if (searchParams.has("account")) return;
    const last = readLastAccount();
    if (last) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("account", last);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
    // Solo al primo render: in seguito e' l'utente a decidere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

// useSearchParams richiede un confine Suspense nelle pagine client di Next.
export default function OmnichannelResponderPage() {
  return (
    <Suspense>
      <InboxPage />
    </Suspense>
  );
}
