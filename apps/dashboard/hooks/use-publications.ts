"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as publicationsService from "@/services/publications";
import { queryKeys } from "@/lib/query/keys";
import { isUnresolvedPublicationStatus } from "@/lib/campaign-stats";
import type { ListPublicationFeedParams, ListPublicationsParams } from "@/services/publications";
import type { ChannelMetrics } from "@/types/api";

export function usePublications(params: ListPublicationsParams = {}) {
  return useQuery({
    queryKey: queryKeys.publications.list(params),
    queryFn: () => publicationsService.listPublications(params),
    placeholderData: (previousData) => previousData,
  });
}

export function usePublicationsSummary() {
  return useQuery({
    queryKey: queryKeys.publications.summary(),
    queryFn: publicationsService.getPublicationsSummary,
  });
}

// "Bacheca" feed - kept as its own hook (not reusing usePublications) since it
// hits a different, pre-joined endpoint (GET /publications/feed) rather than
// the raw publication rows the Publications table view uses.
export function usePublicationFeed(params: ListPublicationFeedParams = {}) {
  return useQuery({
    queryKey: queryKeys.publications.feed(params),
    queryFn: () => publicationsService.listPublicationFeed(params),
    placeholderData: (previousData) => previousData,
  });
}

export function usePublicationDetail(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.publications.detail(id ?? ""),
    queryFn: () => publicationsService.getPublication(id as string),
    enabled: !!id,
    // Same reasoning as the campaigns list/detail pages (lib/campaign-stats.ts):
    // a manual retry only flips the status to "pending" synchronously, the
    // real outcome lands later via a Celery task - keep polling until it does.
    refetchInterval: (query) => {
      const status = query.state.data?.publication.status;
      return !status || isUnresolvedPublicationStatus(status) ? 5000 : false;
    },
  });
}

// On-demand only (never polled), same reasoning as useCampaignMetrics: Buffer
// refreshes post metrics once a day, so the admin explicitly asks via a button.
export function usePublicationMetrics(id: string) {
  return useQuery<ChannelMetrics>({
    queryKey: queryKeys.publications.metrics(id),
    queryFn: () => publicationsService.getPublicationMetrics(id),
    enabled: false,
    retry: false,
  });
}

// `ids` invalidates the specific publication.detail queries too (not just
// the list) - without this, a publication detail page open on the exact
// item being retried/cancelled/skipped never refetches at all, since its
// query key ("publications", "detail", id) isn't a prefix match of
// ("publications", "list").
function invalidatePublications(queryClient: ReturnType<typeof useQueryClient>, ids?: string | string[]) {
  queryClient.invalidateQueries({ queryKey: ["publications", "list"] });
  queryClient.invalidateQueries({ queryKey: ["campaigns"] });
  queryClient.invalidateQueries({ queryKey: queryKeys.publications.summary() });
  queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.summary() });
  const idList = ids ? (Array.isArray(ids) ? ids : [ids]) : [];
  idList.forEach((id) => queryClient.invalidateQueries({ queryKey: queryKeys.publications.detail(id) }));
}

export function useRetryPublication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => publicationsService.retryPublication(id),
    onSuccess: (_data, id) => invalidatePublications(queryClient, id),
  });
}

export function useRetrySelectedPublications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => publicationsService.retrySelectedPublications(ids),
    onSuccess: (_data, ids) => invalidatePublications(queryClient, ids),
  });
}

export function useRetryCampaignFailures() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (campaignId: string) => publicationsService.retryCampaignFailures(campaignId),
    onSuccess: () => invalidatePublications(queryClient),
  });
}

export function useCancelPublication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => publicationsService.cancelPublication(id),
    onSuccess: (_data, id) => invalidatePublications(queryClient, id),
  });
}

export function useSkipPublication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => publicationsService.skipPublication(id),
    onSuccess: (_data, id) => invalidatePublications(queryClient, id),
  });
}
