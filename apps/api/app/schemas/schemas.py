import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field

# ==============================================================================
# Authentication Schemas
# ==============================================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AdminResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# User & Group Schemas
# ==============================================================================
class GroupCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class GroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    # Active (non-soft-deleted) member count - set as a transient attribute by
    # list_groups (api/v1/users.py), not a real column on UserGroup.
    user_count: int = 0

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    name: str = Field(..., max_length=255)
    email: EmailStr
    company_name: Optional[str] = Field(None, max_length=255)
    status: str = Field("active", description="active, inactive, suspended")
    notes: Optional[str] = Field(None, max_length=1000)
    referral_link: Optional[str] = Field(None, max_length=1000)
    personal_contacts: Optional[str] = Field(None, max_length=1000)
    group_ids: Optional[List[uuid.UUID]] = None

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)
    referral_link: Optional[str] = Field(None, max_length=1000)
    personal_contacts: Optional[str] = Field(None, max_length=1000)
    group_ids: Optional[List[uuid.UUID]] = None

class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    company_name: Optional[str]
    status: str
    notes: Optional[str]
    referral_link: Optional[str] = None
    personal_contacts: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    groups: List[GroupResponse] = []

    class Config:
        from_attributes = True


class UserSummaryResponse(BaseModel):
    """Counts for the stat cards atop the Utenti list - active/inactive/suspended
    always sum to total (every non-deleted user has exactly one of the 3
    UserStatus values), unlike StatusCountsSummaryResponse below which is a
    generic bucket for statuses that can grow over time."""
    total: int
    active: int
    inactive: int
    suspended: int


class StatusCountsSummaryResponse(BaseModel):
    """Reused for the Campagne and Pubblicazioni list stat cards: total plus a
    raw per-status count, so the frontend can bucket/group statuses into
    fewer cards (see lib/status-buckets.ts) without a backend change every
    time a new status value is introduced."""
    total: int
    by_status: Dict[str, int]


# ==============================================================================
# Buffer Connection & Channel Schemas
# ==============================================================================
class BufferConnectionCreateRequest(BaseModel):
    user_id: uuid.UUID
    api_key: str = Field(min_length=1)

class BufferConnectionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    authentication_type: str
    external_account_id: Optional[str]
    status: str
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class BufferOrganizationResponse(BaseModel):
    id: uuid.UUID
    external_organization_id: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True

class SocialChannelResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    external_channel_id: str
    platform: str
    name: str
    username: Optional[str]
    avatar_url: Optional[str]
    external_link: Optional[str]
    channel_type: Optional[str]
    is_active: bool
    auto_publish_enabled: bool
    publication_mode: str
    last_sync_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==============================================================================
# Media Schemas
# ==============================================================================
class MediaResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    stored_filename: str
    public_url: str
    mime_type: str
    size_bytes: int
    duration_seconds: Optional[float]
    width: Optional[int]
    height: Optional[int]
    aspect_ratio: Optional[str]
    video_codec: Optional[str]
    audio_codec: Optional[str]
    checksum: Optional[str]
    processing_status: str
    validation_status: str
    validation_errors: Optional[List[Dict[str, Any]]]
    created_at: datetime

    class Config:
        from_attributes = True


class MediaRenameRequest(BaseModel):
    original_filename: str = Field(..., min_length=1, max_length=255)


# ==============================================================================
# AI Content Generation Schemas
# ==============================================================================
class AISettingsResponse(BaseModel):
    configured: bool
    model: str


class AISettingsUpdateRequest(BaseModel):
    # None/omitted = leave unchanged. An explicit empty string is rejected by
    # the endpoint (use DELETE /settings/ai to remove the key instead), so this
    # is never ambiguous between "don't touch" and "clear it".
    openai_api_key: Optional[str] = Field(None, min_length=1, max_length=500)
    openai_model: Optional[str] = Field(None, min_length=1, max_length=100)


class AIGenerateTextRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=1000)
    # Current state of the wizard's "Includi link referral" checkbox at
    # generation time - shrinks the x_text/threads_text targets asked of the
    # model so generated text already leaves room (see openai/client.py).
    include_referral_link: bool = False
    # Same idea as include_referral_link above, but for the "Includi contatti
    # personali" checkbox (see openai/client.py PERSONAL_CONTACTS_RESERVED_CHARS).
    include_personal_contacts: bool = False


class AIGenerateTextResponse(BaseModel):
    default_text: str
    instagram_text: str
    facebook_text: str
    linkedin_text: str
    tiktok_text: str
    x_text: str
    threads_text: str
    youtube_title: str
    youtube_description: str


# ==============================================================================
# Campaign & Targeting Schemas
# ==============================================================================
class CampaignCreate(BaseModel):
    title: str = Field(..., max_length=255)
    default_text: str = Field(..., max_length=5000)
    instagram_text: Optional[str] = Field(None, max_length=5000)
    facebook_text: Optional[str] = Field(None, max_length=5000)
    linkedin_text: Optional[str] = Field(None, max_length=5000)
    tiktok_text: Optional[str] = Field(None, max_length=5000)
    youtube_title: Optional[str] = Field(None, max_length=100)
    youtube_description: Optional[str] = Field(None, max_length=5000)
    x_text: Optional[str] = Field(None, max_length=280)
    threads_text: Optional[str] = Field(None, max_length=500)
    media_file_id: Optional[uuid.UUID] = None
    publishing_mode: str = Field("immediate", description="immediate, scheduled, buffer_queue, draft, approval")
    scheduled_at: Optional[datetime] = None
    timezone: str = "UTC"
    targeting_mode: str = "all_active_channels"
    targeting_params: Dict[str, Any] = Field(default_factory=dict, description="Must match targeting mode selections")
    # Set only when this campaign was created via Blog Writer's "Usa per campagna
    # social" - purely informational (see Campaign.article_id), never required.
    article_id: Optional[uuid.UUID] = None
    # Off by default. When on, each target's resolved text gets that target's
    # owning user's own referral_link appended (see campaign_resolver.py) - a
    # user with no referral_link configured is unaffected either way.
    include_referral_link: bool = False
    # Off by default, same mechanics as include_referral_link but for the
    # owning user's personal_contacts signature block, appended right after
    # the referral link (see campaign_resolver.py).
    include_personal_contacts: bool = False

class CampaignResponse(BaseModel):
    id: uuid.UUID
    title: str
    default_text: str
    instagram_text: Optional[str] = None
    facebook_text: Optional[str] = None
    linkedin_text: Optional[str] = None
    tiktok_text: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_description: Optional[str] = None
    x_text: Optional[str] = None
    threads_text: Optional[str] = None
    publishing_mode: str
    scheduled_at: Optional[datetime]
    timezone: str
    targeting_mode: str
    include_referral_link: bool = False
    include_personal_contacts: bool = False
    # Targeting params used at launch (e.g. {"channel_ids": [...]}), needed to
    # reproduce the same recipient selection when duplicating a campaign.
    metadata_json: Optional[Dict[str, Any]] = None
    status: str
    media_file_id: Optional[uuid.UUID]
    # Same attribute name as the Campaign.media_file SQLAlchemy relationship,
    # so from_attributes resolves it automatically - used for the small
    # thumbnail next to the campaign title in the "Campagne" list (eager-
    # loaded in list_campaigns via joinedload to avoid N+1).
    media_file: Optional[MediaResponse] = None
    article_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class CampaignPreviewResponse(BaseModel):
    estimated_publications_count: int
    total_users_targeted: int
    platform_distribution: Dict[str, int]
    channels_requiring_notification_approval: int
    excluded_channels_count: int
    total_active_users: int

class CampaignDetailResponse(BaseModel):
    campaign: CampaignResponse
    media: Optional[MediaResponse]
    stats: Dict[str, int]
    progress_percentage: float

    class Config:
        from_attributes = True


class PostMetricValue(BaseModel):
    type: str
    name: str
    value: float
    unit: str


