"""
When a portal account becomes eligible for campaigns.

"Active" is the flag CampaignResolver targets on, so it decides whether someone
is reachable by a campaign at all. It used to be set by hand, once per user, by
an administrator - and the cost of forgetting was invisible from both sides: the
promoter saw a working dashboard with no campaigns in it, and the administrator's
campaign simply resolved fewer channels than expected, with nothing anywhere
saying why.

The gate existed for a real reason - anyone who could reach the public
registration form would otherwise have inserted themselves into the next
campaign - but that reason is now covered better elsewhere. Campaigns can be
announced before they are sent (Campaign.participation_mode="opt_out"), so a
promoter's presence in one is visible and refusable, and an administrator can
suspend an account at any time. What is left is a manual step with no
corresponding decision, which is what this module removes.

Two paths lead here:

  registration      honours PlatformSettings.auto_activate_new_users (on by
                    default, switchable for a closed programme).
  first connection  a user who has connected a real social channel has done
                    something no drive-by signup does. That activates them even
                    with the setting off, because the setting guards against
                    unvetted signups and this is evidence against being one.

Suspension is never touched. "suspended" is a decision somebody made about a
specific account; only "inactive" - the waiting-room state - is resolved here.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.platform_settings import PlatformSettings
from app.models.user import User

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"


def auto_activation_enabled(db: Session) -> bool:
    """
    Whether a newly registered account starts active.

    Defaults to True when no settings row exists yet, matching the column
    default, so the behaviour is the same before and after an administrator
    first opens the settings page.
    """
    row = db.query(PlatformSettings).first()
    if row is None:
        return True
    return bool(row.auto_activate_new_users)


def status_for_new_registration(db: Session) -> str:
    return STATUS_ACTIVE if auto_activation_enabled(db) else STATUS_INACTIVE


def activate_on_channel_connection(db: Session, user: User) -> bool:
    """
    Activate a user who has just connected their first channel.

    Returns True when it changed something, so the caller can tell the user their
    account went live rather than leaving them to notice.

    Deliberately unconditional on the settings flag: connecting a channel means
    completing an OAuth flow against a real social account, which is a far
    stronger signal than the flag is guarding against. An operator who genuinely
    wants every promoter vetted still has "suspended", which this never touches.
    """
    if user.status != STATUS_INACTIVE:
        return False

    user.status = STATUS_ACTIVE
    db.add(
        AuditLog(
            administrator_id=None,
            action="user_auto_activate",
            entity_type="user",
            entity_id=user.id,
            metadata_json={"trigger": "channel_connected", "email": user.email},
        )
    )
    db.commit()
    logger.info("User %s activated automatically after connecting a channel", user.id)
    return True
