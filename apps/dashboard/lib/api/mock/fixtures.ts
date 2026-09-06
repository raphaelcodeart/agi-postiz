/**
 * Static, in-memory sample data for local UI development without a running backend.
 * Only active when NEXT_PUBLIC_USE_MOCK_API=true and NODE_ENV !== "production"
 * (see lib/env.ts#isMockApiEnabled). Shapes mirror types/api.ts exactly but the
 * values themselves are illustrative fixtures, not real Buffer/backend data.
 */
import type {
  BufferConnectionResponse,
  CampaignResponse,
  GroupResponse,
  MediaResponse,
  PublicationResponse,
  SocialChannelResponse,
  SystemSettingsResponse,
  UserResponse,
} from "@/types/api";

const now = new Date().toISOString();

export const mockGroups: GroupResponse[] = [
  { id: "grp-hotels", name: "Hotels", description: "Algarve & Lisbon hospitality clients", created_at: now, user_count: 2 },
  { id: "grp-restaurants", name: "Restaurants", description: "Dining and bistro customers", created_at: now, user_count: 1 },
  { id: "grp-premium", name: "Premium Clients", description: "VIP priority subscribers", created_at: now, user_count: 1 },
];

export const mockUsers: UserResponse[] = [
  {
    id: "usr-algarve",
    name: "Algarve Beach Resort",
    email: "info@algarvebeachresort.com",
    company_name: "Algarve Resorts Ltd",
    status: "active",
    notes: null,
    referral_link: "https://algarvebeachresort.example.com/iscriviti",
    personal_contacts: "Algarve Beach Resort\nTel. +351 289 000 000\ninfo@algarvebeachresort.com",
    created_at: now,
    updated_at: now,
    groups: [mockGroups[0], mockGroups[2]],
  },
  {
    id: "usr-sintra",
    name: "Sintra Castle B&B",
    email: "booking@sintracastle.com",
    company_name: "Sintra Boutique Hotels",
    status: "active",
    notes: null,
    referral_link: null,
    personal_contacts: null,
    created_at: now,
    updated_at: now,
    groups: [mockGroups[0]],
  },
  {
    id: "usr-porto",
    name: "Porto Wine Bistro",
    email: "contact@portowinebistro.com",
    company_name: "Porto Bistro Group",
    status: "active",
    notes: null,
    referral_link: null,
    personal_contacts: null,
    created_at: now,
    updated_at: now,
    groups: [mockGroups[1]],
  },
  {
    id: "usr-lisbon",
    name: "Lisbon Surf Academy",
    email: "hello@lisbonsurf.com",
    company_name: "Lisbon Surf & Outdoors",
    status: "suspended",
    notes: "Suspended due to missing invoice settlement.",
    referral_link: null,
    personal_contacts: null,
    created_at: now,
    updated_at: now,
    groups: [],
  },
];

export const mockConnections: BufferConnectionResponse[] = [
  {
    id: "conn-algarve",
    user_id: "usr-algarve",
    authentication_type: "personal_api_key",
    external_account_id: "buffer-acc-1",
    status: "connected",
    last_sync_at: now,
    last_error: null,
    created_at: now,
  },
  {
    id: "conn-sintra",
    user_id: "usr-sintra",
    authentication_type: "personal_api_key",
    external_account_id: "buffer-acc-2",
    status: "expired",
    last_sync_at: now,
    last_error: "Access token expired",
    created_at: now,
  },
];

export const mockChannels: SocialChannelResponse[] = [
  {
    id: "chn-algarve-ig",
    user_id: "usr-algarve",
    external_channel_id: "ext-ig-1",
    platform: "instagram",
    name: "Algarve Beach Resort",
    username: "algarvebeach",
    avatar_url: null,
    external_link: "https://instagram.com/algarvebeach",
    channel_type: "profile",
    is_active: true,
    auto_publish_enabled: true,
    publication_mode: "automatic",
    last_sync_at: now,
  },
  {
    id: "chn-algarve-fb",
    user_id: "usr-algarve",
    external_channel_id: "ext-fb-1",
    platform: "facebook",
    name: "Algarve Beach Resort",
    username: null,
    avatar_url: null,
    external_link: "https://facebook.com/algarvebeachresort",
    channel_type: "page",
    is_active: true,
    auto_publish_enabled: true,
    publication_mode: "notification",
    last_sync_at: now,
  },
  {
    id: "chn-sintra-ig",
    user_id: "usr-sintra",
    external_channel_id: "ext-ig-2",
    platform: "instagram",
    name: "Sintra Castle B&B",
    username: "sintracastle",
    avatar_url: null,
    external_link: "https://instagram.com/sintracastle",
    channel_type: "profile",
    is_active: true,
    auto_publish_enabled: false,
    publication_mode: "approval",
    last_sync_at: now,
  },
];

export const mockMedia: MediaResponse[] = [
  {
    id: "med-1",
    original_filename: "beach-sunset.jpg",
    stored_filename: "beach-sunset-abc123.jpg",
    public_url: "https://placehold.co/600x400",
    mime_type: "image/jpeg",
    size_bytes: 2_345_000,
    duration_seconds: null,
    width: 1920,
    height: 1080,
    aspect_ratio: "16:9",
    video_codec: null,
    audio_codec: null,
    checksum: "mockchecksum1",
    processing_status: "ready",
    validation_status: "valid",
    validation_errors: null,
    created_at: now,
  },
];

export const mockCampaigns: CampaignResponse[] = [
  {
    id: "cmp-1",
    title: "Promozione estiva 2026",
    default_text: "Scopri le nostre offerte estive!",
    publishing_mode: "immediate",
    scheduled_at: null,
    timezone: "Europe/Lisbon",
    targeting_mode: "all_active_channels",
    include_referral_link: false,
    include_personal_contacts: false,
    status: "completed",
    media_file_id: "med-1",
    media_file: mockMedia.find((m) => m.id === "med-1") ?? null,
    started_at: now,
    completed_at: now,
    created_at: now,
  },
];

export const mockPublications: PublicationResponse[] = [
  {
    id: "pub-1",
    campaign_id: "cmp-1",
    user_id: "usr-algarve",
    social_channel_id: "chn-algarve-ig",
    external_channel_id: "ext-ig-1",
    status: "published",
    attempt_count: 1,
    max_attempts: 5,
    idempotency_key: "cmp-1:chn-algarve-ig",
    scheduled_at: null,
    next_attempt_at: null,
    processing_started_at: now,
    submitted_at: now,
    confirmed_at: now,
    published_at: now,
    external_post_id: "post-123",
    external_post_url: "https://instagram.com/p/mock",
    error_category: null,
    error_code: null,
    error_message: null,
    created_at: now,
    updated_at: now,
  },
];

export const mockSettings: SystemSettingsResponse = {
  global_concurrency_limit: 5,
  concurrent_jobs_per_connection: 1,
  pause_between_requests_seconds: 10,
  max_publication_attempts: 5,
  upload_max_size_bytes: 104_857_600,
  buffer_integration_mode: "mock",
  celery_queue_health: "ok",
};
