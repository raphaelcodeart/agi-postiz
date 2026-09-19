import { cookies } from "next/headers";
import { getBackendInternalUrl, PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * Server-side data access for the end-user portal.
 *
 * The portal pages are React Server Components that call the backend directly
 * from here, rather than client components driving react-query like the admin
 * dashboard does. That is a deliberate difference, not drift: these pages only
 * read and render, so there is no client cache to keep coherent, and the portal
 * token stays on the server the whole time - it never has to be reachable from
 * a browser fetch at all.
 *
 * Interactions that do mutate (sign in, sign out, connect a channel) are client
 * components posting to the BFF routes under app/api/portal.
 */

export type PortalUser = {
  id: string;
  name: string;
  email: string;
  company_name: string | null;
  status: string;
  is_active_for_campaigns: boolean;
  referral_link: string | null;
  created_at: string;
};

export type PortalChannel = {
  id: string;
  platform: string;
  name: string;
  username: string | null;
  avatar_url: string | null;
  external_link: string | null;
  is_active: boolean;
  publication_mode: string;
  provider: string;
  provider_label: string;
  last_sync_at: string | null;
  /** Why an inactive channel is inactive - e.g. already connected elsewhere. */
  blocked_reason: string | null;
  /** True once the channel is no longer connected upstream and can be removed. */
  can_remove: boolean;
};

export type PortalCampaign = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  channels_targeted: number;
  published: number;
  failed: number;
  pending: number;
  /**
   * How this user relates to the campaign. A campaign they declined has no
   * targets and no publications at all, so without this it would be invisible
   * in their history - which is precisely the record they need to be able to
   * check.
   */
  participation_included: number;
  participation_withdrawn: number;
  /** Taken out by an administrator, not by the user - shown differently. */
  participation_removed: number;
};

/** One of the user's channels, and where it stands in a given campaign. */
export type PortalLineupChannel = {
  id: string;
  platform: string;
  name: string;
  username: string | null;
  avatar_url: string | null;
  /** included | withdrawn | removed | null (never in the line-up) */
  participation_status: "included" | "withdrawn" | "removed" | null;
  joined_by_me: boolean;
  /** True when a post for this campaign actually went out on this channel. */
  published: boolean;
  decided_at: string | null;
  /** False when an administrator removed it: the user may not put it back. */
  can_rejoin: boolean;
};

/**
 * A campaign in the line-up: announced, not yet sent, and open for the user to
 * join or leave.
 */
export type PortalLineupCampaign = {
  id: string;
  title: string;
  status: string;
  text: string;
  media_url: string | null;
  media_type: "image" | "video" | null;
  scheduled_at: string | null;
  timezone: string;
  opt_out_deadline_at: string | null;
  window_open: boolean;
  auto_launch_at_deadline: boolean;
  announced_at: string | null;
  channels: PortalLineupChannel[];
  included_count: number;
  withdrawn_count: number;
  can_join: boolean;
  /**
   * open     - the window is open: the user can join or leave
   * closed   - announced, deadline passed, not launched yet
   * launched - already gone out: read-only history
   */
  phase: "open" | "closed" | "launched";
};

export type PortalOverview = {
  stats: PortalStats;
  timeline: { date: string; published: number }[];
  top_channels: {
    name: string;
    platform: string;
    impressions: number;
    likes: number;
    posts: number;
  }[];
};

export type PortalStats = {
  channels_connected: number;
  channels_by_provider: Record<string, number>;
  campaigns_joined: number;
  posts_published: number;
  posts_failed: number;
  total_impressions: number;
  total_likes: number;
  total_comments: number;
  total_shares: number;
  total_views: number;
  total_reach: number;
  total_follows: number;
  total_clicks: number;
  /** L'unica metrica in percentuale: media dei post che la riportano, mai una
   *  somma. null quando nessun post ne ha una - 0 direbbe "coinvolgimento
   *  nullo" invece di "non riportato". */
  engagement_rate: number | null;
};

/**
 * Le pagine /portal/statistics non hanno un tipo proprio qui: il backend
 * restituisce le stesse StatUserDetailResponse/StatChannelDetailResponse della
 * dashboard amministrativa (sono gli stessi statistics_service, chiamati con
 * l'id dell'utente del token - vedi apps/api/app/api/v1/portal_statistics.py),
 * quindi si importano da @/types/api. Ridichiararle qui creerebbe una seconda
 * definizione della stessa risposta, destinata a divergere.
 */

/**
 * Fetch a portal endpoint as the signed-in user.
 *
 * Returns null when there is no session or the backend rejects it, so callers
 * can redirect to the login page instead of rendering a broken dashboard.
 */
export async function portalFetch<T>(path: string): Promise<T | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(PORTAL_SESSION_COOKIE_NAME)?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${getBackendInternalUrl()}/api/v1/portal/${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
