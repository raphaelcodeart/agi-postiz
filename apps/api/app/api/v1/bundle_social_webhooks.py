"""
Inbound webhooks from bundle.social.

Why this exists: the hosted OAuth flow finishes on the provider's site, so the
only thing that used to tell us a channel appeared was the user coming back to
our page. That works when they do, and fails silently when they close the tab,
authorise in another window, or connect from the provider's own dashboard - the
exact situation that made a freshly connected Facebook page invisible on our
side until someone pressed refresh.

A webhook removes the dependency on the user's browser entirely: the provider
calls us, and the channel appears whether or not anyone came back.

Public endpoint by necessity (the provider is the caller, it holds no session),
so the signature is the authentication. Configure the URL and copy the signing
secret from https://bundle.social/dashboard/organization/webhooks into
BUNDLE_SOCIAL_WEBHOOK_SECRET.
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.providers import PROVIDER_BUNDLE_SOCIAL
from app.models.buffer import BufferConnection

logger = logging.getLogger(__name__)

router = APIRouter()

# Events that mean "this team's channels may have changed". Post and comment
# events are ignored here: publication state is already tracked through our own
# Publication records, and reacting to both would be two sources of truth.
CHANNEL_EVENTS = {
    "social-account.created",
    "social-account.updated",
    "social-account.deleted",
    "team.updated",
}


def _signature_is_valid(raw_body: bytes, provided: str) -> bool:
    """
    HMAC-SHA256 over the raw request body, compared in constant time.

    The raw bytes matter: re-serializing the parsed JSON would change key order
    and whitespace and never match. Constant-time comparison matters because a
    plain == leaks, one byte at a time, how far a forged signature got.
    """
    expected = hmac.new(
        settings.BUNDLE_SOCIAL_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    candidate = provided.strip()
    # Accept a "sha256=" prefix as well: providers differ on this and the
    # difference is cosmetic, not a security property.
    if candidate.lower().startswith("sha256="):
        candidate = candidate.split("=", 1)[1]

    return hmac.compare_digest(expected, candidate)


@router.post("/bundle-social", status_code=status.HTTP_204_NO_CONTENT)
async def receive_bundle_social_webhook(
    request: Request,
    x_signature: str = Header(default=""),
):
    if not settings.BUNDLE_SOCIAL_WEBHOOK_SECRET:
        # Refuse rather than accept unverified calls: without a secret this
        # endpoint would let anyone trigger syncs on arbitrary teams.
        raise HTTPException(status_code=503, detail="Webhook non configurato.")

    raw_body = await request.body()

    if not x_signature or not _signature_is_valid(raw_body, x_signature):
        # Deliberately terse: a caller who cannot sign gets no detail about why.
        raise HTTPException(status_code=401, detail="Firma non valida.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corpo non valido.")

    event = payload.get("type") or payload.get("event") or ""
    if event not in CHANNEL_EVENTS:
        # Acknowledge and drop: retrying an event we do not act on would just
        # make the provider disable the endpoint.
        return

    data = payload.get("data") or {}
    team_id = data.get("teamId") or data.get("team", {}).get("id") or data.get("id")
    if not team_id:
        logger.warning("Webhook bundle.social '%s' senza teamId, ignorato", event)
        return

    db: Session = SessionLocal()
    try:
        connection = db.query(BufferConnection).filter(
            BufferConnection.provider == PROVIDER_BUNDLE_SOCIAL,
            BufferConnection.provider_account_ref == str(team_id),
        ).first()

        if not connection:
            # A team we do not know about - another integration on the same
            # organization, or one created before this connection existed.
            logger.info("Webhook per team sconosciuto %s, ignorato", team_id)
            return

        connection_id = str(connection.id)
    finally:
        db.close()

    # Queued, not inline: the provider expects a fast acknowledgement and will
    # retry on a timeout, which would sync the same team repeatedly.
    from app.tasks.sync import sync_buffer_connection

    sync_buffer_connection.delay(connection_id)
    logger.info("Webhook '%s': sync accodato per la connessione %s", event, connection_id)
