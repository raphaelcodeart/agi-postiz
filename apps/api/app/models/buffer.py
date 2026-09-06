import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BufferConnection(Base):
    __tablename__ = "buffer_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Upstream provider this connection publishes through - see
    # app/integrations/providers.py. The table keeps its historical buffer_*
    # name although it now holds more than Buffer: renaming it would ripple
    # through every relationship, index and constraint in the schema for no
    # behavioural gain.
    provider: Mapped[str] = mapped_column(String(30), default="buffer", server_default="buffer", nullable=False)
    # Provider-side identifier of this user's isolated space, when the provider
    # has one: bundle.social team id. Always NULL for Buffer, where the user's
    # own API key already scopes every call.
    provider_account_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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

    __table_args__ = (
        # One connection per user per provider: a user can publish through
        # Buffer and through our own provider at the same time, splitting
        # channels across both (useful against Buffer's free-tier channel cap).
        UniqueConstraint("user_id", "provider", name="uq_buffer_connection_user_provider"),
    )

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
    # Denormalized from the owning connection: campaigns filter on it and the
    # dashboard shows it as an origin badge, both hot paths where a two-level
    # join through buffer_organizations would buy nothing.
    provider: Mapped[str] = mapped_column(String(30), default="buffer", server_default="buffer", nullable=False)
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

    __table_args__ = (
        # Campaign targeting filters channels by provider on every launch,
        # alongside is_active/publication_mode.
        Index("idx_social_channels_provider", "provider"),
    )

    # Relationships
    buffer_organization: Mapped[BufferOrganization] = relationship("BufferOrganization", back_populates="channels")
    campaign_targets: Mapped[List["CampaignTarget"]] = relationship(
        "CampaignTarget", back_populates="social_channel", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="social_channel", cascade="all, delete-orphan"
    )
