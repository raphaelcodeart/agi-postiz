import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as proposalsService from "@/services/campaign-proposals";
import { queryKeys } from "@/lib/query/keys";
import type { CampaignProposalStatus } from "@/types/api";

export function useCampaignProposals(params: { status?: CampaignProposalStatus } = {}) {
  return useQuery({
    queryKey: queryKeys.campaignProposals.list(params),
    queryFn: () => proposalsService.listCampaignProposals(params),
  });
}

export function useCampaignProposalsSummary() {
  return useQuery({
    queryKey: queryKeys.campaignProposals.summary(),
    queryFn: () => proposalsService.getCampaignProposalsSummary(),
  });
}

export function useCampaignProposal(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.campaignProposals.detail(id ?? ""),
    queryFn: () => proposalsService.getCampaignProposal(id as string),
    enabled: Boolean(id),
  });
}

export function useRejectCampaignProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reviewNotes }: { id: string; reviewNotes: string }) =>
      proposalsService.rejectCampaignProposal(id, reviewNotes),
    // Invalida tutto il gruppo: la lista cambia, e cambia anche il contatore
    // accanto alla voce di menu.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["campaignProposals"] }),
  });
}
