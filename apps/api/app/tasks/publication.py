import uuid
import time
import random
from datetime import datetime, timezone, timedelta
from celery.utils.log import get_task_logger
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.core.config import settings
from app.core.security import EncryptionService
from app.services.rate_limiter import RateLimiter
from app.integrations.buffer.service import get_buffer_client
from app.integrations.buffer.exceptions import BufferApiError, BufferRateLimitError
from app.models.campaign import Campaign, CampaignTarget
from app.models.buffer import SocialChannel
from app.models.media import MediaFile
from app.models.publication import Publication, PublicationAttempt

logger = get_task_logger(__name__)

@celery.task(name="app.tasks.publication.process_publication", bind=True, max_retries=3)
def process_publication_task(self, publication_id_str: str) -> None:
    """
    Core publishing job executing the state machine transitions.
    1. Lock row to avoid double processing
    2. Check rate limiters
    3. Dispatch to Buffer API
    4. Record execution stats
    5. Handle temporary retries / permanent failures
    """
    logger.info(f"Processing publication task for {publication_id_str}")
    publication_id = uuid.UUID(publication_id_str)
    
    db = SessionLocal()
    rate_limiter = RateLimiter()
    
    try:
        # Acquire row lock using SELECT FOR UPDATE with skip_locked
        pub = db.query(Publication).filter(
            Publication.id == publication_id,
            Publication.status.in_(["pending", "queued", "retry_wait"])
        ).with_for_update(skip_locked=True).first()
        
        if not pub:
            logger.info(f"Publication {publication_id_str} is already processing or completed. Skipping.")
            return

        # Move to processing state immediately
        pub.status = "processing"
        pub.processing_started_at = datetime.now(timezone.utc)
        db.commit()

        # Check rate limiter availability
        if not rate_limiter.acquire_lock(pub.buffer_connection_id):
            logger.info(f"Rate limit or concurrency cap hit for connection {pub.buffer_connection_id}. Re-queuing.")
            # Reset to retry_wait with a small delay
            pub.status = "retry_wait"
            pub.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=15)
            db.commit()
            return

        # Execute Buffer post creation
        success = False
        http_status = None
        ext_err_code = None
        err_category = "unknown"
        err_message = None
        response_data = None
        external_post_id = None
        external_post_url = None

        started_time = time.time()
        
        try:
            # 1. Fetch tokens
            access_token = EncryptionService.decrypt(pub.buffer_connection.access_token_encrypted)
            if not access_token:
                raise BufferApiError("Credentials missing, connection needs reconnection.", category="auth_error")

            # 2. Resolve media attachments
            media_url = None
            thumbnail_url = None
            media_type = None
            video_duration_seconds = None

            campaign = pub.campaign
            if campaign.media_file_id:
                media_file = db.query(MediaFile).filter(MediaFile.id == campaign.media_file_id).first()
                if media_file and media_file.processing_status == "ready":
                    media_url = media_file.public_url
                    media_type = "video" if "video" in media_file.mime_type else "image"
                    if media_type == "video":
                        video_duration_seconds = media_file.duration_seconds
                        if media_file.metadata_json:
                            thumbnail_url = media_file.metadata_json.get("thumbnail_url")

            # Buffer fetches media by URL when the post goes out, so it must be public
            # HTTPS - see https://developers.buffer.com/guides/hosting-media.html. This
            # server has no HTTPS media hosting configured yet, so refuse rather than
            # send Buffer a URL we already know it can never reach.
            if media_url and settings.BUFFER_INTEGRATION_MODE.lower() == "production" and not media_url.startswith("https://"):
                raise BufferApiError(
                    "Pubblicazione con media non disponibile: richiede hosting media HTTPS, non ancora configurato sul server.",
                    category="configuration_error",
                )

            # 3. Resolve target text
            resolved_text = pub.campaign_target.resolved_text
            platform = pub.social_channel.platform
            youtube_title = (campaign.youtube_title or campaign.title) if platform == "youtube" else None

            # 4. Dispatch API request
            client = get_buffer_client()
            res = client.create_post(
                api_key=access_token,
                channel_id=pub.social_channel.external_channel_id,
                text=resolved_text,
                media_url=media_url,
                thumbnail_url=thumbnail_url,
                media_type=media_type,
                scheduled_at=pub.scheduled_at,
                platform=platform,
                youtube_title=youtube_title,
                video_duration_seconds=video_duration_seconds,
            )

            external_post_id = res.get("id")
            external_post_url = res.get("url")
            response_data = res
            success = True
            
        except BufferApiError as e:
            http_status = e.status_code
            ext_err_code = e.error_code
            err_category = e.category
            err_message = e.message
            response_data = {"error": err_message}
            
            # Handle rate-limit pause
            if isinstance(e, BufferRateLimitError):
                # Pause connection for 60 seconds
                rate_limiter.pause_connection(pub.buffer_connection_id, duration_seconds=60)
                
        except Exception as e:
            err_message = str(e)
            response_data = {"error": err_message}

        duration_ms = int((time.time() - started_time) * 1000)

        # Record Attempt logs
        attempt_number = pub.attempt_count + 1
        
        attempt = PublicationAttempt(
            publication_id=pub.id,
            attempt_number=attempt_number,
            started_at=pub.processing_started_at,
            completed_at=datetime.now(timezone.utc),
            success=success,
            http_status=http_status,
            external_error_code=ext_err_code,
            error_category=err_category,
            error_message=err_message,
            sanitized_request={
                "channel_id": pub.social_channel.external_channel_id,
                "publishing_mode": pub.campaign.publishing_mode,
            },
            sanitized_response=response_data,
            duration_ms=duration_ms
        )
        db.add(attempt)
        
        # Release concurrency locks
        rate_limiter.release_lock(pub.buffer_connection_id)

        # Update Publication attributes
        pub.attempt_count = attempt_number
        
        if success:
            pub.status = "published" if pub.scheduled_at is None else "scheduled"
            pub.published_at = datetime.now(timezone.utc) if pub.scheduled_at is None else None
            pub.submitted_at = datetime.now(timezone.utc)
            pub.external_post_id = external_post_id
            pub.external_post_url = external_post_url
            pub.error_message = None
            pub.error_code = None
            pub.error_category = None
        else:
            # Check retry logic
            is_temporary = False
            # Check category / HTTP Status
            if http_status in (429, 500, 502, 503, 504) or err_category in ("network_error", "server_error", "rate_limit"):
                is_temporary = True
                
            if is_temporary and attempt_number < pub.max_attempts:
                # Trigger retry wait state
                pub.status = "retry_wait"
                
                # Fetch retry backoff sequence: 60s, 300s, 900s, 3600s, 21600s
                backoff_list = settings.retry_backoff_list
                backoff_idx = min(attempt_number - 1, len(backoff_list) - 1)
                delay_sec = backoff_list[backoff_idx]
                
                # Add random jitter (10% of backoff time or up to 30s max)
                jitter = random.randint(1, min(30, int(delay_sec * 0.1) + 1))
                next_time = datetime.now(timezone.utc) + timedelta(seconds=delay_sec + jitter)
                
                pub.next_attempt_at = next_time
                logger.info(f"Temporary failure for pub {pub.id}. Next attempt scheduled at {next_time.isoformat()}")
            else:
                # Mark as permanently failed
                pub.status = "failed"
                pub.next_attempt_at = None
                pub.error_message = err_message
                pub.error_code = ext_err_code
                pub.error_category = err_category
                logger.warning(f"Permanent failure for pub {pub.id}. Reason: {err_message}")

        db.commit()

        # Recalculate campaign progress status
        _recalculate_campaign_status(db, pub.campaign_id)

    except Exception as e:
        logger.error(f"Failed to execute publication task {publication_id_str}: {str(e)}")
        # Reset publication back to pending/queued if db rollback is possible
        db.rollback()
    finally:
        db.close()


