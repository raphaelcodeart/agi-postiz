from datetime import datetime, timezone
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_
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
)

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
