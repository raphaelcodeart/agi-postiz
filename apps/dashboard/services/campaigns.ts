import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type {
  CampaignCreatePayload,
  CampaignDetailResponse,
  CampaignMetricsResponse,
  CampaignPreviewResponse,
  CampaignResponse,
  CampaignStatus,
  StatusCountsSummaryResponse,
} from "@/types/api";

export interface ListCampaignsParams {
  skip?: number;
  limit?: number;
  status_filter?: CampaignStatus | "";
}

export function getCampaignsSummary(): Promise<StatusCountsSummaryResponse> {
  if (isMockApiEnabled()) return mock.getCampaignsSummary();
  return apiClient.get<StatusCountsSummaryResponse>("/campaigns/summary");
}

export function listCampaigns(params: ListCampaignsParams = {}): Promise<CampaignResponse[]> {
  if (isMockApiEnabled()) return mock.listCampaigns(params);
  return apiClient.get<CampaignResponse[]>(`/campaigns/${buildQueryString(params)}`);
}

export function createCampaign(payload: CampaignCreatePayload): Promise<CampaignResponse> {
  if (isMockApiEnabled()) return mock.createCampaign(payload);
  return apiClient.post<CampaignResponse>("/campaigns/", payload);
}

export function previewCampaignTargets(
  payload: CampaignCreatePayload
): Promise<CampaignPreviewResponse> {
  if (isMockApiEnabled()) return mock.previewCampaignTargets();
  return apiClient.post<CampaignPreviewResponse>("/campaigns/preview-targets", payload);
}

export function launchCampaign(
  campaignId: string,
  targetingParams: Record<string, unknown>,
  channelOverrides?: Record<string, string>
): Promise<CampaignResponse> {
  if (isMockApiEnabled()) return mock.launchCampaign(campaignId);
  // FastAPI declares targeting_params and channel_overrides as two separate
  // body parameters, so the JSON body must nest them under their param names.
  return apiClient.post<CampaignResponse>(`/campaigns/${campaignId}/launch`, {
    targeting_params: targetingParams,
    channel_overrides: channelOverrides ?? null,
  });
}

export function getCampaignDetail(campaignId: string): Promise<CampaignDetailResponse> {
  if (isMockApiEnabled()) return mock.getCampaignDetail(campaignId);
  return apiClient.get<CampaignDetailResponse>(`/campaigns/${campaignId}`);
}

export function getCampaignMetrics(campaignId: string): Promise<CampaignMetricsResponse> {
  if (isMockApiEnabled()) return mock.getCampaignMetrics(campaignId);
  return apiClient.get<CampaignMetricsResponse>(`/campaigns/${campaignId}/metrics`);
}

export function pauseCampaign(campaignId: string): Promise<CampaignResponse> {
  if (isMockApiEnabled()) return mock.pauseCampaign(campaignId);
  return apiClient.post<CampaignResponse>(`/campaigns/${campaignId}/pause`);
}

export function resumeCampaign(campaignId: string): Promise<CampaignResponse> {
  if (isMockApiEnabled()) return mock.resumeCampaign(campaignId);
  return apiClient.post<CampaignResponse>(`/campaigns/${campaignId}/resume`);
}

export function cancelCampaign(campaignId: string): Promise<CampaignResponse> {
  if (isMockApiEnabled()) return mock.cancelCampaign(campaignId);
  return apiClient.post<CampaignResponse>(`/campaigns/${campaignId}/cancel`);
}

export function deleteCampaign(campaignId: string): Promise<void> {
  if (isMockApiEnabled()) return mock.deleteCampaign(campaignId);
  return apiClient.delete<void>(`/campaigns/${campaignId}`);
}
