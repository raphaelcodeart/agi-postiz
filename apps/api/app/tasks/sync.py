import uuid
from datetime import datetime, timezone, timedelta
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.core.security import EncryptionService
from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.buffer.service import get_buffer_client
from app.integrations.providers import get_provider_context
from app.integrations.buffer.exceptions import BufferAuthError
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel

logger = get_task_logger(__name__)

def _identity_keys(platform: str, chan_info: dict) -> set:
    """
    Candidate identifiers for "which real social account is this".

    Providers describe the same account differently: Buffer reports the handle in
    `username` and the public profile URL in `external_link`, while
    bundle.social reports the platform's own numeric id in `username` and
    exposes it again as `external_id`, with no profile URL at all. So there is no
    single field to compare - the match is made on any overlapping signal.

    Heuristic by nature, which is why a match blocks publishing but stays
    reversible by an administrator rather than being permanent.
    """
    keys = set()
    raw = chan_info.get("raw") or {}

    for value in (
        raw.get("external_id"),
        chan_info.get("username"),
        chan_info.get("name"),
    ):
        if value:
            keys.add(f"{platform}:{str(value).strip().lower().lstrip('@')}")

    link = chan_info.get("external_link")
    if link:
        # Last meaningful path segment: facebook.com/<page-id>, x.com/<handle>.
        tail = link.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        if tail:
            keys.add(f"{platform}:{tail.strip().lower().lstrip('@')}")

    return keys


def find_duplicate_channel(db, user_id, provider: str, platform: str, chan_info: dict):
    """
    An already-connected channel of the SAME user, on a DIFFERENT provider, that
    looks like the same social account.

    Scoped to one user on purpose: two different clients can legitimately connect
    the same brand page, and that is their business, not a duplicate for us.
    """
    incoming = _identity_keys(platform, chan_info)
    if not incoming:
        return None

    existing_channels = (
        db.query(SocialChannel)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(
            BufferConnection.user_id == user_id,
            BufferConnection.provider != provider,
            SocialChannel.platform == platform,
            SocialChannel.duplicate_of_channel_id.is_(None),
        )
        .all()
    )

    for existing in existing_channels:
        existing_info = existing.raw_metadata or {
            "username": existing.username,
            "name": existing.name,
            "external_link": existing.external_link,
        }
        if incoming & _identity_keys(platform, existing_info):
            return existing

    return None


