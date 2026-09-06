from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.models.blog_writer import BlogArticle, BlogPublication, WordpressSite
from app.models.media import MediaFile
from app.core.security import EncryptionService
from app.integrations.wordpress import client as wp_client
from app.integrations.wordpress.exceptions import WordpressApiError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

SUCCESS_STATES = {"published", "updated"}


def _content_with_media(db: Session, article: BlogArticle) -> str:
    """
    Prepends the attached media (manually uploaded via the existing Media
    library, never AI-generated/searched) as a plain <img> in the post body.
    Not a native WordPress "featured image" - that needs the file re-uploaded
    into each target site's own media library first (POST /wp/v2/media), out
    of scope for now (see docs/BLOG_WRITER.md §8). This only needs the
    content field, which WordPress's REST API already accepts as arbitrary
    HTML - no extra endpoint/assumption involved.
    """
    if not article.media_file_id:
        return article.content
    media = db.query(MediaFile).filter(MediaFile.id == article.media_file_id).first()
    if not media or not media.public_url:
        return article.content
    img_tag = f'<img src="{media.public_url}" alt="{article.title}" />'
    return f"{img_tag}\n{article.content}"


def create_or_reset_publications(db: Session, article: BlogArticle, targets: List[Dict[str, Any]]) -> List[BlogPublication]:
    """
    One BlogPublication row per (article, site) - mirrors CampaignResolver's
    idempotent target creation (uq_blog_publication_article_site prevents
    duplicates on re-publish). A site whose publication already succeeded is
    left untouched - never re-published (AGENTS.md rule 2's principle applied
    here too).
    """
    result = []
    for target in targets:
        site_id = target["wordpress_site_id"]
        existing = db.query(BlogPublication).filter(
            BlogPublication.article_id == article.id,
            BlogPublication.wordpress_site_id == site_id,
        ).first()
        request_payload = {
            "category_id": target.get("category_id"),
            "author_id": target.get("author_id"),
            "status": target.get("status"),
        }
        if existing:
            if existing.publication_status in SUCCESS_STATES:
                result.append(existing)
                continue
            existing.publication_status = "pending"
            existing.error_message = None
            existing.request_payload = request_payload
            result.append(existing)
        else:
            pub = BlogPublication(
                article_id=article.id,
                wordpress_site_id=site_id,
                publication_status="pending",
                request_payload=request_payload,
            )
            db.add(pub)
            result.append(pub)

    article.status = "publishing"
    db.commit()
    for pub in result:
        db.refresh(pub)
    return result


def execute_publication(db: Session, publication: BlogPublication) -> None:
    """
    Runs a single site's create/update call. Caller is responsible for locking
    the row (see tasks/blog_writer.py, same SELECT...FOR UPDATE SKIP LOCKED
    pattern as process_publication_task) before calling this.
    """
    site = db.query(WordpressSite).filter(WordpressSite.id == publication.wordpress_site_id).first()
    article = db.query(BlogArticle).filter(BlogArticle.id == publication.article_id).first()
    if not site or not article:
        publication.publication_status = "failed"
        publication.error_message = "Sito WordPress o articolo non trovato"
        db.commit()
        return

    password = EncryptionService.decrypt(site.encrypted_application_password)
    payload = publication.request_payload or {}
    category = payload.get("category_id") or site.default_category_id
    author = payload.get("author_id") or site.default_author_id
    status = payload.get("status") or site.default_status

    content = _content_with_media(db, article)

    try:
        if publication.wordpress_post_id:
            result = wp_client.update_post(
                site.api_url, site.username, password, publication.wordpress_post_id,
                title=article.title, content=content, excerpt=article.excerpt, status=status,
            )
            publication.publication_status = "updated"
        else:
            result = wp_client.create_post(
                site.api_url, site.username, password,
                title=article.title, content=content, excerpt=article.excerpt, status=status,
                author=author, category=category, tag_ids=None, slug=article.slug,
            )
            publication.publication_status = "published"

        publication.wordpress_post_id = result["id"]
        publication.wordpress_post_url = result["link"]
        publication.wordpress_status = result["status"]
        publication.response_summary = {"id": result["id"], "status": result["status"]}
        publication.error_message = None
        publication.published_at = utc_now()
        site.last_published_at = utc_now()
    except WordpressApiError as e:
        publication.retry_count += 1
        publication.publication_status = "failed"
        publication.error_message = e.message
    except Exception as e:
        publication.retry_count += 1
        publication.publication_status = "failed"
        publication.error_message = str(e)

    db.commit()
    _recalculate_article_status(db, article)


def _recalculate_article_status(db: Session, article: BlogArticle) -> None:
    """
    Mirrors _recalculate_campaign_status in tasks/publication.py: a single
    failing site never blocks the others, and the article's own status
    reflects the aggregate without the caller having to compute it everywhere.
    """
    pubs = db.query(BlogPublication).filter(BlogPublication.article_id == article.id).all()
    if not pubs:
        return
    statuses = [p.publication_status for p in pubs]
    if any(s in ("pending", "publishing", "retrying") for s in statuses):
        return  # still in flight, leave status as "publishing"
    if all(s in SUCCESS_STATES for s in statuses):
        article.status = "published"
        if not article.published_at:
            article.published_at = utc_now()
    elif any(s in SUCCESS_STATES for s in statuses):
        article.status = "partially_published"
    else:
        article.status = "failed"
    db.commit()
