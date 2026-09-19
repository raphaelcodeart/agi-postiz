/**
 * I social che un promoter puo' indicare in una proposta, nell'ordine in cui
 * compaiono nel modulo. Stessa lista di CampaignProposal.PLATFORMS nel backend
 * e stessi nomi di SocialChannel.platform: il wizard li passa tali e quali a
 * targeting_params.platform_names.
 */
export const PROPOSAL_PLATFORMS = [
  "instagram",
  "facebook",
  "tiktok",
  "youtube",
  "linkedin",
  "twitter",
  "threads",
] as const;
