"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as omnichannelService from "@/services/omnichannel";
import { queryKeys } from "@/lib/query/keys";
import type { ListConversationsParams } from "@/services/omnichannel";
import type { OmniAIAgentConfigUpdate, OmniBroadcastRequest, OmniChannelAccountCreate, OmniChannelAccountUpdate, OmniCustomerUpdate, OmniKnowledgeCompanyCreate, OmniKnowledgeCompanyUpdate, OmniKnowledgeDocumentCreate, OmniKnowledgeDocumentUpdate, OmniKnowledgeFindParams, OmniKnowledgeListParams, OmniTagCreate } from "@/types/api";

// Channel accounts
export function useChannelAccounts() {
  return useQuery({
    queryKey: queryKeys.omnichannel.channelAccounts(),
    queryFn: omnichannelService.listChannelAccounts,
  });
}

export function useCreateChannelAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OmniChannelAccountCreate) => omnichannelService.createChannelAccount(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

export function useUpdateChannelAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OmniChannelAccountUpdate }) =>
      omnichannelService.updateChannelAccount(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

export function useToggleChannelAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.toggleChannelAccount(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

export function useDeleteChannelAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.deleteChannelAccount(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

export function useCheckChannelAccountStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.getChannelAccountStatus(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

export function useRegisterChannelWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, publicBaseUrl }: { id: string; publicBaseUrl: string }) => omnichannelService.registerChannelWebhook(id, publicBaseUrl),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() }),
  });
}

// Conversations - polled (no WebSocket/SSE in this codebase yet, see lib/navigation.ts group docstring)
export function useConversations(params: ListConversationsParams = {}) {
  return useQuery({
    queryKey: queryKeys.omnichannel.conversations(params),
    queryFn: () => omnichannelService.listConversations(params),
    refetchInterval: 8000,
    placeholderData: (previousData) => previousData,
  });
}

export function useConversationDetail(id: string | null) {
  return useQuery({
    queryKey: queryKeys.omnichannel.conversationDetail(id ?? ""),
    queryFn: () => omnichannelService.getConversationDetail(id as string),
    enabled: !!id,
    refetchInterval: 4000,
  });
}

function useInvalidateConversation(conversationId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.conversationDetail(conversationId) });
    queryClient.invalidateQueries({ queryKey: ["omnichannel", "conversations"] });
  };
}

export function useAssignConversation(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (assignedAdminId: string | null) => omnichannelService.assignConversation(conversationId, assignedAdminId),
    onSuccess: invalidate,
  });
}

export function useResolveConversation(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: () => omnichannelService.resolveConversation(conversationId),
    onSuccess: invalidate,
  });
}

export function useArchiveConversation(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: () => omnichannelService.archiveConversation(conversationId),
    onSuccess: invalidate,
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => omnichannelService.deleteConversation(conversationId),
    onSuccess: (_data, conversationId) => {
      queryClient.removeQueries({ queryKey: queryKeys.omnichannel.conversationDetail(conversationId) });
      queryClient.invalidateQueries({ queryKey: ["omnichannel", "conversations"] });
    },
  });
}

export function useAddConversationTag(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (tagId: string) => omnichannelService.addConversationTag(conversationId, tagId),
    onSuccess: invalidate,
  });
}

export function useRemoveConversationTag(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (tagId: string) => omnichannelService.removeConversationTag(conversationId, tagId),
    onSuccess: invalidate,
  });
}

export function useAddNote(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: ({ text, mentions }: { text: string; mentions?: string[] }) => omnichannelService.addNote(conversationId, text, mentions),
    onSuccess: invalidate,
  });
}

export function useSendManualMessage(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (text: string) => omnichannelService.sendManualMessage(conversationId, text),
    onSuccess: invalidate,
  });
}

export function useGenerateDraft(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: () => omnichannelService.generateDraft(conversationId),
    onSuccess: invalidate,
  });
}

