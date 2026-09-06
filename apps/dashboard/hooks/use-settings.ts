"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as settingsService from "@/services/settings";
import { queryKeys } from "@/lib/query/keys";
import type { AISettingsUpdatePayload, SystemSettingsUpdatePayload } from "@/types/api";

export function useSystemSettings() {
  return useQuery({
    queryKey: queryKeys.settings.detail(),
    queryFn: settingsService.getSettings,
  });
}

export function useUpdateSystemSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SystemSettingsUpdatePayload) => settingsService.updateSettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.detail() });
    },
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.settings.health(),
    queryFn: settingsService.getHealth,
    refetchInterval: 30_000,
  });
}

export function useAISettings() {
  return useQuery({
    queryKey: queryKeys.settings.ai(),
    queryFn: settingsService.getAISettings,
  });
}

export function useUpdateAISettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AISettingsUpdatePayload) => settingsService.updateAISettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.ai() });
    },
  });
}

export function useDeleteAISettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => settingsService.deleteAISettings(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.ai() });
    },
  });
}
