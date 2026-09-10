"""
The announced line-up: who is in a campaign, and their right to leave it.

The problem this solves is one of timing. Launching a campaign is the
irreversible step - a scheduled campaign hands the provider every post *with its
date* the moment it launches, so from then on a promoter saying "I would rather
not be in this one" is something we can no longer honour without deleting posts
from their real profile. Before this module, the only two states a campaign had
were "private draft" and "already sent", with nothing in between.

``Campaign.participation_mode="opt_out"`` adds the state in between:

    draft ──announce──> announced ──launch──> queued ──> ... ──> completed
                            │
                            └─ the window: participants see the campaign,
                               its text and its media, and can take their
                               channels out. Nothing has been sent.

Two rules shape everything here:

1. **The line-up is a snapshot.** It is resolved once, when the campaign is
   announced, and launch publishes to what the snapshot says - not to whatever
   targeting would resolve to on the day. A channel connected during the window
   is not swept in silently: it never had the chance to withdraw, and including
   it would break the promise the window makes. The owner can still add it
   themselves, which is a decision rather than an accident.

2. **Nothing is deleted.** Withdrawing flips a status. A promoter's history of
   which campaigns they were offered, and which they declined, is the record this
   table exists for - and it is invisible in ``campaign_targets``, where a
   refusal correctly leaves no row at all.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign, CampaignParticipant

# Statuses in which a campaign's line-up is published but nothing has gone out.
OPEN_STATUS = "announced"

# Modes.
MODE_AUTOMATIC = "automatic"
MODE_OPT_OUT = "opt_out"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """
    Naive datetimes read back from some drivers/tests compare as UTC.

    Comparing a naive value against an aware ``now()`` raises TypeError, and this
    runs inside the beat task that launches campaigns - a crash there would stop
    every campaign, not just the one with the odd timestamp.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_window_open(campaign: Campaign, now: Optional[datetime] = None) -> bool:
    """
    True while participants may still change their mind.

    A campaign with no deadline keeps its window open right up to launch: that
    is the honest reading of "no deadline set", and the administrator retains
    the Launch button either way.
    """
    if campaign.status != OPEN_STATUS:
        return False
    deadline = _aware(campaign.opt_out_deadline_at)
    if deadline is None:
        return True
    return (now or utc_now()) < deadline


def is_due_for_auto_launch(campaign: Campaign, now: Optional[datetime] = None) -> bool:
    """
    True when the deadline has passed on a campaign set to launch itself.

    ``auto_launch_at_deadline`` is what separates the two things a deadline can
    mean - "the window closes" from "the campaign goes out" - and an
    administrator picks between them per campaign.
    """
    if campaign.status != OPEN_STATUS or not campaign.auto_launch_at_deadline:
        return False
    deadline = _aware(campaign.opt_out_deadline_at)
    if deadline is None:
        return False
    return (now or utc_now()) >= deadline


def channel_owner_id(channel: SocialChannel) -> uuid.UUID:
    return channel.buffer_organization.buffer_connection.user_id


def announce(
    db: Session,
    campaign: Campaign,
    channels: Sequence[SocialChannel],
    admin_id: Optional[uuid.UUID] = None,
) -> List[CampaignParticipant]:
    """
    Publish the line-up: create a participant row per resolved channel and open
    the window.

    Re-announcing an already-announced campaign tops the line-up up rather than
    rebuilding it - a channel someone already withdrew is left withdrawn. Wiping
    their decision because an administrator pressed the button twice is the one
    behaviour this feature must never have.
    """
    existing = {
        participant.social_channel_id: participant
        for participant in db.query(CampaignParticipant)
        .filter(CampaignParticipant.campaign_id == campaign.id)
        .all()
    }

    created: List[CampaignParticipant] = []
    for channel in channels:
        if channel.id in existing:
            continue
        participant = CampaignParticipant(
            campaign_id=campaign.id,
            user_id=channel_owner_id(channel),
            social_channel_id=channel.id,
            status=CampaignParticipant.STATUS_INCLUDED,
            added_by=CampaignParticipant.SOURCE_ADMIN,
        )
        db.add(participant)
        created.append(participant)

    campaign.participation_mode = MODE_OPT_OUT
    campaign.status = OPEN_STATUS
    if campaign.announced_at is None:
        campaign.announced_at = utc_now()

    db.add(
        AuditLog(
            administrator_id=admin_id,
            action="campaign_announce",
            entity_type="campaign",
            entity_id=campaign.id,
            metadata_json={
                "participants_added": len(created),
                "participants_total": len(existing) + len(created),
                "opt_out_deadline_at": campaign.opt_out_deadline_at.isoformat()
                if campaign.opt_out_deadline_at
                else None,
                "auto_launch_at_deadline": campaign.auto_launch_at_deadline,
            },
        )
    )
    db.commit()
    return created


