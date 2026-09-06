import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, DateTime, Table, ForeignKey, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# Many-to-Many Association Table between Users and Groups
user_group_association = Table(
    "user_group_association",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", UUID(as_uuid=True), ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False) # active, inactive, suspended
    # --- Portal access (users signing in on our own dashboard) ---
    # NULL for every user created the historical way, by an administrator: those
    # users have no portal credentials and cannot sign in until one is set. A
    # user who registers on the portal sets it at registration.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when the user registered themselves rather than being created by an
    # administrator. Self-registered users start with status="inactive" on
    # purpose: "active" is what makes a user targetable by campaigns
    # (campaign_resolver), so anyone able to hit the public registration
    # endpoint would otherwise insert themselves into the next campaign.
    # An administrator activates them explicitly.
    self_registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Personal referral/promoter link, pasted verbatim into a campaign's resolved
    # text when Campaign.include_referral_link is on (see campaign_resolver.py).
    # Optional: a user with no link set just gets the campaign text unchanged.
    referral_link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Personal contacts/signature block, pasted verbatim right after the referral
    # link (if also on) into a campaign's resolved text when
    # Campaign.include_personal_contacts is on (see campaign_resolver.py).
    # Optional: a user with nothing set here just gets the text unchanged, same
    # as referral_link above.
    personal_contacts: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    groups: Mapped[List["UserGroup"]] = relationship(
        "UserGroup", secondary=user_group_association, back_populates="users"
    )
    buffer_connections: Mapped[List["BufferConnection"]] = relationship(
        "BufferConnection", back_populates="user", cascade="all, delete-orphan"
    )
    campaign_targets: Mapped[List["CampaignTarget"]] = relationship(
        "CampaignTarget", back_populates="user", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="user", cascade="all, delete-orphan"
    )


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    users: Mapped[List[User]] = relationship(
        "User", secondary=user_group_association, back_populates="groups"
    )
