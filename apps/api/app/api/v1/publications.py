import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.publication import Publication, PublicationAttempt
from app.models.user import User
from app.models.buffer import SocialChannel
from app.models.campaign import Campaign, CampaignTarget
from app.models.media import MediaFile
from app.tasks.publication import process_publication_task
from app.core.security import EncryptionService
from app.integrations.buffer.service import get_buffer_client
from app.integrations.buffer.exceptions import BufferApiError
from app.schemas.schemas import (
    PublicationResponse,
    PublicationDetailResponse,
    PublicationAttemptResponse,
    PublicationFeedItem,
    MediaResponse,
    ChannelMetrics,
    PostMetricValue,
    StatusCountsSummaryResponse,
)

router = APIRouter()

@router.get("/", response_model=List[PublicationResponse])
def list_publications(
    campaign_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve lists of publications, optionally filtered by campaign or status."""
    query = db.query(Publication)
    if campaign_id:
        query = query.filter(Publication.campaign_id == campaign_id)
    if status_filter:
        query = query.filter(Publication.status == status_filter)

    return query.offset(skip).limit(limit).all()


@router.get("/summary", response_model=StatusCountsSummaryResponse)
def get_publications_summary(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Counts for the stat cards atop the Pubblicazioni list - registered
    before "/{pub_id}" so FastAPI doesn't try to parse "summary" as a UUID.
    Deliberately not filterable by campaign_id/status_filter like the list
    above - always the platform-wide totals, same principle as
    statistics_service.build_dashboard."""
    rows = db.query(Publication.status, func.count(Publication.id)).group_by(Publication.status).all()
    counts = dict(rows)
    return StatusCountsSummaryResponse(total=sum(counts.values()), by_status=counts)


@router.get("/feed", response_model=List[PublicationFeedItem])
def list_published_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    """
    "Bacheca" - a Facebook-style feed of every publication that actually went
    live, most recent first. Declared before /{pub_id} so "feed" is never
    swallowed as a path param there. Joins Campaign/SocialChannel/
    CampaignTarget so the frontend gets text/media/channel identity in one
    call instead of N+1 lookups against the plain GET / list.
    """
    rows = (
        db.query(Publication, CampaignTarget, Campaign, SocialChannel, User)
        .join(CampaignTarget, Publication.campaign_target_id == CampaignTarget.id)
        .join(Campaign, Publication.campaign_id == Campaign.id)
        .join(SocialChannel, Publication.social_channel_id == SocialChannel.id)
        .join(User, Publication.user_id == User.id)
        .filter(Publication.status == "published")
        .order_by(Publication.published_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    media_ids = {campaign.media_file_id for _, _, campaign, _, _ in rows if campaign.media_file_id}
    media_by_id = {m.id: m for m in db.query(MediaFile).filter(MediaFile.id.in_(media_ids)).all()} if media_ids else {}

    return [
        PublicationFeedItem(
            id=pub.id,
            campaign_id=campaign.id,
            published_at=pub.published_at,
            text=target.resolved_text,
            external_post_url=pub.external_post_url,
            social_channel_id=channel.id,
            platform=channel.platform,
            channel_name=channel.name,
            channel_avatar_url=channel.avatar_url,
            channel_external_link=channel.external_link,
            user_name=user.name,
            media=MediaResponse.model_validate(media_by_id[campaign.media_file_id]) if campaign.media_file_id in media_by_id else None,
        )
        for pub, target, campaign, channel, user in rows
    ]


@router.get("/{pub_id}", response_model=PublicationDetailResponse)
def get_publication(
    pub_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve detailed publication status, resolving target texts and attempt logs."""
    pub = db.query(Publication).filter(Publication.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
        
    # Query attempts
    attempts = db.query(PublicationAttempt).filter(
        PublicationAttempt.publication_id == pub_id
    ).order_by(PublicationAttempt.attempt_number.asc()).all()
    
    return {
        "publication": pub,
        "attempts": attempts,
        "resolved_text": pub.campaign_target.resolved_text,
        "channel_name": pub.social_channel.name,
        "channel_platform": pub.social_channel.platform,
        "user_name": pub.user.name,
        "channel_external_link": pub.social_channel.external_link,
        "media": pub.campaign.media_file,
    }


@router.get("/{pub_id}/metrics", response_model=ChannelMetrics)
def get_publication_metrics(
    pub_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Fetches engagement metrics for this single publication's post, live from
    Buffer's Post.metrics API - same on-demand call as the campaign-level
    metrics endpoint (GET /campaigns/{id}/metrics), scoped to one destination.
    """
    pub = db.query(Publication).filter(Publication.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")

    # "scheduled" is included alongside "published" for the same reason as the
    # campaign-level endpoint: both mean Buffer accepted the post successfully
    # and carry a real external_post_id (see docs/FUNCTIONALITY.md §6/§10).
    if pub.status not in ("published", "scheduled") or not pub.external_post_id:
        raise HTTPException(
            status_code=400,
            detail="Le statistiche sono disponibili solo per pubblicazioni riuscite (pubblicate o programmate)."
        )

    channel = pub.social_channel
    connection = pub.buffer_connection
    client = get_buffer_client()

    entry = ChannelMetrics(
        publication_id=pub.id,
        social_channel_id=pub.social_channel_id,
        channel_name=channel.name if channel else "—",
        user_name=pub.user.name if pub.user else "—",
        platform=channel.platform if channel else "unknown",
        external_post_url=pub.external_post_url,
    )

    try:
        token = EncryptionService.decrypt(connection.access_token_encrypted) if connection else None
        if not token:
            raise BufferApiError("Connessione Buffer non disponibile", category="auth_error")

        result = client.get_post_metrics(token, pub.external_post_id)
        entry.metrics = [PostMetricValue(**m) for m in result.get("metrics", [])]
        entry.metrics_updated_at = result.get("metrics_updated_at")

        # Backfill the specific post's real URL once Buffer actually has it -
        # it's usually still null right after create_post (see prod_client.py),
        # so this on-demand metrics check is the natural place to pick it up
        # later without a separate polling job.
        external_link = result.get("external_link")
        if external_link and not pub.external_post_url:
            pub.external_post_url = external_link
            db.commit()
            entry.external_post_url = external_link
    except BufferApiError as e:
        entry.error = e.message
    except Exception as e:
        entry.error = str(e)

    return entry


@router.post("/{pub_id}/retry", response_model=PublicationResponse)
def retry_publication(
    pub_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retries a specific failed, cancelled, retry_wait, or stuck queued publication."""
    pub = db.query(Publication).filter(Publication.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")

    # "queued" is included so an admin can manually unstick a publication whose
    # background job was lost (its own automatic recovery only kicks in after 15
    # minutes, see tasks/cleanup.py recover_stale_publications) without waiting.
    if pub.status not in ("failed", "cancelled", "retry_wait", "queued"):
        raise HTTPException(status_code=400, detail="Only failed, cancelled, retry_wait, or stuck queued publications can be manually retried.")
        
    # Reset status
    pub.status = "pending"
    pub.next_attempt_at = None
    pub.error_message = None
    pub.error_code = None
    pub.error_category = None
    
    # Increase attempt limit if already exhausted
    if pub.attempt_count >= pub.max_attempts:
        pub.max_attempts += 3 # extend limit
        
    db.commit()
    db.refresh(pub)
    
    # Trigger task
    process_publication_task.delay(str(pub.id))
    return pub


@router.post("/retry-selected")
def retry_selected_publications(
    pub_ids: List[uuid.UUID],
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Bulk retries a list of selected publications."""
    pubs = db.query(Publication).filter(
        Publication.id.in_(pub_ids),
        Publication.status.in_(["failed", "cancelled", "retry_wait", "queued"])
    ).all()
    
    for pub in pubs:
        pub.status = "pending"
        pub.next_attempt_at = None
        pub.error_message = None
        pub.error_code = None
        pub.error_category = None
        if pub.attempt_count >= pub.max_attempts:
            pub.max_attempts += 3
            
    db.commit()
    
    # Dispatch tasks
    for pub in pubs:
        process_publication_task.delay(str(pub.id))
        
    return {"message": f"Successfully queued {len(pubs)} publications for retry."}


@router.post("/retry-campaign-failures/{campaign_id}")
def retry_campaign_failures(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retries all failed publications for a campaign."""
    pubs = db.query(Publication).filter(
        Publication.campaign_id == campaign_id,
        Publication.status == "failed"
    ).all()
    
    if not pubs:
        return {"message": "No failed publications found for this campaign."}
        
    for pub in pubs:
        pub.status = "pending"
        pub.next_attempt_at = None
        pub.error_message = None
        pub.error_code = None
        pub.error_category = None
        if pub.attempt_count >= pub.max_attempts:
            pub.max_attempts += 3
            
    db.commit()
    
    # Dispatch tasks
    for pub in pubs:
        process_publication_task.delay(str(pub.id))
        
    # Reset campaign status to running
    from app.models.campaign import Campaign
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if campaign:
        campaign.status = "running"
        db.commit()
        
    return {"message": f"Queued {len(pubs)} failed publications for retry."}


@router.post("/{pub_id}/cancel", response_model=PublicationResponse)
def cancel_publication(
    pub_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Cancel a pending, queued or retry_wait publication job."""
    pub = db.query(Publication).filter(Publication.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
        
    if pub.status not in ("pending", "queued", "retry_wait"):
        raise HTTPException(status_code=400, detail="Cannot cancel a job that is already complete or active.")
        
    pub.status = "cancelled"
    db.commit()
    db.refresh(pub)
    return pub


@router.post("/{pub_id}/skip", response_model=PublicationResponse)
def skip_publication(
    pub_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Mark a publication job as skipped (will not be published or retried)."""
    pub = db.query(Publication).filter(Publication.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
        
    if pub.status not in ("pending", "queued", "retry_wait", "failed"):
        raise HTTPException(status_code=400, detail="Cannot skip an already processed job.")
        
    pub.status = "skipped"
    db.commit()
    db.refresh(pub)
    return pub
