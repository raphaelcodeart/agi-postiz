"""
Provider-aware resolution of the publishing client and its credentials.

The platform publishes through more than one upstream provider. Every provider
speaks the same six-method contract (``BaseBufferClient``), so the rest of the
system stays provider-agnostic: campaigns, publications and statistics only ever
reference ``social_channels.id`` and never learn where a channel came from. The
provider is resolved once, here, at the moment of an outbound call.

Two things differ per provider and are the reason this module exists:

1. **Whose key is used.** Buffer authenticates with the *end user's* personal API
   key, stored encrypted on their connection. bundle.social authenticates with a
   single *platform* key that is ours, and identifies the end user by team id
   (``BufferConnection.provider_account_ref``) instead.

2. **Whose quota is consumed.** With Buffer each user has an independent quota,
   so rate limiting is scoped per connection. With bundle.social every channel
   shares our one quota, so the scope is the provider as a whole - see
   ``ProviderContext.rate_limit_scope`` and ``services/rate_limiter.py``.

Adding a third provider (e.g. our own approved social apps) means adding a client
class and a branch in ``_build_client`` - nothing outside this module changes.
"""
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from app.core.config import settings
from app.core.security import EncryptionService
from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.buffer.mock_client import MockBufferClient
from app.integrations.buffer.prod_client import ProductionBufferClient

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a circular import
    from app.models.buffer import BufferConnection

PROVIDER_BUFFER = "buffer"
PROVIDER_BUNDLE_SOCIAL = "bundle_social"

SUPPORTED_PROVIDERS = (PROVIDER_BUFFER, PROVIDER_BUNDLE_SOCIAL)

# Human-readable labels for the dashboard's channel origin badge.
PROVIDER_LABELS = {
    PROVIDER_BUFFER: "Buffer",
    PROVIDER_BUNDLE_SOCIAL: "Collegato da noi",
}


@dataclass(frozen=True)
class ProviderContext:
    """
    Everything an outbound call needs, resolved from a connection in one step.

    Built by :func:`get_provider_context`. ``api_key`` is already decrypted, so a
    context must never be logged, serialized into an API response, or stored on a
    model (AGENTS.md rules 8-10).
    """

    provider: str
    client: BaseBufferClient
    api_key: str
    account_ref: Optional[str]
    rate_limit_scope: str


def _build_client(provider: str, account_ref: Optional[str]) -> BaseBufferClient:
    if provider == PROVIDER_BUFFER:
        if settings.BUFFER_INTEGRATION_MODE.lower() == "mock":
            return MockBufferClient()
        return ProductionBufferClient()

    if provider == PROVIDER_BUNDLE_SOCIAL:
        # Imported lazily: the production client is a placeholder until the real
        # request/response contract is captured from a live account, and nothing
        # should pay its import cost in mock mode.
        if settings.BUNDLE_SOCIAL_INTEGRATION_MODE.lower() == "mock":
            from app.integrations.bundle_social.mock_client import MockBundleSocialClient

            return MockBundleSocialClient(account_ref=account_ref)

        from app.integrations.bundle_social.prod_client import ProductionBundleSocialClient

        return ProductionBundleSocialClient(account_ref=account_ref)

    raise BufferApiError(
        f"Provider sconosciuto: '{provider}'. Provider supportati: {', '.join(SUPPORTED_PROVIDERS)}.",
        category="configuration_error",
    )


def _resolve_api_key(provider: str, connection: "BufferConnection") -> str:
    """
    Return the decrypted key to authenticate with, per the provider's model.

    Raises ``BufferApiError`` rather than returning an empty string: an outbound
    call with no credentials would fail upstream anyway, and failing here keeps
    the reason in the publication attempt instead of an opaque 401.
    """
    if provider == PROVIDER_BUFFER:
        token = EncryptionService.decrypt(connection.access_token_encrypted) if connection.access_token_encrypted else None
        if not token:
            raise BufferApiError(
                "Credenziali mancanti: la connessione Buffer va ricollegata.",
                category="auth_error",
            )
        return token

    if provider == PROVIDER_BUNDLE_SOCIAL:
        token = settings.BUNDLE_SOCIAL_API_KEY
        if not token:
            raise BufferApiError(
                "BUNDLE_SOCIAL_API_KEY non configurata: impossibile pubblicare su canali collegati da noi.",
                category="configuration_error",
            )
        return token

    raise BufferApiError(
        f"Provider sconosciuto: '{provider}'.",
        category="configuration_error",
    )


def resolve_rate_limit_scope(provider: str, connection: "BufferConnection") -> str:
    """
    The key under which concurrency and cooldown are enforced.

    Buffer: one quota per connection, because each user carries their own key.
    bundle.social: one quota for the whole provider, because every connection
    goes out under the same platform key - 3.000 channels are one queue, not
    3.000 independent ones.
    """
    if provider == PROVIDER_BUFFER:
        return f"conn:{connection.id}"
    return f"provider:{provider}"


def get_provider_context(connection: "BufferConnection") -> ProviderContext:
    """
    Resolve client, credentials and rate-limit scope for a connection.

    This replaces the previous global ``get_buffer_client()`` plus a manual
    ``EncryptionService.decrypt`` at every call site: credential handling now
    lives in one place.
    """
    provider = (connection.provider or PROVIDER_BUFFER).lower()
    account_ref = connection.provider_account_ref
    return ProviderContext(
        provider=provider,
        client=_build_client(provider, account_ref),
        api_key=_resolve_api_key(provider, connection),
        account_ref=account_ref,
        rate_limit_scope=resolve_rate_limit_scope(provider, connection),
    )
