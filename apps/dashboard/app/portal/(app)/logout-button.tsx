"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogOutIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function PortalLogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    try {
      await fetch("/api/portal/auth/logout", { method: "POST" });
    } finally {
      router.push("/portal/login");
      router.refresh();
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={onClick} disabled={pending}>
      <LogOutIcon className="size-4" />
      <span className="hidden sm:inline">Esci</span>
    </Button>
  );
}
