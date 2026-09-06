"use client";

import { useChannels } from "@/hooks/use-channels";

/**
 * SocialChannelResponse does not expose a buffer_connection_id, so the only way to
 * count channels for a connection is to filter by the connection owner's user_id
 * (accurate for the common one-connection-per-user case; a user with multiple
 * Buffer connections will see the same total on each of their connection rows).
 */
export function ChannelCountCell({ userId }: { userId: string }) {
  const channels = useChannels({ user_id: userId });

  if (channels.isLoading) {
    return <span className="text-muted-foreground">…</span>;
  }
  return <span>{channels.data?.length ?? 0}</span>;
}
