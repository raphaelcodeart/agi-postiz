/**
 * In-memory mock adapter used only when NEXT_PUBLIC_USE_MOCK_API=true in a
 * non-production build (see lib/env.ts#isMockApiEnabled). Mirrors the function
 * signatures of services/*.ts so callers don't need to know which is active.
 * Mutations affect the fixture arrays for the lifetime of the page session only.
 */
import { ApiError } from "@/lib/api/errors";
import {
  mockCampaigns,
  mockChannels,
  mockConnections,
  mockGroups,
  mockMedia,
  mockPublications,
  mockSettings,
  mockUsers,
} from "@/lib/api/mock/fixtures";
import type {
  AIGenerateTextResponse,
  AISettingsResponse,
  AISettingsUpdatePayload,
  BufferConnectionResponse,
  CampaignCreatePayload,
  CampaignDetailResponse,
  CampaignMetricsResponse,
  CampaignPreviewResponse,
  CampaignResponse,
  ChannelMetrics,
  GroupResponse,
  MediaResponse,
  PublicationDetailResponse,
  PublicationFeedItem,
  PublicationResponse,
  SocialChannelResponse,
  StatusCountsSummaryResponse,
  SystemSettingsResponse,
  SystemSettingsUpdatePayload,
  UserResponse,
  UserSummaryResponse,
} from "@/types/api";
import type { GroupPayload, ListUsersParams, UserPayload } from "@/services/users";
import type { ListChannelsParams } from "@/services/channels";
import type { ListCampaignsParams } from "@/services/campaigns";
import type { ListPublicationFeedParams, ListPublicationsParams } from "@/services/publications";

const LATENCY_MS = 250;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

function notFound(entity: string): never {
  throw new ApiError(404, `${entity} not found`);
}

function nowIso() {
  return new Date().toISOString();
}

function countByStatus(rows: { status: string }[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const row of rows) counts[row.status] = (counts[row.status] ?? 0) + 1;
  return counts;
}

// ---------------------------------------------------------------------------
// Users & Groups
// ---------------------------------------------------------------------------
export function listUsers(params: ListUsersParams = {}): Promise<UserResponse[]> {
  let result = mockUsers.filter((u) => !("deleted" in u));
  if (params.status_filter) result = result.filter((u) => u.status === params.status_filter);
  if (params.search) {
    const term = params.search.toLowerCase();
    result = result.filter(
      (u) =>
        u.name.toLowerCase().includes(term) ||
        u.email.toLowerCase().includes(term) ||
        u.company_name?.toLowerCase().includes(term)
    );
  }
  return delay(result.slice(params.skip ?? 0, (params.skip ?? 0) + (params.limit ?? 20)));
}

export function getUsersSummary(): Promise<UserSummaryResponse> {
  const users = mockUsers.filter((u) => !("deleted" in u));
  const byStatus = countByStatus(users);
  return delay({
    total: users.length,
    active: byStatus.active ?? 0,
    inactive: byStatus.inactive ?? 0,
    suspended: byStatus.suspended ?? 0,
  });
}

export function createUser(payload: UserPayload): Promise<UserResponse> {
  const user: UserResponse = {
    id: `usr-${crypto.randomUUID()}`,
    name: payload.name,
    email: payload.email,
    company_name: payload.company_name ?? null,
    status: payload.status,
    notes: payload.notes ?? null,
    referral_link: payload.referral_link ?? null,
    personal_contacts: payload.personal_contacts ?? null,
    created_at: nowIso(),
    updated_at: nowIso(),
    groups: mockGroups.filter((g) => payload.group_ids?.includes(g.id)),
  };
  mockUsers.push(user);
  return delay(user);
}

export function getUser(id: string): Promise<UserResponse> {
  const user = mockUsers.find((u) => u.id === id);
  if (!user) notFound("User");
  return delay(user);
}

export function updateUser(id: string, payload: Partial<UserPayload>): Promise<UserResponse> {
  const user = mockUsers.find((u) => u.id === id);
  if (!user) notFound("User");
  Object.assign(user, {
    ...(payload.name !== undefined && { name: payload.name }),
    ...(payload.email !== undefined && { email: payload.email }),
    ...(payload.company_name !== undefined && { company_name: payload.company_name }),
    ...(payload.status !== undefined && { status: payload.status }),
    ...(payload.notes !== undefined && { notes: payload.notes }),
    ...(payload.referral_link !== undefined && { referral_link: payload.referral_link }),
    ...(payload.personal_contacts !== undefined && { personal_contacts: payload.personal_contacts }),
    updated_at: nowIso(),
  });
  if (payload.group_ids) {
    user.groups = mockGroups.filter((g) => payload.group_ids?.includes(g.id));
  }
  return delay(user);
}

