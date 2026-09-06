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

  // The hosted flow finishes on the provider's site, so returning here is the
  // only signal that a channel may now exist. Without this the user comes back
  // to a page that looks exactly as they left it.
  useEffect(() => {
    if (searchParams.get("connected") === "1") {
      void sync(true);
      router.replace("/portal/channels");
    }
  }, [searchParams, sync, router]);

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
        // The provider hosts the OAuth UI; leaving the app is the flow, not a
        // failure of it.
        window.location.href = payload.url;
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
