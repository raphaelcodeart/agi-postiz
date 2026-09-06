"""
In-memory bundle.social client for development and tests.

Mirrors ``MockBufferClient`` in shape so the two providers are exercised through
the same code paths, but tags every identifier with ``bs_`` and the team ref, so
a channel's origin is obvious while debugging and the two providers can never be
confused for one another in a test assertion.

Never active in production: selection happens in
``app/integrations/providers.py`` via ``BUNDLE_SOCIAL_INTEGRATION_MODE``
(AGENTS.md rule 16).
"""
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import (
    BufferApiError,
    BufferRateLimitError,
    BufferServerError,
)

# Platforms bundle.social covers that Buffer does not - the reason for adding
# the provider at all. Kept short and deterministic for tests.
_MOCK_PLATFORMS = [
    ("instagram", "profile"),
    ("facebook", "page"),
    ("tiktok", "profile"),
    ("linkedin", "profile"),
    ("youtube", "channel"),
    ("threads", "profile"),
    ("bluesky", "profile"),
    ("mastodon", "profile"),
]


class MockBundleSocialClient(BaseBufferClient):
    def __init__(self, account_ref: Optional[str] = None):
        # The bundle.social team id standing in for "this end user".
        self.account_ref = account_ref or "team_mock"

    # -- identity -----------------------------------------------------------

    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        if not api_key:
            raise BufferApiError("Chiave piattaforma mancante.", category="auth_error")
        return {
            "id": self.account_ref,
            "name": f"Team {self.account_ref}",
            "provider": "bundle_social",
        }

    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        """
        bundle.social has one team per end user, so a connection always maps to
        exactly one organization - unlike Buffer, where an account can own
        several. Returning a single-element list keeps sync.py unchanged.
        """
        return [
            {
                "id": self.account_ref,
                "name": f"Team {self.account_ref}",
                "raw": {"provider": "bundle_social", "team_id": self.account_ref},
            }
        ]

    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        seed = int(hashlib.sha256(organization_id.encode()).hexdigest()[:8], 16)
        # Deterministic subset so tests are stable but different teams differ.
        count = 2 + (seed % 3)
        channels = []
        for index in range(count):
            platform, channel_type = _MOCK_PLATFORMS[(seed + index) % len(_MOCK_PLATFORMS)]
            handle = f"{platform}_{organization_id}_{index}"
            channels.append(
                {
                    "id": f"bs_{handle}",
                    "platform": platform,
                    "name": f"{platform.title()} · {organization_id}",
                    "username": handle,
                    "avatar_url": None,
                    "external_link": f"https://example.invalid/{platform}/{handle}",
                    "channel_type": channel_type,
                    "raw": {"provider": "bundle_social", "team_id": organization_id},
                }
            )
        return channels

    # -- publishing ---------------------------------------------------------

    def create_post(
        self,
        api_key: str,
        channel_id: str,
        text: str,
        media_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        media_type: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        platform: Optional[str] = None,
        youtube_title: Optional[str] = None,
        video_duration_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        # Same magic strings as MockBufferClient so failure-path tests can drive
        # either provider identically.
        if "simulate-fail-temp-429" in text:
            raise BufferRateLimitError("Rate limit simulato (bundle.social).")
        if "simulate-fail-temp-500" in text:
            raise BufferServerError("Errore server simulato (bundle.social).")
        if "simulate-fail-perm" in text:
            raise BufferApiError(
                "Errore permanente simulato (bundle.social).",
                status_code=400,
                category="validation_failed",
            )

        digest = hashlib.sha256(f"{channel_id}:{text}:{scheduled_at}".encode()).hexdigest()[:16]
        post_id = f"bs_post_{digest}"
        return {
            "id": post_id,
            "url": f"https://example.invalid/post/{post_id}",
            "status": "scheduled" if scheduled_at else "sent",
            "provider": "bundle_social",
        }

    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        return {"id": external_post_id, "status": "sent", "provider": "bundle_social"}

    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        """
        Deterministic pseudo-metrics seeded by post id, in the same normalized
        shape the statistics module already consumes from Buffer.
        """
        seed = int(hashlib.sha256(external_post_id.encode()).hexdigest()[:8], 16)
        return {
            "impressions": seed % 5000,
            "reach": seed % 4000,
            "likes": seed % 400,
            "comments": seed % 60,
            "shares": seed % 30,
            "clicks": seed % 120,
            "video_views": seed % 2500,
            "saves": seed % 45,
            "follows_gained": seed % 12,
            "provider": "bundle_social",
        }