class ChannelMetrics(BaseModel):
    publication_id: uuid.UUID
    social_channel_id: uuid.UUID
    channel_name: str
    user_name: str
    platform: str
    external_post_url: Optional[str] = None
    metrics: List[PostMetricValue] = []
    metrics_updated_at: Optional[datetime] = None
    error: Optional[str] = None


class CampaignMetricsResponse(BaseModel):
    # Sum of each metric type across every channel that returned data (e.g.
    # {"reactions": 45, "views": 900, "follows": 3}). A metric type absent here
    # means no channel in this campaign reported it, not that it was zero.
    totals: Dict[str, float]
    channels: List[ChannelMetrics]


# ==============================================================================
# Publication Schemas
# ==============================================================================
class PublicationResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    user_id: uuid.UUID
    social_channel_id: uuid.UUID
    external_channel_id: str
    status: str
    attempt_count: int
    max_attempts: int
    idempotency_key: str
    scheduled_at: Optional[datetime]
    next_attempt_at: Optional[datetime]
    processing_started_at: Optional[datetime]
    submitted_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    published_at: Optional[datetime]
    external_post_id: Optional[str]
    external_post_url: Optional[str]
    error_category: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PublicationFeedItem(BaseModel):
    """
    One card in the "Bacheca" feed (GET /publications/feed) - a Facebook-style
    view of everything actually published, most recent first. Deliberately
    NOT built from the Publication ORM row alone (from_attributes wouldn't
    reach into Campaign/SocialChannel/CampaignTarget/MediaFile) - constructed
    manually in the endpoint from a joined query instead, same spirit as
    ChannelMetrics/CampaignMetricsResponse above.
    """
    id: uuid.UUID
    campaign_id: uuid.UUID
    published_at: Optional[datetime]
    # Per-channel resolved text (CampaignTarget.resolved_text), not
    # Campaign.default_text - reflects the platform override/referral link
    # actually posted, same text the target channel received.
    text: str
    external_post_url: Optional[str]
    # Stable key for the frontend's per-channel filter dropdown - channel_name
    # alone isn't guaranteed unique (two channels can share a display name).
    social_channel_id: uuid.UUID
    platform: str
    channel_name: str
    channel_avatar_url: Optional[str]
    # SocialChannel.external_link - the real profile/page on the platform
    # itself (populated by the Buffer sync), same field the "Canali social"
    # table links the channel name to. Null if Buffer never exposed it for
    # that platform (see DATABASE.md SS5).
    channel_external_link: Optional[str]
    # Publication.user_id -> User.name - the client/customer this channel
    # belongs to (see DATABASE.md SS4), shown alongside channel_name in the
    # channel picker so two channels with a similar name aren't ambiguous.
    user_name: str
    media: Optional[MediaResponse] = None

    class Config:
        from_attributes = True

class PublicationAttemptResponse(BaseModel):
    id: uuid.UUID
    publication_id: uuid.UUID
    attempt_number: int
    started_at: datetime
    completed_at: Optional[datetime]
    success: bool
    http_status: Optional[int]
    external_error_code: Optional[str]
    error_category: Optional[str]
    error_message: Optional[str]
    sanitized_request: Optional[Dict[str, Any]]
    sanitized_response: Optional[Dict[str, Any]]
    duration_ms: Optional[int]

    class Config:
        from_attributes = True

class PublicationDetailResponse(BaseModel):
    publication: PublicationResponse
    attempts: List[PublicationAttemptResponse]
    resolved_text: str
    channel_name: str
    channel_platform: str
    user_name: str
    # Public profile/page URL of the destination channel itself (SocialChannel.
    # external_link, populated by Buffer sync) - shown as a fallback "view
    # profile" link when publication.external_post_url isn't populated yet
    # (see campaign_resolver docs / prod_client.py get_post_metrics comments on
    # why the specific-post link can take a while to become available).
    channel_external_link: Optional[str] = None
    media: Optional[MediaResponse] = None


