import abc
from datetime import datetime
from typing import Dict, Any, List, Optional

class BaseBufferClient(abc.ABC):
    """
    Buffer connections authenticate with a per-account personal API key
    (Bearer token), not OAuth: Buffer's legacy REST API has stopped accepting
    new third-party app registrations, and third-party OAuth on the newer
    GraphQL API is documented but not yet enabled (verified against
    developers.buffer.com, July 2026). Each user generates their own key from
    their Buffer account (Settings -> API) and hands it to the platform admin.
    """

    @abc.abstractmethod
    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        """Fetch basic profile data for the authenticated account. Also used to validate a key."""
        pass

    @abc.abstractmethod
    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        """Fetch organizations belonging to the Buffer connection."""
        pass

    @abc.abstractmethod
    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        """Fetch channels (profiles) available under a specific organization."""
        pass

    @abc.abstractmethod
    def create_post(
        self,
        api_key: str,
        channel_id: str,
        text: str,
        media_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        media_type: Optional[str] = None, # "image" or "video"
        scheduled_at: Optional[datetime] = None,
        platform: Optional[str] = None,
        youtube_title: Optional[str] = None,
        video_duration_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a post (immediate/queued or scheduled)."""
        pass

    @abc.abstractmethod
    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        """Check the status of a specific post on Buffer."""
        pass

    @abc.abstractmethod
    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        """
        Fetch engagement metrics (reactions, views, follows gained, etc.) for a
        single sent post. Buffer refreshes these once a day - a post can take up
        to ~24h after sending before metrics first appear.
        """
        pass
