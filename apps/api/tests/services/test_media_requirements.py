"""
Platform media requirements.

Every rule here comes from a rejection observed against the live provider on
2026-09-07, not from documentation: "At least 1 upload(s) required" for a
text-only Instagram/TikTok post, and "Tiktok video must have only videos" for an
image on TikTok.

Catching these at resolution time is the difference between an administrator
seeing "TikTok accetta solo video" next to the channel, and a campaign that
burns one API call per target to come back as a wall of failed publications.
"""
from types import SimpleNamespace

from app.services.campaign_resolver import CampaignResolver


def _image():
    return SimpleNamespace(mime_type="image/jpeg", duration_seconds=None)


def _video():
    return SimpleNamespace(mime_type="video/mp4", duration_seconds=30.0)


def test_facebook_accepts_text_only():
    """The only one of the three that publishes without media."""
    assert CampaignResolver.compute_media_validation_error("facebook", None) is None


def test_instagram_without_media_is_excluded():
    error = CampaignResolver.compute_media_validation_error("instagram", None)
    assert error is not None
    assert "immagine o video" in error


def test_tiktok_without_media_is_excluded():
    assert CampaignResolver.compute_media_validation_error("tiktok", None) is not None


def test_tiktok_rejects_an_image():
    """TikTok is video-only - an image campaign must not even be attempted there."""
    error = CampaignResolver.compute_media_validation_error("tiktok", _image())
    assert error is not None
    assert "solo video" in error


def test_tiktok_accepts_a_video():
    assert CampaignResolver.compute_media_validation_error("tiktok", _video()) is None


def test_instagram_accepts_both_image_and_video():
    assert CampaignResolver.compute_media_validation_error("instagram", _image()) is None
    assert CampaignResolver.compute_media_validation_error("instagram", _video()) is None


def test_the_message_says_what_to_do():
    """
    An exclusion reason that does not name the fix leaves the administrator
    guessing why a channel was skipped.
    """
    for platform, media in (("instagram", None), ("tiktok", None), ("tiktok", _image())):
        error = CampaignResolver.compute_media_validation_error(platform, media)
        assert "escludi" in error.lower() or "aggiungi" in error.lower()


def test_unknown_platforms_are_left_alone():
    """Only platforms with an observed constraint are gated."""
    for platform in ("linkedin", "twitter", "threads", "bluesky"):
        assert CampaignResolver.compute_media_validation_error(platform, None) is None
