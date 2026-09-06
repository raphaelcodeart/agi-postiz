"use client";

import { useState } from "react";
import { useAISettings } from "@/hooks/use-settings";

// Shared gate for every AI-powered action in the app (campaign text
// generation, blog article generation/regeneration, social-preview
// adaptation). Pair with <AIRequiredDialog open={dialogOpen} onOpenChange={setDialogOpen} />.
export function useAIGate() {
  const aiSettingsQuery = useAISettings();
  const [dialogOpen, setDialogOpen] = useState(false);
  const configured = !!aiSettingsQuery.data?.configured;

  // Runs `action` only if AI is configured; otherwise opens the explanatory
  // dialog instead. While the config status is still loading, lets the action
  // through rather than risk a false "not configured" flash.
  function guard(action: () => void) {
    if (aiSettingsQuery.isLoading) {
      action();
      return;
    }
    if (!configured) {
      setDialogOpen(true);
      return;
    }
    action();
  }

  return {
    configured: aiSettingsQuery.isLoading ? true : configured,
    isLoading: aiSettingsQuery.isLoading,
    dialogOpen,
    setDialogOpen,
    guard,
  };
}
