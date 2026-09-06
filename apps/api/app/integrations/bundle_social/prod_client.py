"""
Production client for bundle.social.

Every endpoint, field name and required parameter below was verified against the
live API on 2026-09-06 with a real organization, not taken from documentation
(AGENTS.md rule 14). Where the published docs disagreed with the API, the API
won - the documented plural paths (/teams, /posts) are 404s; the real ones are
singular.

Verified contract:

  GET  /api/v1/organization                       -> organization + teams[]
  GET  /api/v1/team?limit&offset                  -> {items[], total}
  POST /api/v1/team            {name}             -> team
  GET  /api/v1/team/{teamId}                      -> team + socialAccounts[]
  POST /api/v1/social-account/create-portal-link
       {teamId, socialAccountTypes[], redirectUrl} -> {url}
  POST /api/v1/post/  {teamId, title, postDate, status, socialAccountTypes[], data}
       (the API itself listed these six as required)
  GET  /api/v1/post/{postId}
  GET  /api/v1/analytics/post?postId&platformType -> {post, profilePost, items[]}

Auth is ``x-api-key: <platform key>`` - one key for the whole organization, not
one per end user. The end user is identified by their team.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import (
    BufferApiError,
    BufferAuthError,
    BufferNetworkError,
    BufferRateLimitError,
    BufferServerError,
)

# Our internal platform names (SocialChannel.platform) to bundle.social's enum.
# "twitter" is what Buffer reports for X and what campaign_resolver keys on, so
# it stays the internal name here too - only the wire value differs.
PLATFORM_TO_BUNDLE = {
    "instagram": "INSTAGRAM",
    "facebook": "FACEBOOK",
    "tiktok": "TIKTOK",
    "youtube": "YOUTUBE",
    "linkedin": "LINKEDIN",
    "twitter": "TWITTER",
    "x": "TWITTER",
    "threads": "THREADS",
    "pinterest": "PINTEREST",
    "reddit": "REDDIT",
    "mastodon": "MASTODON",
    "bluesky": "BLUESKY",
    "discord": "DISCORD",
    "slack": "SLACK",
    "snapchat": "SNAPCHAT",
    "google_business": "GOOGLE_BUSINESS",
}

BUNDLE_TO_PLATFORM = {value: key for key, value in PLATFORM_TO_BUNDLE.items() if key != "x"}


class ProductionBundleSocialClient(BaseBufferClient):
    BASE_URL = "https://api.bundle.social/api/v1"
    TIMEOUT_SECONDS = 20.0

    def __init__(self, account_ref: Optional[str] = None):
        # bundle.social team id standing in for "this end user". Set on the
        # connection as provider_account_ref when the user first connects.
        self.account_ref = account_ref

    # -- transport ----------------------------------------------------------

    def _request(
        self,
        api_key: str,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=self.TIMEOUT_SECONDS) as client:
                response = client.request(
                    method,
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    params=params,
                    json=json_body,
                )
        except httpx.RequestError as exc:
            raise BufferNetworkError(f"bundle.social non raggiungibile: {exc}")

        if response.status_code in (401, 403):
            raise BufferAuthError(
                "Chiave API bundle.social non valida o revocata",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise BufferRateLimitError("Limite di frequenza bundle.social superato", status_code=429)
        if response.status_code >= 500:
            raise BufferServerError(
                f"Errore server bundle.social: {response.text[:300]}",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            # 400 carries a Zod "issues" array naming the offending fields; keep
            # it, because it is the difference between a debuggable failure and
            # "Request Validation Error".
            raise BufferApiError(
                message=f"Richiesta bundle.social rifiutata: {response.text[:500]}",
                status_code=response.status_code,
                category="validation_failed",
            )

        if not response.content:
            return {}
        return response.json()

    # -- identity -----------------------------------------------------------

    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        """Validates the platform key and returns the owning organization."""
        org = self._request(api_key, "GET", "/organization")
        return {
            "id": org.get("id"),
            "name": org.get("name"),
            "provider": "bundle_social",
            "api_access": org.get("apiAccess"),
        }

    def create_team(self, api_key: str, name: str) -> Dict[str, Any]:
        """
        Create the isolated space for one end user.

        Not part of BaseBufferClient - it has no Buffer equivalent, because with
        Buffer the user brings an account of their own. Called once, when a user
        connects their first channel.
        """
        team = self._request(api_key, "POST", "/team", json_body={"name": name})
        return {"id": team.get("id"), "name": team.get("name")}

    def create_portal_link(
        self,
        api_key: str,
        team_id: str,
        platforms: List[str],
        redirect_url: str,
        user_name: Optional[str] = None,
    ) -> str:
        """
        Hosted connect flow: returns a URL the END USER opens to authorise their
        own social account, which then lands in this team.

        This is what makes the whole model work - the OAuth consent happens
        against bundle.social's approved platform apps, so we never need our own
        app review with Meta, TikTok and the rest.
        """
        types = [PLATFORM_TO_BUNDLE[p] for p in platforms if p in PLATFORM_TO_BUNDLE]
        if not types:
            raise BufferApiError("Nessuna piattaforma valida richiesta.", category="validation_failed")

        # White-label options, all verified accepted by the API (they come back
        # inside the signed token): our logo, our wording, no provider branding.
        # The OAuth page itself still belongs to the social network - Meta and
        # the others do not allow that step to be rebranded or framed - but
        # everything around it can look like ours.
        body: Dict[str, Any] = {
            "teamId": team_id,
            "socialAccountTypes": types,
            "redirectUrl": redirect_url,
            "language": "it",
            "hidePoweredBy": True,
            "goBackButtonText": "Torna su Agi Post",
            # No success modal: the popup closes on its own and our own page
            # shows the result, so an intermediate dialog is one click of noise.
            "showModalOnConnectSuccess": False,
        }
        if settings.PORTAL_BRAND_LOGO_URL:
            body["logoUrl"] = settings.PORTAL_BRAND_LOGO_URL
        if user_name:
            body["userName"] = user_name

        result = self._request(api_key, "POST", "/social-account/create-portal-link", json_body=body)
        url = result.get("url")
        if not url:
            raise BufferApiError("bundle.social non ha restituito un link di collegamento.", category="unknown")
        return url

    # -- sync ---------------------------------------------------------------

    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        """
        One connection maps to exactly one team, so this returns a single-element
        list - unlike Buffer, where an account can own several organizations.
        Keeping the list shape means tasks/sync.py needs no special case.
        """
        if not self.account_ref:
            return []

        team = self._request(api_key, "GET", f"/team/{self.account_ref}")
        return [
            {
                "id": team.get("id"),
                "name": team.get("name") or "Team",
                "raw": {"provider": "bundle_social", "team_id": team.get("id")},
            }
        ]

    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        """
        The team detail response embeds ``socialAccounts``; there is no endpoint
        that lists them all separately (``/social-account/by-type`` fetches one
        platform at a time), so the team is the listing.
        """
        team = self._request(api_key, "GET", f"/team/{organization_id}")
        channels = []

        for account in team.get("socialAccounts") or []:
            if account.get("deletedAt"):
                continue

            bundle_type = account.get("type") or ""
            platform = BUNDLE_TO_PLATFORM.get(bundle_type, bundle_type.lower())

            channels.append(
                {
                    "id": account.get("id"),
                    "platform": platform,
                    "name": account.get("displayName") or account.get("username") or platform.title(),
                    "username": account.get("username"),
                    "avatar_url": account.get("avatarUrl"),
                    # bundle.social exposes no public profile URL field, so the
                    # dashboard's "open profile" link is simply absent for these
                    # channels rather than pointing somewhere invented.
                    "external_link": None,
                    "channel_type": self._channel_type(account),
                    "raw": {
                        "provider": "bundle_social",
                        "team_id": organization_id,
                        "external_id": account.get("externalId"),
                    },
                }
            )
        return channels

    @staticmethod
    def _channel_type(account: Dict[str, Any]) -> Optional[str]:
        """
        Mirror Buffer's channel_type vocabulary where bundle.social gives us the
        equivalent signal. campaign_resolver excludes Instagram personal profiles
        proactively (they can never publish via API - a Meta rule, not ours), and
        that guard must keep working for channels from this provider too.
        """
        if account.get("type") == "INSTAGRAM":
            # Connected through Facebook = a Business/Creator account linked to a
            # Page, which is exactly the configuration Meta allows publishing on.
            return "business" if account.get("instagramConnectionMethod") == "FACEBOOK" else "profile"
        if account.get("type") == "FACEBOOK":
            return "page"
        return None

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
        """
        Publish one post.

        Two differences from Buffer worth knowing:

        1. bundle.social addresses a *platform within a team*, not a channel id.
           Since one team is one end user, and a user has one account per
           platform in the normal case, this is equivalent - but a team holding
           two accounts of the same platform would receive the post on both.
        2. There is no "publish now": ``status`` is DRAFT or SCHEDULED. An
           immediate publication is therefore scheduled for the current instant,
           which is how the queue-less path is expressed here.
        """
        if not self.account_ref:
            raise BufferApiError(
                "Connessione senza team bundle.social: ricollegare il canale.",
                category="configuration_error",
            )

        bundle_type = PLATFORM_TO_BUNDLE.get((platform or "").lower())
        if not bundle_type:
            raise BufferApiError(
                f"Piattaforma '{platform}' non supportata da bundle.social.",
                category="validation_failed",
            )

        post_date = scheduled_at or datetime.now(timezone.utc)

        platform_data: Dict[str, Any] = {"text": text}

        if bundle_type == "YOUTUBE":
            # YouTube needs a real title; falling back to the text would produce
            # a video titled with the whole caption.
            platform_data["title"] = youtube_title or (text[:95] if text else "Video")
        if bundle_type == "INSTAGRAM":
            # Same rule the Buffer client applies: a video over a minute cannot
            # be a feed post, only a reel.
            is_long_video = (
                media_type == "video"
                and video_duration_seconds is not None
                and video_duration_seconds > 60.0
            )
            platform_data["type"] = "REEL" if is_long_video else "POST"

        body = {
            "teamId": self.account_ref,
            "title": (youtube_title or text or "Post")[:120],
            "postDate": post_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "SCHEDULED",
            "socialAccountTypes": [bundle_type],
            "data": {bundle_type: platform_data},
        }

        result = self._request(api_key, "POST", "/post/", json_body=body)

        # A 200 does not mean every platform accepted it: per-platform failures
        # come back in `errors`, so surface them instead of reporting success.
        errors = result.get("errors") or {}
        platform_error = errors.get(bundle_type) if isinstance(errors, dict) else None
        if platform_error:
            raise BufferApiError(
                f"bundle.social ha rifiutato il post su {bundle_type}: {platform_error}",
                status_code=200,
                category="validation_failed",
            )

        return {
            "id": result.get("id"),
            "url": None,  # populated later by get_post_status once published
            "status": result.get("status"),
            "provider": "bundle_social",
        }

    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        result = self._request(api_key, "GET", f"/post/{external_post_id}")
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "error": result.get("error"),
            "provider": "bundle_social",
        }

    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        """
        Normalized engagement metrics, mapped onto the keys the statistics module
        already stores for Buffer.

        Field parity, verified against the live schema:
          likes, comments, shares, views, impressions -> direct
          reach            <- impressionsUnique (unique impressions IS reach)
          saves            -> kept in metrics_raw, no dedicated column
          clicks, follows, engagement_rate -> NOT PROVIDED by bundle.social;
            those columns stay null for channels of this provider rather than
            being computed from something else and quietly meaning something
            different than they do for Buffer.
        """
        result = self._request(
            api_key,
            "GET",
            "/analytics/post",
            params={"postId": external_post_id},
        )

        items = result.get("items") or []
        if not items:
            return {"metrics": [], "metrics_updated_at": None, "provider": "bundle_social"}

        # Latest snapshot: the API appends a row per refresh.
        latest = items[-1]

        mapping = {
            "likes": latest.get("likes"),
            "comments": latest.get("comments"),
            "shares": latest.get("shares"),
            "views": latest.get("views"),
            "impressions": latest.get("impressions"),
            "reach": latest.get("impressionsUnique"),
        }

        metrics = [
            {"name": name, "value": value}
            for name, value in mapping.items()
            if value is not None
        ]

        post = result.get("post") or {}

        return {
            "metrics": metrics,
            "metrics_updated_at": latest.get("updatedAt"),
            "external_link": post.get("externalLink"),
            "raw": latest,
            "provider": "bundle_social",
        }