def _recalculate_campaign_status(db: Session, campaign_id: uuid.UUID) -> None:
    """
    Inspects all child publication states and sets overall campaign status.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return

    publications = db.query(Publication).filter(Publication.campaign_id == campaign_id).all()
    if not publications:
        return

    statuses = [p.status for p in publications]
    
    total = len(statuses)
    published = statuses.count("published") + statuses.count("scheduled")
    failed = statuses.count("failed")
    cancelled = statuses.count("cancelled")
    skipped = statuses.count("skipped")
    processing = statuses.count("processing")
    queued = statuses.count("queued")
    retry_wait = statuses.count("retry_wait")
    pending = statuses.count("pending")

    # Determine state
    if processing > 0:
        campaign.status = "running"
    elif queued > 0 or retry_wait > 0:
        campaign.status = "running"
    elif pending > 0:
        # If some are pending, but others are active, keep running
        if published > 0 or failed > 0 or processing > 0:
            campaign.status = "running"
        else:
            campaign.status = "queued"
    else:
        # All tasks resolved (published, failed, cancelled, skipped)
        if published == total:
            campaign.status = "completed"
        elif published + skipped + cancelled == total:
            campaign.status = "completed"
        elif failed == total:
            campaign.status = "failed"
        elif published > 0 and failed > 0:
            campaign.status = "partially_completed"
        else:
            campaign.status = "completed"

    if campaign.status in ("completed", "partially_completed", "failed"):
        campaign.completed_at = datetime.now(timezone.utc)

    db.commit()


@celery.task(name="app.tasks.publication.poll_and_queue_scheduled_publications")
def poll_and_queue_scheduled_publications() -> None:
    """
    Periodic task running every 30 seconds to:
    1. Launch scheduled campaigns whose trigger time has arrived
    2. Collect and dispatch pending or retry_wait publications
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Look for scheduled campaigns
        scheduled_campaigns = db.query(Campaign).filter(
            Campaign.status == "draft",
            Campaign.publishing_mode == "scheduled",
            Campaign.scheduled_at <= now
        ).all()

        for camp in scheduled_campaigns:
            logger.info(f"Scheduled campaign {camp.id} ({camp.title}) trigger time reached. Launching.")
            try:
                # Retrieve campaign targeting params stored in campaign metadata or similar
                # For this version we default targeting_mode parameters to empty, 
                # meaning it resolves all active channels as targeting parameters
                targeting_params = camp.metadata_json or {}
                # Mock targeting params if empty to fallback to targeting mode logic
                from app.services.campaign_resolver import CampaignResolver
                CampaignResolver.launch_campaign(db, camp.id, targeting_params)
            except Exception as e:
                logger.error(f"Failed to auto-launch scheduled campaign {camp.id}: {str(e)}")

        # 2. Find all pending and ready-to-retry publications
        pending_pubs = db.query(Publication).filter(
            or_(
                Publication.status == "pending",
                and_(
                    Publication.status == "retry_wait",
                    Publication.next_attempt_at <= now
                )
            )
        ).all()

        if pending_pubs:
            logger.info(f"Found {len(pending_pubs)} publications ready to be queued for processing.")
            pub_ids = [str(pub.id) for pub in pending_pubs]
            for pub in pending_pubs:
                pub.status = "queued"
            # Commit BEFORE dispatching: process_publication_task acquires its row
            # lock with SELECT ... FOR UPDATE SKIP LOCKED. If a worker picks up a
            # .delay() call while this UPDATE is still uncommitted (and thus still
            # holding the row lock), SKIP LOCKED makes it silently skip that row and
            # return - and since "queued" isn't re-scanned by this task's own query
            # above (only "pending"/"retry_wait" are), the publication would then
            # stay "queued" forever with no automatic recovery. Committing first
            # guarantees the lock is released before any worker can race it.
            db.commit()
            for pub_id in pub_ids:
                process_publication_task.delay(pub_id)

    finally:
        db.close()