@celery.task(name="app.tasks.sync.sync_buffer_connection")
def sync_buffer_connection(connection_id_str: str) -> None:
    """
    Syncs organizations and social channels from Buffer for a specific connection.
    """
    logger.info(f"Synchronizing Buffer connection {connection_id_str}")
    connection_id = uuid.UUID(connection_id_str)
    
    db = SessionLocal()
    try:
        conn = db.query(BufferConnection).filter(BufferConnection.id == connection_id).first()
        if not conn:
            logger.error(f"Buffer Connection {connection_id_str} not found.")
            return

        # Client and credentials both come from the provider context: for Buffer
        # that decrypts the user's own key, for a multi-tenant provider it
        # resolves the platform key plus this user's team ref.
        try:
            provider_ctx = get_provider_context(conn)
        except BufferApiError as e:
            conn.status = "error"
            conn.last_error = e.message
            db.commit()
            return
        except Exception as e:
            conn.status = "error"
            conn.last_error = f"Provider resolution failed: {str(e)}"
            db.commit()
            return

        client = provider_ctx.client
        token = provider_ctx.api_key

        # 1. Sync Organizations
        try:
            orgs_data = client.sync_organizations(token)
            active_org_ids = []
            
            for org_info in orgs_data:
                ext_org_id = org_info["id"]
                org_name = org_info["name"]
                
                existing_org = db.query(BufferOrganization).filter(
                    BufferOrganization.buffer_connection_id == conn.id,
                    BufferOrganization.external_organization_id == ext_org_id
                ).first()
                
                if existing_org:
                    existing_org.name = org_name
                    existing_org.is_active = org_info.get("is_active", True)
                    existing_org.raw_metadata = org_info
                    org = existing_org
                else:
                    org = BufferOrganization(
                        buffer_connection_id=conn.id,
                        external_organization_id=ext_org_id,
                        name=org_name,
                        is_active=org_info.get("is_active", True),
                        raw_metadata=org_info
                    )
                    db.add(org)
                
                db.flush()
                active_org_ids.append(org.id)

                # 2. Sync Social Channels for this Organization
                channels_data = client.sync_channels(token, ext_org_id)
                active_chan_ids = []
                
                for chan_info in channels_data:
                    ext_chan_id = chan_info["id"]
                    
                    existing_chan = db.query(SocialChannel).filter(
                        SocialChannel.buffer_organization_id == org.id,
                        SocialChannel.external_channel_id == ext_chan_id
                    ).first()
                    
                    # Same real account already connected through another
                    # provider? Publishing to both would post twice on the
                    # client's actual profile, so the newcomer arrives inactive
                    # and disabled rather than silently doubling every campaign.
                    duplicate_of = None
                    if not existing_chan:
                        duplicate_of = find_duplicate_channel(
                            db, conn.user_id, conn.provider, chan_info["platform"], chan_info
                        )
                        if duplicate_of:
                            logger.warning(
                                "Canale %s (%s) duplica %s: importato disattivato",
                                chan_info.get("name"), conn.provider, duplicate_of.id,
                            )

                    chan_properties = {
                        "platform": chan_info["platform"],
                        "name": chan_info["name"],
                        "username": chan_info.get("username"),
                        "avatar_url": chan_info.get("avatar_url"),
                        "external_link": chan_info.get("external_link"),
                        "channel_type": chan_info.get("channel_type"),
                        "is_active": True,
                        "raw_metadata": chan_info,
                        "last_sync_at": datetime.now(timezone.utc)
                    }

                    if duplicate_of is not None:
                        chan_properties["is_active"] = False
                        chan_properties["publication_mode"] = "disabled"
                        chan_properties["duplicate_of_channel_id"] = duplicate_of.id
                    
                    if existing_chan:
                        for k, v in chan_properties.items():
                            setattr(existing_chan, k, v)
                        existing_chan.provider = conn.provider
                        # A later sync reports the channel as connected upstream
                        # and would flip is_active back on, undoing the block on
                        # every refresh. The flag wins until an admin clears it.
                        if existing_chan.duplicate_of_channel_id is not None:
                            existing_chan.is_active = False
                            existing_chan.publication_mode = "disabled"
                        chan = existing_chan
                    else:
                        chan = SocialChannel(
                            buffer_organization_id=org.id,
                            external_channel_id=ext_chan_id,
                            # Denormalized from the connection so campaigns can
                            # filter by origin without a two-level join.
                            provider=conn.provider,
                            publication_mode="automatic",
                            auto_publish_enabled=True,
                            **chan_properties
                        )
                        db.add(chan)
                    db.flush()
                    active_chan_ids.append(chan.id)
                
                # Deactivate deleted social channels for this org
                db.query(SocialChannel).filter(
                    SocialChannel.buffer_organization_id == org.id,
                    SocialChannel.id.not_in(active_chan_ids)
                ).update({"is_active": False}, synchronize_session=False)

            # Deactivate deleted organizations
            db.query(BufferOrganization).filter(
                BufferOrganization.buffer_connection_id == conn.id,
                BufferOrganization.id.not_in(active_org_ids)
            ).update({"is_active": False}, synchronize_session=False)

            conn.status = "connected"
            conn.last_sync_at = datetime.now(timezone.utc)
            conn.last_error = None
            db.commit()
            logger.info(f"Sync complete for connection {connection_id_str}")

        except BufferAuthError as e:
            logger.warning(f"Auth failure syncing connection {connection_id_str}: {str(e)}")
            conn.status = "expired"
            conn.last_error = f"Authentication failure: {str(e)}"
            db.commit()
        except Exception as e:
            logger.error(f"Generic error syncing connection {connection_id_str}: {str(e)}")
            conn.status = "error"
            conn.last_error = f"Synchronization failure: {str(e)}"
            db.commit()
            
    finally:
        db.close()


