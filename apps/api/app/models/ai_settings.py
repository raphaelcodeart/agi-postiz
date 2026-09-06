import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AISettings(Base):
    """
    Singleton row (always exactly one, or zero before first configuration)
    holding the admin-configurable OpenAI credentials used by the campaign
    wizard's "Genera con AI" text helper. Configured from the Settings page,
    not the .env file - each deployment's admin brings their own OpenAI key
    instead of sharing a platform-wide one.
    """
    __tablename__ = "ai_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    openai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    openai_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
