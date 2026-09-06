import { apiClient } from "@/lib/api/client";
import type {
  StatChannelDetailResponse,
  StatDashboardResponse,
  StatPostRow,
  StatSyncDispatchResponse,
  StatSyncRunResponse,
  StatUserDetailResponse,
} from "@/types/api";

export function getDashboard(): Promise<StatDashboardResponse> {
  return apiClient.get<StatDashboardResponse>("/statistics/dashboard");
}

export function getUserStatistics(userId: string): Promise<StatUserDetailResponse> {
  return apiClient.get<StatUserDetailResponse>(`/statistics/users/${userId}`);
}

export function getChannelStatistics(userId: string, channelId: string): Promise<StatChannelDetailResponse> {
  return apiClient.get<StatChannelDetailResponse>(`/statistics/users/${userId}/channels/${channelId}`);
}

export function syncUser(userId: string): Promise<StatSyncDispatchResponse> {
  return apiClient.post<StatSyncDispatchResponse>(`/statistics/sync/users/${userId}`);
}

export function syncCampaign(campaignId: string): Promise<StatSyncDispatchResponse> {
  return apiClient.post<StatSyncDispatchResponse>(`/statistics/sync/campaigns/${campaignId}`);
}

export function syncAll(): Promise<StatSyncDispatchResponse> {
  return apiClient.post<StatSyncDispatchResponse>("/statistics/sync/all");
}

export function getSyncRun(syncRunId: string): Promise<StatSyncRunResponse> {
  return apiClient.get<StatSyncRunResponse>(`/statistics/sync/${syncRunId}`);
}

export function syncSinglePost(publicationId: string): Promise<StatPostRow> {
  return apiClient.post<StatPostRow>(`/statistics/posts/${publicationId}/sync`);
}

// Gli export Excel non passano da apiClient: sono link <a> diretti verso il
// proxy BFF (stesso dominio, cookie di sessione httpOnly inviato automaticamente
// dal browser) cosi' il download parte come una normale navigazione, senza
// dover gestire il blob via JS - vedi app/api/backend/[...path]/route.ts.
export function dashboardExportUrl(): string {
  return "/api/backend/statistics/export/dashboard.xlsx";
}

export function userExportUrl(userId: string): string {
  return `/api/backend/statistics/export/users/${userId}.xlsx`;
}

export function channelExportUrl(userId: string, channelId: string): string {
  return `/api/backend/statistics/export/users/${userId}/channels/${channelId}.xlsx`;
}
