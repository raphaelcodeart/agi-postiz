/**
 * Types mirror `apps/api/app/schemas/schemas.py` field-for-field.
 * Do not add fields here that the FastAPI backend does not actually return.
 */

// ==============================================================================
// Auth
// ==============================================================================
export interface AdminResponse {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

// ==============================================================================
// Users & Groups
// ==============================================================================
export type UserStatus = "active" | "inactive" | "suspended";

export interface GroupResponse {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  user_count: number;
}

export interface UserResponse {
  id: string;
  name: string;
  email: string;
  company_name: string | null;
  status: UserStatus;
  notes: string | null;
  referral_link: string | null;
  personal_contacts: string | null;
  created_at: string;
  updated_at: string;
  groups: GroupResponse[];
}

export interface UserSummaryResponse {
  total: number;
  active: number;
  inactive: number;
  suspended: number;
}

// Riusato per i conteggi di Campagne e Pubblicazioni (vedi
// StatusCountsSummaryResponse in schemas.py) - un dizionario grezzo
// per-status invece di un campo per ognuno, cosi' il frontend puo'
// raggruppare gli status in meno card senza dover cambiare il backend ogni
// volta che ne viene introdotto uno nuovo.
export interface StatusCountsSummaryResponse {
  total: number;
  by_status: Record<string, number>;
}

// ==============================================================================
// Buffer Connections & Channels
// ==============================================================================
export type BufferConnectionStatus =
  | "pending"
  | "connected"
  | "expired"
  | "revoked"
  | "error"
  | "disconnected";

export interface BufferConnectionResponse {
  id: string;
  user_id: string;
  authentication_type: string;
  external_account_id: string | null;
  status: BufferConnectionStatus;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface BufferOrganizationResponse {
  id: string;
  external_organization_id: string;
  name: string;
  is_active: boolean;
}

export type PublicationMode = "automatic" | "notification" | "approval" | "disabled";

export type SocialPlatform =
  | "instagram"
  | "facebook"
  | "linkedin"
  | "tiktok"
  | "youtube"
  | "twitter"
  | "threads";

export interface SocialChannelResponse {
  id: string;
  user_id: string;
  external_channel_id: string;
  platform: string;
  name: string;
  username: string | null;
  avatar_url: string | null;
  external_link: string | null;
  channel_type: string | null;
  is_active: boolean;
  auto_publish_enabled: boolean;
  publication_mode: PublicationMode;
  last_sync_at: string | null;
}

// ==============================================================================
// Media
// ==============================================================================
export type MediaProcessingStatus = "uploaded" | "inspecting" | "processing" | "ready" | "failed";
export type MediaValidationStatus = "pending" | "valid" | "warning" | "invalid";

export interface MediaValidationError {
  code?: string;
  message: string;
  [key: string]: unknown;
}

export interface MediaResponse {
  id: string;
  original_filename: string;
  stored_filename: string;
  public_url: string;
  mime_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  aspect_ratio: string | null;
  video_codec: string | null;
  audio_codec: string | null;
  checksum: string | null;
  processing_status: MediaProcessingStatus;
  validation_status: MediaValidationStatus;
  validation_errors: MediaValidationError[] | null;
  created_at: string;
}

// ==============================================================================
// Campaigns
// ==============================================================================
export type PublishingMode = "immediate" | "scheduled" | "buffer_queue" | "draft" | "approval";

export type TargetingMode =
  | "all_active_channels"
  | "selected_users"
  | "selected_groups"
  | "selected_channels"
  | "selected_platforms";

export type CampaignStatus =
  | "draft"
  | "preparing"
  | "queued"
  | "running"
  | "paused"
  | "partially_completed"
  | "completed"
  | "failed"
  | "cancelled";

export interface CampaignCreatePayload {
  title: string;
  default_text: string;
  instagram_text?: string | null;
  facebook_text?: string | null;
  linkedin_text?: string | null;
  tiktok_text?: string | null;
  youtube_title?: string | null;
  youtube_description?: string | null;
  x_text?: string | null;
  threads_text?: string | null;
  media_file_id?: string | null;
  article_id?: string | null;
  publishing_mode: PublishingMode;
  scheduled_at?: string | null;
  timezone: string;
  targeting_mode: TargetingMode;
  targeting_params: Record<string, unknown>;
  include_referral_link: boolean;
  include_personal_contacts: boolean;
}

export interface CampaignResponse {
  id: string;
  title: string;
  default_text: string;
  instagram_text?: string | null;
  facebook_text?: string | null;
  linkedin_text?: string | null;
  tiktok_text?: string | null;
  youtube_title?: string | null;
  youtube_description?: string | null;
  x_text?: string | null;
  threads_text?: string | null;
  publishing_mode: PublishingMode;
  scheduled_at: string | null;
  timezone: string;
  targeting_mode: TargetingMode;
  include_referral_link: boolean;
  include_personal_contacts: boolean;
  metadata_json?: Record<string, unknown> | null;
  status: CampaignStatus;
  media_file_id: string | null;
  media_file: MediaResponse | null;
  article_id?: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CampaignPreviewResponse {
  estimated_publications_count: number;
  total_users_targeted: number;
  platform_distribution: Record<string, number>;
  channels_requiring_notification_approval: number;
  excluded_channels_count: number;
  total_active_users: number;
}

export type PublicationStatsMap = Record<
  | "pending"
  | "queued"
  | "processing"
  | "submitted"
  | "scheduled"
  | "published"
  | "retry_wait"
  | "failed"
  | "cancelled"
  | "skipped"
  | "unknown",
  number
>;

export interface CampaignDetailResponse {
  campaign: CampaignResponse;
  media: MediaResponse | null;
  stats: PublicationStatsMap;
  progress_percentage: number;
}

export interface PostMetricValue {
  type: string;
  name: string;
  value: number;
  unit: string;
}

export interface ChannelMetrics {
  publication_id: string;
  social_channel_id: string;
  channel_name: string;
  user_name: string;
  platform: string;
  external_post_url: string | null;
  metrics: PostMetricValue[];
  metrics_updated_at: string | null;
  error: string | null;
}

export interface AISettingsResponse {
  configured: boolean;
  model: string;
}

export interface AISettingsUpdatePayload {
  openai_api_key?: string;
  openai_model?: string;
}

export interface AIGenerateTextResponse {
  default_text: string;
  instagram_text: string;
  facebook_text: string;
  linkedin_text: string;
  tiktok_text: string;
  x_text: string;
  threads_text: string;
  youtube_title: string;
  youtube_description: string;
}

export interface CampaignMetricsResponse {
  totals: Record<string, number>;
  channels: ChannelMetrics[];
}

// ==============================================================================
// Publications
// ==============================================================================
export type PublicationStatus =
  | "pending"
  | "queued"
  | "processing"
  | "submitted"
  | "scheduled"
  | "published"
  | "retry_wait"
  | "failed"
  | "cancelled"
  | "skipped"
  | "unknown";

export interface PublicationResponse {
  id: string;
  campaign_id: string;
  user_id: string;
  social_channel_id: string;
  external_channel_id: string;
  status: PublicationStatus;
  attempt_count: number;
  max_attempts: number;
  idempotency_key: string;
  scheduled_at: string | null;
  next_attempt_at: string | null;
  processing_started_at: string | null;
  submitted_at: string | null;
  confirmed_at: string | null;
  published_at: string | null;
  external_post_id: string | null;
  external_post_url: string | null;
  error_category: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicationAttemptResponse {
  id: string;
  publication_id: string;
  attempt_number: number;
  started_at: string;
  completed_at: string | null;
  success: boolean;
  http_status: number | null;
  external_error_code: string | null;
  error_category: string | null;
  error_message: string | null;
  sanitized_request: Record<string, unknown> | null;
  sanitized_response: Record<string, unknown> | null;
  duration_ms: number | null;
}

export interface PublicationDetailResponse {
  publication: PublicationResponse;
  attempts: PublicationAttemptResponse[];
  resolved_text: string;
  channel_name: string;
  channel_platform: string;
  user_name: string;
  channel_external_link: string | null;
  media: MediaResponse | null;
}

// "Bacheca" (GET /publications/feed) - one card per successfully published post.
export interface PublicationFeedItem {
  id: string;
  campaign_id: string;
  published_at: string | null;
  text: string;
  external_post_url: string | null;
  social_channel_id: string;
  platform: string;
  channel_name: string;
  channel_avatar_url: string | null;
  channel_external_link: string | null;
  user_name: string;
  media: MediaResponse | null;
}

// ==============================================================================
// Settings
// ==============================================================================
export interface SystemSettingsResponse {
  global_concurrency_limit: number;
  concurrent_jobs_per_connection: number;
  pause_between_requests_seconds: number;
  max_publication_attempts: number;
  upload_max_size_bytes: number;
  buffer_integration_mode: string;
  celery_queue_health: string;
}

export interface SystemSettingsUpdatePayload {
  global_concurrency_limit: number;
  concurrent_jobs_per_connection: number;
  pause_between_requests_seconds: number;
  max_publication_attempts: number;
  upload_max_size_bytes: number;
}

export interface HealthResponse {
  status: "healthy" | "unhealthy";
  database: "ok" | "failed";
  redis: "ok" | "failed";
  celery_worker: "ok" | "inactive" | "failed";
  timestamp: string;
}

// ==============================================================================
// Blog Writer AI
// ==============================================================================
export type WordpressConnectionStatus = "untested" | "connected" | "error";

export interface WordpressSiteResponse {
  id: string;
  user_id: string | null;
  name: string;
  site_url: string;
  api_url: string;
  username: string;
  default_author_id: number | null;
  default_author_name: string | null;
  default_category_id: number | null;
  default_category_name: string | null;
  default_status: string;
  language: string;
  is_active: boolean;
  connection_status: WordpressConnectionStatus;
  last_connection_test_at: string | null;
  last_connection_error: string | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WordpressSiteCreatePayload {
  user_id?: string | null;
  name: string;
  site_url: string;
  api_url: string;
  username: string;
  application_password: string;
  default_author_id?: number | null;
  default_category_id?: number | null;
  default_status: string;
  language: string;
}

export interface WordpressSiteUpdatePayload {
  user_id?: string | null;
  name?: string;
  site_url?: string;
  api_url?: string;
  username?: string;
  application_password?: string;
  default_author_id?: number | null;
  default_category_id?: number | null;
  default_status?: string;
  language?: string;
  is_active?: boolean;
}

export interface WordpressOptionItem {
  id: number;
  name: string;
}

export interface WordpressTestConnectionResponse {
  success: boolean;
  message: string;
  wp_user_name: string | null;
}

export type BlogArticleStatus =
  | "generating"
  | "draft"
  | "ready"
  | "publishing"
  | "partially_published"
  | "published"
  | "failed"
  | "archived";

export interface BlogArticleCreatePayload {
  title: string;
  slug?: string;
  excerpt?: string;
  content: string;
  hashtags: string[];
  meta_title?: string;
  meta_description?: string;
  language: string;
  user_id?: string | null;
}

export interface BlogArticleGeneratePayload {
  topic: string;
  description?: string;
  goal?: string;
  target_audience?: string;
  language: string;
  tone?: string;
  length: "short" | "medium" | "long";
  primary_keyword?: string;
  secondary_keywords: string[];
  must_include?: string;
  must_avoid?: string;
  call_to_action?: string;
  hashtag_count: number;
  wordpress_site_id?: string | null;
  wordpress_category_id?: number | null;
  user_id?: string | null;
}

export interface BlogArticleUpdatePayload {
  title?: string;
  slug?: string;
  excerpt?: string;
  content?: string;
  hashtags?: string[];
  meta_title?: string;
  meta_description?: string;
  // Omit = leave unchanged, "" = detach, a media id = attach it.
  media_file_id?: string;
}

export interface BlogArticleResponse {
  id: string;
  user_id: string | null;
  title: string;
  slug: string;
  excerpt: string | null;
  content: string;
  media_file_id: string | null;
  hashtags: string[] | null;
  primary_keyword: string | null;
  secondary_keywords: string[] | null;
  meta_title: string | null;
  meta_description: string | null;
  language: string;
  tone: string | null;
  target_audience: string | null;
  article_goal: string | null;
  generation_model: string | null;
  status: BlogArticleStatus;
  created_at: string;
  updated_at: string;
  last_edited_at: string | null;
  published_at: string | null;
}

export interface BlogArticleListItem {
  id: string;
  title: string;
  language: string;
  status: BlogArticleStatus;
  created_at: string;
  updated_at: string;
  sites_count: number;
  publications_count: number;
}

export type BlogPublicationStatus = "pending" | "publishing" | "published" | "failed" | "retrying" | "removed" | "updated";

export interface BlogPublicationResponse {
  id: string;
  article_id: string;
  wordpress_site_id: string;
  wordpress_site_name: string;
  wordpress_post_id: number | null;
  wordpress_post_url: string | null;
  wordpress_status: string | null;
  publication_status: BlogPublicationStatus;
  error_message: string | null;
  retry_count: number;
  published_at: string | null;
  created_at: string;
}

export interface BlogArticleDetailResponse {
  article: BlogArticleResponse;
  publications: BlogPublicationResponse[];
  social_campaigns: CampaignResponse[];
}

export interface BlogPublishTarget {
  wordpress_site_id: string;
  category_id?: number | null;
  author_id?: number | null;
  status?: string | null;
}

export interface SocialPreviewResponse {
  article_url: string;
  default_text: string;
  instagram_text: string;
  facebook_text: string;
  linkedin_text: string;
  x_text: string;
  threads_text: string;
}

export interface BlogWriterDashboardResponse {
  draft_count: number;
  ready_count: number;
  published_count: number;
  failed_publications_count: number;
  sites_count: number;
  sites_error_count: number;
  social_campaigns_count: number;
  recent_articles: BlogArticleListItem[];
  recent_publications: BlogPublicationResponse[];
}

// ==============================================================================
// Omnichannel Responder (independent add-on module)
// ==============================================================================
export type OmniChannel = "telegram" | "whatsapp" | "instagram" | "facebook" | "gmail" | "mock";

export type OmniConversationStatus =
  | "NEW"
  | "OPEN"
  | "AI_PROCESSING"
  | "WAITING_APPROVAL"
  | "WAITING_CUSTOMER"
  | "RESOLVED"
  | "ARCHIVED"
  | "SPAM";

export type OmniDraftStatus =
  | "GENERATING"
  | "PENDING_APPROVAL"
  | "EDITED"
  | "APPROVED"
  | "SENDING"
  | "SENT"
  | "REJECTED"
  | "FAILED"
  | "HUMAN_REVIEW_REQUIRED";

export interface OmniChannelAccountResponse {
  id: string;
  channel: OmniChannel;
  name: string;
  external_account_id: string | null;
  status: string;
  webhook_secret: string;
  config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  conversation_count: number;
}

export interface OmniChannelAccountCreate {
  channel: OmniChannel;
  name: string;
  external_account_id?: string;
  access_token?: string;
  /** Facebook only: Meta App Secret, used to verify webhook signatures. */
  app_secret?: string;
  config?: Record<string, unknown>;
}

export interface OmniChannelAccountUpdate {
  name?: string;
  external_account_id?: string;
  /** Only re-encrypted if provided - omit/blank to leave the current credential unchanged. */
  access_token?: string;
  app_secret?: string;
  config?: Record<string, unknown>;
}

export interface OmniCustomerIdentityResponse {
  id: string;
  channel: OmniChannel;
  external_user_id: string;
  display_name: string | null;
}

export interface OmniCustomerResponse {
  id: string;
  name: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  language: string | null;
  timezone: string | null;
  notes: string | null;
  is_blocked: boolean;
  created_at: string;
  last_contact_at: string | null;
  identities: OmniCustomerIdentityResponse[];
}

export interface OmniCustomerUpdate {
  name?: string;
  phone?: string;
  email?: string;
  language?: string;
  notes?: string;
}

export interface OmniTagResponse {
  id: string;
  name: string;
  color: string | null;
}

export interface OmniTagCreate {
  name: string;
  color?: string;
}

export interface OmniMessageResponse {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  sender_type: "customer" | "operator" | "ai";
  text: string | null;
  message_type: string;
  attachments: Array<Record<string, unknown>> | null;
  status: string;
  created_at: string;
}

export interface OmniBroadcastRequest {
  text: string;
  conversation_ids?: string[];
}

export interface OmniBroadcastFailure {
  conversation_id: string;
  customer_name: string | null;
  channel: OmniChannel;
  error: string;
}

export interface OmniBroadcastResult {
  total_targeted: number;
  sent: number;
  failed: number;
  failures: OmniBroadcastFailure[];
}

export interface OmniAIDraftResponse {
  id: string;
  conversation_id: string;
  source_message_id: string | null;
  original_ai_text: string | null;
  edited_text: string | null;
  status: OmniDraftStatus;
  model: string | null;
  confidence_score: number | null;
  sensitive_category: string | null;
  failure_reason: string | null;
  created_at: string;
  approved_at: string | null;
  sent_at: string | null;
}

export interface OmniInternalNoteResponse {
  id: string;
  conversation_id: string;
  admin_id: string | null;
  text: string;
  mentions: string[] | null;
  created_at: string;
}

export interface OmniConversationListItem {
  id: string;
  status: OmniConversationStatus;
  channel: OmniChannel;
  channel_account_name: string;
  customer: OmniCustomerResponse;
  assigned_admin_id: string | null;
  unread_count: number;
  last_message_at: string | null;
  last_message_preview: string | null;
  tags: OmniTagResponse[];
}

export interface OmniConversationDetailResponse {
  id: string;
  status: OmniConversationStatus;
  channel: OmniChannel;
  channel_account_id: string;
  channel_account_name: string;
  customer: OmniCustomerResponse;
  assigned_admin_id: string | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
  tags: OmniTagResponse[];
  messages: OmniMessageResponse[];
  drafts: OmniAIDraftResponse[];
  notes: OmniInternalNoteResponse[];
}

export interface OmniAIAgentConfigResponse {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string | null;
  language: string;
  tone: string;
  temperature: number;
  company_description: string | null;
  allowed_topics: string[] | null;
  forbidden_topics: string[] | null;
  signature: string | null;
  max_context_messages: number;
  knowledge_base_enabled: boolean;
  automatic_language_detection: boolean;
  auto_generate_draft: boolean;
  response_mode: "MANUAL" | "APPROVAL_REQUIRED" | "AUTO_REPLY";
  sensitive_categories: string[] | null;
}

export type OmniAIAgentConfigUpdate = Partial<Omit<OmniAIAgentConfigResponse, "id">>;

export interface OmniKnowledgeDocumentResponse {
  id: string;
  title: string;
  source_type: "manual" | "faq" | "url" | "pdf" | "docx" | "txt";
  content_text: string | null;
  source_url: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface OmniKnowledgeDocumentCreate {
  title: string;
  source_type?: string;
  content_text?: string;
  source_url?: string;
}

export interface OmniNotificationResponse {
  id: string;
  type: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface OmniAnalyticsResponse {
  conversations_total: number;
  conversations_open: number;
  messages_received: number;
  messages_sent: number;
  ai_drafts_approved_unedited: number;
  ai_drafts_approved_edited: number;
  ai_drafts_rejected: number;
  ai_acceptance_rate: number | null;
  ai_edit_rate: number | null;
  ai_rejection_rate: number | null;
}

// ==============================================================================
// Statistics module (see docs/STATISTICS.md) - persisted Buffer post metrics,
// browsable by utente -> canale -> campagna/post. Separate from the live,
// on-demand ChannelMetrics/CampaignMetricsResponse above.
// ==============================================================================
export interface StatMetricTotals {
  reactions: number | null;
  likes: number | null;
  views: number | null;
  impressions: number | null;
  reach: number | null;
  follows: number | null;
  clicks: number | null;
  comments: number | null;
  shares: number | null;
  engagement_rate: number | null;
}

export interface StatTimeseriesPoint {
  period: string;
  post_count: number;
  totals: StatMetricTotals;
}

export type StatSyncScope = "global" | "user" | "campaign";
export type StatSyncStatus = "queued" | "running" | "completed" | "completed_with_errors" | "failed";

export interface StatSyncRunResponse {
  id: string;
  scope: StatSyncScope;
  scope_user_id: string | null;
  scope_campaign_id: string | null;
  status: StatSyncStatus;
  total_posts: number;
  synced_posts: number;
  failed_posts: number;
  skipped_posts: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface StatSyncDispatchResponse {
  sync_run_id: string;
  message: string;
}

export interface StatPostRow {
  publication_id: string;
  campaign_id: string;
  campaign_title: string;
  platform: string;
  external_post_url: string | null;
  published_at: string | null;
  metrics: StatMetricTotals;
  last_synced_at: string | null;
  last_sync_error: string | null;
}

export interface StatChannelSummary {
  social_channel_id: string;
  channel_name: string;
  username: string | null;
  platform: string;
  post_count: number;
  totals: StatMetricTotals;
  last_synced_at: string | null;
}

export interface StatChannelDetailResponse {
  social_channel_id: string;
  channel_name: string;
  username: string | null;
  platform: string;
  user_id: string;
  user_name: string;
  totals: StatMetricTotals;
  posts: StatPostRow[];
  last_synced_at: string | null;
  timeseries_monthly: StatTimeseriesPoint[];
  timeseries_yearly: StatTimeseriesPoint[];
}

export interface StatUserSummary {
  user_id: string;
  user_name: string;
  company_name: string | null;
  channel_count: number;
  post_count: number;
  totals: StatMetricTotals;
  last_synced_at: string | null;
}

export interface StatUserDetailResponse {
  user_id: string;
  user_name: string;
  company_name: string | null;
  totals: StatMetricTotals;
  channels: StatChannelSummary[];
  last_synced_at: string | null;
  timeseries_monthly: StatTimeseriesPoint[];
  timeseries_yearly: StatTimeseriesPoint[];
}

export interface StatDashboardResponse {
  totals: StatMetricTotals;
  user_count: number;
  channel_count: number;
  post_count: number;
  platform_distribution: Record<string, number>;
  users: StatUserSummary[];
  last_synced_at: string | null;
  timeseries_monthly: StatTimeseriesPoint[];
  timeseries_yearly: StatTimeseriesPoint[];
}
