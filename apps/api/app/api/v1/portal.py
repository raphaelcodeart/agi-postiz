"""
Portal API - the surface end users see when they sign in on our own dashboard.

Deliberately a SEPARATE router rather than tenancy retrofitted onto the existing
admin endpoints. Those endpoints were written on the assumption that the caller
sees everything (``get_current_admin``), and every one of them would have to be
audited and re-tested to be safe for an end user; one missed filter is a data
leak between customers. A small purpose-built surface that can only ever read
the authenticated user's own rows is far easier to keep correct - and to review.

Two rules hold everywhere in this file:

1. Every query filters on ``current_user.id``. The user id is taken from the
   validated token, never from a path or body parameter, so there is no
   identifier for a caller to tamper with.
2. Nothing here exposes a credential, not even indirectly - no API keys, no
   encrypted blobs, no provider tokens (AGENTS.md rules 8-10).
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import TOKEN_TYPE_PORTAL_USER, SecurityService
from app.db.session import get_db
from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.providers import PROVIDER_BUNDLE_SOCIAL, PROVIDER_LABELS
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign, CampaignParticipant, CampaignTarget
from app.models.publication import Publication
from app.models.statistics import StatPostMetric
from app.models.user import User
from app.services import campaign_participation, user_activation

router = APIRouter()

portal_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/portal/auth/login",
    auto_error=False,
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class PortalRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    company_name: Optional[str] = Field(default=None, max_length=255)


class PortalLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PortalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PortalUserResponse(BaseModel):
    id: str
    name: str
    email: str
    company_name: Optional[str]
    status: str
    # False until an administrator activates the account. The dashboard uses it
    # to explain why a freshly registered user is not in any campaign yet.
    is_active_for_campaigns: bool
    referral_link: Optional[str]
    created_at: datetime


class PortalChannelResponse(BaseModel):
    id: str
    platform: str
    name: str
    username: Optional[str]
    avatar_url: Optional[str]
    external_link: Optional[str]
    is_active: bool
    publication_mode: str
    provider: str
    provider_label: str
    last_sync_at: Optional[datetime]
    # Explains why an inactive channel is inactive. Without it the user sees a
    # channel they connected sitting there switched off with no reason given,
    # and reasonably assumes something is broken.
    blocked_reason: Optional[str] = None
    # True when the channel is no longer connected upstream and can therefore be
    # removed from the list without touching anything that still works.
    can_remove: bool = False


class PortalCampaignResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    # This user's own slice of the campaign, never the campaign-wide totals:
    # a promoter has no business seeing how other promoters performed.
    channels_targeted: int
    published: int
    failed: int
    pending: int
    # How this user stands in the campaign's line-up. A campaign they declined
    # produces no targets and no publications at all, so without these two it
    # would vanish from their history - which is exactly the record they need to
    # be able to check ("did I actually say no to that one?").
    participation_included: int = 0
    participation_withdrawn: int = 0
    # Taken out by an administrator rather than by the user. Reported separately
    # because the two read very differently to the person looking at their own
    # history: one is a decision they made, the other is one made about them, and
    # collapsing them would have the portal tell someone they declined a campaign
    # they never declined.
    participation_removed: int = 0


class PortalStatsResponse(BaseModel):
    channels_connected: int
    channels_by_provider: Dict[str, int]
    campaigns_joined: int
    posts_published: int
    posts_failed: int
    total_impressions: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_views: int
    total_reach: int
    total_follows: int
    total_clicks: int
    # L'unica metrica in percentuale: media dei post che la riportano, mai una
    # somma (stessa regola di statistics_service._totals_dict). None quando
    # nessun post ne ha una - 0.0 direbbe "coinvolgimento nullo" invece di
    # "non riportato".
    engagement_rate: Optional[float] = None


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

def get_current_portal_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(portal_oauth2_scheme),
) -> User:
    """
    Resolve the signed-in end user.

    Rejects administrator tokens: ``verify_access_token`` is asked for the
    portal audience specifically, so a valid admin JWT does not authenticate
    here (and vice versa - see core/security.py).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessione non valida o scaduta.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    user_id = SecurityService.verify_access_token(token, expected_type=TOKEN_TYPE_PORTAL_USER)
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id,
        User.deleted_at.is_(None),
    ).first()

    if not user or not user.password_hash:
        raise credentials_exception

    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="Account sospeso. Contatta l'amministratore.")

    return user


