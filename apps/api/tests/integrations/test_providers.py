"""
Provider resolution: which client, whose credentials, whose quota.

The third of these is the one worth guarding. Rate-limit scoping is the only
part of the multi-provider split whose failure mode is silent under test and
catastrophic under load: with a shared-quota provider, scoping per connection
would let a campaign fire thousands of concurrent calls against a single
upstream limit. A unit test is cheap; discovering it mid-campaign is not.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.core.security import EncryptionService
from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.bundle_social.mock_client import MockBundleSocialClient
from app.integrations.buffer.mock_client import MockBufferClient
from app.integrations.providers import (
    PROVIDER_BUFFER,
    PROVIDER_BUNDLE_SOCIAL,
    get_provider_context,
    resolve_rate_limit_scope,
)


def _connection(provider=PROVIDER_BUFFER, account_ref=None, token="user-key", conn_id=None):
    """A stand-in for BufferConnection carrying only what providers.py reads."""
    return SimpleNamespace(
        id=conn_id or uuid.uuid4(),
        provider=provider,
        provider_account_ref=account_ref,
        access_token_encrypted=EncryptionService.encrypt(token) if token else None,
    )


# --- rate-limit scoping ----------------------------------------------------

def test_buffer_scope_is_per_connection():
    """Each Buffer user carries their own API key, so quotas are independent."""
    a = _connection()
    b = _connection()
    assert resolve_rate_limit_scope(PROVIDER_BUFFER, a) == f"conn:{a.id}"
    assert resolve_rate_limit_scope(PROVIDER_BUFFER, a) != resolve_rate_limit_scope(PROVIDER_BUFFER, b)


def test_bundle_social_scope_is_shared_across_connections():
    """
    The load-bearing assertion of this module.

    Every bundle.social connection publishes under the same platform key, so
    they must collapse onto one scope. If this ever returns per-connection
    scopes again, a campaign would treat one upstream quota as if it were
    thousands.
    """
    a = _connection(provider=PROVIDER_BUNDLE_SOCIAL, account_ref="team_a", token=None)
    b = _connection(provider=PROVIDER_BUNDLE_SOCIAL, account_ref="team_b", token=None)

    scope_a = resolve_rate_limit_scope(PROVIDER_BUNDLE_SOCIAL, a)
    scope_b = resolve_rate_limit_scope(PROVIDER_BUNDLE_SOCIAL, b)

    assert scope_a == scope_b == f"provider:{PROVIDER_BUNDLE_SOCIAL}"
    assert str(a.id) not in scope_a


# --- client and credential resolution --------------------------------------

def test_buffer_connection_resolves_to_buffer_client_and_user_key():
    conn = _connection(token="the-users-own-key")
    ctx = get_provider_context(conn)

    assert ctx.provider == PROVIDER_BUFFER
    assert isinstance(ctx.client, MockBufferClient)
    assert ctx.api_key == "the-users-own-key"
    assert ctx.account_ref is None


def test_bundle_connection_uses_platform_key_not_connection_token(monkeypatch):
    """
    The credential inversion that makes this provider different: the key comes
    from configuration, and the connection only supplies the team reference.
    """
    monkeypatch.setattr("app.core.config.settings.BUNDLE_SOCIAL_API_KEY", "platform-key")
    conn = _connection(provider=PROVIDER_BUNDLE_SOCIAL, account_ref="team_42", token=None)

    ctx = get_provider_context(conn)

    assert isinstance(ctx.client, MockBundleSocialClient)
    assert ctx.api_key == "platform-key"
    assert ctx.account_ref == "team_42"
    assert ctx.client.account_ref == "team_42"


def test_bundle_without_platform_key_fails_as_configuration_error(monkeypatch):
    """
    Fail here rather than upstream: the publication attempt then records a
    readable reason instead of an opaque 401 from the provider.
    """
    monkeypatch.setattr("app.core.config.settings.BUNDLE_SOCIAL_API_KEY", "")
    conn = _connection(provider=PROVIDER_BUNDLE_SOCIAL, account_ref="team_42", token=None)

    with pytest.raises(BufferApiError) as exc:
        get_provider_context(conn)
    assert exc.value.category == "configuration_error"


def test_buffer_without_token_fails_as_auth_error():
    conn = _connection(token=None)
    with pytest.raises(BufferApiError) as exc:
        get_provider_context(conn)
    assert exc.value.category == "auth_error"


def test_missing_provider_defaults_to_buffer():
    """Rows written before the provider column existed must keep working."""
    conn = _connection()
    conn.provider = None
    assert get_provider_context(conn).provider == PROVIDER_BUFFER


def test_unknown_provider_is_rejected():
    conn = _connection(provider="nope")
    with pytest.raises(BufferApiError) as exc:
        get_provider_context(conn)
    assert exc.value.category == "configuration_error"


# --- contract parity -------------------------------------------------------

def test_bundle_mock_satisfies_the_same_contract():
    """
    Both providers must be interchangeable from the caller's side: campaigns,
    publications and statistics only ever see this six-method surface.
    """
    client = MockBundleSocialClient(account_ref="team_x")

    orgs = client.sync_organizations("k")
    assert len(orgs) == 1 and orgs[0]["id"] == "team_x"

    channels = client.sync_channels("k", "team_x")
    assert channels and all({"id", "platform", "name"} <= set(c) for c in channels)

    post = client.create_post(api_key="k", channel_id=channels[0]["id"], text="ciao")
    assert post["id"].startswith("bs_post_")

    metrics = client.get_post_metrics("k", post["id"])
    assert {"impressions", "likes", "comments", "shares"} <= set(metrics)
