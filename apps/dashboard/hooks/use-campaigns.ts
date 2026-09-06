"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import * as campaignsService from "@/services/campaigns";
import { queryKeys } from "@/lib/query/keys";
import type { ListCampaignsParams } from "@/services/campaigns";
import type { CampaignCreatePayload, CampaignDetailResponse, CampaignMetricsResponse } from "@/types/api";

export function useCampaigns(params: ListCampaignsParams = {}) {
  return useQuery({
    queryKey: queryKeys.campaigns.list(params),
    queryFn: () => campaignsService.listCampaigns(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useCampaignsSummary() {
  return useQuery({
    queryKey: queryKeys.campaigns.summary(),
    queryFn: campaignsService.getCampaignsSummary,
  });
}

export function useCampaignDetail(
  id: string | undefined,
  options?: { refetchInterval?: UseQueryOptions<CampaignDetailResponse>["refetchInterval"] }
) {
  return useQuery({
    queryKey: queryKeys.campaigns.detail(id ?? ""),
    queryFn: () => campaignsService.getCampaignDetail(id as string),
    enabled: !!id,
    refetchInterval: options?.refetchInterval,
  });
}

// On-demand only (never polled): Buffer refreshes post metrics once a day, so
// there's no point re-fetching automatically like the rest of the campaign
// detail page does. The admin explicitly asks for it via a button.
export function useCampaignMetrics(campaignId: string) {
  return useQuery<CampaignMetricsResponse>({
    queryKey: queryKeys.campaigns.metrics(campaignId),
    queryFn: () => campaignsService.getCampaignMetrics(campaignId),
    enabled: false,
    retry: false,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CampaignCreatePayload) => campaignsService.createCampaign(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.summary() });
    },
  });
}

export function usePreviewCampaignTargets() {
  return useMutation({
    mutationFn: (payload: CampaignCreatePayload) => campaignsService.previewCampaignTargets(payload),
  });
}

export function useLaunchCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      campaignId,
      targetingParams,
      channelOverrides,
    }: {
      campaignId: string;
      targetingParams: Record<string, unknown>;
      channelOverrides?: Record<string, string>;
    }) => campaignsService.launchCampaign(campaignId, targetingParams, channelOverrides),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.detail(variables.campaignId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.summary() });
      queryClient.invalidateQueries({ queryKey: queryKeys.publications.summary() });
    },
  });
}

function useCampaignAction(
  mutationFn: (campaignId: string) => Promise<unknown>,
  campaignId: string
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => mutationFn(campaignId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.detail(campaignId) });
      queryClient.invalidateQueries({ queryKey: ["publications", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.summary() });
      queryClient.invalidateQueries({ queryKey: queryKeys.publications.summary() });
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: string) => campaignsService.deleteCampaign(campaignId),
    onSuccess: (_data, campaignId) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns", "list"] });
      queryClient.removeQueries({ queryKey: queryKeys.campaigns.detail(campaignId) });
      queryClient.invalidateQueries({ queryKey: ["publications", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.summary() });
      queryClient.invalidateQueries({ queryKey: queryKeys.publications.summary() });
    },
  });
}

export function usePauseCampaign(campaignId: string) {
  return useCampaignAction(campaignsService.pauseCampaign, campaignId);
}

export function useResumeCampaign(campaignId: string) {
  return useCampaignAction(campaignsService.resumeCampaign, campaignId);
}

export function useCancelCampaign(campaignId: string) {
  return useCampaignAction(campaignsService.cancelCampaign, campaignId);
}
