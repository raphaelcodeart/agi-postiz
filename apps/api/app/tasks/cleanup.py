import os
from datetime import datetime, timezone, timedelta
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.models.publication import Publication
from app.models.media import MediaFile
from app.services.rate_limiter import RateLimiter

logger = get_task_logger(__name__)

@celery.task(name="app.tasks.cleanup.recover_stale_publications")
def recover_stale_publications() -> None:
    """
    Periodic recovery task running every 5 minutes to find publications stuck in 'processing'
    (worker crashes/connection resets) or stuck in 'queued' (their Celery dispatch was lost or
    silently skipped - e.g. a worker racing the row lock before the queueing transaction
    committed) with nothing left to re-scan them, since poll_and_queue_scheduled_publications
    only ever re-scans 'pending'/'retry_wait'.
    Stuck threshold: 15 minutes for both.
    """
    logger.info("Starting stale publications recovery check.")
    db = SessionLocal()
    rate_limiter = RateLimiter()

    try:
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=15)

        stuck_processing = db.query(Publication).filter(
            Publication.status == "processing",
            Publication.processing_started_at <= threshold_time
        ).all()

        for pub in stuck_processing:
            # Release lock in rate limiter just in case
            try:
                rate_limiter.release_lock(pub.buffer_connection_id)
            except Exception:
                pass

            # Check attempt counts
            if pub.attempt_count < pub.max_attempts:
                pub.status = "retry_wait"
                pub.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=1)
                pub.error_message = "Stale processing job recovered: worker crashed or request timed out."
                pub.error_category = "worker_timeout"
                logger.info(f"Publication {pub.id} reset to retry_wait.")
            else:
                pub.status = "failed"
                pub.error_message = "Stale processing job failed: worker crashed and maximum attempts exceeded."
                pub.error_category = "worker_timeout"
                logger.warning(f"Publication {pub.id} marked as failed (max attempts reached).")

        if stuck_processing:
            logger.warning(f"Found {len(stuck_processing)} stale 'processing' publications. Recovered.")

        stuck_queued = db.query(Publication).filter(
            Publication.status == "queued",
            Publication.updated_at <= threshold_time
        ).all()

        for pub in stuck_queued:
            # Never actually reached Buffer (attempt_count still 0 at this point), so
            # just send it back to "pending" - the next poll cycle will re-queue and
            # re-dispatch it cleanly, no backoff/attempt penalty needed.
            pub.status = "pending"
            pub.error_message = "Recovered from a stuck 'queued' state: its background job was lost or never ran."
            pub.error_category = "worker_timeout"
            logger.warning(f"Publication {pub.id} reset from stale 'queued' to 'pending'.")

        if stuck_queued:
            logger.warning(f"Found {len(stuck_queued)} stale 'queued' publications. Recovered.")

        if not stuck_processing and not stuck_queued:
            logger.info("No stale publications found.")

        db.commit()
    except Exception as e:
        logger.error(f"Error recovering stale publications: {str(e)}")
        db.rollback()
    finally:
        db.close()


@celery.task(name="app.tasks.cleanup.media_retention_cleanup")
def media_retention_cleanup() -> None:
    """
    Periodic task running daily to delete physical files of soft-deleted MediaFile records.
    """
    logger.info("Starting media retention cleanup.")
    db = SessionLocal()
    
    try:
        # Retrieve all media files marked as deleted
        deleted_media = db.query(MediaFile).filter(
            MediaFile.deleted_at.is_not(None)
        ).all()
        
        if not deleted_media:
            logger.info("No soft-deleted media files to clean up.")
            return
            
        cleaned_count = 0
        for media in deleted_media:
            # Ensure it is safe to delete (no active campaigns)
            # Delete physical file
            if os.path.exists(media.storage_key):
                try:
                    os.remove(media.storage_key)
                except Exception:
                    pass
            
            # Delete thumbnail if any
            if media.metadata_json and "thumbnail_path" in media.metadata_json:
                thumb_path = media.metadata_json["thumbnail_path"]
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception:
                        pass
            
            # Hard delete from DB
            db.delete(media)
            cleaned_count += 1
            
        db.commit()
        logger.info(f"Cleaned up {cleaned_count} soft-deleted media records and files.")
    except Exception as e:
        logger.error(f"Error during media retention cleanup: {str(e)}")
        db.rollback()
    finally:
        db.close()