# ==============================================================================
# System & Settings Schemas
# ==============================================================================
class SystemSettingsUpdate(BaseModel):
    global_concurrency_limit: int = Field(..., ge=1, le=100)
    concurrent_jobs_per_connection: int = Field(..., ge=1, le=20)
    pause_between_requests_seconds: int = Field(..., ge=0, le=120)
    max_publication_attempts: int = Field(..., ge=1, le=10)
    upload_max_size_bytes: int = Field(..., ge=1024*1024)

class SystemSettingsResponse(BaseModel):
    global_concurrency_limit: int
    concurrent_jobs_per_connection: int
    pause_between_requests_seconds: int
    max_publication_attempts: int
    upload_max_size_bytes: int
    buffer_integration_mode: str
    celery_queue_health: str = "ok"

class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    celery_worker: str
    timestamp: datetime


# ==============================================================================
# Blog Writer AI Schemas
# ==============================================================================

class WordpressSiteCreate(BaseModel):
    user_id: Optional[uuid.UUID] = None
    name: str = Field(..., max_length=255)
    site_url: str = Field(..., max_length=1000)
    api_url: str = Field(..., max_length=1000, description="WordPress REST API root, e.g. https://example.com/wp-json")
    username: str = Field(..., max_length=255)
    application_password: str = Field(..., min_length=1, max_length=500)
    default_author_id: Optional[int] = None
    default_category_id: Optional[int] = None
    default_status: str = Field("draft", description="publish, draft, pending, private")
    language: str = Field("it", max_length=10)


class WordpressSiteUpdate(BaseModel):
    user_id: Optional[uuid.UUID] = None
    name: Optional[str] = Field(None, max_length=255)
    site_url: Optional[str] = Field(None, max_length=1000)
    api_url: Optional[str] = Field(None, max_length=1000)
    username: Optional[str] = Field(None, max_length=255)
    # Omitted = keep existing password. Present = replace it. There is no
    # "clear the password" case - a site without one can't publish, so removal
    # only happens via DELETE on the whole site.
    application_password: Optional[str] = Field(None, min_length=1, max_length=500)
    default_author_id: Optional[int] = None
    default_category_id: Optional[int] = None
    default_status: Optional[str] = None
    language: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None


class WordpressSiteResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    site_url: str
    api_url: str
    username: str
    default_author_id: Optional[int]
    default_author_name: Optional[str]
    default_category_id: Optional[int]
    default_category_name: Optional[str]
    default_status: str
    language: str
    is_active: bool
    connection_status: str
    last_connection_test_at: Optional[datetime]
    last_connection_error: Optional[str]
    last_published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WordpressOptionItem(BaseModel):
    id: int
    name: str


class WordpressTestConnectionResponse(BaseModel):
    success: bool
    message: str
    wp_user_name: Optional[str] = None


class BlogArticleGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    goal: Optional[str] = Field(None, max_length=500)
    target_audience: Optional[str] = Field(None, max_length=500)
    language: str = Field("it", max_length=10)
    tone: Optional[str] = Field(None, max_length=100)
    length: str = Field("medium", description="short, medium, long")
    primary_keyword: Optional[str] = Field(None, max_length=255)
    secondary_keywords: List[str] = Field(default_factory=list)
    must_include: Optional[str] = Field(None, max_length=1000)
    must_avoid: Optional[str] = Field(None, max_length=1000)
    call_to_action: Optional[str] = Field(None, max_length=255)
    hashtag_count: int = Field(5, ge=0, le=15)
    wordpress_site_id: Optional[uuid.UUID] = None
    wordpress_category_id: Optional[int] = None
    user_id: Optional[uuid.UUID] = None


class BlogArticleCreateRequest(BaseModel):
    """Manual creation - no AI call. See POST /blog-writer/articles/."""
    title: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=1000)
    content: str = Field(..., min_length=1)
    hashtags: List[str] = Field(default_factory=list)
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    language: str = Field("it", max_length=10)
    user_id: Optional[uuid.UUID] = None


class BlogArticleUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=1000)
    content: Optional[str] = None
    hashtags: Optional[List[str]] = None
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    # Explicit sentinel: omitted = leave unchanged, empty string = detach the
    # current media, a UUID string = attach that media. A plain Optional[UUID]
    # can't tell "don't touch" apart from "clear it" the way this can.
    media_file_id: Optional[str] = None


class BlogPublicationResponse(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    wordpress_site_id: uuid.UUID
    wordpress_site_name: str
    wordpress_post_id: Optional[int]
    wordpress_post_url: Optional[str]
    wordpress_status: Optional[str]
    publication_status: str
    error_message: Optional[str]
    retry_count: int
    published_at: Optional[datetime]
    created_at: datetime


class BlogArticleResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    title: str
    slug: str
    excerpt: Optional[str]
    content: str
    media_file_id: Optional[uuid.UUID] = None
    hashtags: Optional[List[str]]
    primary_keyword: Optional[str]
    secondary_keywords: Optional[List[str]]
    meta_title: Optional[str]
    meta_description: Optional[str]
    language: str
    tone: Optional[str]
    target_audience: Optional[str]
    article_goal: Optional[str]
    generation_model: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    last_edited_at: Optional[datetime]
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class BlogArticleDetailResponse(BaseModel):
    article: BlogArticleResponse
    publications: List[BlogPublicationResponse]
    social_campaigns: List[CampaignResponse]


class BlogArticleListItem(BaseModel):
    id: uuid.UUID
    title: str
    language: str
    status: str
    created_at: datetime
    updated_at: datetime
    sites_count: int
    publications_count: int


class BlogPublishTarget(BaseModel):
    wordpress_site_id: uuid.UUID
    category_id: Optional[int] = None
    author_id: Optional[int] = None
    status: Optional[str] = Field(None, description="Overrides the site's default_status for this publish")


class BlogArticlePublishRequest(BaseModel):
    targets: List[BlogPublishTarget] = Field(..., min_length=1)


class SocialPreviewRequest(BaseModel):
    wordpress_site_id: Optional[uuid.UUID] = Field(
        None, description="Which published URL to use if the article is on multiple sites"
    )


class SocialPreviewResponse(BaseModel):
    article_url: str
    default_text: str
    instagram_text: str
    facebook_text: str
    linkedin_text: str
    x_text: str
    threads_text: str


class BlogWriterDashboardResponse(BaseModel):
    draft_count: int
    ready_count: int
    published_count: int
    failed_publications_count: int
    sites_count: int
    sites_error_count: int
    social_campaigns_count: int
    recent_articles: List[BlogArticleListItem]
    recent_publications: List[BlogPublicationResponse]


# ==============================================================================
# Omnichannel Responder - AI unified inbox (independent add-on module).
# Every *Response schema below mirrors a table in app/models/omnichannel.py
# 1:1; none of them are ever returned without the caller's own owner_id
# scoping already applied at the query level (see app/api/v1/omnichannel.py).
# ==============================================================================
class OmniChannelAccountCreate(BaseModel):
    channel: str  # telegram, whatsapp, instagram, facebook, gmail, mock
    name: str
    # WhatsApp only: the Phone Number ID from WhatsApp Manager. Gmail only:
    # the Gmail address itself (used as the IMAP/SMTP username) - neither is
    # a secret, so both reuse this field rather than adding a new one.
    external_account_id: Optional[str] = None
    access_token: Optional[str] = Field(None, description="Plaintext token/secret, encrypted at rest server-side and never echoed back. For Facebook/Instagram this is the Page/IG Access Token; for WhatsApp, the Cloud API access token; for Gmail, an App Password (not the account's login password).")
    # Meta channels only (facebook/instagram/whatsapp): the App Secret, used
    # to verify inbound webhook signatures (X-Hub-Signature-256) - see
    # connectors/facebook.py, connectors/whatsapp.py. Combined with
    # access_token into a single encrypted JSON blob server-side
    # (OmnichannelService.create_channel_account); ignored by telegram/gmail/mock.
    app_secret: Optional[str] = Field(None, description="Facebook/Instagram/WhatsApp only: Meta App Secret, used to verify webhook signatures")
    config: Optional[Dict[str, Any]] = None


class OmniChannelAccountUpdate(BaseModel):
    """
    Fills in/rotates credentials after creation - e.g. a WhatsApp channel
    created with no credentials yet just to get its webhook_secret for
    Meta's Webhooks screen, completed once real Cloud API credentials exist.
    None/omitted = leave unchanged, same convention as AISettingsUpdateRequest:
    a blank access_token never silently wipes an already-configured one.
    """
    name: Optional[str] = None
    external_account_id: Optional[str] = None
    access_token: Optional[str] = Field(None, description="Plaintext token/secret - only re-encrypted if provided")
    app_secret: Optional[str] = Field(None, description="Facebook/Instagram/WhatsApp only")
    config: Optional[Dict[str, Any]] = None


class OmniChannelAccountResponse(BaseModel):
    id: uuid.UUID
    channel: str
    name: str
    external_account_id: Optional[str]
    status: str
    webhook_secret: str
    config: Optional[Dict[str, Any]] = Field(None, validation_alias="config_json", serialization_alias="config")
    created_at: datetime
    updated_at: datetime
    # Number of conversations on this channel (one per customer who has ever
    # written in, not one per message) - transient attribute set by
    # list_channel_accounts (api/v1/omnichannel.py), not a real column.
    conversation_count: int = 0

    class Config:
        from_attributes = True
        populate_by_name = True


class OmniCustomerIdentityResponse(BaseModel):
    id: uuid.UUID
    channel: str
    external_user_id: str
    display_name: Optional[str]

    class Config:
        from_attributes = True


class OmniCustomerResponse(BaseModel):
    id: uuid.UUID
    name: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    language: Optional[str]
    timezone: Optional[str]
    notes: Optional[str]
    is_blocked: bool
    created_at: datetime
    last_contact_at: Optional[datetime]
    identities: List[OmniCustomerIdentityResponse] = []

    class Config:
        from_attributes = True


class OmniCustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[str] = None


class OmniTagResponse(BaseModel):
    id: uuid.UUID
    name: str
    color: Optional[str]

    class Config:
        from_attributes = True


class OmniTagCreate(BaseModel):
    name: str
    color: Optional[str] = None


class OmniMessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    sender_type: str
    text: Optional[str]
    message_type: str
    attachments: Optional[List[Dict[str, Any]]] = Field(None, validation_alias="attachments_json", serialization_alias="attachments")
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class OmniMessageCreate(BaseModel):
    """Manual outbound message sent directly by an operator (bypasses the AI draft workflow)."""
    text: str = Field(..., min_length=1, max_length=5000)


class OmniBroadcastRequest(BaseModel):
    """
    Bulk send to multiple existing conversations at once ("message everyone
    who's contacted me"). conversation_ids=None (or empty) means every
    eligible conversation for this owner - see api/v1/omnichannel.py::
    send_broadcast for exactly what "eligible" excludes (blocked customers,
    archived/spam conversations).
    """
    text: str = Field(..., min_length=1, max_length=5000)
    conversation_ids: Optional[List[uuid.UUID]] = None


class OmniBroadcastFailure(BaseModel):
    conversation_id: uuid.UUID
    customer_name: Optional[str]
    channel: str
    error: str


class OmniBroadcastResult(BaseModel):
    total_targeted: int
    sent: int
    failed: int
    failures: List[OmniBroadcastFailure]


class OmniAIDraftResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    source_message_id: Optional[uuid.UUID]
    original_ai_text: Optional[str]
    edited_text: Optional[str]
    status: str
    model: Optional[str]
    confidence_score: Optional[float]
    sensitive_category: Optional[str]
    failure_reason: Optional[str]
    created_at: datetime
    approved_at: Optional[datetime]
    sent_at: Optional[datetime]

    class Config:
        from_attributes = True


class OmniAIDraftEditRequest(BaseModel):
    edited_text: str = Field(..., min_length=1, max_length=5000)


class OmniInternalNoteCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    mentions: Optional[List[str]] = None


class OmniInternalNoteResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    admin_id: Optional[uuid.UUID]
    text: str
    mentions: Optional[List[str]] = Field(None, validation_alias="mentions_json", serialization_alias="mentions")
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class OmniConversationAssignRequest(BaseModel):
    assigned_admin_id: Optional[uuid.UUID] = None


class OmniConversationListItem(BaseModel):
    id: uuid.UUID
    status: str
    channel: str
    channel_account_name: str
    customer: OmniCustomerResponse
    assigned_admin_id: Optional[uuid.UUID]
    unread_count: int
    last_message_at: Optional[datetime]
    last_message_preview: Optional[str]
    tags: List[OmniTagResponse] = []


class OmniConversationDetailResponse(BaseModel):
    id: uuid.UUID
    status: str
    channel: str
    channel_account_id: uuid.UUID
    # Which specific connected account (e.g. which of several Telegram bots)
    # this conversation belongs to - distinct from `channel` (the channel
    # type, e.g. "telegram"), which alone can't tell two bots of the same
    # type apart. See OmniConversationListItem, which already has this.
    channel_account_name: str
    customer: OmniCustomerResponse
    assigned_admin_id: Optional[uuid.UUID]
    unread_count: int
    created_at: datetime
    updated_at: datetime
    tags: List[OmniTagResponse] = []
    messages: List[OmniMessageResponse] = []
    drafts: List[OmniAIDraftResponse] = []
    notes: List[OmniInternalNoteResponse] = []


class OmniAIAgentConfigResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    system_prompt: Optional[str]
    language: str
    tone: str
    temperature: float
    company_description: Optional[str]
    allowed_topics: Optional[List[str]] = Field(None, validation_alias="allowed_topics_json", serialization_alias="allowed_topics")
    forbidden_topics: Optional[List[str]] = Field(None, validation_alias="forbidden_topics_json", serialization_alias="forbidden_topics")
    signature: Optional[str]
    max_context_messages: int
    knowledge_base_enabled: bool
    automatic_language_detection: bool
    auto_generate_draft: bool
    response_mode: str
    sensitive_categories: Optional[List[str]] = Field(None, validation_alias="sensitive_categories_json", serialization_alias="sensitive_categories")

    class Config:
        from_attributes = True
        populate_by_name = True


class OmniAIAgentConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    language: Optional[str] = None
    tone: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    company_description: Optional[str] = None
    allowed_topics: Optional[List[str]] = None
    forbidden_topics: Optional[List[str]] = None
    signature: Optional[str] = None
    max_context_messages: Optional[int] = Field(None, ge=1, le=100)
    knowledge_base_enabled: Optional[bool] = None
    automatic_language_detection: Optional[bool] = None
    auto_generate_draft: Optional[bool] = None
    # MANUAL, APPROVAL_REQUIRED (default), AUTO_REPLY - validated server-side
    # (api/v1/omnichannel.py) and audited on every change (AI_RESPONSE_MODE_
    # CHANGED). AUTO_REPLY never applies to a sensitive-topic draft regardless
    # of this setting - see omnichannel_draft_service.py module docstring.
    response_mode: Optional[str] = None
    sensitive_categories: Optional[List[str]] = None


class OmniKnowledgeDocumentCreate(BaseModel):
    title: str
    source_type: str = "manual"  # manual, faq, url, txt (pdf/docx parsing not implemented in this MVP)
    content_text: Optional[str] = None
    source_url: Optional[str] = None


class OmniKnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    content_text: Optional[str]
    source_url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OmniNotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    read_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class OmniSimulateMessageRequest(BaseModel):
    """Dev-only ingestion path - only accepted for channel_accounts of type 'mock' (see api/v1/omnichannel_webhooks.py)."""
    channel_account_id: uuid.UUID
    external_user_id: str = Field(..., description="Fake per-channel id of the simulated customer, e.g. 'test-user-1'")
    customer_name: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=5000)


