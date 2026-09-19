import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import type {
  CampaignProposalResponse,
  CampaignProposalStatus,
  StatusCountsSummaryResponse,
} from "@/types/api";

/**
 * Proposte di campagna scritte dai promoter, lato amministratore.
 *
 * Non c'è un `approveProposal`: approvare significa creare la campagna, e la
 * crea `createCampaign` passando `proposal_id` (vedi
 * apps/api/app/api/v1/campaign_proposals.py per il perché le due cose sono una
 * sola operazione).
 */
export function listCampaignProposals(
  params: { status?: CampaignProposalStatus } = {}
): Promise<CampaignProposalResponse[]> {
  return apiClient.get<CampaignProposalResponse[]>(`/campaign-proposals/${buildQueryString(params)}`);
}

export function getCampaignProposalsSummary(): Promise<StatusCountsSummaryResponse> {
  return apiClient.get<StatusCountsSummaryResponse>("/campaign-proposals/summary");
}

export function getCampaignProposal(id: string): Promise<CampaignProposalResponse> {
  return apiClient.get<CampaignProposalResponse>(`/campaign-proposals/${id}`);
}

export function rejectCampaignProposal(
  id: string,
  reviewNotes: string
): Promise<CampaignProposalResponse> {
  return apiClient.post<CampaignProposalResponse>(`/campaign-proposals/${id}/reject`, {
    review_notes: reviewNotes,
  });
}