export function deleteUser(id: string): Promise<void> {
  const index = mockUsers.findIndex((u) => u.id === id);
  if (index === -1) notFound("User");
  mockUsers.splice(index, 1);
  return delay(undefined);
}

export function listGroups(): Promise<GroupResponse[]> {
  return delay(mockGroups);
}

export function createGroup(payload: GroupPayload): Promise<GroupResponse> {
  const group: GroupResponse = {
    id: `grp-${crypto.randomUUID()}`,
    name: payload.name,
    description: payload.description ?? null,
    created_at: nowIso(),
    user_count: 0,
  };
  mockGroups.push(group);
  return delay(group);
}

export function updateGroup(groupId: string, payload: GroupPayload): Promise<GroupResponse> {
  const group = mockGroups.find((g) => g.id === groupId);
  if (!group) notFound("Group");
  if (payload.name !== undefined) group.name = payload.name;
  if (payload.description !== undefined) group.description = payload.description ?? null;
  return delay(group);
}

export function listGroupUsers(groupId: string): Promise<UserResponse[]> {
  if (!mockGroups.some((g) => g.id === groupId)) notFound("Group");
  return delay(mockUsers.filter((u) => u.groups.some((g) => g.id === groupId)));
}

// ---------------------------------------------------------------------------
// Buffer connections & channels
// ---------------------------------------------------------------------------
export function listConnections(): Promise<BufferConnectionResponse[]> {
  return delay(mockConnections);
}

export function createConnection(userId: string, apiKey: string): Promise<BufferConnectionResponse> {
  if (!apiKey.trim()) {
    return Promise.reject(new Error("Chiave API Buffer non valida"));
  }
  const existing = mockConnections.find((c) => c.user_id === userId);
  if (existing) {
    existing.status = "connected";
    existing.last_error = null;
    existing.last_sync_at = nowIso();
    return delay(existing);
  }
  const connection: BufferConnectionResponse = {
    id: `conn-${crypto.randomUUID()}`,
    user_id: userId,
    authentication_type: "personal_api_key",
    external_account_id: `buffer-acc-${crypto.randomUUID().slice(0, 8)}`,
    status: "connected",
    last_sync_at: nowIso(),
    last_error: null,
    created_at: nowIso(),
  };
  mockConnections.push(connection);
  return delay(connection);
}

export function syncConnection(connectionId: string): Promise<{ message: string }> {
  const conn = mockConnections.find((c) => c.id === connectionId);
  if (conn) conn.last_sync_at = nowIso();
  return delay({ message: "Sync job dispatched to background worker" });
}

export function disconnectConnection(connectionId: string): Promise<void> {
  const index = mockConnections.findIndex((c) => c.id === connectionId);
  if (index === -1) notFound("Connection");
  mockConnections.splice(index, 1);
  return delay(undefined);
}

export function listChannels(params: ListChannelsParams = {}): Promise<SocialChannelResponse[]> {
  let result = mockChannels;
  if (params.platform) result = result.filter((c) => c.platform === params.platform);
  if (params.publication_mode) result = result.filter((c) => c.publication_mode === params.publication_mode);
  return delay(result);
}

export function updateChannelMode(
  channelId: string,
  mode: SocialChannelResponse["publication_mode"]
): Promise<SocialChannelResponse> {
  const channel = mockChannels.find((c) => c.id === channelId);
  if (!channel) notFound("Channel");
  channel.publication_mode = mode;
  return delay(channel);
}

// ---------------------------------------------------------------------------
// Media
// ---------------------------------------------------------------------------
export function listMedia(): Promise<MediaResponse[]> {
  return delay(mockMedia);
}

export function uploadMedia(file: File): Promise<MediaResponse> {
  const media: MediaResponse = {
    id: `med-${crypto.randomUUID()}`,
    original_filename: file.name,
    stored_filename: file.name,
    public_url: "https://placehold.co/600x400",
    mime_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    duration_seconds: null,
    width: null,
    height: null,
    aspect_ratio: null,
    video_codec: null,
    audio_codec: null,
    checksum: null,
    processing_status: "ready",
    validation_status: "valid",
    validation_errors: null,
    created_at: nowIso(),
  };
  mockMedia.unshift(media);
  return delay(media);
}

export function getMedia(id: string): Promise<MediaResponse> {
  const media = mockMedia.find((m) => m.id === id);
  if (!media) notFound("Media");
  return delay(media);
}

