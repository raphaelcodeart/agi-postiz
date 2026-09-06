import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type { PublicationMode, SocialChannelResponse } from "@/types/api";

export interface ListChannelsParams {
  user_id?: string;
  platform?: string;
  publication_mode?: PublicationMode | "";
}

export function listChannels(params: ListChannelsParams = {}): Promise<SocialChannelResponse[]> {
  if (isMockApiEnabled()) return mock.listChannels(params);
  return apiClient.get<SocialChannelResponse[]>(`/buffer/channels${buildQueryString(params)}`);
}

export function updateChannelMode(
  channelId: string,
  mode: PublicationMode
): Promise<SocialChannelResponse> {
  if (isMockApiEnabled()) return mock.updateChannelMode(channelId, mode);
  return apiClient.put<SocialChannelResponse>(
    `/buffer/channels/${channelId}/publication-mode?mode=${mode}`
  );
}