@router.post("/auth/register", response_model=PortalTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: PortalRegisterRequest, db: Session = Depends(get_db)):
    """
    Self-service registration.

    A new account starts active unless an administrator has turned automatic
    activation off (PlatformSettings.auto_activate_new_users) - see
    services/user_activation.py for why that default flipped. With it off the
    account still works: the user signs in, connects channels and sees their
    dashboard; it is only campaign targeting that waits.
    """
    email = payload.email.lower().strip()
    existing = db.query(User).filter(func.lower(User.email) == email).first()

    if existing:
        # An administrator may already have created this person, without portal
        # credentials. Let them claim that account rather than being blocked by
        # a row they cannot see - but never overwrite an existing password, or
        # this endpoint would be an account takeover.
        if existing.password_hash or existing.deleted_at is not None:
            raise HTTPException(status_code=409, detail="Esiste già un account con questa email.")
        existing.password_hash = SecurityService.hash_password(payload.password)
        existing.self_registered_at = datetime.now(timezone.utc)
        # An administrator created this row and may have set its status
        # deliberately; claiming it must not silently promote a suspended
        # account, so only the waiting-room state is resolved.
        if existing.status == user_activation.STATUS_INACTIVE:
            existing.status = user_activation.status_for_new_registration(db)
        if payload.company_name:
            existing.company_name = payload.company_name
        user = existing
    else:
        user = User(
            name=payload.name.strip(),
            email=email,
            company_name=payload.company_name,
            status=user_activation.status_for_new_registration(db),
            password_hash=SecurityService.hash_password(payload.password),
            self_registered_at=datetime.now(timezone.utc),
        )
        db.add(user)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return PortalTokenResponse(
        access_token=SecurityService.create_access_token(
            subject=user.id, token_type=TOKEN_TYPE_PORTAL_USER
        )
    )


@router.post("/auth/login", response_model=PortalTokenResponse)
def login(payload: PortalLoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(
        func.lower(User.email) == email,
        User.deleted_at.is_(None),
    ).first()

    # Same message whether the address is unknown or the password is wrong, so
    # this endpoint cannot be used to enumerate registered users.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email o password non corretti.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not user or not user.password_hash:
        raise invalid
    if not SecurityService.verify_password(payload.password, user.password_hash):
        raise invalid
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="Account sospeso. Contatta l'amministratore.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return PortalTokenResponse(
        access_token=SecurityService.create_access_token(
            subject=user.id, token_type=TOKEN_TYPE_PORTAL_USER
        )
    )


@router.get("/me", response_model=PortalUserResponse)
def get_me(current_user: User = Depends(get_current_portal_user)):
    return PortalUserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=current_user.company_name,
        status=current_user.status,
        is_active_for_campaigns=current_user.status == "active",
        referral_link=current_user.referral_link,
        created_at=current_user.created_at,
    )


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------

def _user_channels_query(db: Session, user: User):
    """
    Channels belonging to this user, across every provider.

    Ownership runs channel -> organization -> connection -> user, so the join is
    the access control: there is no path here to another user's rows.
    """
    return (
        db.query(SocialChannel)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(
            BufferConnection.user_id == user.id,
            SocialChannel.deleted_at.is_(None),
        )
    )


@router.get("/channels", response_model=List[PortalChannelResponse])
def list_my_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    channels = _user_channels_query(db, current_user).order_by(SocialChannel.platform).all()
    return [
        PortalChannelResponse(
            id=str(c.id),
            platform=c.platform,
            name=c.name,
            username=c.username,
            avatar_url=c.avatar_url,
            external_link=c.external_link,
            is_active=c.is_active,
            publication_mode=c.publication_mode,
            provider=c.provider,
            provider_label=PROVIDER_LABELS.get(c.provider, c.provider),
            last_sync_at=c.last_sync_at,
            blocked_reason=(
                "Questo profilo risulta già collegato tramite un altro "
                "servizio. È tenuto disattivo per non pubblicare due volte "
                "sullo stesso account."
                if c.duplicate_of_channel_id is not None
                else None
            ),
            can_remove=not c.is_active,
        )
        for c in channels
    ]


# --------------------------------------------------------------------------
# Campaigns and statistics
# --------------------------------------------------------------------------

