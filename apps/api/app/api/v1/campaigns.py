from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.campaign import Campaign, CampaignTarget
from app.models.publication import Publication
from app.models.media import MediaFile
from app.models.audit import AuditLog
from app.core.security import EncryptionService
from app.integrations.buffer.service import get_buffer_client
from app.integrations.buffer.exceptions import BufferApiError
from app.services.campaign_resolver import CampaignResolver
from app.schemas.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignPreviewResponse,
    CampaignDetailResponse,
    CampaignMetricsResponse,
    ChannelMetrics,
    PostMetricValue,
    StatusCountsSummaryResponse,
)

router = APIRouter()

@router.get("/", response_model=List[CampaignResponse])
def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve lists of campaigns."""
    # joinedload avoids one extra query per row for CampaignResponse.media_file
    # (the thumbnail shown next to the title in the dashboard's list).
    query = db.query(Campaign).options(joinedload(Campaign.media_file))
    if status_filter:
        query = query.filter(Campaign.status == status_filter)
    return query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/summary", response_model=StatusCountsSummaryResponse)
def get_campaigns_summary(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Counts for the stat cards atop the Campagne list - registered before
    "/{campaign_id}" so FastAPI doesn't try to parse "summary" as a UUID."""
    rows = db.query(Campaign.status, func.count(Campaign.id)).group_by(Campaign.status).all()
    counts = dict(rows)
    return StatusCountsSummaryResponse(total=sum(counts.values()), by_status=counts)


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Create a new campaign in draft status."""
    # Ensure media exists if specified
    if payload.media_file_id:
        media = db.query(MediaFile).filter(MediaFile.id == payload.media_file_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="Media file not found")
            
    campaign = Campaign(
        title=payload.title,
        default_text=payload.default_text,
        instagram_text=payload.instagram_text,
        facebook_text=payload.facebook_text,
        linkedin_text=payload.linkedin_text,
        tiktok_text=payload.tiktok_text,
        youtube_title=payload.youtube_title,
        youtube_description=payload.youtube_description,
        x_text=payload.x_text,
        threads_text=payload.threads_text,
        media_file_id=payload.media_file_id,
        article_id=payload.article_id,
        publishing_mode=payload.publishing_mode,
        scheduled_at=payload.scheduled_at,
        timezone=payload.timezone,
        targeting_mode=payload.targeting_mode,
        include_referral_link=payload.include_referral_link,
        include_personal_contacts=payload.include_personal_contacts,
        status="draft",
        created_by=admin.id,
        metadata_json=payload.targeting_params, # Save targeting parameters here
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/preview-targets", response_model=CampaignPreviewResponse)
def preview_targets(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Simulates target resolution before launch, returning counts, 
    distribution, and warning exclusions.
    """
    # Create transient campaign model to run resolver
    campaign = Campaign(
        title=payload.title,
        default_text=payload.default_text,
        instagram_text=payload.instagram_text,
        facebook_text=payload.facebook_text,
        linkedin_text=payload.linkedin_text,
        tiktok_text=payload.tiktok_text,
        youtube_title=payload.youtube_title,
        youtube_description=payload.youtube_description,
        x_text=payload.x_text,
        threads_text=payload.threads_text,
        targeting_mode=payload.targeting_mode
    )
    
    preview = CampaignResolver.preview_campaign_targets(db, campaign, payload.targeting_params)
    return preview


