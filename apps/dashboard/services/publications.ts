import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type {
  ChannelMetrics,
  PublicationDetailResponse,
  PublicationFeedItem,
  PublicationResponse,
  PublicationStatus,
  StatusCountsSummaryResponse,
} from "@/types/api";

export interface ListPublicationsParams {
  campaign_id?: string;
  status_filter?: PublicationStatus | "";
  skip?: number;
  limit?: number;
}

export function listPublications(params: ListPublicationsParams = {}): Promise<PublicationResponse[]> {
  if (isMockApiEnabled()) return mock.listPublications(params);
  return apiClient.get<PublicationResponse[]>(`/publications/${buildQueryString(params)}`);
}

export function getPublicationsSummary(): Promise<StatusCountsSummaryResponse> {
  if (isMockApiEnabled()) return mock.getPublicationsSummary();
  return apiClient.get<StatusCountsSummaryResponse>("/publications/summary");
}

export interface ListPublicationFeedParams {
  skip?: number;
  limit?: number;
}

// "Bacheca" - everything actually published, most recent first, with
// text/media/channel already joined server-side (GET /publications/feed).
export function listPublicationFeed(params: ListPublicationFeedParams = {}): Promise<PublicationFeedItem[]> {
  if (isMockApiEnabled()) return mock.listPublicationFeed(params);
  return apiClient.get<PublicationFeedItem[]>(`/publications/feed${buildQueryString(params)}`);
}

export function getPublication(id: string): Promise<PublicationDetailResponse> {
  if (isMockApiEnabled()) return mock.getPublication(id);
  return apiClient.get<PublicationDetailResponse>(`/publications/${id}`);
}

export function getPublicationMetrics(id: string): Promise<ChannelMetrics> {
  if (isMockApiEnabled()) return mock.getPublicationMetrics(id);
  return apiClient.get<ChannelMetrics>(`/publications/${id}/metrics`);
}

export function retryPublication(id: string): Promise<PublicationResponse> {
  if (isMockApiEnabled()) return mock.retryPublication(id);
  return apiClient.post<PublicationResponse>(`/publications/${id}/retry`);
}

export function retrySelectedPublications(ids: string[]): Promise<{ message: string }> {
  if (isMockApiEnabled()) return mock.retrySelectedPublications(ids);
  // Sole body parameter is a bare List[uuid.UUID] -> raw JSON array, not wrapped.
  return apiClient.post<{ message: string }>("/publications/retry-selected", ids);
}

export function retryCampaignFailures(campaignId: string): Promise<{ message: string }> {
  if (isMockApiEnabled()) return mock.retryCampaignFailures(campaignId);
  return apiClient.post<{ message: string }>(`/publications/retry-campaign-failures/${campaignId}`);
}

export function cancelPublication(id: string): Promise<PublicationResponse> {
  if (isMockApiEnabled()) return mock.cancelPublication(id);
  return apiClient.post<PublicationResponse>(`/publications/${id}/cancel`);
}

export function skipPublication(id: string): Promise<PublicationResponse> {
  if (isMockApiEnabled()) return mock.skipPublication(id);
  return apiClient.post<PublicationResponse>(`/publications/${id}/skip`);
}