@router.get("/campaigns", response_model=List[PortalCampaignResponse])
def list_my_campaigns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Campaigns this user takes part in, with their own outcome only.

    Scoped through ``campaign_targets.user_id``: a campaign the user was never
    targeted by simply does not appear, and the counters below are filtered by
    the same user id rather than aggregated campaign-wide.
    """
    # Union of two routes into a campaign, not just one: a campaign the user was
    # offered and declined has no CampaignTarget row by design, and filtering on
    # targets alone would erase every refusal from their own history.
    targeted_ids = {
        row[0]
        for row in db.query(CampaignTarget.campaign_id)
        .filter(CampaignTarget.user_id == current_user.id)
        .distinct()
        .all()
    }
    participated_ids = {
        row[0]
        for row in db.query(CampaignParticipant.campaign_id)
        .filter(CampaignParticipant.user_id == current_user.id)
        .distinct()
        .all()
    }
    campaign_ids = list(targeted_ids | participated_ids)
    if not campaign_ids:
        return []

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.id.in_(campaign_ids))
        .order_by(Campaign.created_at.desc())
        .all()
    )

    counts = dict(
        db.query(CampaignTarget.campaign_id, func.count(CampaignTarget.id))
        .filter(CampaignTarget.user_id == current_user.id)
        .group_by(CampaignTarget.campaign_id)
        .all()
    )

    status_rows = (
        db.query(Publication.campaign_id, Publication.status, func.count(Publication.id))
        .filter(
            Publication.user_id == current_user.id,
            Publication.campaign_id.in_(campaign_ids),
        )
        .group_by(Publication.campaign_id, Publication.status)
        .all()
    )
    by_campaign: Dict[Any, Dict[str, int]] = {}
    for campaign_id, pub_status, count in status_rows:
        by_campaign.setdefault(campaign_id, {})[pub_status] = count

    participation_rows = (
        db.query(
            CampaignParticipant.campaign_id,
            CampaignParticipant.status,
            func.count(CampaignParticipant.id),
        )
        .filter(
            CampaignParticipant.user_id == current_user.id,
            CampaignParticipant.campaign_id.in_(campaign_ids),
        )
        .group_by(CampaignParticipant.campaign_id, CampaignParticipant.status)
        .all()
    )
    participation_by_campaign: Dict[Any, Dict[str, int]] = {}
    for campaign_id, participation_status, count in participation_rows:
        participation_by_campaign.setdefault(campaign_id, {})[participation_status] = count

    result = []
    for campaign in campaigns:
        statuses = by_campaign.get(campaign.id, {})
        published = statuses.get("published", 0) + statuses.get("scheduled", 0)
        failed = statuses.get("failed", 0)
        pending = sum(
            count for key, count in statuses.items()
            if key in ("pending", "queued", "processing", "retry_wait")
        )
        participation = participation_by_campaign.get(campaign.id, {})
        result.append(
            PortalCampaignResponse(
                id=str(campaign.id),
                title=campaign.title,
                status=campaign.status,
                created_at=campaign.created_at,
                channels_targeted=counts.get(campaign.id, 0),
                published=published,
                failed=failed,
                pending=pending,
                participation_included=participation.get(
                    CampaignParticipant.STATUS_INCLUDED, 0
                ),
                participation_withdrawn=participation.get(
                    CampaignParticipant.STATUS_WITHDRAWN, 0
                ),
                participation_removed=participation.get(
                    CampaignParticipant.STATUS_REMOVED, 0
                ),
            )
        )
    return result


@router.get("/stats", response_model=PortalStatsResponse)
def get_my_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Headline figures for the user's own dashboard.

    Reads the same persisted ``stat_post_metrics`` the admin statistics module
    fills, filtered to this user - so the numbers a promoter sees always agree
    with what the administrator sees for them, and no upstream call is made
    while rendering a dashboard.
    """
    channels = _user_channels_query(db, current_user).all()
    channels_by_provider: Dict[str, int] = {}
    for channel in channels:
        label = PROVIDER_LABELS.get(channel.provider, channel.provider)
        channels_by_provider[label] = channels_by_provider.get(label, 0) + 1

    campaigns_joined = (
        db.query(func.count(func.distinct(CampaignTarget.campaign_id)))
        .filter(CampaignTarget.user_id == current_user.id)
        .scalar()
        or 0
    )

    status_counts = dict(
        db.query(Publication.status, func.count(Publication.id))
        .filter(Publication.user_id == current_user.id)
        .group_by(Publication.status)
        .all()
    )

    totals = (
        db.query(
            func.coalesce(func.sum(StatPostMetric.impressions), 0),
            func.coalesce(func.sum(StatPostMetric.likes), 0),
            func.coalesce(func.sum(StatPostMetric.comments), 0),
            func.coalesce(func.sum(StatPostMetric.shares), 0),
            func.coalesce(func.sum(StatPostMetric.views), 0),
            func.coalesce(func.sum(StatPostMetric.reach), 0),
            func.coalesce(func.sum(StatPostMetric.follows), 0),
            func.coalesce(func.sum(StatPostMetric.clicks), 0),
            # Niente coalesce: AVG ignora gia' i NULL, e un NULL qui significa
            # "nessun post riporta questa metrica", che e' diverso da zero.
            func.avg(StatPostMetric.engagement_rate),
        )
        .filter(StatPostMetric.user_id == current_user.id)
        .one()
    )

    return PortalStatsResponse(
        channels_connected=len([c for c in channels if c.is_active]),
        channels_by_provider=channels_by_provider,
        campaigns_joined=campaigns_joined,
        posts_published=status_counts.get("published", 0) + status_counts.get("scheduled", 0),
        posts_failed=status_counts.get("failed", 0),
        total_impressions=int(totals[0] or 0),
        total_likes=int(totals[1] or 0),
        total_comments=int(totals[2] or 0),
        total_shares=int(totals[3] or 0),
        total_views=int(totals[4] or 0),
        total_reach=int(totals[5] or 0),
        total_follows=int(totals[6] or 0),
        total_clicks=int(totals[7] or 0),
        engagement_rate=float(totals[8]) if totals[8] is not None else None,
    )


