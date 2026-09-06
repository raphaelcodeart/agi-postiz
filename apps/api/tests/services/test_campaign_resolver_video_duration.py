from types import SimpleNamespace
from app.services.campaign_resolver import CampaignResolver


def _media_file(mime_type="video/mp4", duration_seconds=None):
    return SimpleNamespace(mime_type=mime_type, duration_seconds=duration_seconds)


def test_x_video_over_140s_is_rejected():
    media_file = _media_file(duration_seconds=180.0)
    error = CampaignResolver.compute_video_duration_validation_error("x", media_file)
    assert error is not None
    assert "140" in error


def test_x_video_under_140s_is_accepted():
    media_file = _media_file(duration_seconds=90.0)
    error = CampaignResolver.compute_video_duration_validation_error("x", media_file)
    assert error is None


def test_x_video_exactly_at_limit_is_accepted():
    media_file = _media_file(duration_seconds=140.0)
    error = CampaignResolver.compute_video_duration_validation_error("x", media_file)
    assert error is None


def test_no_media_file_is_fail_open():
    assert CampaignResolver.compute_video_duration_validation_error("x", None) is None


def test_duration_not_yet_known_is_fail_open():
    media_file = _media_file(duration_seconds=None)
    assert CampaignResolver.compute_video_duration_validation_error("x", media_file) is None


def test_image_media_is_never_checked():
    error = CampaignResolver.compute_video_duration_validation_error(
        "x", _media_file(mime_type="image/png", duration_seconds=999.0)
    )
    assert error is None


def test_instagram_has_no_proactive_video_limit():
    # Instagram is handled reactively instead: prod_client.create_post() switches
    # to metadata.instagram.type="reel" for videos over
    # INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS rather than this function blocking
    # the channel proactively - see PLATFORM_VIDEO_MAX_DURATION_SECONDS.
    error = CampaignResolver.compute_video_duration_validation_error(
        "instagram", _media_file(duration_seconds=9999.0)
    )
    assert error is None


def test_platform_name_is_case_and_whitespace_insensitive():
    media_file = _media_file(duration_seconds=180.0)
    error = CampaignResolver.compute_video_duration_validation_error(" X ", media_file)
    assert error is not None