export function renameMedia(id: string, originalFilename: string): Promise<MediaResponse> {
  const media = mockMedia.find((m) => m.id === id);
  if (!media) notFound("Media");
  media.original_filename = originalFilename;
  return delay(media);
}

export function deleteMedia(id: string): Promise<void> {
  const index = mockMedia.findIndex((m) => m.id === id);
  if (index === -1) notFound("Media");
  mockMedia.splice(index, 1);
  return delay(undefined);
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------
export function listCampaigns(params: ListCampaignsParams = {}): Promise<CampaignResponse[]> {
  let result = mockCampaigns;
  if (params.status_filter) result = result.filter((c) => c.status === params.status_filter);
  return delay(result.slice(params.skip ?? 0, (params.skip ?? 0) + (params.limit ?? 20)));
}

export function getCampaignsSummary(): Promise<StatusCountsSummaryResponse> {
  return delay({ total: mockCampaigns.length, by_status: countByStatus(mockCampaigns) });
}

export function generateCampaignText(topic: string): Promise<AIGenerateTextResponse> {
  const clean = topic.trim();
  return delay({
    default_text: `${clean}. Scopri di più e non perderti le novità! #novita #2026`,
    instagram_text: `${clean} ✨\n\nScopri di più nel nostro ultimo contenuto! 👇\n\n#instagram #novita #2026 #contentcreator`,
    facebook_text: `${clean}\n\nCosa ne pensate? Fatecelo sapere nei commenti!`,
    linkedin_text: `${clean}\n\nUn tema che sta ridefinendo il settore. Condividete la vostra esperienza nei commenti.`,
    tiktok_text: `${clean} 🔥 #fyp #trend2026`,
    x_text: `${clean.slice(0, 250)} #novita`,
    threads_text: `${clean}\n\nVoi cosa ne pensate?`,
    youtube_title: clean.slice(0, 95),
    youtube_description: `${clean}\n\nIscriviti al canale per non perdere i prossimi contenuti!\n\n#novita #2026`,
  });
}

export function createCampaign(payload: CampaignCreatePayload): Promise<CampaignResponse> {
  const campaign: CampaignResponse = {
    id: `cmp-${crypto.randomUUID()}`,
    title: payload.title,
    default_text: payload.default_text,
    publishing_mode: payload.publishing_mode,
    scheduled_at: payload.scheduled_at ?? null,
    timezone: payload.timezone,
    targeting_mode: payload.targeting_mode,
    include_referral_link: payload.include_referral_link,
    include_personal_contacts: payload.include_personal_contacts,
    status: "draft",
    media_file_id: payload.media_file_id ?? null,
    media_file: payload.media_file_id ? (mockMedia.find((m) => m.id === payload.media_file_id) ?? null) : null,
    started_at: null,
    completed_at: null,
    created_at: nowIso(),
  };
  mockCampaigns.unshift(campaign);
  return delay(campaign);
}

export function previewCampaignTargets(): Promise<CampaignPreviewResponse> {
  // Approximate preview against the fixture channel set only; not authoritative.
  return delay({
    estimated_publications_count: mockChannels.length,
    total_users_targeted: mockUsers.filter((u) => u.status === "active").length,
    platform_distribution: mockChannels.reduce<Record<string, number>>((acc, channel) => {
      acc[channel.platform] = (acc[channel.platform] ?? 0) + 1;
      return acc;
    }, {}),
    channels_requiring_notification_approval: mockChannels.filter((c) =>
      ["notification", "approval"].includes(c.publication_mode)
    ).length,
    excluded_channels_count: 0,
    total_active_users: mockUsers.filter((u) => u.status === "active").length,
  });
}

export function launchCampaign(campaignId: string): Promise<CampaignResponse> {
  const campaign = mockCampaigns.find((c) => c.id === campaignId);
  if (!campaign) notFound("Campaign");
  campaign.status = "queued";
  campaign.started_at = nowIso();
  return delay(campaign);
}

export function getCampaignDetail(campaignId: string): Promise<CampaignDetailResponse> {
  const campaign = mockCampaigns.find((c) => c.id === campaignId);
  if (!campaign) notFound("Campaign");
  const publications = mockPublications.filter((p) => p.campaign_id === campaignId);
  const stats = {
    pending: 0,
    queued: 0,
    processing: 0,
    submitted: 0,
    scheduled: 0,
    published: 0,
    retry_wait: 0,
    failed: 0,
    cancelled: 0,
    skipped: 0,
    unknown: 0,
  };
  publications.forEach((p) => {
    stats[p.status] += 1;
  });
  const total = publications.length;
  const resolved = stats.published + stats.scheduled + stats.failed + stats.cancelled + stats.skipped;
  return delay({
    campaign,
    media: mockMedia.find((m) => m.id === campaign.media_file_id) ?? null,
    stats,
    progress_percentage: total > 0 ? Math.round((resolved / total) * 10000) / 100 : 0,
  });
}

function buildChannelMetrics(pub: PublicationResponse): ChannelMetrics {
  const channel = mockChannels.find((c) => c.id === pub.social_channel_id);
  const user = mockUsers.find((u) => u.id === pub.user_id);
  const seed = pub.id.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  const reactions = 5 + (seed % 200);
  const views = reactions * 4 + (seed % 300);
  const follows = seed % 6;
  const clicks = seed % 40;
  const metrics = [
    { type: "reactions", name: "Reactions", value: reactions, unit: "count" },
    { type: "views", name: "Views", value: views, unit: "count" },
    { type: "clicks", name: "Clicks", value: clicks, unit: "count" },
    { type: "follows", name: "New follows", value: follows, unit: "count" },
    {
      type: "engagementRate",
      name: "Eng. Rate",
      value: Math.round(Math.min(100, ((reactions + clicks + follows) / Math.max(views, 1)) * 100) * 100) / 100,
      unit: "percentage",
    },
  ];
  return {
    publication_id: pub.id,
    social_channel_id: pub.social_channel_id,
    channel_name: channel?.name ?? "—",
    user_name: user?.name ?? "—",
    platform: channel?.platform ?? "unknown",
    external_post_url: pub.external_post_url ?? null,
    metrics,
    metrics_updated_at: nowIso(),
    error: null,
  };
}

export function getPublicationMetrics(id: string): Promise<ChannelMetrics> {
  const pub = mockPublications.find((p) => p.id === id);
  if (!pub) notFound("Publication");
  if (pub.status !== "published" && pub.status !== "scheduled") {
    throw new ApiError(
      400,
      "Le statistiche sono disponibili solo per pubblicazioni riuscite (pubblicate o programmate)."
    );
  }
  return delay(buildChannelMetrics(pub));
}

export function getCampaignMetrics(campaignId: string): Promise<CampaignMetricsResponse> {
  const published = mockPublications.filter(
    (p) => p.campaign_id === campaignId && (p.status === "published" || p.status === "scheduled")
  );
  const totals: Record<string, number> = {};
  const channels = published.map((pub) => {
    const entry = buildChannelMetrics(pub);
    entry.metrics.forEach((m) => {
      totals[m.type] = (totals[m.type] ?? 0) + m.value;
    });
    return entry;
  });
  return delay({ totals, channels });
}

function updateCampaignStatus(campaignId: string, status: CampaignResponse["status"]): Promise<CampaignResponse> {
  const campaign = mockCampaigns.find((c) => c.id === campaignId);
  if (!campaign) notFound("Campaign");
  campaign.status = status;
  return delay(campaign);
}

export const pauseCampaign = (campaignId: string) => updateCampaignStatus(campaignId, "paused");
export const resumeCampaign = (campaignId: string) => updateCampaignStatus(campaignId, "running");
export const cancelCampaign = (campaignId: string) => updateCampaignStatus(campaignId, "cancelled");

export function deleteCampaign(campaignId: string): Promise<void> {
  const campaignIndex = mockCampaigns.findIndex((c) => c.id === campaignId);
  if (campaignIndex === -1) notFound("Campaign");
  mockCampaigns.splice(campaignIndex, 1);
  for (let i = mockPublications.length - 1; i >= 0; i--) {
    if (mockPublications[i].campaign_id === campaignId) mockPublications.splice(i, 1);
  }
  return delay(undefined);
}

// ---------------------------------------------------------------------------
// Publications
// ---------------------------------------------------------------------------
export function listPublications(params: ListPublicationsParams = {}): Promise<PublicationResponse[]> {
  let result = mockPublications;
  if (params.campaign_id) result = result.filter((p) => p.campaign_id === params.campaign_id);
  if (params.status_filter) result = result.filter((p) => p.status === params.status_filter);
  return delay(result.slice(params.skip ?? 0, (params.skip ?? 0) + (params.limit ?? 50)));
}

export function getPublicationsSummary(): Promise<StatusCountsSummaryResponse> {
  return delay({ total: mockPublications.length, by_status: countByStatus(mockPublications) });
}

export function listPublicationFeed(params: ListPublicationFeedParams = {}): Promise<PublicationFeedItem[]> {
  const items: PublicationFeedItem[] = mockPublications
    .filter((p) => p.status === "published")
    .sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""))
    .map((p) => {
      const campaign = mockCampaigns.find((c) => c.id === p.campaign_id);
      const channel = mockChannels.find((c) => c.id === p.social_channel_id);
      const user = mockUsers.find((u) => u.id === p.user_id);
      const media = campaign?.media_file_id ? mockMedia.find((m) => m.id === campaign.media_file_id) ?? null : null;
      return {
        id: p.id,
        campaign_id: p.campaign_id,
        published_at: p.published_at,
        // No mock campaign_targets fixture exists (resolved per-channel text
        // isn't modeled here) - the campaign's default text is close enough
        // for local dev preview.
        text: campaign?.default_text ?? "",
        external_post_url: p.external_post_url,
        social_channel_id: p.social_channel_id,
        platform: channel?.platform ?? "—",
        channel_name: channel?.name ?? "—",
        channel_avatar_url: channel?.avatar_url ?? null,
        channel_external_link: channel?.external_link ?? null,
        user_name: user?.name ?? "—",
        media,
      };
    });
  return delay(items.slice(params.skip ?? 0, (params.skip ?? 0) + (params.limit ?? 30)));
}

