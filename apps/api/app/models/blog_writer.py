import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WordpressSite(Base):
    """
    A WordPress site an admin can publish Blog Writer articles to, authenticated
    via a WordPress Application Password (developer.wordpress.org - Basic Auth
    over HTTPS, not OAuth). Optionally scoped to a User (client), same pattern
    as BufferConnection.user_id - not a login-tenant, just an optional owner tag.
    """
    __tablename__ = "blog_writer_wordpress_sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    api_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_application_password: Mapped[str] = mapped_column(String(1000), nullable=False)

    default_author_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_category_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # publish, draft, pending, private
    language: Mapped[str] = mapped_column(String(10), default="it", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(20), default="untested", nullable=False)  # untested, connected, error
    last_connection_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connection_error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    last_published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[Optional["User"]] = relationship("User")
    publications: Mapped[List["BlogPublication"]] = relationship(
        "BlogPublication", back_populates="wordpress_site", cascade="all, delete-orphan"
    )


class BlogArticle(Base):
    """A Blog Writer article: AI-drafted, edited, optionally published to one or more WordpressSite rows."""
    __tablename__ = "blog_writer_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    content: Mapped[str] = mapped_column(String, nullable=False)  # HTML body
    # Manually uploaded via the existing Media library (apps/api/app/models/media.py)
    # - not generated/searched by AI, see AGENTS.md rule 8/docs/BLOG_WRITER.md §8.
    # Embedded into the post content on publish (see blog_writer_publication_service),
    # not a native WordPress "featured image" (that would require re-uploading the
    # file into each target site's own media library first - out of scope for now).
    media_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True)

    hashtags: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    primary_keyword: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    secondary_keywords: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    meta_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    language: Mapped[str] = mapped_column(String(10), default="it", nullable=False)
    tone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    article_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Full generation form payload (topic, keywords, length, must-include/avoid,
    # cta, hashtag count, etc.) - kept for "rigenera" and for audit/reference.
    generation_prompt: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    generation_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    # generating, draft, ready, publishing, partially_published, published, failed, archived

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    last_edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[Optional["User"]] = relationship("User")
    publications: Mapped[List["BlogPublication"]] = relationship(
        "BlogPublication", back_populates="article", cascade="all, delete-orphan"
    )


class BlogPublication(Base):
    """
    One row per (article, wordpress_site) - mirrors Publication/CampaignTarget's
    "every destination is independent" principle (AGENTS.md rule 1). A failure on
    one site never affects another article's publications on other sites.
    """
    __tablename__ = "blog_writer_publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("blog_writer_articles.id", ondelete="CASCADE"), nullable=False)
    wordpress_site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("blog_writer_wordpress_sites.id", ondelete="CASCADE"), nullable=False)

    wordpress_post_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wordpress_post_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    wordpress_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # publish, draft, pending, private (as WP reports it)

    publication_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending, publishing, published, failed, retrying, removed, updated

    request_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)  # sanitized, never credentials
    response_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    article: Mapped[BlogArticle] = relationship("BlogArticle", back_populates="publications")
    wordpress_site: Mapped[WordpressSite] = relationship("WordpressSite", back_populates="publications")

    __table_args__ = (
        UniqueConstraint("article_id", "wordpress_site_id", name="uq_blog_publication_article_site"),
    )