# ==============================================================================
# Statistics Module Schemas (see docs/STATISTICS.md)
# ==============================================================================
class StatMetricTotals(BaseModel):
    """Same shape/semantics as CampaignMetricsResponse.totals: sums per metric
    type, with percentage-unit metrics (engagementRate) averaged, not summed -
    see docs/STATISTICS.md."""
    reactions: Optional[float] = None
    likes: Optional[float] = None
    views: Optional[float] = None
    impressions: Optional[float] = None
    reach: Optional[float] = None
    follows: Optional[float] = None
    clicks: Optional[float] = None
    comments: Optional[float] = None
    shares: Optional[float] = None
    engagement_rate: Optional[float] = None


class StatTimeseriesPoint(BaseModel):
    """One bucket of a monthly/annual trend chart - period is "YYYY-MM" for
    monthly buckets, "YYYY" for annual ones, bucketed by the post's
    published_at (when it went out), not by when we last synced its metrics
    (see statistics_service.timeseries)."""
    period: str
    post_count: int
    totals: StatMetricTotals


class StatSyncRunResponse(BaseModel):
    id: uuid.UUID
    scope: str
    scope_user_id: Optional[uuid.UUID]
    scope_campaign_id: Optional[uuid.UUID]
    status: str
    total_posts: int
    synced_posts: int
    failed_posts: int
    skipped_posts: int
    error_message: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class StatSyncDispatchResponse(BaseModel):
    sync_run_id: uuid.UUID
    message: str