def included_channel_ids(db: Session, campaign_id: uuid.UUID) -> List[uuid.UUID]:
    """Channels still in the line-up, in no particular order."""
    return [
        row[0]
        for row in db.query(CampaignParticipant.social_channel_id)
        .filter(
            CampaignParticipant.campaign_id == campaign_id,
            CampaignParticipant.status == CampaignParticipant.STATUS_INCLUDED,
        )
        .all()
    ]


def participants_for_user(
    db: Session, campaign_id: uuid.UUID, user_id: uuid.UUID
) -> Dict[uuid.UUID, CampaignParticipant]:
    """This user's own rows in one campaign's line-up, keyed by channel."""
    rows = (
        db.query(CampaignParticipant)
        .filter(
            CampaignParticipant.campaign_id == campaign_id,
            CampaignParticipant.user_id == user_id,
        )
        .all()
    )
    return {row.social_channel_id: row for row in rows}


def eligible_channels_for_user(db: Session, user_id: uuid.UUID) -> List[SocialChannel]:
    """
    The channels a user could put into a campaign themselves.

    Mirrors the health filters in CampaignResolver.resolve_targets - an inactive,
    removed or disabled channel is not offered, because adding it would only
    produce a target that fails. Deliberately does NOT filter on User.status: a
    user reading their own line-up page is signed in, and telling them "you may
    not join" by silently showing an empty list explains nothing. The portal says
    it in words instead.
    """
    return (
        db.query(SocialChannel)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(
            BufferConnection.user_id == user_id,
            BufferConnection.status == "connected",
            SocialChannel.is_active.is_(True),
            SocialChannel.deleted_at.is_(None),
            SocialChannel.publication_mode != "disabled",
        )
        .order_by(SocialChannel.platform)
        .all()
    )


def resolve_lineup_channels(db: Session, campaign: Campaign) -> List[SocialChannel]:
    """
    The channels an announced campaign will actually publish to.

    This REPLACES targeting resolution at launch, rather than filtering it. A
    channel the owner added themselves need not match the campaign's targeting
    criteria at all - joining is a decision they made about this campaign, not a
    query result - so intersecting the two would silently drop exactly the people
    who volunteered.

    The health filters are still applied on top, because the line-up was fixed
    days earlier and the world moved: a channel disconnected, removed or switched
    off since the announcement must not be published to. It keeps its
    participant row (nothing here is deleted); it simply gets no target.
    """
    channel_ids = included_channel_ids(db, campaign.id)
    if not channel_ids:
        return []

    return (
        db.query(SocialChannel)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(
            SocialChannel.id.in_(channel_ids),
            BufferConnection.status == "connected",
            SocialChannel.is_active.is_(True),
            SocialChannel.deleted_at.is_(None),
            SocialChannel.publication_mode != "disabled",
        )
        .all()
    )


class ParticipationError(ValueError):
    """A participation change that cannot be honoured, with a reason to show."""


def _assert_window_open(campaign: Campaign) -> None:
    if campaign.participation_mode != MODE_OPT_OUT:
        raise ParticipationError(
            "Questa campagna non prevede l'adesione dei partecipanti."
        )
    if campaign.status != OPEN_STATUS:
        raise ParticipationError(
            "Questa campagna e gia stata avviata: i post sono gia stati inviati "
            "e non e piu possibile modificare la partecipazione."
        )
    if not is_window_open(campaign):
        raise ParticipationError(
            "Il termine per modificare la partecipazione a questa campagna e scaduto."
        )


