"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as omnichannelService from "@/services/omnichannel";
import { queryKeys } from "@/lib/query/keys";
import type { ListConversationsParams } from "@/services/omnichannel";
import type { OmniAIAgentConfigUpdate, OmniBroadcastRequest, OmniChannelAccountCreate, OmniChannelAccountUpdate, OmniCustomerUpdate, OmniKnowledgeDocumentCreate, OmniTagCreate } from "@/types/api";

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

// Knowledge base
export function useKnowledgeDocuments() {
  return useQuery({ queryKey: queryKeys.omnichannel.knowledgeBase(), queryFn: omnichannelService.listKnowledgeDocuments });
}

export function useCreateKnowledgeDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OmniKnowledgeDocumentCreate) => omnichannelService.createKnowledgeDocument(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.knowledgeBase() }),
  });
}

export function useDeleteKnowledgeDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => omnichannelService.deleteKnowledgeDocument(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.knowledgeBase() }),
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
