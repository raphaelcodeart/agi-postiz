"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2Icon, RefreshCwIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";

/**
 * Kicks off the hosted connect flow: the backend returns a URL, the user opens
 * it, authorises on the social network itself, and comes back with the channel
 * attached to their account.
 *
 * The provider integration is not live yet, so the backend answers 501 with an
 * explanation. That message is shown as-is rather than hidden behind a generic
 * failure: "not available yet" and "something broke" call for different
 * reactions from the person reading it.
 */
const PLATFORMS = [
  { id: "instagram", label: "Instagram" },
  { id: "facebook", label: "Facebook" },
  { id: "tiktok", label: "TikTok" },
  { id: "youtube", label: "YouTube" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "x", label: "X" },
  { id: "threads", label: "Threads" },
  { id: "pinterest", label: "Pinterest" },
];

export function ConnectChannelPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pendingPlatform, setPendingPlatform] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const sync = useCallback(
    async (silent: boolean) => {
      setSyncing(true);
      try {
        const response = await fetch("/api/portal/backend/connect/sync", { method: "POST" });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          setMessage(payload?.detail ?? "Aggiornamento non riuscito.");
          return;
        }
        // Silent on the automatic pass: the freshly imported channel appearing
        // in the list below is the confirmation, a banner on top of it is noise.
        if (!silent || payload?.channels === 0) {
          setMessage(payload?.message ?? null);
        }
        router.refresh();
      } catch {
        setMessage("Servizio non raggiungibile. Riprova fra poco.");
      } finally {
        setSyncing(false);
      }
    },
    [router]
  );

  // Same-tab fallback: the popup was blocked, so the flow navigated away and
  // came back with the marker.
  useEffect(() => {
    if (searchParams.get("connected") === "1") {
      void sync(true);
      router.replace("/portal/channels");
    }
  }, [searchParams, sync, router]);

  // Popup path: the callback page posts a message before closing itself. The
  // origin check matters - without it any site could open a window onto this
  // page and drive a sync.
  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.source !== "agipost" || event.data?.type !== "channel-connected") return;
      setMessage(null);
      void sync(true);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [sync]);

  async function connect(platform: string) {
    setMessage(null);
    setPendingPlatform(platform);
    try {
      const response = await fetch("/api/portal/backend/connect/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform }),
      });
      const payload = await response.json().catch(() => null);

      if (response.ok && payload?.url) {
        // Opened in a popup rather than by navigating away: the user keeps our
        // page behind the window and comes back to it, instead of leaving the
        // site and returning through a redirect. A full iframe is not an option
        // - the social networks send X-Frame-Options on their login pages
        // precisely to stop anyone embedding them - so a popup is as integrated
        // as this step can be. It is the same shape as "Sign in with Google".
        const popup = window.open(
          payload.url,
          "agipost-connect",
          "width=620,height=760,menubar=no,toolbar=no,location=no,status=no"
        );

        if (!popup) {
          // Popup blocked: fall back to navigating, which still works - the
          // callback page redirects back with ?connected=1.
          window.location.href = payload.url;
          return;
        }

        setMessage("Completa l'autorizzazione nella finestra che si è aperta.");
        return;
      }

      setMessage(payload?.detail ?? "Collegamento non riuscito. Riprova fra poco.");
    } catch {
      setMessage("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPendingPlatform(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5">
          <CardTitle className="text-base">Collega un canale</CardTitle>
          <CardDescription>
            Scegli la piattaforma: ti portiamo sul sito del social per autorizzare, poi torni qui.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => sync(false)} disabled={syncing}>
          {syncing ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <RefreshCwIcon className="size-4" />
          )}
          Aggiorna
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {message && (
          <Alert>
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PLATFORMS.map((platform) => (
            <Button
              key={platform.id}
              variant="outline"
              className="h-auto justify-start gap-2 py-3"
              disabled={pendingPlatform !== null}
              onClick={() => connect(platform.id)}
            >
              {pendingPlatform === platform.id ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <PlatformIcon platform={platform.id} className="size-6" />
              )}
              <span className="truncate">{platform.label}</span>
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
