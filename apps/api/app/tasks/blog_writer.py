import uuid
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.models.blog_writer import BlogPublication
from app.services.blog_writer_publication_service import execute_publication

logger = get_task_logger(__name__)


@celery.task(name="app.tasks.blog_writer.publish_article_to_wordpress", bind=True, max_retries=3)
def publish_article_to_wordpress_task(self, publication_id_str: str) -> None:
    """
    Publishes/updates a single BlogPublication (one article on one WordPress
    site). Same row-lock pattern as process_publication_task
    (apps/api/app/tasks/publication.py): SELECT...FOR UPDATE SKIP LOCKED so a
    duplicate dispatch of the same publication_id is a safe no-op instead of a
    double post, and one site's failure never touches any other site's row.
    """
    logger.info(f"Processing blog publication task for {publication_id_str}")
    publication_id = uuid.UUID(publication_id_str)
    db = SessionLocal()
    try:
        pub = db.query(BlogPublication).filter(
            BlogPublication.id == publication_id,
            BlogPublication.publication_status.in_(["pending", "retrying"])
        ).with_for_update(skip_locked=True).first()

        if not pub:
            logger.info(f"Blog publication {publication_id_str} already processing or completed. Skipping.")
            return

        pub.publication_status = "publishing"
        db.commit()

        execute_publication(db, pub)
    finally:
        db.close()
