import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlatformSettings(Base):
    """
    Singleton row holding admin-configurable texts that must be changeable
    without a deploy.

    Same pattern as AISettings: exactly one row, or none before first
    configuration, in which case the defaults below apply.

    The disclosure wording lives here rather than in the code because the exact
    formulation is a legal decision, not a technical one - an administrator (or
    their lawyer) settles it once and it applies to every campaign from then on,
    with no code change and no campaign to re-edit.
    """

    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Full wording, used where there is room for it.
    affiliate_disclosure_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Short form for platforms with a tight character budget - X allows 280, and
    # a long sentence there eats a fifth of the post.
    affiliate_disclosure_text_short: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


# Applied when no row exists yet, so the feature works out of the box. Explicit
# sentence rather than a bare hashtag: a "#adv" buried at the end of fifteen
# other tags is exactly what regulators call insufficient, because the reader
# has to hunt for it.
DEFAULT_AFFILIATE_DISCLOSURE = "Link affiliato: se acquisti ricevo una commissione. #adv"
DEFAULT_AFFILIATE_DISCLOSURE_SHORT = "#adv #affiliazione"
