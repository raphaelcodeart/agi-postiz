import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.blog_writer import BlogArticle, BlogPublication, WordpressSite
from app.models.campaign import Campaign
from app.integrations.openai.exceptions import OpenAIApiError
from app.services import blog_writer_article_service as article_service
from app.services import blog_writer_publication_service as publication_service
from app.tasks.blog_writer import publish_article_to_wordpress_task
from app.schemas.schemas import (
    BlogArticleCreateRequest,
    BlogArticleGenerateRequest,
    BlogArticleUpdateRequest,
    BlogArticleResponse,
    BlogArticleDetailResponse,
    BlogArticleListItem,
    BlogArticlePublishRequest,
    BlogPublicationResponse,
    SocialPreviewRequest,
    SocialPreviewResponse,
    BlogWriterDashboardResponse,
)

router = APIRouter()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _publication_to_response(db: Session, pub: BlogPublication) -> BlogPublicationResponse:
    site = db.query(WordpressSite).filter(WordpressSite.id == pub.wordpress_site_id).first()
    return BlogPublicationResponse(
        id=pub.id,
        article_id=pub.article_id,
        wordpress_site_id=pub.wordpress_site_id,
        wordpress_site_name=site.name if site else "—",
        wordpress_post_id=pub.wordpress_post_id,
        wordpress_post_url=pub.wordpress_post_url,
        wordpress_status=pub.wordpress_status,
        publication_status=pub.publication_status,
        error_message=pub.error_message,
        retry_count=pub.retry_count,
        published_at=pub.published_at,
        created_at=pub.created_at,
    )


