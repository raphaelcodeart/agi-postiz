"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as myagiService from "@/services/myagi";
import * as omnichannelService from "@/services/omnichannel";
import { queryKeys } from "@/lib/query/keys";

export function useMyAgiGatewayStatus() {
  return useQuery({ queryKey: queryKeys.myagi.status(), queryFn: myagiService.getGatewayStatus, staleTime: 30_000 });
}

// Lo stato della sessione cambia da solo (il telefono si collega, la sessione
// cade): si rilegge a intervalli, piu' fitti quando c'e' un QR da scansionare.
export function useMyAgiSessions(fast: boolean) {
  return useQuery({
    queryKey: queryKeys.myagi.sessions(),
    queryFn: myagiService.listSessions,
    refetchInterval: fast ? 5_000 : 20_000,
  });
}

function useInvalidateMyAgi() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.myagi.sessions() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.omnichannel.channelAccounts() });
  };
}

export function useCreateMyAgiSession() {
  const invalidate = useInvalidateMyAgi();
  return useMutation({ mutationFn: (name: string) => myagiService.createSession(name), onSuccess: invalidate });
}

export function useStartMyAgiSession() {
  const invalidate = useInvalidateMyAgi();
  return useMutation({ mutationFn: (accountId: string) => myagiService.startSession(accountId), onSuccess: invalidate });
}

export function useRestartMyAgiSession() {
  const invalidate = useInvalidateMyAgi();
  return useMutation({ mutationFn: (accountId: string) => myagiService.restartSession(accountId), onSuccess: invalidate });
}

export function useLogoutMyAgiSession() {
  const invalidate = useInvalidateMyAgi();
  return useMutation({ mutationFn: (accountId: string) => myagiService.logoutSession(accountId), onSuccess: invalidate });
}

// Eliminare un numero = eliminare il canale Omnichannel: il backend toglie
// anche la sessione dal gateway (DELETE /channel-accounts/{id}).
export function useDeleteMyAgiSession() {
  const invalidate = useInvalidateMyAgi();
  return useMutation({ mutationFn: (accountId: string) => omnichannelService.deleteChannelAccount(accountId), onSuccess: invalidate });
}

// Il QR cambia ogni ~20 secondi: finche' lo stato e' SCAN_QR_CODE lo si
// richiede ogni 10, poi si smette (enabled=false).
export function useMyAgiQr(accountId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.myagi.qr(accountId ?? ""),
    queryFn: () => myagiService.getSessionQr(accountId ?? ""),
    enabled: enabled && !!accountId,
    refetchInterval: enabled ? 10_000 : false,
    retry: false,
  });
}