# --------------------------------------------------------------------------
# Channel connection
# --------------------------------------------------------------------------

class ConnectLinkRequest(BaseModel):
    # Platform identifier ("instagram", "facebook", "tiktok"...).
    # min_length is 1, not 2: "x" is a legitimate value and the only platform
    # whose name is a single character. A length floor of 2 silently rejected it
    # with a 422 before it ever reached the allow-list below, which is the real
    # validation. Keep it at 1.
    platform: str = Field(min_length=1, max_length=40)


class ConnectLinkResponse(BaseModel):
    url: str


# Platforms offered in the portal's connect panel.
#
# This list is the enum the hosted connect flow actually accepts, read back from
# the API itself on 2026-09-06 (send an invalid value and it names the valid
# ones). It is NOT the provider's marketing list: "telegram" was on that one and
# is rejected by this endpoint, so offering it produced a button that could only
# fail. A test asserts every entry here maps to a provider value.
CONNECTABLE_PLATFORMS = [
    "instagram", "facebook", "tiktok", "youtube", "linkedin", "x",
    "threads", "pinterest", "reddit", "bluesky", "mastodon",
    "discord", "slack", "snapchat", "google_business",
]


@router.get("/connect/platforms", response_model=List[str])
def list_connectable_platforms(current_user: User = Depends(get_current_portal_user)):
    return CONNECTABLE_PLATFORMS


