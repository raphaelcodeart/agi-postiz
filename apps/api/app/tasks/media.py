import uuid
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.services.media_service import MediaService

logger = get_task_logger(__name__)

@celery.task(name="app.tasks.media.inspect_media")
def inspect_media_task(media_id_str: str) -> None:
    """
    Background task to inspect uploaded media, read details via ffprobe,
    and generate video thumbnails.
    """
    logger.info(f"Starting inspection for media {media_id_str}")
    media_id = uuid.UUID(media_id_str)
    
    db = SessionLocal()
    try:
        MediaService.run_media_inspection_task(db, media_id)
        logger.info(f"Successfully completed inspection for media {media_id_str}")
    except Exception as e:
        logger.error(f"Error during inspection for media {media_id_str}: {str(e)}")
    finally:
        db.close()
