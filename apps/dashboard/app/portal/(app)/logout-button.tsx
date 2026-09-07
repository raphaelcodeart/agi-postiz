"use client";

import { useState } from "react";
import { LogOutIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function PortalLogoutButton() {
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    try {
      await fetch("/api/portal/auth/logout", { method: "POST" });
    } finally {
      // Hard navigation for the same reason as the admin logout: a
      // router.refresh() here would fetch the RSC payload of a page the route
      // guard now redirects away from, and the client router throws on a bare
      // redirect instead of following it.
      window.location.href = "/portal/login";
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={onClick} disabled={pending}>
      <LogOutIcon className="size-4" />
      <span className="hidden sm:inline">Esci</span>
    </Button>
  );
}