def _get_article_or_404(db: Session, article_id: uuid.UUID) -> BlogArticle:
    article = db.query(BlogArticle).filter(BlogArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Articolo non trovato")
    return article


@router.get("/", response_model=List[BlogArticleListItem])
def list_articles(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    query = db.query(BlogArticle)
    if status_filter:
        query = query.filter(BlogArticle.status == status_filter)
    articles = query.order_by(BlogArticle.updated_at.desc()).offset(skip).limit(limit).all()

    result = []
    for a in articles:
        pubs = db.query(BlogPublication).filter(BlogPublication.article_id == a.id).all()
        result.append(BlogArticleListItem(
            id=a.id, title=a.title, language=a.language, status=a.status,
            created_at=a.created_at, updated_at=a.updated_at,
            sites_count=len(pubs), publications_count=len(pubs),
        ))
    return result


@router.post("/", response_model=BlogArticleResponse, status_code=201)
def create_article(
    payload: BlogArticleCreateRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Creates a draft directly from hand-written/pasted text - no AI call (see POST /generate for that)."""
    article = article_service.create_manual_article(db, payload.model_dump(mode="json"), admin.id, payload.user_id)
    return article


@router.post("/generate", response_model=BlogArticleResponse, status_code=201)
def generate_article(
    payload: BlogArticleGenerateRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    try:
        # mode="json" so UUID/datetime fields serialize cleanly when this dict
        # is later persisted into the JSONB generation_prompt column.
        article = article_service.generate_article(db, payload.model_dump(mode="json"), admin.id, payload.user_id)
    except OpenAIApiError as e:
        raise HTTPException(status_code=502, detail=e.message)
    return article


@router.get("/dashboard/stats", response_model=BlogWriterDashboardResponse)
def dashboard_stats(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    draft_count = db.query(BlogArticle).filter(BlogArticle.status == "draft").count()
    ready_count = db.query(BlogArticle).filter(BlogArticle.status == "ready").count()
    published_count = db.query(BlogArticle).filter(BlogArticle.status == "published").count()
    failed_publications_count = db.query(BlogPublication).filter(BlogPublication.publication_status == "failed").count()
    sites_count = db.query(WordpressSite).count()
    sites_error_count = db.query(WordpressSite).filter(WordpressSite.connection_status == "error").count()
    social_campaigns_count = db.query(Campaign).filter(Campaign.article_id.isnot(None)).count()

    recent = db.query(BlogArticle).order_by(BlogArticle.updated_at.desc()).limit(5).all()
    recent_articles = []
    for a in recent:
        pubs = db.query(BlogPublication).filter(BlogPublication.article_id == a.id).all()
        recent_articles.append(BlogArticleListItem(
            id=a.id, title=a.title, language=a.language, status=a.status,
            created_at=a.created_at, updated_at=a.updated_at,
            sites_count=len(pubs), publications_count=len(pubs),
        ))

    recent_pubs = db.query(BlogPublication).order_by(BlogPublication.updated_at.desc()).limit(5).all()
    recent_publications = [_publication_to_response(db, p) for p in recent_pubs]

    return BlogWriterDashboardResponse(
        draft_count=draft_count, ready_count=ready_count, published_count=published_count,
        failed_publications_count=failed_publications_count, sites_count=sites_count,
        sites_error_count=sites_error_count, social_campaigns_count=social_campaigns_count,
        recent_articles=recent_articles, recent_publications=recent_publications,
    )


@router.get("/{article_id}", response_model=BlogArticleDetailResponse)
def get_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    article = _get_article_or_404(db, article_id)
    pubs = db.query(BlogPublication).filter(BlogPublication.article_id == article.id).all()
    campaigns = db.query(Campaign).filter(Campaign.article_id == article.id).all()
    return BlogArticleDetailResponse(
        article=article,
        publications=[_publication_to_response(db, p) for p in pubs],
        social_campaigns=campaigns,
    )


@router.put("/{article_id}", response_model=BlogArticleResponse)
def update_article(
    article_id: uuid.UUID,
    payload: BlogArticleUpdateRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    article = _get_article_or_404(db, article_id)
    data = payload.model_dump(exclude_unset=True)
    if "media_file_id" in data:
        raw = data.pop("media_file_id")
        article.media_file_id = uuid.UUID(raw) if raw else None
    for key, value in data.items():
        setattr(article, key, value)
    article.last_edited_at = utc_now()
    if article.status == "draft" and data:
        article.status = "ready"
    db.commit()
    db.refresh(article)
    return article


@router.post("/{article_id}/archive", response_model=BlogArticleResponse)
def archive_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    article = _get_article_or_404(db, article_id)
    article.status = "archived"
    db.commit()
    db.refresh(article)
    return article


@router.post("/{article_id}/restore", response_model=BlogArticleResponse)
def restore_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Undoes an accidental archive - sends the article back to 'draft' from the trash (Cestino) view."""
    article = _get_article_or_404(db, article_id)
    if article.status != "archived":
        raise HTTPException(status_code=400, detail="Solo un articolo archiviato può essere ripristinato.")
    article.status = "draft"
    db.commit()
    db.refresh(article)
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    article = _get_article_or_404(db, article_id)
    has_live_publication = db.query(BlogPublication).filter(
        BlogPublication.article_id == article.id,
        BlogPublication.publication_status.in_(["published", "updated"]),
    ).first()
    if has_live_publication:
        raise HTTPException(
            status_code=400,
            detail="Articolo già pubblicato su almeno un sito: archivialo invece di eliminarlo."
        )
    db.delete(article)
    db.commit()
    return


@router.post("/{article_id}/duplicate", response_model=BlogArticleResponse, status_code=201)
def duplicate_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    original = _get_article_or_404(db, article_id)
    slug = article_service.ensure_unique_slug(db, article_service.slugify(f"{original.title}-copia"))

    copy = BlogArticle(
        user_id=original.user_id, title=f"{original.title} (copia)", slug=slug,
        excerpt=original.excerpt, content=original.content, media_file_id=original.media_file_id, hashtags=original.hashtags,
        primary_keyword=original.primary_keyword, secondary_keywords=original.secondary_keywords,
        meta_title=original.meta_title, meta_description=original.meta_description,
        language=original.language, tone=original.tone, target_audience=original.target_audience,
        article_goal=original.article_goal, generation_prompt=original.generation_prompt,
        generation_model=original.generation_model, status="draft", created_by=admin.id,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{article_id}/regenerate", response_model=BlogArticleResponse)
def regenerate_article(article_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    article = _get_article_or_404(db, article_id)
    if not article.generation_prompt:
        raise HTTPException(status_code=400, detail="Nessun parametro di generazione salvato per questo articolo.")
    try:
        api_key_model_params = article.generation_prompt
        regenerated = article_service.generate_article(db, api_key_model_params, admin.id, article.user_id)
    except OpenAIApiError as e:
        raise HTTPException(status_code=502, detail=e.message)
    # Overwrite the existing draft in place rather than creating a new row, so
    # links/publications already pointing at this article_id stay valid.
    article.title = regenerated.title
    article.slug = regenerated.slug
    article.excerpt = regenerated.excerpt
    article.content = regenerated.content
    article.hashtags = regenerated.hashtags
    article.secondary_keywords = regenerated.secondary_keywords
    article.meta_title = regenerated.meta_title
    article.meta_description = regenerated.meta_description
    article.tone = regenerated.tone
    article.status = "draft"
    article.last_edited_at = utc_now()
    db.delete(regenerated)
    db.commit()
    db.refresh(article)
    return article


@router.post("/{article_id}/publish", response_model=List[BlogPublicationResponse])
def publish_article(
    article_id: uuid.UUID,
    payload: BlogArticlePublishRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    article = _get_article_or_404(db, article_id)
    targets = [t.model_dump() for t in payload.targets]
    pubs = publication_service.create_or_reset_publications(db, article, targets)

    pending_ids = [str(p.id) for p in pubs if p.publication_status == "pending"]
    for pub_id in pending_ids:
        publish_article_to_wordpress_task.delay(pub_id)

    return [_publication_to_response(db, p) for p in pubs]


@router.post("/{article_id}/publications/{publication_id}/retry", response_model=BlogPublicationResponse)
def retry_publication(
    article_id: uuid.UUID,
    publication_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    pub = db.query(BlogPublication).filter(
        BlogPublication.id == publication_id, BlogPublication.article_id == article_id
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Pubblicazione non trovata")
    if pub.publication_status not in ("failed",):
        raise HTTPException(status_code=400, detail="Solo le pubblicazioni fallite possono essere riprovate.")

    pub.publication_status = "pending"
    pub.error_message = None
    db.commit()
    publish_article_to_wordpress_task.delay(str(pub.id))
    db.refresh(pub)
    return _publication_to_response(db, pub)


@router.post("/{article_id}/social-preview", response_model=SocialPreviewResponse)
def social_preview(
    article_id: uuid.UUID,
    payload: SocialPreviewRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Powers "Usa per campagna social": requires the article to be published on
    at least one site, generates per-platform summaries + the public URL. The
    frontend takes this response and prefills the *existing* campaign wizard -
    this endpoint never creates a Campaign itself (see docs/FUNCTIONALITY.md
    for the reasoning: reuse the existing flow, don't duplicate it).
    """
    article = _get_article_or_404(db, article_id)

    query = db.query(BlogPublication).filter(
        BlogPublication.article_id == article.id,
        BlogPublication.publication_status.in_(["published", "updated"]),
    )
    if payload.wordpress_site_id:
        query = query.filter(BlogPublication.wordpress_site_id == payload.wordpress_site_id)
    publication = query.first()

    if not publication or not publication.wordpress_post_url:
        raise HTTPException(
            status_code=400,
            detail="L'articolo deve essere pubblicato su almeno un sito WordPress prima di poterlo usare per una campagna social."
        )

    try:
        texts = article_service.build_social_preview(db, article, publication.wordpress_post_url)
    except OpenAIApiError as e:
        raise HTTPException(status_code=502, detail=e.message)

    return SocialPreviewResponse(article_url=publication.wordpress_post_url, **texts)