export function getPublication(id: string): Promise<PublicationDetailResponse> {
  const publication = mockPublications.find((p) => p.id === id);
  if (!publication) notFound("Publication");
  const channel = mockChannels.find((c) => c.id === publication.social_channel_id);
  const user = mockUsers.find((u) => u.id === publication.user_id);
  const campaign = mockCampaigns.find((c) => c.id === publication.campaign_id);
  const media = campaign?.media_file_id ? mockMedia.find((m) => m.id === campaign.media_file_id) ?? null : null;
  return delay({
    publication,
    attempts: [],
    resolved_text: "Testo di esempio (dati mock)",
    channel_name: channel?.name ?? "—",
    channel_platform: channel?.platform ?? "—",
    user_name: user?.name ?? "—",
    channel_external_link: channel?.external_link ?? null,
    media,
  });
}

function updatePublicationStatus(id: string, status: PublicationResponse["status"]): Promise<PublicationResponse> {
  const publication = mockPublications.find((p) => p.id === id);
  if (!publication) notFound("Publication");
  publication.status = status;
  publication.updated_at = nowIso();
  return delay(publication);
}

export const retryPublication = (id: string) => updatePublicationStatus(id, "pending");
export const cancelPublication = (id: string) => updatePublicationStatus(id, "cancelled");
export const skipPublication = (id: string) => updatePublicationStatus(id, "skipped");

