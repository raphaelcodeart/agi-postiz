import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import type {
  OmniAIAgentConfigResponse,
  OmniAIAgentConfigUpdate,
  OmniAIDraftResponse,
  OmniAnalyticsResponse,
  OmniBroadcastRequest,
  OmniBroadcastResult,
  OmniChannelAccountCreate,
  OmniChannelAccountResponse,
  OmniChannelAccountUpdate,
  OmniConversationDetailResponse,
  OmniConversationListItem,
  OmniConversationStatus,
  OmniCustomerResponse,
  OmniCustomerUpdate,
  OmniInternalNoteResponse,
  OmniKnowledgeDocumentCreate,
  OmniKnowledgeDocumentResponse,
  OmniMessageResponse,
  OmniNotificationResponse,
  OmniTagCreate,
  OmniTagResponse,
} from "@/types/api";

const BASE = "/omnichannel-responder";

// Channel accounts
export function listChannelAccounts(): Promise<OmniChannelAccountResponse[]> {
  return apiClient.get<OmniChannelAccountResponse[]>(`${BASE}/channel-accounts`);
}

export function listSupportedChannels(): Promise<string[]> {
  return apiClient.get<string[]>(`${BASE}/channel-accounts/supported`);
}

export function createChannelAccount(payload: OmniChannelAccountCreate): Promise<OmniChannelAccountResponse> {
  return apiClient.post<OmniChannelAccountResponse>(`${BASE}/channel-accounts`, payload);
}

export function updateChannelAccount(id: string, payload: OmniChannelAccountUpdate): Promise<OmniChannelAccountResponse> {
  return apiClient.put<OmniChannelAccountResponse>(`${BASE}/channel-accounts/${id}`, payload);
}

export function toggleChannelAccount(id: string): Promise<OmniChannelAccountResponse> {
  return apiClient.post<OmniChannelAccountResponse>(`${BASE}/channel-accounts/${id}/toggle`);
}

export function getChannelAccountStatus(id: string): Promise<{ status: string; [key: string]: unknown }> {
  return apiClient.get(`${BASE}/channel-accounts/${id}/status`);
}

export function registerChannelWebhook(id: string, publicBaseUrl: string): Promise<{ webhook_url: string; status: string }> {
  return apiClient.post(`${BASE}/channel-accounts/${id}/register-webhook?public_base_url=${encodeURIComponent(publicBaseUrl)}`);
}

export function deleteChannelAccount(id: string): Promise<void> {
  return apiClient.delete(`${BASE}/channel-accounts/${id}`);
}

// Conversations
export interface ListConversationsParams {
  status?: OmniConversationStatus | "";
  channel?: string;
  channel_account_id?: string;
  search?: string;
  skip?: number;
  limit?: number;
}

export function listConversations(params: ListConversationsParams = {}): Promise<OmniConversationListItem[]> {
  return apiClient.get<OmniConversationListItem[]>(`${BASE}/conversations${buildQueryString(params)}`);
}

export function getConversationDetail(id: string): Promise<OmniConversationDetailResponse> {
  return apiClient.get<OmniConversationDetailResponse>(`${BASE}/conversations/${id}`);
}

export function assignConversation(id: string, assignedAdminId: string | null): Promise<OmniConversationDetailResponse> {
  return apiClient.post<OmniConversationDetailResponse>(`${BASE}/conversations/${id}/assign`, { assigned_admin_id: assignedAdminId });
}

export function resolveConversation(id: string): Promise<OmniConversationDetailResponse> {
  return apiClient.post<OmniConversationDetailResponse>(`${BASE}/conversations/${id}/resolve`);
}

export function archiveConversation(id: string): Promise<OmniConversationDetailResponse> {
  return apiClient.post<OmniConversationDetailResponse>(`${BASE}/conversations/${id}/archive`);
}

export function deleteConversation(id: string): Promise<void> {
  return apiClient.delete(`${BASE}/conversations/${id}`);
}

export function addConversationTag(conversationId: string, tagId: string): Promise<OmniConversationDetailResponse> {
  return apiClient.post<OmniConversationDetailResponse>(`${BASE}/conversations/${conversationId}/tags/${tagId}`);
}

export function removeConversationTag(conversationId: string, tagId: string): Promise<OmniConversationDetailResponse> {
  return apiClient.delete<OmniConversationDetailResponse>(`${BASE}/conversations/${conversationId}/tags/${tagId}`);
}

export function addNote(conversationId: string, text: string, mentions?: string[]): Promise<OmniInternalNoteResponse> {
  return apiClient.post<OmniInternalNoteResponse>(`${BASE}/conversations/${conversationId}/notes`, { text, mentions });
}

