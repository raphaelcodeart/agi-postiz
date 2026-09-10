import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
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

    # Whether an account that registers on the portal becomes campaign-eligible
    # straight away, instead of waiting for an administrator to flip it.
    #
    # It defaults to ON, which reverses the original decision, because the reason
    # for that decision is gone. Self-registration used to be the only gate: an
    # active user was silently in the next campaign, so anyone who could reach
    # the registration form could insert themselves into one. Campaigns can now
    # be announced first (Campaign.participation_mode="opt_out"), which puts a
    # visible line-up and a withdrawal window in front of publishing - and an
    # administrator can still suspend an account at any time.
    #
    # What that gate cost in the meantime was not theoretical: every new promoter
    # connected their channels, saw an empty dashboard, and stayed invisible to
    # campaign targeting until somebody remembered to go and activate them. The
    # failure was silent on both sides - the user saw nothing wrong, and the
    # administrator's campaign just resolved fewer channels than expected.
    #
    # Left switchable rather than hardcoded: an operator running a closed
    # programme, where every promoter is vetted before joining, turns it off and
    # gets the old behaviour back with no deploy.
    auto_activate_new_users: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


# Applied when no row exists yet, so the feature works out of the box. Explicit
# sentence rather than a bare hashtag: a "#adv" buried at the end of fifteen
# other tags is exactly what regulators call insufficient, because the reader
# has to hunt for it.
DEFAULT_AFFILIATE_DISCLOSURE = "Link affiliato: se acquisti ricevo una commissione. #adv"
DEFAULT_AFFILIATE_DISCLOSURE_SHORT = "#adv #affiliazione"
