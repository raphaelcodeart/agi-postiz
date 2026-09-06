import { apiClient } from "@/lib/api/client";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type { AIGenerateTextResponse } from "@/types/api";

export function generateCampaignText(
  topic: string,
  includeReferralLink: boolean,
  includePersonalContacts: boolean
): Promise<AIGenerateTextResponse> {
  if (isMockApiEnabled()) return mock.generateCampaignText(topic);
  return apiClient.post<AIGenerateTextResponse>("/ai/generate-campaign-text", {
    topic,
    include_referral_link: includeReferralLink,
    include_personal_contacts: includePersonalContacts,
  });
}
