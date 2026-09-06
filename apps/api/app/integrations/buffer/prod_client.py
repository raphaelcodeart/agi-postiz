from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx
from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import (
    BufferApiError,
    BufferAuthError,
    BufferRateLimitError,
    BufferServerError,
    BufferNetworkError,
)

class ProductionBufferClient(BaseBufferClient):
    """
    Production client for Buffer's GraphQL API (https://api.buffer.com).
    Documentation reference: https://developers.buffer.com/
    Auth: single personal API key per account, sent as `Authorization: Bearer <key>`
    (verified against developers.buffer.com/guides/authentication.html, July 2026).
    """

    BASE_URL = "https://api.buffer.com"

    # Instagram rejects a video sent with metadata.instagram.type="post" once it
    # exceeds this length, with the exact error "Video must be no longer than 1
    # minute for Instagram Posts" - observed directly from a real Buffer API
    # response on this deployment (campaign launch, 2026-08-14), not a documented
    # Buffer spec page, per AGENTS.md rule 8. A Reel has no such ceiling, so
    # create_post() switches type to "reel" above this threshold instead of
    # always sending "post" (see the instagram branch below).
    INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS = 60.0

    def _request(self, api_key: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"query": query, "variables": variables or {}}

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(self.BASE_URL, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise BufferNetworkError(f"HTTP communication failure: {str(exc)}")

        if response.status_code == 401:
            raise BufferAuthError("Invalid or revoked Buffer API key", status_code=401)
        elif response.status_code == 429:
            raise BufferRateLimitError("Buffer API rate limit exceeded", status_code=429)
        elif response.status_code >= 500:
            raise BufferServerError(f"Buffer API server error: {response.text}", status_code=response.status_code)
        elif response.status_code >= 400:
            raise BufferApiError(
                message=f"Buffer API request failed: {response.text}",
                status_code=response.status_code,
                category="bad_request",
            )

        body = response.json()
        errors = body.get("errors")
        if errors:
            message = "; ".join(e.get("message", "Unknown GraphQL error") for e in errors)
            raise BufferApiError(message=message, status_code=response.status_code, category="graphql_error")

        return body.get("data", {})

    def _run_mutation(self, api_key: str, query: str, variables: Dict[str, Any], field_name: str) -> Dict[str, Any]:
        """Runs a mutation returning a union type (e.g. PostActionSuccess | MutationError) and unwraps it."""
        data = self._request(api_key, query, variables)
        result = data.get(field_name) or {}
        if "message" in result and "post" not in result:
            # Shape matches the MutationError branch of the response union.
            raise BufferApiError(message=result["message"], category="validation_failed")
        return result

    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        query = """
        query GetAccount {
          account {
            id
            email
            name
          }
        }
        """
        data = self._request(api_key, query)
        account = data.get("account") or {}
        return {
            "id": account.get("id"),
            "name": account.get("name"),
            "email": account.get("email"),
        }

    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        query = """
        query GetOrganizations {
          account {
            organizations {
              id
              name
            }
          }
        }
        """
        data = self._request(api_key, query)
        organizations = (data.get("account") or {}).get("organizations") or []
        return [
            {"id": org.get("id"), "name": org.get("name"), "is_active": True}
            for org in organizations
        ]

    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        query = """
        query GetChannels($organizationId: OrganizationId!) {
          channels(input: { organizationId: $organizationId }) {
            id
            service
            name
            avatar
            descriptor
            isDisconnected
            type
            externalLink
          }
        }
        """
        data = self._request(api_key, query, {"organizationId": organization_id})
        channels = data.get("channels") or []
        return [
            {
                "id": chan.get("id"),
                "platform": str(chan.get("service", "unknown")).lower(),
                "name": chan.get("descriptor") or chan.get("name", "Unknown"),
                "username": chan.get("name"),
                "avatar_url": chan.get("avatar"),
                "channel_type": chan.get("type"),
                "is_active": not chan.get("isDisconnected", False),
                # Channel.externalLink (developers.buffer.com/types/Channel.html):
                # "the channel's URL on the social network", null for unsupported
                # channels - not a Buffer URL.
                "external_link": chan.get("externalLink"),
            }
            for chan in channels
        ]

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
        post_input: Dict[str, Any] = {
            "channelId": channel_id,
            "text": text,
        }

        if platform == "youtube":
            # YoutubePostMetadataInput.title and .categoryId are both required on
            # create (see developers.buffer.com/types/YoutubePostMetadataInput.html).
            # categoryId is a string form of YouTube's own numeric category taxonomy
            # (1-29); the platform has no per-campaign category setting yet, so this
            # defaults to "22" (People & Blogs), YouTube's own catch-all default for
            # uncategorized uploads - not a Buffer-specific value.
            post_input["metadata"] = {
                "youtube": {
                    "title": youtube_title or text[:100],
                    "categoryId": "22",
                }
            }
        elif platform == "instagram":
            # InstagramPostMetadataInput.type and .shouldShareToFeed are both required
            # on create (see developers.buffer.com/types/InstagramPostMetadataInput.html).
            # type selects post/story/reel (PostType enum). Instagram feed "post" videos
            # are capped at INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS (see constant
            # above); a Reel tolerates much longer clips, so videos over that length are
            # sent as a Reel instead, keeping shouldShareToFeed=true so it still shows up
            # in the main feed like a post would. Images and videos at/under the limit
            # (or with unknown duration, matching the previous fail-open default) keep
            # the standard feed "post".
            is_long_video = (
                media_type == "video"
                and video_duration_seconds is not None
                and video_duration_seconds > self.INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS
            )
            post_input["metadata"] = {
                "instagram": {
                    "type": "reel" if is_long_video else "post",
                    "shouldShareToFeed": True,
                }
            }
        elif platform == "facebook":
            # FacebookPostMetadataInput.type is required on create (see
            # developers.buffer.com/types/FacebookPostMetadataInput.html); values are
            # post/story/reel (PostTypeFacebook enum, developers.buffer.com/types/PostTypeFacebook.html).
            # The platform has no per-campaign post-type setting yet, so this defaults
            # to a standard feed "post", mirroring Instagram's default above.
            # .annotations is also a required (non-nullable) list field on the same
            # input type, tagging detected mentions/links inside the text; none are
            # computed by this project, so an empty list is sent to satisfy the
            # required-list constraint with zero entries.
            post_input["metadata"] = {
                "facebook": {
                    "type": "post",
                    "annotations": [],
                }
            }

        if scheduled_at:
            post_input["schedulingType"] = "automatic"
            post_input["mode"] = "customScheduled"
            post_input["dueAt"] = scheduled_at.isoformat()
        else:
            # Adds the post to the channel's next available queue slot, i.e. the
            # user's Buffer posting schedule ("palinsesto") - this is the default
            # and desired behavior for this platform.
            post_input["schedulingType"] = "automatic"
            post_input["mode"] = "addToQueue"

        if media_url:
            if media_type == "video":
                # thumbnail_url is intentionally not sent here: Buffer's real schema
                # (VideoAssetInput.thumbnailUrl, see developers.buffer.com/reference.html)
                # documents that field as rejected by the API - social networks don't
                # accept custom video thumbnail images. The only supported thumbnail
                # control is metadata.thumbnailOffset (a frame offset within the video
                # itself, in ms, and only honored by Instagram/TikTok/Pinterest), which
                # isn't equivalent to our server-generated thumbnail image and isn't
                # implemented here.
                post_input["assets"] = [{"video": {"url": media_url}}]
            else:
                post_input["assets"] = [{"image": {"url": media_url}}]

        query = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                dueAt
                externalLink
              }
            }
            ... on MutationError {
              message
            }
          }
        }
        """
        result = self._run_mutation(api_key, query, {"input": post_input}, "createPost")
        post = result.get("post") or result

        is_scheduled = scheduled_at is not None
        return {
            "id": post.get("id"),
            "status": "scheduled" if is_scheduled else "queued",
            "channel_id": channel_id,
            "text": text,
            "media_url": media_url,
            "scheduled_at": post.get("dueAt"),
            "published_at": None,
            # Post.externalLink (developers.buffer.com/types/Post.html, "The
            # external URL of the post at the destination service" - verified
            # directly against Buffer's live API, 2026-08-15, both via docs and
            # a real read-only query). Almost always null right here: Buffer's
            # own Post.status stays "scheduled" on its side until it actually
            # delivers the post to the destination network, which happens some
            # time after this mutation returns - same "not available yet, not a
            # bug" pattern as metrics below. get_post_metrics backfills this
            # once it's actually populated.
            "url": post.get("externalLink"),
        }

    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        # BUFFER_API_TODO: Not verified against developers.buffer.com - reconciliation
        # of a single post's status isn't in this platform's active publication path
        # yet. Implement once needed, using the documented posts/pagination queries
        # (see https://developers.buffer.com/examples/get-posts-for-channels.html)
        # instead of guessing a field name.
        raise NotImplementedError(
            "get_post_status is not yet implemented for the Buffer GraphQL API client"
        )

    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        # Verified against developers.buffer.com/types/Post.html,
        # developers.buffer.com/types/PostMetric.html and the "Post Metrics" guide
        # (July 2026): `post(input: PostInput!)` returns `metrics: [PostMetric]` +
        # `metricsUpdatedAt`. Metrics are refreshed once a day by Buffer itself, so a
        # freshly-sent post can take up to ~24h before any metric appears here -
        # a missing/empty list does not necessarily mean the post has 0 engagement.
        query = """
        query GetPostMetrics($input: PostInput!) {
          post(input: $input) {
            id
            metrics {
              type
              name
              value
              unit
            }
            metricsUpdatedAt
            externalLink
          }
        }
        """
        data = self._request(api_key, query, {"input": {"id": external_post_id}})
        post = data.get("post")
        if not post:
            return {"metrics": [], "metrics_updated_at": None, "external_link": None}

        return {
            "metrics": [
                {
                    "type": m.get("type"),
                    "name": m.get("name"),
                    "value": m.get("value"),
                    "unit": m.get("unit"),
                }
                for m in (post.get("metrics") or [])
            ],
            "metrics_updated_at": post.get("metricsUpdatedAt"),
            # See create_post()'s "url" field above for what this is and why it's
            # often still null even long after publish - callers (publications.py,
            # campaigns.py) backfill Publication.external_post_url with this once
            # it's non-null, since metrics are checked well after create_post.
            "external_link": post.get("externalLink"),
        }
