"""
PLACEHOLDER - production bundle.social client (AGENTS.md rule 15).

This file deliberately contains NO request or response mapping. The endpoint
*names* below are taken from bundle.social's public documentation, but their
exact payloads, field names and error shapes have not been observed against a
live account, and AGENTS.md rule 14 forbids inventing an external API's
behaviour. Guessing here would produce code that looks finished, passes review,
and fails on the first real campaign.

WHAT IS KNOWN (bundle.social public docs, September 2026):

  - one platform API key authenticates every request; the end user is
    identified by *team*, created one per customer;
  - ``POST`` create team, ``GET`` list teams / organization;
  - a hosted "connect link" returns a URL the end user opens to authorise their
    own social account - bundle.social renders the OAuth UI and channel picker;
  - posts: create, list, delete, update status;
  - analytics: per-post and per-account, each in a *normalized* form (likes,
    comments, shares, views / followers, reach, impressions) and a *raw* form
    returned exactly as the platform gave it;
  - bulk post analytics accepts at most 60 posts per request, 20 per page.

TO COMPLETE THIS FILE, in order:

  1. Open a bundle.social account (the free tier is enough: 3 channels).
  2. Connect one real channel through the hosted connect link.
  3. Capture real request/response pairs for: create team, connect link, create
     post, get post analytics (normalized *and* raw).
  4. Fill in the methods below from those captures, mapping the analytics
     fields onto the keys ``app/tasks/statistics.py`` already consumes.
  5. Record the captured responses as fixtures and write the unit tests against
     them, never against invented payloads.

Until then ``BUNDLE_SOCIAL_INTEGRATION_MODE`` must stay ``mock``. Selecting
``production`` raises immediately and loudly rather than sending malformed
requests to a real API on behalf of real users.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import BufferApiError

API_BASE = "https://api.bundle.social/api/v1"

_NOT_IMPLEMENTED = (
    "Client bundle.social di produzione non ancora implementato: il contratto "
    "dell'API va prima verificato su un account reale (vedi le istruzioni in "
    "app/integrations/bundle_social/prod_client.py). Tenere "
    "BUNDLE_SOCIAL_INTEGRATION_MODE=mock finché non è completato."
)


class ProductionBundleSocialClient(BaseBufferClient):
    def __init__(self, account_ref: Optional[str] = None):
        self.account_ref = account_ref
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

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
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")

    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        raise BufferApiError(_NOT_IMPLEMENTED, category="configuration_error")
