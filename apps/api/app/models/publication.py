import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    campaign_target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_targets.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    social_channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("social_channels.id", ondelete="CASCADE"), nullable=False)
    buffer_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buffer_connections.id", ondelete="CASCADE"), nullable=False)
    
    external_channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # State Machine: pending, queued, processing, submitted, scheduled, published, retry_wait, failed, cancelled, skipped, unknown
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Timestamps
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Remote Post Info
    external_post_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_post_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Error Context
    error_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    request_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    response_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="publications")
    campaign_target: Mapped["CampaignTarget"] = relationship("CampaignTarget", back_populates="publication")
    user: Mapped["User"] = relationship("User", back_populates="publications")
    social_channel: Mapped["SocialChannel"] = relationship("SocialChannel", back_populates="publications")
    buffer_connection: Mapped["BufferConnection"] = relationship("BufferConnection", back_populates="publications")
    attempts: Mapped[List["PublicationAttempt"]] = relationship(
        "PublicationAttempt", back_populates="publication", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "social_channel_id", name="uq_publication_campaign_channel"),
        UniqueConstraint("idempotency_key", name="uq_publication_idempotency_key"),
        Index("idx_publication_status", "status"),
        Index("idx_publication_scheduled_at", "scheduled_at"),
        Index("idx_publication_next_attempt_at", "next_attempt_at"),
        Index("idx_publication_campaign_id", "campaign_id"),
    )


class PublicationAttempt(Base):
    __tablename__ = "publication_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    external_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    sanitized_request: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    sanitized_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    publication: Mapped[Publication] = relationship("Publication", back_populates="attempts")
