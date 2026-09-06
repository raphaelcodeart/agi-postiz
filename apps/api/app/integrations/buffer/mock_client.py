import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import (
    BufferAuthError,
    BufferRateLimitError,
    BufferServerError,
    BufferApiError,
)

class MockBufferClient(BaseBufferClient):
    def get_user_info(self, api_key: str) -> Dict[str, Any]:
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)
        return {
            "id": "mock_buffer_user_123",
            "name": "Mock Administrator",
            "email": "mock_admin@buffer.com",
        }

    def sync_organizations(self, api_key: str) -> List[Dict[str, Any]]:
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)
        return [
            {
                "id": "org_mock_1",
                "name": "Algarve Hotels Group",
                "is_active": True,
            },
            {
                "id": "org_mock_2",
                "name": "Lisbon Marketing Agency",
                "is_active": True,
            }
        ]

    def sync_channels(self, api_key: str, organization_id: str) -> List[Dict[str, Any]]:
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)

        # Depending on organization, return different channels
        if organization_id == "org_mock_1":
            return [
                {
                    "id": "chan_ig_hotel",
                    "platform": "instagram",
                    "name": "Algarve Beach Resort IG",
                    "username": "@algarvebeachresort",
                    "avatar_url": "https://media.example.com/avatars/hotel_ig.png",
                    "channel_type": "instagram_business",
                    "external_link": "https://instagram.com/algarvebeachresort",
                },
                {
                    "id": "chan_fb_hotel",
                    "platform": "facebook",
                    "name": "Algarve Hotel FB Page",
                    "username": "AlgarveHotelOfficial",
                    "avatar_url": "https://media.example.com/avatars/hotel_fb.png",
                    "channel_type": "facebook_page",
                    "external_link": "https://facebook.com/AlgarveHotelOfficial",
                },
                {
                    "id": "chan_li_hotel",
                    "platform": "linkedin",
                    "name": "Algarve Hospitality Group",
                    "username": "algarve-hospitality",
                    "avatar_url": "https://media.example.com/avatars/hotel_li.png",
                    "channel_type": "linkedin_organization",
                    "external_link": "https://linkedin.com/company/algarve-hospitality",
                }
            ]
        elif organization_id == "org_mock_2":
            return [
                {
                    "id": "chan_x_agency",
                    "platform": "twitter",
                    "name": "Lisbon Marketing X",
                    "username": "@lisbonmarketing",
                    "avatar_url": "https://media.example.com/avatars/agency_x.png",
                    "channel_type": "x_profile",
                    "external_link": "https://x.com/lisbonmarketing",
                },
                {
                    "id": "chan_tt_agency",
                    "platform": "tiktok",
                    "name": "Lisbon Agency TikTok",
                    "username": "@lisbonagency",
                    "avatar_url": "https://media.example.com/avatars/agency_tt.png",
                    "channel_type": "tiktok_profile",
                    "external_link": "https://tiktok.com/@lisbonagency",
                }
            ]
        return []

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
        # Auth checks
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)

        # Failure simulations
        if "simulate-fail-temp-429" in text:
            raise BufferRateLimitError("Buffer API Rate Limit Exceeded", status_code=429)
        elif "simulate-fail-temp-500" in text:
            raise BufferServerError("Buffer Internal Server Error", status_code=500)
        elif "simulate-fail-perm" in text:
            raise BufferApiError(
                message="Unsupported media format for this platform",
                status_code=400,
                error_code="invalid_media_format",
                is_temporary=False,
                category="invalid_media"
            )

        # Simulate successful post response
        post_id = f"buffer_post_{uuid.uuid4().hex[:12]}"

        # Calculate status
        is_scheduled = scheduled_at is not None
        status = "scheduled" if is_scheduled else "published"

        return {
            "id": post_id,
            "status": status,
            "channel_id": channel_id,
            "text": text,
            "media_url": media_url,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "published_at": datetime.now(timezone.utc).isoformat() if not is_scheduled else None,
            "url": f"https://buffer.com/post/{post_id}",
        }

    def get_post_status(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)

        return {
            "id": external_post_id,
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "url": f"https://buffer.com/post/{external_post_id}",
        }

    def get_post_metrics(self, api_key: str, external_post_id: str) -> Dict[str, Any]:
        if "invalid" in api_key:
            raise BufferAuthError("Invalid API key", status_code=401)

        # Deterministic per post_id so repeated calls in a demo look stable, not
        # randomly flickering on every refresh.
        rng = random.Random(external_post_id)
        reactions = rng.randint(5, 250)
        views = rng.randint(reactions * 3, reactions * 20 + 100)
        clicks = rng.randint(0, views // 10 + 1)
        follows = rng.randint(0, 8)
        return {
            "metrics": [
                {"type": "reactions", "name": "Reactions", "value": float(reactions), "unit": "count"},
                {"type": "comments", "name": "Comments", "value": float(rng.randint(0, reactions // 4 + 1)), "unit": "count"},
                {"type": "shares", "name": "Shares", "value": float(rng.randint(0, reactions // 5 + 1)), "unit": "count"},
                {"type": "views", "name": "Views", "value": float(views), "unit": "count"},
                {"type": "clicks", "name": "Clicks", "value": float(clicks), "unit": "count"},
                {"type": "follows", "name": "New follows", "value": float(follows), "unit": "count"},
                {
                    "type": "engagementRate",
                    "name": "Eng. Rate",
                    "value": round(min(100.0, (reactions + clicks + follows) / max(views, 1) * 100), 2),
                    "unit": "percentage",
                },
            ],
            "metrics_updated_at": datetime.now(timezone.utc).isoformat(),
            "external_link": f"https://example.com/mock-post/{external_post_id}",
        }