export function useSendBroadcast() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OmniBroadcastRequest) => omnichannelService.sendBroadcast(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["omnichannel", "conversations"] }),
  });
}

// Customers
export function useUpdateCustomer(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: ({ customerId, payload }: { customerId: string; payload: OmniCustomerUpdate }) => omnichannelService.updateCustomer(customerId, payload),
    onSuccess: invalidate,
  });
}

export function useBlockCustomer(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (customerId: string) => omnichannelService.blockCustomer(customerId),
    onSuccess: invalidate,
  });
}

export function useUnblockCustomer(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (customerId: string) => omnichannelService.unblockCustomer(customerId),
    onSuccess: invalidate,
  });
}

// Tags
export function useTags() {
  return useQuery({ queryKey: queryKeys.omnichannel.tags(), queryFn: omnichannelService.listTags });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OmniTagCreate) => omnichannelService.createTag(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.tags() }),
  });
}

// AI drafts
export function useEditDraft(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: ({ draftId, editedText }: { draftId: string; editedText: string }) => omnichannelService.editDraft(draftId, editedText),
    onSuccess: invalidate,
  });
}

export function useApproveDraft(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (draftId: string) => omnichannelService.approveDraft(draftId),
    onSuccess: invalidate,
  });
}

export function useRegenerateDraft(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (draftId: string) => omnichannelService.regenerateDraft(draftId),
    onSuccess: invalidate,
  });
}

export function useRejectDraft(conversationId: string) {
  const invalidate = useInvalidateConversation(conversationId);
  return useMutation({
    mutationFn: (draftId: string) => omnichannelService.rejectDraft(draftId),
    onSuccess: invalidate,
  });
}

// AI agent config
export function useAIAgentConfig() {
  return useQuery({ queryKey: queryKeys.omnichannel.aiAgent(), queryFn: omnichannelService.getAIAgentConfig });
}

export function useUpdateAIAgentConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OmniAIAgentConfigUpdate) => omnichannelService.updateAIAgentConfig(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.aiAgent() }),
  });
}

export function useCheckCrmKey() {
  return useMutation({ mutationFn: () => omnichannelService.checkCrmKey() });
}

// A richiesta (enabled=false finche' l'operatore non clicca): ogni lettura e'
// una chiamata al CRM e una riga di audit, non va fatta a ogni apertura.
export function useCustomerCrmProfile(customerId: string | null, channel: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.omnichannel.customerCrmProfile(customerId ?? "", channel),
    queryFn: () => omnichannelService.getCustomerCrmProfile(customerId ?? "", channel),
    enabled: enabled && !!customerId,
    staleTime: 60_000,
    retry: false,
  });
}

// Knowledge base
// Tutte le mutazioni invalidano anche le statistiche: la chiave delle stats sta
// sotto quella della lista, quindi basta invalidare il prefisso.
function useInvalidateKnowledge() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.knowledgeBase() });
}

export function useKnowledgeDocuments(params: OmniKnowledgeListParams = {}) {
  return useQuery({
    queryKey: queryKeys.omnichannel.knowledgeDocuments(params),
    queryFn: () => omnichannelService.listKnowledgeDocuments(params),
    placeholderData: keepPreviousData,
    // Gli embedding li calcola il worker qualche secondo dopo il salvataggio:
    // finche' ne manca qualcuno si ricontrolla, poi si smette.
    refetchInterval: (query) =>
      query.state.data?.some((doc) => doc.embedded_chunks < doc.chunk_count && !doc.error_message) ? 4000 : false,
  });
}

