"use client";

import { useEffect, useState } from "react";
import { CheckCircle2Icon } from "lucide-react";

/**
 * Where the provider sends the user at the end of the hosted OAuth flow.
 *
 * The popup version of this page must END here - it notifies the opener and
 * closes. It must NOT navigate onward to the dashboard: doing so loads the whole
 * portal a second time inside a 620px popup, which is what the "back" button in
 * the provider's UI produced before.
 *
 * window.close() is not guaranteed - browsers refuse it for windows the script
 * did not open, and the chain of cross-origin redirects can break that
 * relationship - so a short confirmation is rendered as the fallback rather than
 * a redirect. Only a page with no opener at all (popup blocked, flow ran in the
 * main tab) goes back to the channels list.
 */
export default function ConnectDonePage() {
  const [standalone, setStandalone] = useState(false);

  useEffect(() => {
    const hasOpener = Boolean(window.opener) && !window.opener.closed;

    if (!hasOpener) {
      // Ran in the main tab: continue the journey where the user expects it.
      window.location.replace("/portal/channels?connected=1");
      return;
    }

    window.opener.postMessage(
      { source: "agipost", type: "channel-connected" },
      window.location.origin
    );

    window.close();
    // If the browser refused to close it, say so instead of leaving a blank page.
    const timer = setTimeout(() => setStandalone(true), 400);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="flex max-w-xs flex-col items-center gap-3 text-center">
        <CheckCircle2Icon className="size-10 text-emerald-500" />
        <p className="font-medium">Canale collegato</p>
        <p className="text-sm text-muted-foreground">
          {standalone
            ? "Puoi chiudere questa finestra: il canale è già comparso nella tua pagina."
            : "Un attimo…"}
        </p>
      </div>
    </div>
  );
}
