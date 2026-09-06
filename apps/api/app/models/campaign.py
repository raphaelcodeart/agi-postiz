import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    default_text: Mapped[str] = mapped_column(String(5000), nullable=False)
    
    # Platform Overrides
    instagram_text: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    facebook_text: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    linkedin_text: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    tiktok_text: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    youtube_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    youtube_description: Mapped[Optional[str]] = mapped_column(String(5000), nullable=True)
    x_text: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    threads_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    media_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True)
    # Set when this campaign was created via Blog Writer's "Usa per campagna social"
    # (blog_writer_articles.id) - purely informational, no behavior depends on it.
    article_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("blog_writer_articles.id", ondelete="SET NULL"), nullable=True)

    publishing_mode: Mapped[str] = mapped_column(String(50), default="immediate", nullable=False) # immediate, scheduled, buffer_queue, draft, approval
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    targeting_mode: Mapped[str] = mapped_column(String(50), default="all_active_channels", nullable=False) # all_active_channels, selected_users, selected_groups, selected_channels, selected_platforms
    # Off by default: when on, resolve_text_for_channel appends the resolving
    # channel's owning User.referral_link (if that user has one set) to the
    # resolved text of every target - each channel always gets its own owning
    # user's link, never another user's, since resolution happens per target.
    # If off, text resolution is identical to before this field existed.
    include_referral_link: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Off by default, same mechanics as include_referral_link above but for the
    # resolving channel's owning User.personal_contacts, appended right after the
    # referral link (see resolve_text_for_channel) - a signature-style block of
    # text (name, phone, etc.) rather than a single URL.
    include_personal_contacts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Targeting params matching targeting_mode (e.g. user_ids/group_ids/channel_ids),
    # persisted so poll_and_queue_scheduled_publications can re-launch a scheduled
    # campaign with the same selection later.
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False) # draft, preparing, queued, running, paused, partially_completed, completed, failed, cancelled
    
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    media_file: Mapped[Optional["MediaFile"]] = relationship("MediaFile", back_populates="campaigns")
    targets: Mapped[List["CampaignTarget"]] = relationship("CampaignTarget", back_populates="campaign", cascade="all, delete-orphan")
    publications: Mapped[List["Publication"]] = relationship("Publication", back_populates="campaign", cascade="all, delete-orphan")


class CampaignTarget(Base):
    __tablename__ = "campaign_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    social_channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("social_channels.id", ondelete="CASCADE"), nullable=False)
    resolved_text: Mapped[str] = mapped_column(String(5000), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False) # pending, created, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="targets")
    user: Mapped["User"] = relationship("User", back_populates="campaign_targets")
    social_channel: Mapped["SocialChannel"] = relationship("SocialChannel", back_populates="campaign_targets")
    publication: Mapped[Optional["Publication"]] = relationship("Publication", back_populates="campaign_target", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("campaign_id", "social_channel_id", name="uq_campaign_target_campaign_channel"),
    )