// Ricerca avanzata: parte solo con una ricerca confermata (Invio) di almeno
// 2 caratteri. Sta sotto la chiave della Knowledge Base, quindi caricare,
// spostare o eliminare un documento la aggiorna come l'elenco.
export function useFindKnowledgeDocuments(params: OmniKnowledgeFindParams) {
  const q = params.q?.trim() ?? "";
  return useQuery({
    queryKey: queryKeys.omnichannel.knowledgeFind({ ...params, q }),
    queryFn: () => omnichannelService.findKnowledgeDocuments({ ...params, q }),
    enabled: q.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useKnowledgeDocument(id: string | null) {
  return useQuery({
    queryKey: queryKeys.omnichannel.knowledgeDocument(id ?? ""),
    queryFn: () => omnichannelService.getKnowledgeDocument(id as string),
    enabled: !!id,
  });
}

export function useKnowledgeCompanies() {
  return useQuery({ queryKey: queryKeys.omnichannel.knowledgeCompanies(), queryFn: omnichannelService.listKnowledgeCompanies });
}

export function useCreateKnowledgeCompany() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: (payload: OmniKnowledgeCompanyCreate) => omnichannelService.createKnowledgeCompany(payload),
    onSuccess: invalidate,
  });
}

export function useUpdateKnowledgeCompany() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OmniKnowledgeCompanyUpdate }) => omnichannelService.updateKnowledgeCompany(id, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteKnowledgeCompany() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: ({ id, deleteDocuments }: { id: string; deleteDocuments: boolean }) => omnichannelService.deleteKnowledgeCompany(id, deleteDocuments),
    onSuccess: invalidate,
  });
}

export function useMoveKnowledgeDocuments() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: ({ ids, companyId }: { ids: string[]; companyId: string | null }) => omnichannelService.moveKnowledgeDocuments(ids, companyId),
    onSuccess: invalidate,
  });
}

export function useKnowledgeStats() {
  return useQuery({ queryKey: queryKeys.omnichannel.knowledgeStats(), queryFn: omnichannelService.getKnowledgeStats });
}

export function useCreateKnowledgeDocument() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: (payload: OmniKnowledgeDocumentCreate) => omnichannelService.createKnowledgeDocument(payload),
    onSuccess: invalidate,
  });
}

export function useUpdateKnowledgeDocument() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OmniKnowledgeDocumentUpdate }) => omnichannelService.updateKnowledgeDocument(id, payload),
    onSuccess: invalidate,
  });
}

export function useUploadKnowledgeFile() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: ({ file, companyId }: { file: File; companyId?: string | null }) => omnichannelService.uploadKnowledgeFile(file, companyId),
    onSettled: invalidate,
  });
}

export function useDeleteKnowledgeDocument() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.deleteKnowledgeDocument(id),
    onSuccess: invalidate,
  });
}

export function useReindexKnowledgeBase() {
  const invalidate = useInvalidateKnowledge();
  return useMutation({ mutationFn: omnichannelService.reindexKnowledgeBase, onSuccess: invalidate });
}

export function useSearchKnowledgeBase() {
  return useMutation({
    mutationFn: ({ query, generateReply, companyId }: { query: string; generateReply: boolean; companyId?: string | null }) =>
      omnichannelService.searchKnowledgeBase(query, generateReply, companyId),
  });
}

// Notifications
export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: queryKeys.omnichannel.notifications(unreadOnly),
    queryFn: () => omnichannelService.listNotifications(unreadOnly),
    refetchInterval: 15000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.markNotificationRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["omnichannel", "notifications"] }),
  });
}

// Analytics
export function useAnalytics() {
  return useQuery({ queryKey: queryKeys.omnichannel.analytics(), queryFn: omnichannelService.getAnalytics });
}

// Sidebar notification dot - polled app-wide (mounted in AppSidebar, present on every page)
export function usePendingCount() {
  return useQuery({
    queryKey: queryKeys.omnichannel.pendingCount(),
    queryFn: omnichannelService.getPendingCount,
    refetchInterval: 20000,
  });
}

// Dev simulate tool
export function useSimulateMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ channelAccountId, externalUserId, text, customerName }: { channelAccountId: string; externalUserId: string; text: string; customerName?: string }) =>
      omnichannelService.simulateMessage(channelAccountId, externalUserId, text, customerName),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["omnichannel", "conversations"] }),
  });
}
