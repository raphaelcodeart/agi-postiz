"""
Omnichannel Responder - AI-assisted unified inbox (WhatsApp/Instagram/
Facebook/Telegram...) with mandatory human approval before any reply is sent.

Independent add-on module: every table below is new (prefixed omni_) and
none of the existing tables/models are modified. The single link back to
the rest of the platform is `owner_id`, a FK to administrators.id (the
identity that actually logs into this dashboard - see
app/models/administrator.py). Every row in every table below carries it
directly (denormalized on purpose, not just reachable via a join) so that
if this system ever becomes multi-admin, every query can filter by
owner_id alone and no data ever leaks across accounts.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Integer, Float, Boolean, Table, Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# Channel accounts - one row per connected social/messaging account
# (Telegram bot, WhatsApp Business number, Instagram/Facebook page...)
# ==============================================================================
class OmniChannelAccount(Base):
    __tablename__ = "omni_channel_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)

    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # telegram, whatsapp, instagram, facebook, gmail, mock
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_account_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, connected, error, disabled

    # Never returned to the frontend - see app/core/security.py EncryptionService,
    # same Fernet-at-rest pattern already used for Buffer connection tokens.
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Random per-account secret, appended to the webhook URL path so an
    # attacker can't post fake messages without knowing it (Telegram has no
    # built-in payload signature like Meta's X-Hub-Signature-256).
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False, default=lambda: uuid.uuid4().hex)
    config_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("config", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # passive_deletes=True: without it, SQLAlchemy's default ORM behavior when
    # deleting the parent is to load this collection and try to null out each
    # child's channel_account_id before/instead of deleting - but that column
    # is NOT NULL, so it fails with an unhandled IntegrityError (surfaced as a
    # raw 500) the moment any conversation exists for this channel. The FK
    # already has ondelete="CASCADE" at the database level (see
    # OmniConversation.channel_account_id below) - this tells SQLAlchemy to
    # trust that entirely instead of managing it in Python. Real bug, found
    # and fixed 2026-08-15: deleting a channel account failed until every one
    # of its conversations was deleted by hand first.
    conversations: Mapped[List["OmniConversation"]] = relationship("OmniConversation", back_populates="channel_account", passive_deletes=True)


# ==============================================================================
# CRM - the person writing in, kept separate from their per-channel identity
# so the same human can eventually be recognized across WhatsApp/Instagram/etc.
# Deliberately NOT the existing `users` table (app/models/user.py), which
# represents accounts managed by the admin for social publishing - a
# different concept from "a contact who messaged the business".
# ==============================================================================
class OmniCustomer(Base):
    __tablename__ = "omni_customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # When true, ingest_message() (services/omnichannel_service.py) still records
    # the customer's messages (nothing is silently lost) but files the
    # conversation straight into SPAM and never enqueues an AI draft - see
    # webhooks/omnichannel_webhooks.py::_ingest_and_trigger.
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    identities: Mapped[List["OmniCustomerIdentity"]] = relationship("OmniCustomerIdentity", back_populates="customer", cascade="all, delete-orphan")
    # Same passive_deletes reasoning as OmniChannelAccount.conversations above
    # - customer_id is also NOT NULL with ondelete="CASCADE" at the DB level;
    # without this, deleting a customer with any conversation would hit the
    # identical bug.
    conversations: Mapped[List["OmniConversation"]] = relationship("OmniConversation", back_populates="customer", passive_deletes=True)


class OmniCustomerIdentity(Base):
    """A customer's identity on one specific channel (e.g. WhatsApp +39..., Telegram chat id)."""
    __tablename__ = "omni_customer_identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_customers.id", ondelete="CASCADE"), nullable=False)

    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    customer: Mapped[OmniCustomer] = relationship("OmniCustomer", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("owner_id", "channel", "external_user_id", name="uq_omni_identity_owner_channel_external"),
    )


