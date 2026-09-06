import re
import unicodedata
from typing import Any, Dict
from sqlalchemy.orm import Session
from app.models.blog_writer import BlogArticle
from app.integrations.openai.client import generate_blog_article, adapt_article_for_platforms
from app.integrations.openai.exceptions import OpenAIApiError
from app.services.ai_settings_service import get_openai_credentials


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", normalized).strip().lower()
    return re.sub(r"[\s-]+", "-", normalized)[:255] or "articolo"


def ensure_unique_slug(db: Session, base_slug: str) -> str:
    """
    Slug uniqueness among local articles is not a hard DB constraint - WordPress
    itself de-duplicates slugs per-site on publish - this is just to keep the
    local list/URLs readable.
    """
    slug = base_slug
    suffix = 2
    while db.query(BlogArticle).filter(BlogArticle.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def create_manual_article(db: Session, params: Dict[str, Any], created_by, user_id) -> BlogArticle:
    """
    Creates a draft directly from admin-provided text - no AI call at all. For
    when the article is dictated, pasted from elsewhere, or the admin simply
    prefers to write it by hand; everything downstream (editor, publish,
    "usa per campagna social") treats it identically to an AI-generated draft.
    """
    slug = ensure_unique_slug(db, params.get("slug") or slugify(params["title"]))
    article = BlogArticle(
        user_id=user_id,
        title=params["title"],
        slug=slug,
        excerpt=params.get("excerpt"),
        content=params["content"],
        hashtags=params.get("hashtags") or [],
        meta_title=params.get("meta_title"),
        meta_description=params.get("meta_description"),
        language=params.get("language", "it"),
        status="draft",
        created_by=created_by,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def generate_article(db: Session, params: Dict[str, Any], created_by, user_id) -> BlogArticle:
    """
    Calls OpenAI to draft a full article and persists it immediately as a
    'draft' - generation is never left un-saved, matching AGENTS.md's spirit
    for publications (every attempt should be traceable/recoverable), and
    letting the admin resume editing even if they navigate away right after.
    """
    api_key, model = get_openai_credentials(db)
    if not api_key:
        raise OpenAIApiError("Generazione AI non configurata: collega una chiave API OpenAI in Impostazioni.")

    result = generate_blog_article(api_key, model, params)
    slug = ensure_unique_slug(db, result["slug"] or slugify(result["title"]))

    article = BlogArticle(
        user_id=user_id,
        title=result["title"] or params["topic"][:255],
        slug=slug,
        excerpt=result["excerpt"],
        content=result["content"],
        hashtags=result["hashtags"],
        primary_keyword=params.get("primary_keyword"),
        secondary_keywords=result["keywords"] or params.get("secondary_keywords"),
        meta_title=result["meta_title"] or None,
        meta_description=result["meta_description"] or None,
        language=result["language"] or params.get("language", "it"),
        tone=result["tone"] or params.get("tone"),
        target_audience=params.get("target_audience"),
        article_goal=params.get("goal"),
        generation_prompt=params,
        generation_model=model,
        status="draft",
        created_by=created_by,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def build_social_preview(db: Session, article: BlogArticle, article_url: str) -> Dict[str, str]:
    api_key, model = get_openai_credentials(db)
    if not api_key:
        raise OpenAIApiError("Generazione AI non configurata: collega una chiave API OpenAI in Impostazioni.")
    return adapt_article_for_platforms(api_key, model, article.title, article.excerpt or "", article_url)