export function retrySelectedPublications(ids: string[]): Promise<{ message: string }> {
  ids.forEach((id) => {
    const publication = mockPublications.find((p) => p.id === id);
    if (publication) publication.status = "pending";
  });
  return delay({ message: `Successfully queued ${ids.length} publications for retry.` });
}

export function retryCampaignFailures(campaignId: string): Promise<{ message: string }> {
  const failed = mockPublications.filter((p) => p.campaign_id === campaignId && p.status === "failed");
  failed.forEach((p) => (p.status = "pending"));
  return delay({ message: `Queued ${failed.length} failed publications for retry.` });
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
export function getSettings(): Promise<SystemSettingsResponse> {
  return delay(mockSettings);
}

export function updateSettings(payload: SystemSettingsUpdatePayload): Promise<SystemSettingsResponse> {
  Object.assign(mockSettings, payload);
  return delay(mockSettings);
}

const mockAISettings: AISettingsResponse = { configured: false, model: "gpt-4o-mini" };

export function getAISettings(): Promise<AISettingsResponse> {
  return delay(mockAISettings);
}

export function updateAISettings(payload: AISettingsUpdatePayload): Promise<AISettingsResponse> {
  if (payload.openai_api_key) {
    if (payload.openai_api_key.includes("invalid")) {
      throw new ApiError(400, "Chiave API OpenAI non valida");
    }
    mockAISettings.configured = true;
  }
  if (payload.openai_model) mockAISettings.model = payload.openai_model;
  return delay({ ...mockAISettings });
}

export function deleteAISettings(): Promise<void> {
  mockAISettings.configured = false;
  return delay(undefined);
}

export function getHealth() {
  return delay({
    status: "healthy" as const,
    database: "ok" as const,
    redis: "ok" as const,
    celery_worker: "ok" as const,
    timestamp: nowIso(),
  });
}
