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
};

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
