import json
import pytest
from app.integrations.openai import client as openai_client


class _FakeResponse:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _fake_completion(x_text_length: int):
    content = json.dumps({
        "default_text": "x" * 50,
        "instagram_text": "x" * 50,
        "facebook_text": "x" * 50,
        "linkedin_text": "x" * 50,
        "tiktok_text": "x" * 50,
        "x_text": "x" * x_text_length,
        "threads_text": "x" * 50,
        "youtube_title": "x" * 20,
        "youtube_description": "x" * 50,
    })
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture(autouse=True)
def _patch_httpx_post(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        # The model is asked for a 260-char x_text regardless of the branch
        # under test - truncation to the (possibly reduced) hard limit is
        # what this test actually verifies.
        return _FakeResponse(_fake_completion(x_text_length=260))

    monkeypatch.setattr(openai_client.httpx, "post", fake_post)


def test_x_text_truncated_to_normal_280_limit_when_referral_off():
    result = openai_client.generate_campaign_text("key", "gpt-4o-mini", "argomento", include_referral_link=False)
    assert len(result["x_text"]) <= 280


def test_x_text_truncated_to_reduced_limit_when_referral_on():
    result = openai_client.generate_campaign_text("key", "gpt-4o-mini", "argomento", include_referral_link=True)
    assert len(result["x_text"]) <= 280 - openai_client.REFERRAL_LINK_RESERVED_CHARS


def test_system_prompt_targets_shrink_when_referral_on(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["system_prompt"] = json["messages"][0]["content"]
        return _FakeResponse(_fake_completion(x_text_length=50))

    monkeypatch.setattr(openai_client.httpx, "post", fake_post)
    openai_client.generate_campaign_text("key", "gpt-4o-mini", "argomento", include_referral_link=True)
    assert f"x_text={280 - openai_client.REFERRAL_LINK_RESERVED_CHARS}" in captured["system_prompt"]
