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
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TOKEN_TYPE_PORTAL_USER, SecurityService
from app.db.session import get_db
from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.providers import PROVIDER_BUNDLE_SOCIAL, PROVIDER_LABELS
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign, CampaignTarget
from app.models.publication import Publication
from app.models.statistics import StatPostMetric
from app.models.user import User

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

    A new account starts ``status="inactive"``: that is what keeps it out of
    campaign targeting until an administrator vets it (see the note on
    ``User.self_registered_at``). The user can sign in immediately, connect
    their channels and see their dashboard - they simply are not published to
    yet.
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
        if payload.company_name:
            existing.company_name = payload.company_name
        user = existing
    else:
        user = User(
            name=payload.name.strip(),
            email=email,
            company_name=payload.company_name,
            status="inactive",
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
    campaign_ids = [
        row[0]
        for row in db.query(CampaignTarget.campaign_id)
        .filter(CampaignTarget.user_id == current_user.id)
        .distinct()
        .all()
    ]
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

    result = []
    for campaign in campaigns:
        statuses = by_campaign.get(campaign.id, {})
        published = statuses.get("published", 0) + statuses.get("scheduled", 0)
        failed = statuses.get("failed", 0)
        pending = sum(
            count for key, count in statuses.items()
            if key in ("pending", "queued", "processing", "retry_wait")
        )
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
                "Nel frattempo un amministratore può collegare i tuoi canali tramite Buffer."
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

    return ConnectSyncResponse(
        channels=count,
        message="Canali aggiornati." if count else "Nessun canale trovato: completa l'autorizzazione sul social.",
    )


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
