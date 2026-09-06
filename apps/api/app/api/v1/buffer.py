from datetime import datetime, timezone
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.core.security import EncryptionService
from app.integrations.buffer.service import get_buffer_client
from app.integrations.buffer.exceptions import BufferAuthError
from app.tasks.sync import sync_buffer_connection
from app.schemas.schemas import (
    BufferConnectionCreateRequest,
    BufferConnectionResponse,
    BufferOrganizationResponse,
    SocialChannelResponse,
)

router = APIRouter()

@router.get("/connections", response_model=List[BufferConnectionResponse])
def list_connections(
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve list of all connection instances."""
    return db.query(BufferConnection).all()


@router.post("/connections", response_model=BufferConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_or_update_connection(
    payload: BufferConnectionCreateRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Collega (o ricollega) l'account Buffer personale di un utente usando la
    chiave API personale che l'utente genera dal proprio account Buffer
    (Settings -> API). Buffer non offre OAuth per app di terze parti al
    momento (verificato su developers.buffer.com, luglio 2026), quindi questo
    è l'unico meccanismo di collegamento supportato.
    """
    from app.models.user import User
    user = db.query(User).filter(User.id == payload.user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    client = get_buffer_client()
    try:
        account_info = client.get_user_info(payload.api_key)
    except BufferAuthError:
        raise HTTPException(status_code=400, detail="Chiave API Buffer non valida")

    ext_account_id = account_info.get("id")
    enc_key = EncryptionService.encrypt(payload.api_key)

    connection = db.query(BufferConnection).filter(BufferConnection.user_id == payload.user_id).first()
    if connection:
        connection.authentication_type = "personal_api_key"
        connection.external_account_id = ext_account_id
        connection.access_token_encrypted = enc_key
        connection.refresh_token_encrypted = None
        connection.token_expires_at = None
        connection.status = "connected"
        connection.last_error = None
    else:
        connection = BufferConnection(
            user_id=payload.user_id,
            authentication_type="personal_api_key",
            external_account_id=ext_account_id,
            access_token_encrypted=enc_key,
            status="connected",
        )
        db.add(connection)

    db.commit()
    db.refresh(connection)

    # Dispatch background sync task for organizations/channels
    sync_buffer_connection.delay(str(connection.id))

    return connection


@router.post("/connections/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_connection(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Enqueues manual channels/organizations sync for a Buffer connection."""
    conn = db.query(BufferConnection).filter(BufferConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    sync_buffer_connection.delay(str(conn.id))
    return {"message": "Sync job dispatched to background worker"}


@router.get("/channels", response_model=List[SocialChannelResponse])
def list_channels(
    user_id: Optional[uuid.UUID] = None,
    platform: Optional[str] = None,
    publication_mode: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """List social channels with filters."""
    query = db.query(SocialChannel, BufferConnection.user_id).join(
        BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id
    ).join(
        BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id
    )

    if user_id:
        query = query.filter(BufferConnection.user_id == user_id)
    if platform:
        query = query.filter(SocialChannel.platform == platform.lower().strip())
    if publication_mode:
        query = query.filter(SocialChannel.publication_mode == publication_mode)

    channels = []
    for channel, owner_user_id in query.all():
        channel.user_id = owner_user_id
        channels.append(channel)
    return channels


@router.put("/channels/{channel_id}/publication-mode", response_model=SocialChannelResponse)
def update_channel_mode(
    channel_id: uuid.UUID,
    mode: str, # automatic, notification, approval, disabled
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Modify the publishing configuration mode of a social channel."""
    if mode not in ("automatic", "notification", "approval", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid publication mode name.")
        
    channel = db.query(SocialChannel).filter(SocialChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel.publication_mode = mode
    channel.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(channel)

    owner_user_id = db.query(BufferConnection.user_id).join(
        BufferOrganization, BufferOrganization.buffer_connection_id == BufferConnection.id
    ).filter(BufferOrganization.id == channel.buffer_organization_id).scalar()
    channel.user_id = owner_user_id
    return channel


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_connection(
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Delete a Buffer connection, which cascade-deletes organizations and channels."""
    conn = db.query(BufferConnection).filter(BufferConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    db.delete(conn)
    db.commit()
    return
