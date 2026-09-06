import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BufferConnection(Base):
    __tablename__ = "buffer_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    authentication_type: Mapped[str] = mapped_column(String(50), default="personal_api_key", nullable=False) # personal_api_key (only supported mechanism; Buffer has no working third-party OAuth as of July 2026)
    external_account_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False) # pending, connected, expired, revoked, error, disconnected
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="buffer_connections")
    organizations: Mapped[List["BufferOrganization"]] = relationship(
        "BufferOrganization", back_populates="buffer_connection", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="buffer_connection"
    )


class BufferOrganization(Base):
    __tablename__ = "buffer_organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buffer_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buffer_connections.id", ondelete="CASCADE"), nullable=False)
    external_organization_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    buffer_connection: Mapped[BufferConnection] = relationship("BufferConnection", back_populates="organizations")
    channels: Mapped[List["SocialChannel"]] = relationship(
        "SocialChannel", back_populates="buffer_organization", cascade="all, delete-orphan"
    )


class SocialChannel(Base):
    __tablename__ = "social_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buffer_organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buffer_organizations.id", ondelete="CASCADE"), nullable=False)
    external_channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False) # instagram, facebook, linkedin, tiktok, youtube, x, etc.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    external_link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True) # public profile/page URL on the social network itself (Buffer's Channel.externalLink), not a Buffer URL
    channel_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # e.g. "page", "group", "profile"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_publish_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    publication_mode: Mapped[str] = mapped_column(String(50), default="automatic", nullable=False) # automatic, notification, approval, disabled
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    buffer_organization: Mapped[BufferOrganization] = relationship("BufferOrganization", back_populates="channels")
    campaign_targets: Mapped[List["CampaignTarget"]] = relationship(
        "CampaignTarget", back_populates="social_channel", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="social_channel", cascade="all, delete-orphan"
    )
