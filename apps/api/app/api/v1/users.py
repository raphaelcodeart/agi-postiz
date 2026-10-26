from datetime import datetime, timezone
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_
from app.core.config import settings
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.user import User, UserGroup
from app.schemas.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserSummaryResponse,
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    ChannelRequirementBulkRequest,
    ChannelRequirementBulkResponse,
    ChannelRequirementChannel,
    ChannelRequirementNoticeResponse,
    ChannelRequirementResponse,
    ChannelRequirementUser,
)
from app.services import channel_requirement_service as channel_req

router = APIRouter()

# ==============================================================================
# Users Endpoints
# ==============================================================================
@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """List and search clients / users."""
    query = db.query(User).filter(User.deleted_at.is_(None))
    
    if search:
        query = query.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.company_name.ilike(f"%{search}%")
            )
        )
        
    if status_filter:
        query = query.filter(User.status == status_filter)
        
    return query.offset(skip).limit(limit).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Create a new client / user and optionally assign groups."""
    existing_user = db.query(User).filter(User.email == payload.email, User.deleted_at.is_(None)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists.")
        
    user = User(
        name=payload.name,
        email=payload.email,
        company_name=payload.company_name,
        city=payload.city,
        postal_code=payload.postal_code,
        status=payload.status,
        notes=payload.notes,
        referral_link=payload.referral_link,
        personal_contacts=payload.personal_contacts,
    )
    
    if payload.group_ids:
        groups = db.query(UserGroup).filter(UserGroup.id.in_(payload.group_ids)).all()
        user.groups = groups
        
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/summary", response_model=UserSummaryResponse)
def get_users_summary(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Counts for the stat cards atop the Utenti list - registered before
    "/{user_id}" so FastAPI doesn't try to parse "summary" as a UUID."""
    rows = (
        db.query(User.status, func.count(User.id))
        .filter(User.deleted_at.is_(None))
        .group_by(User.status)
        .all()
    )
    counts = dict(rows)
    return UserSummaryResponse(
        total=sum(counts.values()),
        active=counts.get("active", 0),
        inactive=counts.get("inactive", 0),
        suspended=counts.get("suspended", 0),
        below_channel_requirement=channel_req.count_users_below_requirement(db),
    )


# ==============================================================================
# Requisito canali social (vedi services/channel_requirement_service.py)
# ==============================================================================
# Registrati prima di "/{user_id}" per la stessa ragione di "/summary": il
# segmento "channel-requirement" non deve essere letto come un UUID.

def _requirement_user(row: channel_req.UserBelowRequirement) -> ChannelRequirementUser:
    return ChannelRequirementUser(
        id=row.user.id,
        name=row.user.name,
        email=row.user.email,
        company_name=row.user.company_name,
        status=row.user.status,
        has_portal_access=row.user.password_hash is not None,
        connected_channels_count=row.connected_count,
        connected_channels=[
            ChannelRequirementChannel(platform=platform, name=name)
            for platform, name in row.connected_channels
        ],
        last_notified_at=row.last_notified_at,
        notifications_count=row.notifications_count,
    )


@router.get("/channel-requirement", response_model=ChannelRequirementResponse)
def list_users_below_channel_requirement(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    """Utenti con meno canali social utilizzabili di quanti il progetto ne richieda."""
    rows = channel_req.list_users_below_requirement(db, status_filter=status_filter, search=search)
    return ChannelRequirementResponse(
        required_channels=channel_req.required_channels(),
        cooldown_days=channel_req.cooldown_days(),
        email_enabled=settings.email_enabled,
        total=len(rows),
        without_channels=sum(1 for r in rows if r.connected_count == 0),
        never_notified=sum(1 for r in rows if r.notifications_count == 0),
        users=[_requirement_user(r) for r in rows],
    )


@router.post("/channel-requirement/notify-all", response_model=ChannelRequirementBulkResponse)
def notify_all_below_channel_requirement(
    payload: ChannelRequirementBulkRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    """
    Avvisa via email tutti gli utenti sotto soglia, saltando chi e' stato
    avvisato negli ultimi ``skip_notified_within_days`` giorni (0 = nessuno
    saltato). 503 se l'invio email non e' configurato: niente viene registrato.
    """
    try:
        result = channel_req.notify_all(
            db,
            admin,
            status_filter=payload.status_filter,
            skip_notified_within_days=payload.skip_notified_within_days,
        )
    except channel_req.EmailDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return ChannelRequirementBulkResponse(
        sent=len(result.sent),
        skipped_recent=len(result.skipped_recent),
        failed=len(result.failed),
        sent_user_ids=result.sent,
        failed_user_ids=result.failed,
    )


@router.post("/{user_id}/channel-requirement/notify", response_model=ChannelRequirementNoticeResponse)
def notify_user_below_channel_requirement(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    """Invia l'avviso a un singolo utente, sempre (nessun cooldown sul singolo)."""
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        notice = channel_req.notify_user(db, user, admin)
    except channel_req.EmailDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    count = (
        db.query(func.count(channel_req.UserNotification.id))
        .filter(
            channel_req.UserNotification.user_id == user.id,
            channel_req.UserNotification.kind == channel_req.KIND_CHANNEL_REQUIREMENT,
        )
        .scalar()
    )
    return ChannelRequirementNoticeResponse(
        user_id=user.id, email=notice.email, sent_at=notice.sent_at, notifications_count=count
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve details for a specific client."""
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Update a client's profile details or group assignments."""
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if payload.email and payload.email != user.email:
        existing = db.query(User).filter(User.email == payload.email, User.deleted_at.is_(None)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already taken")
            
    for k, v in payload.model_dump(exclude={"group_ids"}, exclude_unset=True).items():
        setattr(user, k, v)
        
    if payload.group_ids is not None:
        groups = db.query(UserGroup).filter(UserGroup.id.in_(payload.group_ids)).all()
        user.groups = groups
        
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Soft-delete a user."""
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return


# ==============================================================================
# Groups Endpoints
# ==============================================================================
@router.get("/groups/list", response_model=List[GroupResponse])
def list_groups(
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    List all user groups, each annotated with user_count (active members,
    i.e. excluding soft-deleted users - same rule as list_users below).
    selectinload avoids an N+1 query (one extra query for all groups' members
    combined, instead of one per group); user_count is a transient attribute
    set here for response serialization only, not a real column on UserGroup.
    """
    groups = db.query(UserGroup).options(selectinload(UserGroup.users)).all()
    for group in groups:
        group.user_count = sum(1 for u in group.users if u.deleted_at is None)
    return groups


@router.get("/groups/{group_id}/users", response_model=List[UserResponse])
def list_group_users(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """List the (non-deleted) members of a specific group, for the group card's member popup."""
    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    return (
        db.query(User)
        .filter(User.groups.any(UserGroup.id == group_id), User.deleted_at.is_(None))
        .order_by(User.name)
        .all()
    )


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Create a new targeting user group."""
    existing = db.query(UserGroup).filter(UserGroup.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group with this name already exists.")
        
    group = UserGroup(
        name=payload.name,
        description=payload.description
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.put("/groups/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Update a targeting user group's name/description."""
    group = db.query(UserGroup).filter(UserGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if payload.name and payload.name != group.name:
        existing = db.query(UserGroup).filter(UserGroup.name == payload.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Group with this name already exists.")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(group, k, v)

    db.commit()
    db.refresh(group)
    return group
