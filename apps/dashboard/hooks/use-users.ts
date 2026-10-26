"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as usersService from "@/services/users";
import { queryKeys } from "@/lib/query/keys";
import type { ChannelRequirementParams, ListUsersParams, UserPayload } from "@/services/users";
import type { ChannelRequirementBulkRequest } from "@/types/api";

export function useUsers(params: ListUsersParams = {}) {
  return useQuery({
    queryKey: queryKeys.users.list(params),
    queryFn: () => usersService.listUsers(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useUser(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.users.detail(id ?? ""),
    queryFn: () => usersService.getUser(id as string),
    enabled: !!id,
  });
}

export function useUsersSummary() {
  return useQuery({
    queryKey: queryKeys.users.summary(),
    queryFn: usersService.getUsersSummary,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserPayload) => usersService.createUser(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.summary() });
    },
  });
}

export function useUpdateUser(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<UserPayload>) => usersService.updateUser(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.summary() });
    },
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => usersService.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users", "list"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.summary() });
    },
  });
}

export function useGroups() {
  return useQuery({
    queryKey: queryKeys.groups.list(),
    queryFn: usersService.listGroups,
  });
}

export function useGroupUsers(groupId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.groups.users(groupId ?? ""),
    queryFn: () => usersService.listGroupUsers(groupId as string),
    enabled: !!groupId,
  });
}

export function useCreateGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersService.createGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.groups.list() });
    },
  });
}

export function useUpdateGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, payload }: { groupId: string; payload: usersService.GroupPayload }) =>
      usersService.updateGroup(groupId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.groups.list() });
    },
  });
}

// --- Requisito canali social -------------------------------------------------

export function useChannelRequirement(params: ChannelRequirementParams = {}) {
  return useQuery({
    queryKey: queryKeys.users.channelRequirement(params),
    queryFn: () => usersService.getChannelRequirement(params),
    placeholderData: (previousData) => previousData,
  });
}

function useInvalidateChannelRequirement() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["users", "channel-requirement"] });
    queryClient.invalidateQueries({ queryKey: queryKeys.users.summary() });
  };
}

export function useNotifyChannelRequirement() {
  const invalidate = useInvalidateChannelRequirement();
  return useMutation({
    mutationFn: (userId: string) => usersService.notifyChannelRequirement(userId),
    onSuccess: invalidate,
  });
}

export function useNotifyAllChannelRequirement() {
  const invalidate = useInvalidateChannelRequirement();
  return useMutation({
    mutationFn: (payload: ChannelRequirementBulkRequest) => usersService.notifyAllChannelRequirement(payload),
    onSuccess: invalidate,
  });
}
