import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # General
    ENVIRONMENT: str = "local"
    PROJECT_NAME: str = "Agi Post"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(default="supersecretjwtkeyforadminauthsocialpublisher123!")
    ENCRYPTION_KEY: str = Field(default="38x26P_s-Ld_j4pL9V10L1-82h0YF6p2-LpE10d9Y2I=")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Databases
    DATABASE_URL: str = Field(default="postgresql+psycopg://postgres:postgres_secure_pass_123@db:5432/agi_post")
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # Buffer API - connections authenticate with a per-user personal API key
    # pasted into the dashboard, not OAuth (see app/integrations/buffer/client.py)
    BUFFER_INTEGRATION_MODE: str = "mock"  # "mock" or "production"

    # bundle.social: multi-tenant provider where ONE platform key serves every
    # end user, who is identified by team id instead. Keep "mock" until the
    # production client is completed - see
    # app/integrations/bundle_social/prod_client.py.
    BUNDLE_SOCIAL_INTEGRATION_MODE: str = "mock"  # "mock" or "production"
    BUNDLE_SOCIAL_API_KEY: str = ""
    # Every connection of this provider shares one upstream quota, so its
    # concurrency is capped per provider rather than per connection
    # (see services/rate_limiter.py).
    BUNDLE_SOCIAL_CONCURRENCY_LIMIT: int = 4
    # Public origin of the portal, used to build the return URL of the hosted
    # OAuth flow. Must be the address the END USER sees in their browser, not an
    # internal one, or the provider bounces them somewhere unreachable.
    PORTAL_PUBLIC_BASE_URL: str = "http://localhost:3000"
    # Logo shown on the provider's hosted connect page, so the step looks like
    # ours. Must be a public absolute URL the provider can load.
    PORTAL_BRAND_LOGO_URL: str = ""
    # Shared secret from the provider's webhook dashboard, used to verify the
    # HMAC-SHA256 signature on incoming deliveries. Empty = webhook disabled.
    BUNDLE_SOCIAL_WEBHOOK_SECRET: str = ""

    # OpenAI - optional, powers the campaign wizard's AI text-generation helper
    # (app/integrations/openai/client.py). Feature is hidden in the dashboard
    # when unset; never exposed to the frontend, requests are proxied server-side.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Media Storage
    UPLOAD_MAX_SIZE_BYTES: int = 524288000  # 500MB - see infrastructure/nginx/nginx.conf client_max_body_size, must match
    MEDIA_STORAGE_DIR: str = "/storage/uploads"
    THUMBNAIL_STORAGE_DIR: str = "/storage/thumbnails"
    # Public origin the "media" nginx vhost is reachable at (see
    # infrastructure/nginx/nginx.conf). Must be HTTPS in production - Buffer
    # fetches media by URL and requires it to be public HTTPS.
    PUBLIC_MEDIA_BASE_URL: str = "http://localhost:8080"
    TEMPORARY_STORAGE_DIR: str = "/storage/temporary"

    # Concurrency & Policies
    GLOBAL_CONCURRENCY_LIMIT: int = 5
    CONCURRENT_JOBS_PER_CONNECTION: int = 1
    PAUSE_BETWEEN_REQUESTS_SECONDS: int = 10
    # Randomness added to the pause above. A request landing on exactly the same
    # interval every time is itself a machine signature; a few seconds of jitter
    # makes the cadence irregular at no cost.
    PAUSE_JITTER_SECONDS: int = 5
    # Minimum spacing between two posts on the SAME channel. This is the limit
    # that protects a promoter's own account: what a platform sees is one
    # profile's posting frequency, not our aggregate throughput. Set to 0 to
    # disable (not recommended with a shared-quota provider, where nothing else
    # would space out two campaigns hitting the same profile).
    MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL: int = 900
    MAX_PUBLICATION_ATTEMPTS: int = 5

    # Retry sequence in seconds (comma-separated list parsed by property)
    RETRY_BACKOFF_SEQUENCE_SECONDS: str = "60,300,900,3600,21600"

    @property
    def retry_backoff_list(self) -> List[int]:
        try:
            return [int(x.strip()) for x in self.RETRY_BACKOFF_SEQUENCE_SECONDS.split(",")]
        except ValueError:
            return [60, 300, 900, 3600, 21600]

    # Ensure storage paths exist
    def create_directories(self) -> None:
        for path in [self.MEDIA_STORAGE_DIR, self.THUMBNAIL_STORAGE_DIR, self.TEMPORARY_STORAGE_DIR]:
            os.makedirs(path, exist_ok=True)

settings = Settings()
# Execute directory creation during startup configuration parsing
try:
    settings.create_directories()
except Exception:
    # Fail silently if running in environments where storage volumes aren't mounted yet (e.g., local builds)
    pass