@celery.task(name="app.tasks.sync.sync_all_buffer_connections")
def sync_all_buffer_connections() -> None:
    """
    Periodic fan-out: re-syncs every connection whose state might legitimately
    have drifted since the last sync (organizations/channels added, removed, or
    changed on Buffer's side - e.g. is_active, channel_type). Dispatches the
    existing per-connection sync_buffer_connection task for each one instead of
    duplicating its logic here.

    Deliberately excludes:
    - "disconnected": the admin explicitly disconnected it - resyncing would
      contradict that choice.
    - "revoked": this platform authenticates with a personal Buffer API key
      pasted by the admin (see DATABASE.md §5), not OAuth - a revoked key can
      only be fixed by pasting a new one, sync can never recover it on its own.
    - "pending": not yet validated once, nothing to refresh yet.
    """
    db = SessionLocal()
    try:
        connections = db.query(BufferConnection).filter(
            BufferConnection.status.in_(["connected", "expired", "error"])
        ).all()
        if not connections:
            return
        logger.info(f"Periodic sync: dispatching sync_buffer_connection for {len(connections)} connections")
        for conn in connections:
            sync_buffer_connection.delay(str(conn.id))
    finally:
        db.close()


@celery.task(name="app.tasks.sync.refresh_expired_tokens")
def refresh_expired_tokens() -> None:
    """
    LEGACY, currently a no-op by construction - kept for the day a provider with
    expiring OAuth tokens is added.

    It dates from when Buffer still offered third-party OAuth. Neither provider
    in use today has a per-connection token to refresh: Buffer authenticates
    with a personal API key that never expires (so token_expires_at is always
    NULL and the query below matches nothing), and a multi-tenant provider
    authenticates with our own platform key, which is not stored per connection.

    Note it calls ``client.refresh_token()``, which is NOT part of
    BaseBufferClient: reaching that line with a real connection would raise
    AttributeError. The provider filter below makes that unreachable rather
    than merely unlikely. Implement refresh_token on the client interface before
    enabling this for any provider.
    """
    db = SessionLocal()
    try:
        # Check tokens expiring in less than 2 days or already expired
        limit_time = datetime.now(timezone.utc) + timedelta(days=2)
        expiring_connections = db.query(BufferConnection).filter(
            BufferConnection.status.in_(["connected", "expired"]),
            BufferConnection.token_expires_at.isnot(None),
            BufferConnection.token_expires_at <= limit_time,
            # No provider currently supports refresh - see the docstring.
            BufferConnection.authentication_type == "oauth",
        ).all()

        if not expiring_connections:
            return

        client = get_buffer_client()
        logger.info(f"Found {len(expiring_connections)} expiring connections. Starting refresh.")

        for conn in expiring_connections:
            try:
                refresh_token = EncryptionService.decrypt(conn.refresh_token_encrypted)
                if not refresh_token:
                    raise ValueError("Refresh token is empty")
                
                # Request new token pair
                refresh_res = client.refresh_token(refresh_token)
                
                # Encrypt and update
                conn.access_token_encrypted = EncryptionService.encrypt(refresh_res["access_token"])
                if "refresh_token" in refresh_res:
                    conn.refresh_token_encrypted = EncryptionService.encrypt(refresh_res["refresh_token"])
                
                expires_in = refresh_res.get("expires_in", 3600)
                conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                conn.status = "connected"
                conn.last_error = None
                
                logger.info(f"Successfully refreshed token for connection {conn.id}")
            except BufferAuthError as e:
                logger.error(f"Auth failure refreshing token for connection {conn.id}: {str(e)}")
                conn.status = "revoked"
                conn.last_error = f"Token refresh authorization revoked: {str(e)}"
            except Exception as e:
                logger.error(f"Failed to refresh token for connection {conn.id}: {str(e)}")
                conn.last_error = f"Token refresh failure: {str(e)}"
                
        db.commit()
    finally:
        db.close()