@router.post("/connect/link", response_model=ConnectLinkResponse)
def create_connect_link(
    payload: ConnectLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Start the hosted OAuth flow.

    Returns a URL the user opens to authorise their own social account on the
    platform itself. The consent happens against the provider's approved apps,
    which is what lets us onboard channels without our own Meta/TikTok app
    review.

    Creates the user's provider connection and team on first use, so a user who
    has never connected anything needs no setup step of their own.
    """
    if payload.platform not in CONNECTABLE_PLATFORMS:
        raise HTTPException(status_code=400, detail="Piattaforma non supportata.")

    if settings.BUNDLE_SOCIAL_INTEGRATION_MODE.lower() != "production" or not settings.BUNDLE_SOCIAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Il collegamento diretto dei canali non è ancora attivo su questo server. "
                "Nel frattempo un amministratore può collegare i tuoi canali per te."
            ),
        )

    from app.integrations.bundle_social.prod_client import ProductionBundleSocialClient

    client = ProductionBundleSocialClient()
    api_key = settings.BUNDLE_SOCIAL_API_KEY

    connection = db.query(BufferConnection).filter(
        BufferConnection.user_id == current_user.id,
        BufferConnection.provider == PROVIDER_BUNDLE_SOCIAL,
    ).first()

    try:
        if not connection:
            # The team name carries the user id, not just their display name:
            # names are neither unique nor stable, and this is what an operator
            # reads in the provider's own dashboard when tracing a channel back
            # to a customer.
            team = client.create_team(api_key, name=f"{current_user.name} ({current_user.id})")
            connection = BufferConnection(
                user_id=current_user.id,
                provider=PROVIDER_BUNDLE_SOCIAL,
                authentication_type="platform_key",
                provider_account_ref=team["id"],
                external_account_id=team["id"],
                status="connected",
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)
        elif not connection.provider_account_ref:
            team = client.create_team(api_key, name=f"{current_user.name} ({current_user.id})")
            connection.provider_account_ref = team["id"]
            connection.external_account_id = team["id"]
            connection.status = "connected"
            db.commit()

        url = client.create_portal_link(
            api_key=api_key,
            team_id=connection.provider_account_ref,
            platforms=[payload.platform],
            # Lands on a page whose only job is to notify the opener and close
            # itself, so the flow ends inside our site instead of on a page the
            # user has to navigate away from.
            redirect_url=f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/connect-done",
            user_name=current_user.name,
        )
    except BufferApiError as e:
        # The provider's own message is more useful than a generic failure, but
        # it must never carry the platform key - it does not: the key travels in
        # a header, and only response bodies reach this message.
        raise HTTPException(status_code=502, detail=f"Collegamento non riuscito: {e.message}")

    return ConnectLinkResponse(url=url)


# How long a sync stays "fresh enough" for the automatic pass on page load.
# Short enough that the list is effectively live, long enough that opening the
# page repeatedly does not hammer the provider.
SYNC_MIN_INTERVAL_SECONDS = 30


class ConnectSyncResponse(BaseModel):
    channels: int
    message: str


@router.post("/connect/sync", response_model=ConnectSyncResponse)
def sync_my_channels(
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Import the channels the user just authorised.

    The hosted OAuth flow finishes on the provider's own site, so nothing tells
    us a channel appeared: authorising creates it upstream, and until we pull it
    in, the user comes back to a page that looks unchanged. That is the gap this
    closes, and it is why the channels page calls it on return from the flow.

    Runs inline rather than through Celery on purpose: it is one or two upstream
    calls, and the point is that the user sees the channel immediately instead of
    reloading until a worker catches up.
    """
    connection = db.query(BufferConnection).filter(
        BufferConnection.user_id == current_user.id,
        BufferConnection.provider == PROVIDER_BUNDLE_SOCIAL,
    ).first()

    if not connection or not connection.provider_account_ref:
        return ConnectSyncResponse(channels=0, message="Nessun collegamento da sincronizzare.")

    # Freshness guard for the automatic pass. Opening the channels page triggers
    # a sync so the list is never stale, but without this every page view - and
    # every back-navigation to it - would be an upstream call. A user returning
    # from the connect flow is the case that must NOT be throttled, so an
    # explicit refresh always goes through.
    if not force and connection.last_sync_at is not None:
        age = (datetime.now(timezone.utc) - connection.last_sync_at).total_seconds()
        if age < SYNC_MIN_INTERVAL_SECONDS:
            count = _user_channels_query(db, current_user).filter(
                SocialChannel.provider == PROVIDER_BUNDLE_SOCIAL
            ).count()
            return ConnectSyncResponse(channels=count, message="Già aggiornato.")

    from app.tasks.sync import sync_buffer_connection

    try:
        sync_buffer_connection(str(connection.id))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        raise HTTPException(status_code=502, detail=f"Sincronizzazione non riuscita: {exc}")

    count = _user_channels_query(db, current_user).filter(
        SocialChannel.provider == PROVIDER_BUNDLE_SOCIAL
    ).count()

    # Connecting a real channel is what an account was waiting to prove. Doing it
    # here rather than in the sync task keeps it on the one path that means "this
    # person just finished authorising something".
    activated = bool(count) and user_activation.activate_on_channel_connection(db, current_user)

    if not count:
        message = "Nessun canale trovato: completa l'autorizzazione sul social."
    elif activated:
        message = "Canali aggiornati. Il tuo account e ora attivo per le campagne."
    else:
        message = "Canali aggiornati."

    return ConnectSyncResponse(channels=count, message=message)


class PortalTimelinePoint(BaseModel):
    date: str
    published: int


class PortalOverviewResponse(BaseModel):
    """Everything the dashboard renders, in one round trip."""
    stats: PortalStatsResponse
    timeline: List[PortalTimelinePoint]
    top_channels: List[Dict[str, Any]]


@router.get("/overview", response_model=PortalOverviewResponse)
def get_my_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Dashboard payload: headline figures, a 30-day publishing timeline, and the
    user's best performing channels.

    One endpoint rather than three because the dashboard always needs all of it
    at once; splitting would only add round trips to a page that is a single
    view.
    """
    stats = get_my_stats(db=db, current_user=current_user)

    since = datetime.now(timezone.utc) - timedelta(days=30)

    # Daily counts, aggregated in SQL: a promoter with thousands of publications
    # should not ship them all to Python to be counted.
    rows = (
        db.query(
            func.date_trunc("day", Publication.published_at).label("day"),
            func.count(Publication.id),
        )
        .filter(
            Publication.user_id == current_user.id,
            Publication.published_at.isnot(None),
            Publication.published_at >= since,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    by_day = {row[0].date().isoformat(): row[1] for row in rows if row[0]}

    # Every day present, including the empty ones: a line with gaps in it reads
    # as missing data rather than as days with no activity.
    timeline = []
    for offset in range(30, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date().isoformat()
        timeline.append(PortalTimelinePoint(date=day, published=by_day.get(day, 0)))

    channel_rows = (
        db.query(
            SocialChannel.name,
            SocialChannel.platform,
            func.coalesce(func.sum(StatPostMetric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(StatPostMetric.likes), 0).label("likes"),
            func.count(StatPostMetric.id).label("posts"),
        )
        .join(StatPostMetric, StatPostMetric.social_channel_id == SocialChannel.id)
        .filter(StatPostMetric.user_id == current_user.id)
        .group_by(SocialChannel.id, SocialChannel.name, SocialChannel.platform)
        .order_by(func.coalesce(func.sum(StatPostMetric.impressions), 0).desc())
        .limit(5)
        .all()
    )

    top_channels = [
        {
            "name": row[0],
            "platform": row[1],
            "impressions": int(row[2] or 0),
            "likes": int(row[3] or 0),
            "posts": int(row[4] or 0),
        }
        for row in channel_rows
    ]

    return PortalOverviewResponse(stats=stats, timeline=timeline, top_channels=top_channels)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_my_channel(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Remove a channel the user no longer uses from their list.

    A SOFT delete, not a row delete. campaign_targets, publications and
    stat_post_metrics all cascade from social_channels, so dropping the row would
    erase the record of everything ever published on that client's real profile
    - and Postgres is the source of truth for exactly that (AGENTS.md rule 4).
    The history stays; the channel leaves the user's view and can never be
    targeted by a campaign again.

    Only offered for channels already disconnected upstream. Removing one that is
    still connected would be a lie: the provider would keep it, the next sync
    would find it, and the user would watch a channel they "deleted" come back.
    To get rid of a live channel, disconnect it at the social network first.
    """
    channel = _user_channels_query(db, current_user).filter(
        SocialChannel.id == channel_id
    ).first()

    if not channel:
        # Same answer whether it does not exist or belongs to someone else: this
        # endpoint must not confirm the existence of another user's channels.
        raise HTTPException(status_code=404, detail="Canale non trovato.")

    if channel.is_active:
        raise HTTPException(
            status_code=409,
            detail=(
                "Questo canale risulta ancora collegato. Scollegalo prima dal social, "
                "poi aggiorna la pagina e potrai rimuoverlo."
            ),
        )

    channel.deleted_at = datetime.now(timezone.utc)
    channel.publication_mode = "disabled"
    db.commit()


# --------------------------------------------------------------------------
# Campaign line-up: what a user is invited to, and their right to leave it
# --------------------------------------------------------------------------

# Quante campagne gia' concluse mostrare nel palinsesto. Sufficiente a coprire
# mesi di attivita' senza trasformare la pagina in un archivio: lo storico
# completo, con i numeri, resta la pagina Storico.
HISTORY_LIMIT = 20


class PortalLineupChannel(BaseModel):
    """One of the user's channels, and where it stands in this campaign."""
    id: str
    platform: str
    name: str
    username: Optional[str]
    avatar_url: Optional[str]
    # included | withdrawn | removed | None (never in the line-up)
    participation_status: Optional[str]
    # True when this user put the channel in themselves.
    joined_by_me: bool
    # True when a post for this campaign actually went out on this channel.
    published: bool = False
    decided_at: Optional[datetime]
    # False when an administrator removed the channel: the user may not put it
    # back, and the interface has to say so rather than offer a button that
    # silently fails.
    can_rejoin: bool


class PortalLineupCampaign(BaseModel):
    id: str
    title: str
    status: str
    # The text this user's channels would publish. The campaign's default text,
    # not any per-platform override: the point is to let someone read what they
    # would be posting before deciding, and showing eight variants of it would
    # obscure that rather than serve it.
    text: str
    media_url: Optional[str]
    media_type: Optional[str]
    scheduled_at: Optional[datetime]
    timezone: str
    opt_out_deadline_at: Optional[datetime]
    # True while this user can still change their participation.
    window_open: bool
    # True when the campaign launches by itself at the deadline, which changes
    # what the deadline means for the reader.
    auto_launch_at_deadline: bool
    announced_at: Optional[datetime]
    # This user's own channels, with their standing. Includes channels not in
    # the line-up at all, so the "partecipa" flow has something to offer.
    channels: List[PortalLineupChannel]
    # Convenience counters so the list page needs no client-side arithmetic.
    included_count: int
    withdrawn_count: int
    # True when the user has no channel in this campaign but could add one.
    can_join: bool
    # "open"     la finestra e' aperta: si puo' entrare o uscire
    # "closed"   annunciata, termine scaduto, non ancora lanciata
    # "launched" gia' partita: sola lettura, i post sono usciti
    phase: str


class PortalParticipationRequest(BaseModel):
    # Channels to act on. Omitted or empty means "all of mine in this campaign"
    # for a withdrawal - the one-click "non partecipo" the portal offers - and is
    # rejected for a join, where there is nothing sensible to guess.
    channel_ids: List[str] = Field(default_factory=list)
    reason: Optional[str] = Field(default=None, max_length=500)


class PortalParticipationResponse(BaseModel):
    changed: int
    message: str
    # Channels that could not be added, each with its reason. Not an error: a
    # user ticking four channels where one has gone stale gets the other three.
    warnings: List[str] = Field(default_factory=list)


def _campaign_media(campaign: Campaign) -> tuple:
    media = campaign.media_file
    if media is None:
        return None, None
    media_type = "video" if (media.mime_type or "").startswith("video") else "image"
    return media.public_url, media_type


def _lineup_payload(
    db: Session,
    campaign: Campaign,
    user: User,
    user_channels: List[SocialChannel],
    published_channel_ids: Optional[set] = None,
) -> PortalLineupCampaign:
    """
    One campaign as this user sees it.

    ``published_channel_ids`` carries the channels that actually received a post,
    and is what lets an already-launched campaign appear here as history. Those
    campaigns often have no participant rows at all - anything published before
    the line-up existed, or in "automatic" mode, went straight from targeting to
    publication - so their record of "I was in this" lives only in the
    publications. Without it a past campaign would render as though the user had
    never taken part.
    """
    participants = campaign_participation.participants_for_user(db, campaign.id, user.id)
    window_open = campaign_participation.is_window_open(campaign)
    launched = campaign.status not in ("draft", campaign_participation.OPEN_STATUS)
    published_channel_ids = published_channel_ids or set()
    media_url, media_type = _campaign_media(campaign)

    channels: List[PortalLineupChannel] = []
    for channel in user_channels:
        participant = participants.get(channel.id)
        status_value = participant.status if participant else None
        if status_value is None and channel.id in published_channel_ids:
            status_value = CampaignParticipant.STATUS_INCLUDED
        channels.append(
            PortalLineupChannel(
                id=str(channel.id),
                platform=channel.platform,
                name=channel.name,
                username=channel.username,
                avatar_url=channel.avatar_url,
                participation_status=status_value,
                joined_by_me=bool(
                    participant and participant.added_by == CampaignParticipant.SOURCE_USER
                ),
                decided_at=participant.decided_at if participant else None,
                can_rejoin=(
                    window_open
                    and status_value != CampaignParticipant.STATUS_REMOVED
                    and status_value != CampaignParticipant.STATUS_INCLUDED
                ),
                published=channel.id in published_channel_ids,
            )
        )

    included = sum(
        1 for c in channels if c.participation_status == CampaignParticipant.STATUS_INCLUDED
    )
    withdrawn = sum(
        1 for c in channels if c.participation_status == CampaignParticipant.STATUS_WITHDRAWN
    )

    return PortalLineupCampaign(
        id=str(campaign.id),
        title=campaign.title,
        status=campaign.status,
        text=campaign.default_text,
        media_url=media_url,
        media_type=media_type,
        scheduled_at=campaign.scheduled_at,
        timezone=campaign.timezone,
        opt_out_deadline_at=campaign.opt_out_deadline_at,
        window_open=window_open,
        auto_launch_at_deadline=campaign.auto_launch_at_deadline,
        announced_at=campaign.announced_at,
        channels=channels,
        included_count=included,
        withdrawn_count=withdrawn,
        can_join=window_open and included == 0 and any(c.can_rejoin or c.participation_status is None for c in channels),
        phase="launched" if launched else ("open" if window_open else "closed"),
    )


@router.get("/lineup", response_model=List[PortalLineupCampaign])
def list_lineup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Every campaign currently open for participation - including ones this user
    was not put in.

    Showing all of them is deliberate. A promoter who was left out of a campaign
    they would have wanted has no way to discover it otherwise, and asking an
    administrator to notice and add them by hand is the manual step this whole
    feature exists to remove. Joining is one click and takes effect immediately;
    the administrator sees who joined, marked as such, in the line-up panel.

    Campaigns that have already gone out follow, read-only, so the page answers
    "which campaigns am I in" rather than only "which can I still leave". Their
    channels are read from the user's own publications, which is what makes this
    work for everything published before the line-up existed.
    """
    open_campaigns = (
        db.query(Campaign)
        .options(joinedload(Campaign.media_file))
        .filter(Campaign.status == campaign_participation.OPEN_STATUS)
        .order_by(Campaign.opt_out_deadline_at.asc().nullslast(), Campaign.announced_at.desc())
        .all()
    )

    # Campaigns already gone out that this user was part of, so the page reads as
    # "the campaigns I am in", not only "the ones still up for decision". Scoped
    # through the user's own publications: that is the record of what actually
    # reached their channels, and it exists for campaigns published long before
    # the line-up did.
    published_rows = (
        db.query(Publication.campaign_id, Publication.social_channel_id)
        .filter(Publication.user_id == current_user.id)
        .all()
    )
    published_by_campaign: Dict[Any, set] = {}
    for campaign_id, channel_id in published_rows:
        published_by_campaign.setdefault(campaign_id, set()).add(channel_id)

    open_ids = {campaign.id for campaign in open_campaigns}
    history_ids = [cid for cid in published_by_campaign if cid not in open_ids]

    history_campaigns: List[Campaign] = []
    if history_ids:
        history_campaigns = (
            db.query(Campaign)
            .options(joinedload(Campaign.media_file))
            .filter(
                Campaign.id.in_(history_ids),
                # A campaign still being prepared is not history yet, and showing
                # it as such would be wrong twice over.
                Campaign.status.notin_(("draft", campaign_participation.OPEN_STATUS)),
            )
            .order_by(Campaign.started_at.desc().nullslast(), Campaign.created_at.desc())
            .limit(HISTORY_LIMIT)
            .all()
        )

    if not open_campaigns and not history_campaigns:
        return []

    user_channels = campaign_participation.eligible_channels_for_user(db, current_user.id)

    return [
        _lineup_payload(
            db,
            campaign,
            current_user,
            user_channels,
            published_channel_ids=published_by_campaign.get(campaign.id),
        )
        for campaign in [*open_campaigns, *history_campaigns]
    ]


@router.get("/lineup/{campaign_id}", response_model=PortalLineupCampaign)
def get_lineup_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    One campaign in full: its text, its media, when it goes out, and this user's
    own standing in it.

    Readable for any announced campaign, not only ones the user is in - that is
    what makes the "partecipa" button on the list page lead somewhere. It exposes
    nothing about other participants.
    """
    campaign = (
        db.query(Campaign)
        .options(joinedload(Campaign.media_file))
        .filter(Campaign.id == campaign_id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagna non trovata.")

    # A campaign the user takes part in stays readable after launch, so their
    # history has somewhere to link to. One they were never in does not: before
    # it is announced it is somebody's private draft.
    if campaign.status != campaign_participation.OPEN_STATUS:
        takes_part = (
            db.query(CampaignParticipant)
            .filter(
                CampaignParticipant.campaign_id == campaign.id,
                CampaignParticipant.user_id == current_user.id,
            )
            .first()
        )
        # ...or took part the old way, through a publication. Checking only
        # participants would have hidden every campaign published before the
        # line-up existed - which is most of a promoter's history.
        if takes_part is None:
            takes_part = (
                db.query(Publication)
                .filter(
                    Publication.campaign_id == campaign.id,
                    Publication.user_id == current_user.id,
                )
                .first()
            )
        if takes_part is None:
            raise HTTPException(status_code=404, detail="Campagna non trovata.")

    published_channel_ids = {
        row[0]
        for row in db.query(Publication.social_channel_id).filter(
            Publication.campaign_id == campaign.id,
            Publication.user_id == current_user.id,
        )
    }
    user_channels = campaign_participation.eligible_channels_for_user(db, current_user.id)
    return _lineup_payload(
        db, campaign, current_user, user_channels, published_channel_ids=published_channel_ids
    )


def _open_campaign_or_404(db: Session, campaign_id: uuid.UUID) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagna non trovata.")
    return campaign


def _parse_channel_ids(raw: List[str]) -> List[uuid.UUID]:
    parsed = []
    for value in raw:
        try:
            parsed.append(uuid.UUID(value))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Identificativo canale non valido.")
    return parsed


@router.post("/lineup/{campaign_id}/withdraw", response_model=PortalParticipationResponse)
def withdraw_from_campaign(
    campaign_id: uuid.UUID,
    payload: PortalParticipationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Take this user's channels out of a campaign before it is launched.

    The user id comes from the validated token and is the filter on every row
    touched (see campaign_participation.withdraw), so a channel id belonging to
    somebody else simply matches nothing.
    """
    campaign = _open_campaign_or_404(db, campaign_id)
    channel_ids = _parse_channel_ids(payload.channel_ids) if payload.channel_ids else None

    try:
        changed = campaign_participation.withdraw(
            db,
            campaign,
            user_id=current_user.id,
            channel_ids=channel_ids,
            reason=payload.reason,
        )
    except campaign_participation.ParticipationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if changed == 0:
        return PortalParticipationResponse(
            changed=0, message="Nessuna partecipazione da annullare."
        )
    return PortalParticipationResponse(
        changed=changed,
        message=(
            "Non parteciperai a questa campagna."
            if changed == 1
            else f"{changed} canali rimossi da questa campagna."
        ),
    )


@router.post("/lineup/{campaign_id}/join", response_model=PortalParticipationResponse)
def join_campaign(
    campaign_id: uuid.UUID,
    payload: PortalParticipationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Put this user's own channels into an open campaign.

    Takes effect immediately, with no administrator approval: a promoter opting
    IN to promotional content is not a decision that needs vetting, and requiring
    approval would reintroduce exactly the manual queue this replaces.
    """
    campaign = _open_campaign_or_404(db, campaign_id)
    if not payload.channel_ids:
        raise HTTPException(status_code=400, detail="Seleziona almeno un canale.")

    channel_ids = _parse_channel_ids(payload.channel_ids)

    try:
        added, warnings = campaign_participation.join(
            db, campaign, user_id=current_user.id, channel_ids=channel_ids
        )
    except campaign_participation.ParticipationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if added == 0:
        return PortalParticipationResponse(
            changed=0,
            message="Nessun canale aggiunto.",
            warnings=warnings,
        )
    return PortalParticipationResponse(
        changed=added,
        message=(
            "Parteciperai a questa campagna."
            if added == 1
            else f"{added} canali aggiunti a questa campagna."
        ),
        warnings=warnings,
    )