# ==============================================================================
# Conversations & messages
# ==============================================================================
class OmniConversation(Base):
    __tablename__ = "omni_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_channel_accounts.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_customers.id", ondelete="CASCADE"), nullable=False)

    # NEW, OPEN, AI_PROCESSING, WAITING_APPROVAL, WAITING_CUSTOMER, RESOLVED, ARCHIVED, SPAM
    status: Mapped[str] = mapped_column(String(50), default="NEW", nullable=False)
    assigned_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    channel_account: Mapped[OmniChannelAccount] = relationship("OmniChannelAccount", back_populates="conversations")
    customer: Mapped[OmniCustomer] = relationship("OmniCustomer", back_populates="conversations")
    messages: Mapped[List["OmniMessage"]] = relationship("OmniMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="OmniMessage.created_at")
    drafts: Mapped[List["OmniAIDraft"]] = relationship("OmniAIDraft", back_populates="conversation", cascade="all, delete-orphan")
    notes: Mapped[List["OmniInternalNote"]] = relationship("OmniInternalNote", back_populates="conversation", cascade="all, delete-orphan")
    tags: Mapped[List["OmniTag"]] = relationship("OmniTag", secondary="omni_conversation_tags", back_populates="conversations")


class OmniMessage(Base):
    __tablename__ = "omni_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_conversations.id", ondelete="CASCADE"), nullable=False)
    # Denormalized from the conversation so (channel_account_id, external_message_id)
    # can carry the webhook idempotency uniqueness constraint directly.
    channel_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_channel_accounts.id", ondelete="CASCADE"), nullable=False)

    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # inbound, outbound
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # customer, operator, ai
    external_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_type: Mapped[str] = mapped_column(String(20), default="TEXT", nullable=False)  # TEXT, IMAGE, VIDEO, AUDIO, VOICE, DOCUMENT, LOCATION, CONTACT, OTHER
    attachments_json: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column("attachments", JSONB, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)  # received, pending, sent, failed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversation: Mapped[OmniConversation] = relationship("OmniConversation", back_populates="messages")

    __table_args__ = (
        UniqueConstraint("channel_account_id", "external_message_id", name="uq_omni_message_channel_external"),
    )


# ==============================================================================
# AI draft replies - PENDING_APPROVAL until a human approves/edits/sends them.
# The AI is never allowed to send directly (see omnichannel_draft_service.py).
# ==============================================================================
class OmniAIDraft(Base):
    __tablename__ = "omni_ai_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_conversations.id", ondelete="CASCADE"), nullable=False)
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_messages.id", ondelete="SET NULL"), nullable=True)

    original_ai_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Never overwrites original_ai_text - kept side by side so operator edits
    # can later be mined as a feedback signal for prompt/KB improvements.
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # GENERATING, PENDING_APPROVAL, EDITED, APPROVED, SENDING, SENT, REJECTED, FAILED, HUMAN_REVIEW_REQUIRED
    status: Mapped[str] = mapped_column(String(30), default="GENERATING", nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Set when a safety-sensitive topic (refund, legal, medical...) was detected -
    # see AI_AGENT_CONFIG.sensitive_categories_json and integrations/omnichannel/ai.py
    sensitive_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped[OmniConversation] = relationship("OmniConversation", back_populates="drafts")


# ==============================================================================
# Per-owner AI Agent configuration - system prompt, tone, guardrails.
# One row per owner (administrator) for the MVP - a single agent per account.
# ==============================================================================
class OmniAIAgentConfig(Base):
    __tablename__ = "omni_ai_agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    name: Mapped[str] = mapped_column(String(255), default="Assistente AI", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    tone: Mapped[str] = mapped_column(String(50), default="professionale", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    company_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_topics_json: Mapped[Optional[List[str]]] = mapped_column("allowed_topics", JSONB, nullable=True)
    forbidden_topics_json: Mapped[Optional[List[str]]] = mapped_column("forbidden_topics", JSONB, nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    max_context_messages: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    knowledge_base_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automatic_language_detection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Orthogonal to response_mode below - this controls WHEN a draft gets
    # generated, response_mode controls what happens to it once it exists.
    # True (default, current/original behavior): every inbound message
    # immediately enqueues generate_ai_draft_task. False: no draft is
    # generated automatically (saves an OpenAI call on every single inbound
    # message when the operator doesn't always want to use AI) - the
    # operator triggers it on demand from the chat
    # (POST /conversations/{id}/generate-draft), and from that point on the
    # exact same downstream logic applies (approval, or auto-send if
    # response_mode=AUTO_REPLY) - there is no second/different code path,
    # see omnichannel_draft_service.py::generate_draft_for_message, called
    # identically either way.
    auto_generate_draft: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # MANUAL, APPROVAL_REQUIRED, AUTO_REPLY. Defaults to APPROVAL_REQUIRED for
    # every new owner (never opted-in silently) - toggled explicitly from the
    # AI Agent settings page. AUTO_REPLY still never applies to a
    # HUMAN_REVIEW_REQUIRED (sensitive-topic) draft, see
    # omnichannel_draft_service.py module docstring.
    response_mode: Mapped[str] = mapped_column(String(30), default="APPROVAL_REQUIRED", nullable=False)
    # Topics that always force HUMAN_REVIEW_REQUIRED instead of a ready-to-send
    # draft (refund, legal, medical, complaint...) - see integrations/omnichannel/ai.py
    sensitive_categories_json: Mapped[Optional[List[str]]] = mapped_column("sensitive_categories", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


# ==============================================================================
# Knowledge base - lightweight RAG. MVP retrieval is keyword-based (ILIKE) over
# omni_knowledge_chunks; the schema is shaped so a real embedding column/vector
# index (pgvector) can be added later purely additively (see integrations/
# omnichannel/ai.py docstring) without touching this table's meaning.
# ==============================================================================
class OmniKnowledgeDocument(Base):
    __tablename__ = "omni_knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual, faq, url, pdf, docx, txt
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)  # processing, ready, failed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    chunks: Mapped[List["OmniKnowledgeChunk"]] = relationship("OmniKnowledgeChunk", back_populates="document", cascade="all, delete-orphan")


class OmniKnowledgeChunk(Base):
    __tablename__ = "omni_knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_knowledge_documents.id", ondelete="CASCADE"), nullable=False)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    document: Mapped[OmniKnowledgeDocument] = relationship("OmniKnowledgeDocument", back_populates="chunks")


