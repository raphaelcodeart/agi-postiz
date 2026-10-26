import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Boolean, String, DateTime, Table, ForeignKey, Column, false
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
    # administrator. These accounts used to start status="inactive" and wait for
    # a manual activation, because "active" is what makes a user targetable by
    # campaigns (campaign_resolver) and the registration endpoint is public.
    # They now start active by default - the risk that gate covered is handled
    # by announcing campaigns before sending them, which makes a promoter's
    # presence in one visible and refusable. See services/user_activation.py;
    # PlatformSettings.auto_activate_new_users restores the old behaviour.
    self_registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Conferma dell'indirizzo e consenso ---
    # NULL finche' l'utente non ha cliccato il link dell'email di benvenuto. Il
    # portale non lo lascia entrare prima (vedi la guardia in
    # apps/dashboard/app/portal/(app)/layout.tsx): senza un indirizzo che
    # funziona non potremmo ne' resettare la sua password ne' avvisarlo di una
    # campagna, e l'account sarebbe irrecuperabile al primo problema.
    #
    # Resta NULL anche per chi era iscritto prima che la conferma esistesse: la
    # migrazione non la retrodata, perche' insieme all'indirizzo si accettano
    # informativa e termini, che quando si sono iscritti non c'erano. Vedi
    # ``verification_retroactive`` qui sotto.
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Quando ha accettato informativa privacy e termini. Lo stesso clic
    # sull'email di benvenuto vale per entrambe le cose - l'email lo dice
    # esplicitamente e linka i due documenti prima del pulsante - percio' questa
    # colonna e quella sopra si valorizzano insieme. Restano due colonne perche'
    # sono due fatti diversi: un domani l'informativa cambia e va riaccettata
    # senza riconfermare l'indirizzo.
    privacy_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Vero per chi era iscritto prima dell'introduzione di conferma e consenso.
    # Non cambia cosa deve fare - lo stesso clic sull'email - ma cambia cosa gli
    # si dice: non e' un nuovo arrivato da accogliere, e' un utente di sempre a
    # cui si chiede di accettare documenti che prima non esistevano.
    verification_retroactive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # --- Profilo richiesto al primo accesso al portale ---
    # Citta', CAP e gruppi di partecipazione: il portale li chiede con una
    # finestra obbligatoria al primo accesso (vedi get_verified_portal_user in
    # api/v1/portal.py) e non apre nulla finche' profile_completed_at e' NULL.
    # I gruppi scelti finiscono in User.groups, gli stessi che usa il targeting
    # delle campagne: l'utente si trova gia' dentro i gruppi che ha scelto.
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    profile_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
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
    campaign_participations: Mapped[List["CampaignParticipant"]] = relationship(
        "CampaignParticipant", back_populates="user", cascade="all, delete-orphan"
    )
    publications: Mapped[List["Publication"]] = relationship(
        "Publication", back_populates="user", cascade="all, delete-orphan"
    )
    auth_tokens: Mapped[List["UserAuthToken"]] = relationship(
        "UserAuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["UserNotification"]] = relationship(
        "UserNotification", back_populates="user", cascade="all, delete-orphan"
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
