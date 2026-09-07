"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as authService from "@/services/auth";
import { queryKeys } from "@/lib/query/keys";

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: authService.getMe,
    retry: false,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authService.login(email, password),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authService.logout,
    onSuccess: () => {
      queryClient.clear();
      // Hard navigation, not router.push + router.refresh.
      //
      // The refresh issues an RSC request for the page being left, and the
      // session cookie is already gone by then, so the route guard answers with
      // a 307 to /login. The client router cannot read a bare redirect as an RSC
      // payload: it throws, and the global error boundary shows "si è verificato
      // un errore imprevisto" - on a logout that actually succeeded.
      //
      // A full page load sidesteps the RSC round trip entirely and leaves no
      // client cache or in-flight query behind, which is what you want after
      // signing out anyway.
      window.location.href = "/login";
    },
  });
}