# ==============================================================================
# Tags
# ==============================================================================
class OmniTag(Base):
    __tablename__ = "omni_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversations: Mapped[List[OmniConversation]] = relationship("OmniConversation", secondary="omni_conversation_tags", back_populates="tags")

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_omni_tag_owner_name"),
    )


# Many-to-many association - still carries owner_id directly per this
# module's rule that every table (including join tables) filters by owner_id
# on its own, without requiring a join through conversations/tags.
#
# owner_id is NOT NULL but SQLAlchemy's automatic secondary-table sync (via
# OmniConversation.tags / OmniTag.conversations) only ever writes the two
# association columns on INSERT - it has no way to know an extra column's
# value. Adding a tag to a conversation MUST go through an explicit
# `insert(omni_conversation_tags).values(owner_id=..., ...)` (see
# api/v1/omnichannel.py::add_conversation_tag), never `conversation.tags.append()`.
# Removing one is fine either way since DELETE doesn't need owner_id.
omni_conversation_tags = Table(
    "omni_conversation_tags",
    Base.metadata,
    Column("owner_id", UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False),
    Column("conversation_id", UUID(as_uuid=True), ForeignKey("omni_conversations.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("omni_tags.id", ondelete="CASCADE"), primary_key=True),
)


# ==============================================================================
# Internal notes - operator-only, never sent to the customer (see UI: rendered
# with a distinct visual style, see components/omnichannel/chat-panel.tsx)
# ==============================================================================
class OmniInternalNote(Base):
    __tablename__ = "omni_internal_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_conversations.id", ondelete="CASCADE"), nullable=False)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[Optional[List[str]]] = mapped_column("mentions", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversation: Mapped[OmniConversation] = relationship("OmniConversation", back_populates="notes")


# ==============================================================================
# Audit log - separate from the platform's existing audit_logs table on
# purpose (this module never writes to that one), same shape/spirit though.
# ==============================================================================
class OmniAuditLog(Base):
    __tablename__ = "omni_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)  # AI_GENERATED, AI_EDITED, AI_APPROVED, MESSAGE_SENT, MESSAGE_FAILED, ASSIGNMENT_CHANGED, CUSTOMER_UPDATED, SETTINGS_CHANGED...
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ==============================================================================
# In-app notifications, polled by the frontend (see hooks/use-omnichannel.ts).
# admin_id nullable = broadcast to every administrator of this owner.
# ==============================================================================
class OmniNotification(Base):
    __tablename__ = "omni_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=True)

    type: Mapped[str] = mapped_column(String(50), nullable=False)  # new_message, ai_ready, mention, conversation_assigned, send_error...
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ==============================================================================
# AI cost tracking - foundation for future billing/usage limits (section 69/46
# of the product spec), not wired to any limit enforcement yet.
# ==============================================================================
class OmniAIUsage(Base):
    __tablename__ = "omni_ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("omni_conversations.id", ondelete="SET NULL"), nullable=True)

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
