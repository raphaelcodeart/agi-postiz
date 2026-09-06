import uuid
from datetime import datetime, timezone, timedelta
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.core.security import EncryptionService
from app.integrations.buffer.service import get_buffer_client
from app.integrations.buffer.exceptions import BufferAuthError
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel

logger = get_task_logger(__name__)

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

        client = get_buffer_client()
        
        # Decrypt access token
        try:
            token = EncryptionService.decrypt(conn.access_token_encrypted)
        except Exception as e:
            conn.status = "error"
            conn.last_error = f"Token decryption failed: {str(e)}"
            db.commit()
            return

        if not token:
            conn.status = "error"
            conn.last_error = "Access token is empty"
            db.commit()
            return

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
                    
                    if existing_chan:
                        for k, v in chan_properties.items():
                            setattr(existing_chan, k, v)
                        chan = existing_chan
                    else:
                        chan = SocialChannel(
                            buffer_organization_id=org.id,
                            external_channel_id=ext_chan_id,
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
    Checks for all connections nearing expiration (or expired) and refreshes their access tokens.
    """
    db = SessionLocal()
    try:
        # Check tokens expiring in less than 2 days or already expired
        limit_time = datetime.now(timezone.utc) + timedelta(days=2)
        expiring_connections = db.query(BufferConnection).filter(
            BufferConnection.status.in_(["connected", "expired"]),
            BufferConnection.token_expires_at <= limit_time
        ).all()

        if not expiring_connections:
            return

        client = get_buffer_client()
        logger.info(f"Found {len(expiring_connections)} expiring Buffer connections. Starting refresh.")

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