def withdraw(
    db: Session,
    campaign: Campaign,
    user_id: uuid.UUID,
    channel_ids: Optional[Iterable[uuid.UUID]] = None,
    reason: Optional[str] = None,
    by_admin: bool = False,
    admin_id: Optional[uuid.UUID] = None,
) -> int:
    """
    Take channels out of the line-up. ``channel_ids=None`` means all of them.

    Only ever touches rows already belonging to ``user_id``: the caller passes a
    user id taken from the validated token, and the filter below is what stops a
    channel id from someone else's campaign being withdrawn by guessing it.
    """
    if not by_admin:
        _assert_window_open(campaign)

    query = db.query(CampaignParticipant).filter(
        CampaignParticipant.campaign_id == campaign.id,
        CampaignParticipant.user_id == user_id,
        CampaignParticipant.status == CampaignParticipant.STATUS_INCLUDED,
    )
    if channel_ids is not None:
        ids = list(channel_ids)
        if not ids:
            return 0
        query = query.filter(CampaignParticipant.social_channel_id.in_(ids))

    rows = query.all()
    now = utc_now()
    for row in rows:
        row.status = (
            CampaignParticipant.STATUS_REMOVED if by_admin else CampaignParticipant.STATUS_WITHDRAWN
        )
        row.decided_at = now
        row.decided_reason = (reason or None)

    if rows:
        db.add(
            AuditLog(
                administrator_id=admin_id,
                action="campaign_participation_withdraw",
                entity_type="campaign",
                entity_id=campaign.id,
                metadata_json={
                    "user_id": str(user_id),
                    "channels": len(rows),
                    "by_admin": by_admin,
                    "reason": reason,
                },
            )
        )
    db.commit()
    return len(rows)


def join(
    db: Session,
    campaign: Campaign,
    user_id: uuid.UUID,
    channel_ids: Sequence[uuid.UUID],
) -> Tuple[int, List[str]]:
    """
    Add this user's own channels to an open line-up, or put back ones they had
    withdrawn.

    Returns the number of channels now in, plus any messages about channels that
    could not be added - a channel that is no longer connected, say. Refusals are
    reported rather than raised: a user ticking four channels where one has gone
    stale should get the other three in, and be told about the fourth.
    """
    _assert_window_open(campaign)

    eligible = {channel.id: channel for channel in eligible_channels_for_user(db, user_id)}
    existing = participants_for_user(db, campaign.id, user_id)

    added = 0
    problems: List[str] = []

    for channel_id in channel_ids:
        channel = eligible.get(channel_id)
        if channel is None:
            problems.append(
                "Un canale selezionato non e piu disponibile: potrebbe essere "
                "stato scollegato o disattivato."
            )
            continue

        participant = existing.get(channel_id)
        if participant is not None:
            if participant.status == CampaignParticipant.STATUS_INCLUDED:
                continue
            if participant.status == CampaignParticipant.STATUS_REMOVED:
                # An administrator took this channel out. Letting the user put it
                # straight back would make that decision unenforceable.
                problems.append(
                    f"Il canale {channel.name} e stato escluso da questa campagna "
                    "da un amministratore e non puo essere reinserito."
                )
                continue
            participant.status = CampaignParticipant.STATUS_INCLUDED
            participant.decided_at = utc_now()
            participant.decided_reason = None
            added += 1
            continue

        db.add(
            CampaignParticipant(
                campaign_id=campaign.id,
                user_id=user_id,
                social_channel_id=channel_id,
                status=CampaignParticipant.STATUS_INCLUDED,
                added_by=CampaignParticipant.SOURCE_USER,
            )
        )
        added += 1

    if added:
        db.add(
            AuditLog(
                action="campaign_participation_join",
                entity_type="campaign",
                entity_id=campaign.id,
                metadata_json={"user_id": str(user_id), "channels": added},
            )
        )
    db.commit()
    return added, problems