export function sendManualMessage(conversationId: string, text: string): Promise<OmniMessageResponse> {
  return apiClient.post<OmniMessageResponse>(`${BASE}/conversations/${conversationId}/messages`, { text });
}

export function generateDraft(conversationId: string): Promise<OmniAIDraftResponse> {
  return apiClient.post<OmniAIDraftResponse>(`${BASE}/conversations/${conversationId}/generate-draft`);
}

export function sendBroadcast(payload: OmniBroadcastRequest): Promise<OmniBroadcastResult> {
  return apiClient.post<OmniBroadcastResult>(`${BASE}/broadcast`, payload);
}

// Customers
export function updateCustomer(id: string, payload: OmniCustomerUpdate): Promise<OmniCustomerResponse> {
  return apiClient.patch<OmniCustomerResponse>(`${BASE}/customers/${id}`, payload);
}

export function blockCustomer(id: string): Promise<OmniCustomerResponse> {
  return apiClient.post<OmniCustomerResponse>(`${BASE}/customers/${id}/block`);
}

export function unblockCustomer(id: string): Promise<OmniCustomerResponse> {
  return apiClient.post<OmniCustomerResponse>(`${BASE}/customers/${id}/unblock`);
}

// Tags
export function listTags(): Promise<OmniTagResponse[]> {
  return apiClient.get<OmniTagResponse[]>(`${BASE}/tags`);
}

export function createTag(payload: OmniTagCreate): Promise<OmniTagResponse> {
  return apiClient.post<OmniTagResponse>(`${BASE}/tags`, payload);
}

// AI drafts
export function editDraft(id: string, editedText: string): Promise<OmniAIDraftResponse> {
  return apiClient.patch<OmniAIDraftResponse>(`${BASE}/drafts/${id}`, { edited_text: editedText });
}

export function approveDraft(id: string): Promise<OmniAIDraftResponse> {
  return apiClient.post<OmniAIDraftResponse>(`${BASE}/drafts/${id}/approve`);
}

export function regenerateDraft(id: string): Promise<OmniAIDraftResponse> {
  return apiClient.post<OmniAIDraftResponse>(`${BASE}/drafts/${id}/regenerate`);
}

export function rejectDraft(id: string): Promise<OmniAIDraftResponse> {
  return apiClient.post<OmniAIDraftResponse>(`${BASE}/drafts/${id}/reject`);
}

// AI agent config
export function getAIAgentConfig(): Promise<OmniAIAgentConfigResponse> {
  return apiClient.get<OmniAIAgentConfigResponse>(`${BASE}/ai-agent`);
}

export function updateAIAgentConfig(payload: OmniAIAgentConfigUpdate): Promise<OmniAIAgentConfigResponse> {
  return apiClient.put<OmniAIAgentConfigResponse>(`${BASE}/ai-agent`, payload);
}

// Knowledge base
export function listKnowledgeDocuments(): Promise<OmniKnowledgeDocumentResponse[]> {
  return apiClient.get<OmniKnowledgeDocumentResponse[]>(`${BASE}/knowledge-base`);
}

export function createKnowledgeDocument(payload: OmniKnowledgeDocumentCreate): Promise<OmniKnowledgeDocumentResponse> {
  return apiClient.post<OmniKnowledgeDocumentResponse>(`${BASE}/knowledge-base`, payload);
}

export function deleteKnowledgeDocument(id: string): Promise<void> {
  return apiClient.delete(`${BASE}/knowledge-base/${id}`);
}

// Notifications
export function listNotifications(unreadOnly = false): Promise<OmniNotificationResponse[]> {
  return apiClient.get<OmniNotificationResponse[]>(`${BASE}/notifications${buildQueryString({ unread_only: unreadOnly })}`);
}

export function markNotificationRead(id: string): Promise<OmniNotificationResponse> {
  return apiClient.post<OmniNotificationResponse>(`${BASE}/notifications/${id}/read`);
}

// Analytics
export function getAnalytics(): Promise<OmniAnalyticsResponse> {
  return apiClient.get<OmniAnalyticsResponse>(`${BASE}/analytics`);
}

// Sidebar notification dot - conversations needing attention (draft to approve or unread)
export function getPendingCount(): Promise<{ count: number }> {
  return apiClient.get<{ count: number }>(`${BASE}/conversations/pending-count`);
}

// Dev tool - only works against 'mock' channel accounts (see backend)
export function simulateMessage(channelAccountId: string, externalUserId: string, text: string, customerName?: string): Promise<OmniMessageResponse> {
  return apiClient.post<OmniMessageResponse>(`${BASE}/dev/simulate-message`, {
    channel_account_id: channelAccountId,
    external_user_id: externalUserId,
    text,
    customer_name: customerName,
  });
}
