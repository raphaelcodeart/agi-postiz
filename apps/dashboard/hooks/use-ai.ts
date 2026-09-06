"use client";

import { useMutation } from "@tanstack/react-query";
import * as aiService from "@/services/ai";

export function useGenerateCampaignText() {
  return useMutation({
    mutationFn: ({
      topic,
      includeReferralLink,
      includePersonalContacts,
    }: {
      topic: string;
      includeReferralLink: boolean;
      includePersonalContacts: boolean;
    }) => aiService.generateCampaignText(topic, includeReferralLink, includePersonalContacts),
  });
}
