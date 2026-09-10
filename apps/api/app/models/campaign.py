import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Boolean, Index
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
    # Off by default, same mechanics as the two above. Appends the advertising
    # disclosure required when a post carries an affiliate link: the promoter
    # earns a commission, which makes it commercial communication regardless of
    # whether the platform pays them directly. Put on the campaign rather than
    # left to each promoter because the text is written here - with hundreds of
    # collaborators, relying on each of them remembering is not a control.
    # The wording itself is configurable (platform_settings), not hardcoded.
    include_affiliate_disclosure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Targeting params matching targeting_mode (e.g. user_ids/group_ids/channel_ids),
    # persisted so poll_and_queue_scheduled_publications can re-launch a scheduled
    # campaign with the same selection later.
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # --- Participation (the announced line-up) ---------------------------------
    # "automatic": every resolved channel is published to, the way campaigns have
    #     always worked here. Unchanged default, so nothing that exists behaves
    #     differently.
    # "opt_out": the campaign is announced to the people it targets first, and
    #     they get a window in which to take their channels out of it. Nothing
    #     reaches the provider until the campaign is launched.
    #
    # The distinction is not cosmetic. Launching is the irreversible step: a
    # scheduled campaign hands the provider each post *with its date* at launch,
    # so from that moment on "I do not want to be in this" is no longer something
    # we can honour. The line-up exists to put a real decision point before it.
    participation_mode: Mapped[str] = mapped_column(
        String(30), default="automatic", server_default="automatic", nullable=False
    )
    # When the line-up was published to its participants. NULL while the campaign
    # is still a private draft.
    announced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Until when a participant may withdraw. After it the line-up is final; the
    # portal keeps showing the campaign, with the button gone and the reason
    # stated. NULL means the window stays open until the campaign is launched.
    opt_out_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # What happens when that deadline passes. False (the default) means the
    # campaign simply waits for an administrator to press Launch - the deadline
    # only closes the window. True means the beat task launches it with whoever
    # is left, so an announced campaign needs no second visit to go out.
    auto_launch_at_deadline: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # draft, announced, preparing, queued, running, paused, partially_completed,
    # completed, failed, cancelled.
    # "announced" is the opt-out window: participants exist, nothing has been
    # sent, and both an administrator's Launch and the deadline can end it.
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    media_file: Mapped[Optional["MediaFile"]] = relationship("MediaFile", back_populates="campaigns")
    targets: Mapped[List["CampaignTarget"]] = relationship("CampaignTarget", back_populates="campaign", cascade="all, delete-orphan")
    participants: Mapped[List["CampaignParticipant"]] = relationship(
        "CampaignParticipant", back_populates="campaign", cascade="all, delete-orphan"
    )
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


class CampaignParticipant(Base):
    """
    One channel's place in an *announced* campaign, before it becomes a target.

    Separate from CampaignTarget on purpose - they answer different questions at
    different times:

      CampaignParticipant  who is in the line-up, and did the owner accept it?
                           Exists from the moment the campaign is announced,
                           while nothing has been sent anywhere.
      CampaignTarget       what text goes to which channel, and its Publication.
                           Created at launch, one per channel that will actually
                           be published to.

    Folding the two together would have meant creating targets for channels that
    may never publish, which breaks the invariant the whole publishing side rests
    on: one target, one publication, one post (AGENTS.md rule 1). It would also
    make it impossible to record a refusal at all - a channel whose owner opted
    out must have no target, yet the refusal is exactly the thing the user's own
    history has to show.

    Rows are never deleted, including when someone withdraws: the history of
    which campaigns a promoter was offered and which they declined is the record
    this table exists for. Withdrawing flips ``status``.
    """

    __tablename__ = "campaign_participants"

    # Currently in the line-up: will receive a target when the campaign launches.
    STATUS_INCLUDED = "included"
    # The channel's owner took themselves out during the opt-out window.
    STATUS_WITHDRAWN = "withdrawn"
    # An administrator took the channel out after announcing.
    STATUS_REMOVED = "removed"

    # Put in the line-up by the administrator who announced the campaign.
    SOURCE_ADMIN = "admin"
    # Added by the channel's own owner, from the portal's line-up page.
    SOURCE_USER = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    social_channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_channels.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(30), default=STATUS_INCLUDED, nullable=False)
    added_by: Mapped[str] = mapped_column(String(20), default=SOURCE_ADMIN, nullable=False)

    # Set when status leaves STATUS_INCLUDED. The reason is optional and free
    # text: an administrator reading "non mi interessa il prodotto" learns
    # something a status flag cannot carry, and forcing a reason would only
    # produce a field full of ".".
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="participants")
    user: Mapped["User"] = relationship("User", back_populates="campaign_participations")
    social_channel: Mapped["SocialChannel"] = relationship(
        "SocialChannel", back_populates="campaign_participations"
    )

    __table_args__ = (
        # A channel appears at most once per campaign, whoever put it there.
        # This is also what makes "join" idempotent: a second click updates the
        # existing row instead of adding a duplicate to the line-up.
        UniqueConstraint("campaign_id", "social_channel_id", name="uq_campaign_participant_campaign_channel"),
        # The portal's line-up page is "every open campaign for this user", read
        # on every page load.
        Index("idx_campaign_participants_user", "user_id"),
        Index("idx_campaign_participants_campaign_status", "campaign_id", "status"),
    )
