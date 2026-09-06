import pytest
from app.integrations.buffer.prod_client import ProductionBufferClient


class _FakeResponse:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakeHttpxClient:
    next_body = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        return _FakeResponse(_FakeHttpxClient.next_body)


@pytest.fixture(autouse=True)
def _patch_httpx_client(monkeypatch):
    monkeypatch.setattr("app.integrations.buffer.prod_client.httpx.Client", _FakeHttpxClient)


def test_create_post_uses_external_link_when_buffer_provides_it_immediately():
    _FakeHttpxClient.next_body = {
        "data": {"createPost": {"post": {"id": "post_1", "dueAt": None, "externalLink": "https://instagram.com/p/xyz"}}}
    }
    client = ProductionBufferClient()
    result = client.create_post(api_key="key", channel_id="chan_1", text="hello", platform="instagram")
    assert result["url"] == "https://instagram.com/p/xyz"


def test_create_post_url_is_none_when_buffer_hasnt_delivered_the_post_yet():
    # The common case: Buffer's own Post.status stays "scheduled" internally
    # until it actually delivers to the destination network, so externalLink
    # is null right after create_post - not a bug, see prod_client.py comment.
    _FakeHttpxClient.next_body = {
        "data": {"createPost": {"post": {"id": "post_1", "dueAt": None, "externalLink": None}}}
    }
    client = ProductionBufferClient()
    result = client.create_post(api_key="key", channel_id="chan_1", text="hello", platform="instagram")
    assert result["url"] is None


def test_get_post_metrics_returns_external_link_when_available():
    _FakeHttpxClient.next_body = {
        "data": {"post": {"id": "post_1", "metrics": [], "metricsUpdatedAt": None, "externalLink": "https://x.com/user/status/1"}}
    }
    client = ProductionBufferClient()
    result = client.get_post_metrics(api_key="key", external_post_id="post_1")
    assert result["external_link"] == "https://x.com/user/status/1"


def test_get_post_metrics_external_link_none_when_post_not_found():
    _FakeHttpxClient.next_body = {"data": {"post": None}}
    client = ProductionBufferClient()
    result = client.get_post_metrics(api_key="key", external_post_id="missing")
    assert result["external_link"] is None
