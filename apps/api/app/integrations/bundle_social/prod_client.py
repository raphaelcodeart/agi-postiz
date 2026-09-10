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
       (the API itself listed these six as required; the per-platform shape of
        `data` was mapped from its validator on 2026-09-10 - see
        PLATFORM_TEXT_MAX_CHARS below, and note that for YouTube `text` is the
        video title, not the description)
  GET  /api/v1/post/{postId}
  GET  /api/v1/analytics/post?postId&platformType -> {post, profilePost, items[]}

Auth is ``x-api-key: <platform key>`` - one key for the whole organization, not
one per end user. The end user is identified by their team.
"""
import hashlib
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

# Per-platform shape of ``data.<PLATFORM>``, read off the live API's own Zod
# validator on 2026-09-10 by posting deliberately wrong types and recording which
# fields it named (AGENTS.md rule 14 - the published docs describe none of this):
#
#   YOUTUBE    text* description type('VIDEO'|'SHORT') madeForKids uploadIds
#   INSTAGRAM  text  type('POST'|'REEL'|'STORY') altText shareToFeed
#              collaborators carouselItems uploadIds
#   TIKTOK     text  type('VIDEO'|'IMAGE') autoAddMusic uploadIds
#   FACEBOOK   text  type('POST'|'REEL'|'STORY') link uploadIds
#   LINKEDIN   text  link uploadIds
#
# (*) The one that had been costing every YouTube publication: for YOUTUBE
# ``text`` is the video TITLE - capped at 100 characters, exactly YouTube's own
# title limit - and the description body belongs in ``description``. Sending the
# caption as ``text`` produced
#   {"code":"custom","message":"Max 100 characters allowed",
#    "path":["data","YOUTUBE","text"]}
# on every attempt, while the title we did send travelled under a "title" key
# that is not in the schema at all and was silently discarded.
YOUTUBE_TITLE_MAX_CHARS = 100
YOUTUBE_DESCRIPTION_MAX_CHARS = 5000

# Maximum ``data.<PLATFORM>.text`` length the provider enforces, each read from
# its own rejection message ("Max N characters allowed") on 2026-09-10. FACEBOOK
# accepted 20 000 characters without complaint and is therefore deliberately
# absent rather than given an invented ceiling.
PLATFORM_TEXT_MAX_CHARS = {
    "YOUTUBE": YOUTUBE_TITLE_MAX_CHARS,  # the title - see above
    "INSTAGRAM": 2200,
    "TIKTOK": 2200,
    "LINKEDIN": 3000,
}


def _clip(value: str, max_chars: int) -> str:
    """
    Shorten to the provider's ceiling, marking the cut so a truncated field reads
    as truncated rather than as a sentence that simply stops.

    Used only for values we derive ourselves (a YouTube title built from the
    caption). Text an administrator actually wrote is never silently shortened -
    campaign_resolver rejects that target before launch with a message naming the
    limit, which is a thing they can act on.
    """
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "\u2026"


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
            # No back button: it navigates to redirectUrl, which in the popup
            # meant loading our whole portal inside a 620px window. The popup
            # closes itself when the flow ends, so there is nothing to go back
            # to - and a user who changes their mind just closes the window.
            "hideGoBackButton": True,
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

        Instagram is always reported as publishable here, whichever of the two
        connection methods was used. That is a correction, not a relaxation: this
        method used to call anything but ``instagramConnectionMethod ==
        "FACEBOOK"`` a personal profile, which took every Instagram account
        connected the other way and had campaign_resolver reject it before a
        single call was made - the reason Instagram "required a Facebook Page"
        here while the same accounts had published fine through Buffer.

        Meta offers two publishing integrations and bundle.social reports which
        one the account came through:

          FACEBOOK   Instagram Graph API - Business/Creator linked to a Page.
          INSTAGRAM  Instagram API with Instagram Login - Business/Creator
                     authorising directly, no Page involved. Introduced by Meta
                     in 2024 and equally able to publish.

        Neither can be completed by a personal profile: Meta's OAuth simply
        refuses one, so an account that reached this method is Business/Creator
        by construction. Verified against this deployment's own teams on
        2026-09-10 - three live accounts (mamifyofficial, johanagomez109,
        negro.marco1) all report ``instagramConnectionMethod: "INSTAGRAM"``.
        """
        if account.get("type") == "INSTAGRAM":
            return "business"
        if account.get("type") == "FACEBOOK":
            return "page"
        return None


    # -- media --------------------------------------------------------------

    # An upload created without a teamId belongs to the ORGANIZATION and can be
    # referenced by a post in any team - verified against the live API. That is
    # what makes one upload per campaign possible instead of one per channel:
    # the same video going out to 1000 promoters is transferred once, not a
    # thousand times.
    UPLOAD_CACHE_TTL_SECONDS = 6 * 60 * 60

    def _upload_cache_key(self, media_url: str) -> str:
        digest = hashlib.sha256(media_url.encode()).hexdigest()[:32]
        return f"bundle_social:upload:{digest}"

    def ensure_upload(self, api_key: str, media_url: str) -> str:
        """
        The provider's upload id for this media, uploading it once if needed.

        bundle.social does not fetch media by URL the way Buffer does - it wants
        the bytes - so the file is downloaded from our own media host and
        forwarded. The resulting id is cached in Redis by source URL, so every
        other publication of the same campaign reuses it.
        """
        import redis as redis_lib

        cache = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        key = self._upload_cache_key(media_url)

        cached = cache.get(key)
        if cached:
            return cached

        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                download = client.get(media_url)
                download.raise_for_status()
                content = download.content
                content_type = download.headers.get("content-type", "application/octet-stream")
        except httpx.HTTPError as exc:
            raise BufferApiError(
                f"Media non scaricabile da {media_url}: {exc}",
                category="invalid_media",
            )

        filename = media_url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "media"

        try:
            with httpx.Client(timeout=180.0) as client:
                response = client.post(
                    f"{self.BASE_URL}/upload/",
                    headers={"x-api-key": api_key},
                    files={"file": (filename, content, content_type)},
                )
        except httpx.RequestError as exc:
            raise BufferNetworkError(f"Upload verso bundle.social fallito: {exc}")

        if response.status_code >= 400:
            raise BufferApiError(
                f"Upload rifiutato da bundle.social: {response.text[:300]}",
                status_code=response.status_code,
                category="invalid_media",
            )

        upload_id = (response.json() or {}).get("id")
        if not upload_id:
            raise BufferApiError("bundle.social non ha restituito un id di upload.", category="invalid_media")

        # Long enough to cover a campaign that spreads over hours, short enough
        # that a re-run after the provider prunes old uploads re-uploads instead
        # of referencing something gone.
        cache.setex(key, self.UPLOAD_CACHE_TTL_SECONDS, upload_id)
        return upload_id

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

        # bundle.social refuses a postDate more than 10 minutes in the past
        # ("Scheduled date cannot be more than 10 minutes in the past"), so a
        # scheduled time that has already gone by must become "now" rather than
        # be sent as-is. This is not an edge case: a campaign scheduled for 9:00
        # whose targets are still working through the publishing queue at 10:30,
        # or one launched after its scheduled moment, both land here. Publishing
        # a late post late is right; failing it is not.
        now = datetime.now(timezone.utc)
        post_date = scheduled_at or now
        if post_date.tzinfo is None:
            post_date = post_date.replace(tzinfo=timezone.utc)
        if post_date < now:
            post_date = now

        platform_data: Dict[str, Any] = {"text": text}

        # Instagram and TikTok reject a post with no media outright ("At least 1
        # upload(s) required", observed from the live API), and Facebook accepts
        # text alone. Attach whatever the campaign carries; campaign_resolver
        # excludes the channels that cannot work before we get here.
        if media_url:
            platform_data["uploadIds"] = [self.ensure_upload(api_key, media_url)]

        if bundle_type == "YOUTUBE":
            # For YOUTUBE the provider's "text" IS the title (max 100 chars) and
            # the caption belongs in "description" - see PLATFORM_TEXT_MAX_CHARS
            # above for how that was established. Both fields are written here
            # explicitly, overwriting the generic {"text": text} set above, so
            # neither can be left holding the other one's value.
            #
            # The title is truncated rather than rejected: it is derived from the
            # caption whenever the campaign has no youtube_title of its own, and
            # a caption is routinely longer than 100 characters. An administrator
            # who cares about the exact wording sets youtube_title (capped at 100
            # by the campaign schema, so never truncated here); an administrator
            # who does not still gets a published video with a sensible title
            # instead of a permanent failure.
            platform_data["text"] = _clip(
                youtube_title or text or "Video", YOUTUBE_TITLE_MAX_CHARS
            )
            platform_data["description"] = _clip(text or "", YOUTUBE_DESCRIPTION_MAX_CHARS)
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

        try:
            result = self._request(api_key, "POST", "/post/", json_body=body)
        except BufferApiError as exc:
            raise self._explain_rejection(exc, bundle_type) from exc

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

    @staticmethod
    def _explain_rejection(error: BufferApiError, bundle_type: str) -> BufferApiError:
        """
        Replace a raw provider rejection with something an administrator can act
        on, where we recognise it.

        The provider answers a validation failure with a Zod dump - useful when
        debugging the integration, unreadable on the Errori page, and in one case
        actively misleading. "No social accounts selected" sounds like a mistake
        in the request; it actually means the team no longer holds an account of
        this platform, i.e. our copy of the channel outlived the connection
        upstream (observed 2026-09-08 on a LinkedIn channel the user had already
        disconnected). Retrying cannot fix that, so it is reported for what it is
        - a channel to reconnect - rather than left looking like a transient
        request problem.

        Anything unrecognised is passed through untouched: inventing an
        explanation for an error we have not seen would be worse than the dump.
        """
        raw = error.message or ""
        if "No social accounts selected" in raw:
            return BufferApiError(
                f"Il canale {bundle_type.title()} non risulta piu collegato: "
                "l'account non e presente nello spazio dell'utente. "
                "L'utente deve ricollegarlo dal portale perche questa campagna "
                "possa raggiungerlo.",
                status_code=error.status_code,
                category="channel_disconnected",
            )
        return error

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
        Emitted under the "type" key that the statistics module indexes by.
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

        # The key is "type", NOT "name": extract_metric_columns in
        # services/statistics_service.py looks up METRIC_TYPE_TO_COLUMN by
        # m["type"], and a metric under any other key is silently dropped. That
        # failure mode is the dangerous one - the sync reports success, the
        # dashboard shows zeros, and nothing anywhere says why.
        metrics = [
            {"type": metric_type, "value": value}
            for metric_type, value in mapping.items()
            if value is not None
        ]

        return {
            "metrics": metrics,
            "metrics_updated_at": latest.get("updatedAt"),
            "external_link": self._permalink_from(result.get("post") or {}),
            "raw": latest,
            "provider": "bundle_social",
        }

    @staticmethod
    def _permalink_from(post: Dict[str, Any]) -> Optional[str]:
        """
        The published post's public URL on the social network.

        Lives at ``externalData.<PLATFORM>.permalink``, keyed by platform - not
        at a top-level field. Each of our publications targets exactly one
        platform, so the first permalink present is the right one; iterating
        avoids having to thread the platform down into this call just to index
        a single-entry object.
        """
        external_data = post.get("externalData") or {}
        if not isinstance(external_data, dict):
            return None
        for platform_payload in external_data.values():
            if isinstance(platform_payload, dict):
                permalink = platform_payload.get("permalink")
                if permalink:
                    return permalink
        return None