@router.post("/{campaign_id}/launch", response_model=CampaignResponse)
def launch_campaign(
    campaign_id: uuid.UUID,
    targeting_params: Dict[str, Any],
    channel_overrides: Optional[Dict[str, str]] = None,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Launches a draft campaign. Resolves targets, creates Publications,
    and dispatches tasks to background workers.
    """
    try:
        campaign, publications = CampaignResolver.launch_campaign(
            db=db,
            campaign_id=campaign_id,
            targeting_params=targeting_params,
            admin_id=admin.id,
            channel_overrides=channel_overrides
        )
        
        # Enqueue enqueuing task or trigger immediately
        if campaign.publishing_mode == "immediate":
            # For immediate mode, we trigger the scheduled publication task immediately 
            # to queue and execute jobs
            from app.tasks.publication import poll_and_queue_scheduled_publications
            poll_and_queue_scheduled_publications.delay()
            
        return campaign
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{campaign_id}", response_model=CampaignDetailResponse)
def get_campaign_detail(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve detailed stats and progress percentages for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    publications = db.query(Publication).filter(Publication.campaign_id == campaign_id).all()
    
    stats = {
        "pending": 0, "queued": 0, "processing": 0, "submitted": 0,
        "scheduled": 0, "published": 0, "retry_wait": 0, "failed": 0,
        "cancelled": 0, "skipped": 0, "unknown": 0
    }
    
    for pub in publications:
        status_name = pub.status
        stats[status_name] = stats.get(status_name, 0) + 1
        
    # Calculate progress percentage
    total = len(publications)
    resolved = stats["published"] + stats["scheduled"] + stats["failed"] + stats["cancelled"] + stats["skipped"]
    progress = (resolved / total * 100.0) if total > 0 else 0.0
    
    # Get Media info
    media_res = None
    if campaign.media_file_id:
        media_res = db.query(MediaFile).filter(MediaFile.id == campaign.media_file_id).first()
        
    return {
        "campaign": campaign,
        "media": media_res,
        "stats": stats,
        "progress_percentage": round(progress, 2)
    }


@router.get("/{campaign_id}/metrics", response_model=CampaignMetricsResponse)
def get_campaign_metrics(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Fetches engagement metrics (reactions, views, follows gained, etc.) for every
    published destination of this campaign, live from Buffer's Post.metrics API.
    Called on demand (not polled) - Buffer only refreshes these once a day, and a
    freshly-sent post can take up to ~24h before any metric appears.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    publications = (
        db.query(Publication)
        .filter(
            Publication.campaign_id == campaign_id,
            # "scheduled" is included alongside "published": both mean Buffer
            # accepted the post successfully (see docs/FUNCTIONALITY.md §6) and both
            # carry a real external_post_id metrics can be fetched for. A "scheduled"
            # publication whose due time has already passed has most likely gone
            # live on the real platform by now anyway - get_post_status isn't
            # implemented to confirm that (see docs/FUNCTIONALITY.md §13), so our
            # own status label never flips from "scheduled" to "published", but
            # Buffer's metrics endpoint doesn't care about our internal label.
            Publication.status.in_(["published", "scheduled"]),
            Publication.external_post_id.isnot(None),
        )
        .all()
    )

    client = get_buffer_client()
    totals: Dict[str, float] = {}
    # Per developers.buffer.com/types/PostMetricUnit.html, "percentage" metrics
    # (currently only engagementRate) are already a 0-100 rate, not a count - they
    # must be averaged across channels, never summed, or the total is nonsense.
    percentage_metric_counts: Dict[str, int] = {}
    channels: List[ChannelMetrics] = []

    for pub in publications:
        channel = pub.social_channel
        connection = pub.buffer_connection
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
            # see the same logic/comment in publications.py get_publication_metrics.
            external_link = result.get("external_link")
            if external_link and not pub.external_post_url:
                pub.external_post_url = external_link
                db.commit()
                entry.external_post_url = external_link

            for metric in entry.metrics:
                totals[metric.type] = totals.get(metric.type, 0.0) + metric.value
                if metric.unit == "percentage":
                    percentage_metric_counts[metric.type] = percentage_metric_counts.get(metric.type, 0) + 1

        except BufferApiError as e:
            entry.error = e.message
        except Exception as e:
            entry.error = str(e)

        channels.append(entry)

    for metric_type, count in percentage_metric_counts.items():
        totals[metric_type] = totals[metric_type] / count

    return CampaignMetricsResponse(totals=totals, channels=channels)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
def pause_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Pauses a running campaign. Moves all pending or queued jobs to retry_wait/paused state."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    if campaign.status != "running":
        raise HTTPException(status_code=400, detail="Only running campaigns can be paused")
        
    campaign.status = "paused"
    
    # Freeze pending publications
    db.query(Publication).filter(
        Publication.campaign_id == campaign_id,
        Publication.status.in_(["pending", "queued"])
    ).update({"status": "retry_wait", "next_attempt_at": datetime.now(timezone.utc) + timedelta(hours=24)}, synchronize_session=False)
    
    db.commit()
    return campaign


@router.post("/{campaign_id}/resume", response_model=CampaignResponse)
def resume_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Resume a paused campaign, shifting suspended jobs back to pending/queued status."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    if campaign.status != "paused":
        raise HTTPException(status_code=400, detail="Only paused campaigns can be resumed")
        
    campaign.status = "running"
    
    # Release frozen publications back to pending
    db.query(Publication).filter(
        Publication.campaign_id == campaign_id,
        Publication.status == "retry_wait"
    ).update({"status": "pending", "next_attempt_at": None}, synchronize_session=False)
    
    db.commit()
    
    # Trigger execution poll
    from app.tasks.publication import poll_and_queue_scheduled_publications
    poll_and_queue_scheduled_publications.delay()
    
    return campaign


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Cancels a campaign, moving all incomplete publications to cancelled state."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    campaign.status = "cancelled"
    campaign.completed_at = datetime.now(timezone.utc)
    
    # Cancel outstanding publications
    db.query(Publication).filter(
        Publication.campaign_id == campaign_id,
        Publication.status.in_(["pending", "queued", "retry_wait"])
    ).update({"status": "cancelled"}, synchronize_session=False)

    db.commit()
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Permanently deletes a campaign and everything tied to it - campaign_targets,
    publications and their publication_attempts - even if it was already
    published. Allowed regardless of status: this is an explicit, confirmed
    administrator action (per AGENTS.md, deleting historical records is
    distinct from silently re-publishing them), not an automatic cleanup.

    Nothing is orphaned: CampaignTarget/Publication both have
    ondelete="CASCADE" on campaign_id (and PublicationAttempt likewise on
    publication_id), mirrored by cascade="all, delete-orphan" on the Campaign/
    Publication relationships, so a single delete of the Campaign row cascades
    all the way down at the database level. The linked MediaFile (if any) is
    deliberately NOT deleted - it's a reusable asset independent of any one
    campaign, not campaign-owned data.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    audit = AuditLog(
        administrator_id=admin.id,
        action="campaign_delete",
        entity_type="campaign",
        entity_id=campaign.id,
        metadata_json={"title": campaign.title, "status": campaign.status},
    )
    db.add(audit)

    db.delete(campaign)
    db.commit()
    return
