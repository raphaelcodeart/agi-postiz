import pytest
from app.integrations.buffer.prod_client import ProductionBufferClient


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"data": {"createPost": {"post": {"id": "post_123", "dueAt": None}}}}


class _FakeHttpxClient:
    captured_payload = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        _FakeHttpxClient.captured_payload = json
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _patch_httpx_client(monkeypatch):
    monkeypatch.setattr("app.integrations.buffer.prod_client.httpx.Client", _FakeHttpxClient)


def _instagram_metadata():
    variables = _FakeHttpxClient.captured_payload["variables"]
    return variables["input"]["metadata"]["instagram"]


def test_short_instagram_video_is_sent_as_post():
    client = ProductionBufferClient()
    client.create_post(
        api_key="key",
        channel_id="chan_1",
        text="hello",
        media_url="https://example.com/video.mp4",
        media_type="video",
        platform="instagram",
        video_duration_seconds=45.0,
    )
    assert _instagram_metadata()["type"] == "post"


def test_long_instagram_video_is_sent_as_reel():
    client = ProductionBufferClient()
    client.create_post(
        api_key="key",
        channel_id="chan_1",
        text="hello",
        media_url="https://example.com/video.mp4",
        media_type="video",
        platform="instagram",
        video_duration_seconds=90.0,
    )
    assert _instagram_metadata()["type"] == "reel"


def test_instagram_video_exactly_at_limit_is_sent_as_post():
    client = ProductionBufferClient()
    client.create_post(
        api_key="key",
        channel_id="chan_1",
        text="hello",
        media_url="https://example.com/video.mp4",
        media_type="video",
        platform="instagram",
        video_duration_seconds=60.0,
    )
    assert _instagram_metadata()["type"] == "post"


def test_instagram_video_with_unknown_duration_defaults_to_post():
    client = ProductionBufferClient()
    client.create_post(
        api_key="key",
        channel_id="chan_1",
        text="hello",
        media_url="https://example.com/video.mp4",
        media_type="video",
        platform="instagram",
        video_duration_seconds=None,
    )
    assert _instagram_metadata()["type"] == "post"


def test_instagram_image_is_always_sent_as_post_regardless_of_stray_duration():
    client = ProductionBufferClient()
    client.create_post(
        api_key="key",
        channel_id="chan_1",
        text="hello",
        media_url="https://example.com/photo.jpg",
        media_type="image",
        platform="instagram",
        video_duration_seconds=9999.0,
    )
    assert _instagram_metadata()["type"] == "post"