class StatPostRow(BaseModel):
    """One synced post, as shown in a channel's campaign/post list."""
    publication_id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_title: str
    platform: str
    external_post_url: Optional[str]
    published_at: Optional[datetime]
    metrics: StatMetricTotals
    last_synced_at: Optional[datetime]
    last_sync_error: Optional[str]


class StatChannelSummary(BaseModel):
    social_channel_id: uuid.UUID
    channel_name: str
    username: Optional[str]
    platform: str
    post_count: int
    totals: StatMetricTotals
    last_synced_at: Optional[datetime]


class StatChannelDetailResponse(BaseModel):
    social_channel_id: uuid.UUID
    channel_name: str
    username: Optional[str]
    platform: str
    user_id: uuid.UUID
    user_name: str
    totals: StatMetricTotals
    posts: List[StatPostRow]
    last_synced_at: Optional[datetime]
    timeseries_monthly: List[StatTimeseriesPoint]
    timeseries_yearly: List[StatTimeseriesPoint]


class StatUserSummary(BaseModel):
    user_id: uuid.UUID
    user_name: str
    company_name: Optional[str]
    channel_count: int
    post_count: int
    totals: StatMetricTotals
    last_synced_at: Optional[datetime]


class StatUserDetailResponse(BaseModel):
    user_id: uuid.UUID
    user_name: str
    company_name: Optional[str]
    totals: StatMetricTotals
    channels: List[StatChannelSummary]
    last_synced_at: Optional[datetime]
    timeseries_monthly: List[StatTimeseriesPoint]
    timeseries_yearly: List[StatTimeseriesPoint]


class StatDashboardResponse(BaseModel):
    totals: StatMetricTotals
    user_count: int
    channel_count: int
    post_count: int
    platform_distribution: Dict[str, int]
    users: List[StatUserSummary]
    last_synced_at: Optional[datetime]
    timeseries_monthly: List[StatTimeseriesPoint]
    timeseries_yearly: List[StatTimeseriesPoint]


class PublicPlatformStats(BaseModel):
    """One platform's aggregate totals for the public marketing site - no
    user/channel identifier, see app/api/v1/public_stats.py."""
    platform: str
    post_count: int
    totals: StatMetricTotals


class PublicStatsResponse(BaseModel):
    """Anonymous, aggregate-only snapshot exposed without authentication to
    the public marketing site (agimarketing.app) - see
    app/api/v1/public_stats.py and docs/STATISTICS.md."""
    post_count: int
    campaign_count: int
    channel_count: int
    active_user_count: int
    totals: StatMetricTotals
    platforms: List[PublicPlatformStats]
    last_synced_at: Optional[datetime]
