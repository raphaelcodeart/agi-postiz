"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as channelsService from "@/services/channels";
import { queryKeys } from "@/lib/query/keys";
import type { ListChannelsParams } from "@/services/channels";
import type { PublicationMode } from "@/types/api";

export function useChannels(params: ListChannelsParams = {}) {
  return useQuery({
    queryKey: queryKeys.channels.list(params),
    queryFn: () => channelsService.listChannels(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useUpdateChannelMode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ channelId, mode }: { channelId: string; mode: PublicationMode }) =>
      channelsService.updateChannelMode(channelId, mode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channels", "list"] });
    },
  });
}
