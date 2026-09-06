"use client";

import { useEffect } from "react";

/**
 * Landing page for the provider's redirect at the end of the hosted OAuth flow.
 *
 * It exists only to close the loop: the flow runs in a popup, so this page tells
 * the opener that something changed and closes itself. The user never really
 * reads it - if the popup was blocked and the flow ran in the same tab instead,
 * the fallback redirect below still gets them back to their channels.
 *
 * Deliberately in the (public) group: the popup is a fresh browsing context and
 * may not carry the session cookie on the way back, and bouncing the user to a
 * login screen at the very end of a successful authorisation would be absurd.
 */
export default function ConnectDonePage() {
  useEffect(() => {
    const opener = window.opener;
    if (opener && !opener.closed) {
      opener.postMessage({ source: "agipost", type: "channel-connected" }, window.location.origin);
      window.close();
      return;
    }
    // No opener: the popup was blocked and this ran in the main tab.
    window.location.replace("/portal/channels?connected=1");
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <p className="text-sm text-muted-foreground">Collegamento completato, puoi chiudere questa finestra.</p>
    </div>
  );
}
