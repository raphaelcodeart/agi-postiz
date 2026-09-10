"""
The announced line-up: who is in a campaign, and their right to leave it.

What makes these rules worth pinning is that they gate an irreversible step.
Launching hands the provider every post with its date; after that, a promoter
saying "not this one" is something we can no longer honour. Every test here is
about the window before that moment - and about the two ways it can be got
wrong: publishing to someone who withdrew, or dropping someone who did not.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign, CampaignParticipant
from app.models.user import User
from app.services import campaign_participation as participation


def _now():
    return datetime.now(timezone.utc)


# --- pure window rules (no database) ---------------------------------------

def _campaign(**kwargs) -> Campaign:
    defaults = {
        "status": participation.OPEN_STATUS,
        "participation_mode": participation.MODE_OPT_OUT,
        "auto_launch_at_deadline": False,
        "opt_out_deadline_at": None,
    }
    defaults.update(kwargs)
    return Campaign(title="c", default_text="t", **defaults)


def test_window_with_no_deadline_stays_open():
    """
    "No deadline" means the window runs until launch. Treating a missing value
    as "already closed" would silently strip the opt-out from every campaign an
    administrator did not set a date on.
    """
    assert participation.is_window_open(_campaign()) is True


def test_window_closes_after_the_deadline():
    past = _campaign(opt_out_deadline_at=_now() - timedelta(minutes=1))
    assert participation.is_window_open(past) is False


def test_window_is_open_before_the_deadline():
    future = _campaign(opt_out_deadline_at=_now() + timedelta(days=1))
    assert participation.is_window_open(future) is True


def test_a_launched_campaign_has_no_window():
    """Whatever the deadline says: the posts are already at the provider."""
    launched = _campaign(status="queued", opt_out_deadline_at=_now() + timedelta(days=5))
    assert participation.is_window_open(launched) is False


def test_naive_deadlines_do_not_crash_the_beat_task():
    """
    This runs inside the poll that launches every campaign. A TypeError from
    comparing a naive datetime to an aware one would stop all of them, not just
    the campaign with the odd timestamp.
    """
    naive = _campaign(opt_out_deadline_at=datetime.now() + timedelta(days=1))
    assert participation.is_window_open(naive) is True


# --- auto-launch ------------------------------------------------------------

def test_auto_launch_only_when_the_flag_is_on():
    """
    The deadline and the launch are two separate decisions: a campaign can close
    its window and still wait for an administrator. Firing without the flag would
    publish campaigns nobody released.
    """
    due = _campaign(opt_out_deadline_at=_now() - timedelta(minutes=1))
    assert participation.is_due_for_auto_launch(due) is False

    due.auto_launch_at_deadline = True
    assert participation.is_due_for_auto_launch(due) is True


def test_auto_launch_waits_for_the_deadline():
    pending = _campaign(
        auto_launch_at_deadline=True, opt_out_deadline_at=_now() + timedelta(hours=2)
    )
    assert participation.is_due_for_auto_launch(pending) is False


def test_auto_launch_needs_a_deadline_to_fire_on():
    no_date = _campaign(auto_launch_at_deadline=True)
    assert participation.is_due_for_auto_launch(no_date) is False


# --- line-up over a real database ------------------------------------------

@pytest.fixture()
def world(db):
    """Two promoters, three channels, one campaign ready to be announced."""
    def make_user(name, email):
        user = User(name=name, email=email, status="active")
        db.add(user)
        db.flush()
        connection = BufferConnection(
            user_id=user.id, provider="bundle_social", status="connected",
            provider_account_ref=f"team_{name}",
        )
        db.add(connection)
        db.flush()
        org = BufferOrganization(
            buffer_connection_id=connection.id, external_organization_id=f"org_{name}", name=name
        )
        db.add(org)
        db.flush()
        return user, org

    def make_channel(org, platform, name):
        channel = SocialChannel(
            buffer_organization_id=org.id,
            external_channel_id=f"ext_{name}",
            provider="bundle_social",
            platform=platform,
            name=name,
            is_active=True,
        )
        db.add(channel)
        db.flush()
        return channel

    anna, anna_org = make_user("Anna", "anna@example.test")
    bruno, bruno_org = make_user("Bruno", "bruno@example.test")

    anna_ig = make_channel(anna_org, "instagram", "anna_ig")
    anna_tt = make_channel(anna_org, "tiktok", "anna_tt")
    bruno_ig = make_channel(bruno_org, "instagram", "bruno_ig")

    campaign = Campaign(
        title="Lancio autunno",
        default_text="Testo della campagna",
        participation_mode=participation.MODE_OPT_OUT,
        status="draft",
    )
    db.add(campaign)
    db.commit()

    return {
        "campaign": campaign,
        "anna": anna, "bruno": bruno,
        "anna_ig": anna_ig, "anna_tt": anna_tt, "bruno_ig": bruno_ig,
    }


def test_announce_creates_one_participant_per_channel(db, world):
    participation.announce(db, world["campaign"], [world["anna_ig"], world["bruno_ig"]])

    assert world["campaign"].status == participation.OPEN_STATUS
    assert world["campaign"].announced_at is not None
    assert set(participation.included_channel_ids(db, world["campaign"].id)) == {
        world["anna_ig"].id, world["bruno_ig"].id
    }


def test_re_announcing_never_undoes_a_withdrawal(db, world):
    """
    The one behaviour this feature must not have. An administrator pressing
    "metti in palinsesto" a second time - to pick up newly connected channels -
    must not quietly put back everyone who had already said no.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"], world["bruno_ig"]])
    participation.withdraw(db, campaign, user_id=world["anna"].id)

    participation.announce(db, campaign, [world["anna_ig"], world["bruno_ig"], world["anna_tt"]])

    remaining = set(participation.included_channel_ids(db, campaign.id))
    assert world["anna_ig"].id not in remaining, "una rinuncia e stata annullata"
    assert remaining == {world["bruno_ig"].id, world["anna_tt"].id}


def test_withdrawing_only_touches_your_own_channels(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"], world["anna_tt"], world["bruno_ig"]])

    participation.withdraw(db, campaign, user_id=world["anna"].id)

    assert participation.included_channel_ids(db, campaign.id) == [world["bruno_ig"].id]


def test_withdrawing_a_named_channel_leaves_the_others_in(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"], world["anna_tt"]])

    participation.withdraw(
        db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id]
    )

    assert participation.included_channel_ids(db, campaign.id) == [world["anna_tt"].id]


def test_a_withdrawal_keeps_its_row_for_the_history(db, world):
    """
    The record of "I was offered this and declined" lives nowhere else -
    campaign_targets correctly has no row for a channel that never published.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    participation.withdraw(db, campaign, user_id=world["anna"].id, reason="Non in linea")

    row = db.query(CampaignParticipant).filter(
        CampaignParticipant.campaign_id == campaign.id
    ).one()
    assert row.status == CampaignParticipant.STATUS_WITHDRAWN
    assert row.decided_reason == "Non in linea"
    assert row.decided_at is not None


def test_withdrawing_after_the_deadline_is_refused(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    campaign.opt_out_deadline_at = _now() - timedelta(minutes=1)
    db.commit()

    with pytest.raises(participation.ParticipationError) as excinfo:
        participation.withdraw(db, campaign, user_id=world["anna"].id)
    assert "scaduto" in str(excinfo.value)

    assert participation.included_channel_ids(db, campaign.id) == [world["anna_ig"].id]


def test_withdrawing_from_a_launched_campaign_is_refused(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    campaign.status = "running"
    db.commit()

    with pytest.raises(participation.ParticipationError):
        participation.withdraw(db, campaign, user_id=world["anna"].id)


def test_an_administrator_can_remove_after_the_window_closed(db, world):
    """
    The deadline binds participants, not the administrator running the campaign.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    campaign.opt_out_deadline_at = _now() - timedelta(hours=1)
    db.commit()

    removed = participation.withdraw(
        db, campaign, user_id=world["anna"].id, by_admin=True, reason="fuori target"
    )

    assert removed == 1
    row = db.query(CampaignParticipant).one()
    assert row.status == CampaignParticipant.STATUS_REMOVED


# --- joining ----------------------------------------------------------------

def test_a_user_can_join_a_campaign_they_were_not_put_in(db, world):
    """
    The whole point of showing every open campaign in the portal: someone left
    out of one they wanted can add themselves, instead of the administrator
    having to notice and do it by hand.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["bruno_ig"]])

    added, warnings = participation.join(
        db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id]
    )

    assert (added, warnings) == (1, [])
    row = db.query(CampaignParticipant).filter(
        CampaignParticipant.social_channel_id == world["anna_ig"].id
    ).one()
    assert row.added_by == CampaignParticipant.SOURCE_USER
    assert row.status == CampaignParticipant.STATUS_INCLUDED


def test_joining_twice_does_not_duplicate_the_line_up(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [])
    participation.join(db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id])
    participation.join(db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id])

    assert db.query(CampaignParticipant).count() == 1


def test_a_user_can_change_their_mind_back(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    participation.withdraw(db, campaign, user_id=world["anna"].id)

    added, _ = participation.join(
        db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id]
    )

    assert added == 1
    assert participation.included_channel_ids(db, campaign.id) == [world["anna_ig"].id]


def test_a_channel_an_administrator_removed_cannot_be_put_back(db, world):
    """
    Otherwise the removal is unenforceable: the owner clicks "partecipa" and
    undoes it.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"]])
    participation.withdraw(db, campaign, user_id=world["anna"].id, by_admin=True)

    added, warnings = participation.join(
        db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id]
    )

    assert added == 0
    assert warnings and "amministratore" in warnings[0]
    assert participation.included_channel_ids(db, campaign.id) == []


def test_joining_someone_elses_channel_does_nothing(db, world):
    """
    The channel id is attacker-supplied; ownership is re-derived from the token's
    user, never trusted from the request.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [])

    added, warnings = participation.join(
        db, campaign, user_id=world["anna"].id, channel_ids=[world["bruno_ig"].id]
    )

    assert added == 0
    assert warnings
    assert db.query(CampaignParticipant).count() == 0


def test_joining_a_launched_campaign_is_refused(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [])
    campaign.status = "completed"
    db.commit()

    with pytest.raises(participation.ParticipationError):
        participation.join(db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_ig"].id])


# --- what a launch actually resolves to -------------------------------------

def test_launch_resolves_the_line_up_not_the_targeting(db, world):
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"], world["bruno_ig"]])
    participation.withdraw(db, campaign, user_id=world["bruno"].id)

    channels = participation.resolve_lineup_channels(db, campaign)

    assert [c.id for c in channels] == [world["anna_ig"].id]


def test_a_channel_disconnected_during_the_window_is_not_published_to(db, world):
    """
    The line-up is fixed days before launch and the world moves. A channel the
    owner removed in the meantime keeps its participant row - the history stays -
    but must get no target.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [world["anna_ig"], world["anna_tt"]])

    world["anna_tt"].deleted_at = _now()
    db.commit()

    channels = participation.resolve_lineup_channels(db, campaign)

    assert [c.id for c in channels] == [world["anna_ig"].id]
    assert db.query(CampaignParticipant).count() == 2, "la storia non deve sparire"


def test_a_self_joined_channel_is_published_to(db, world):
    """
    A volunteer's channel need not match the campaign's targeting at all -
    intersecting the line-up with a fresh resolve would drop exactly the people
    who put themselves forward.
    """
    campaign = world["campaign"]
    participation.announce(db, campaign, [])
    participation.join(db, campaign, user_id=world["anna"].id, channel_ids=[world["anna_tt"].id])

    channels = participation.resolve_lineup_channels(db, campaign)

    assert [c.id for c in channels] == [world["anna_tt"].id]


# --- the beat task must not bypass the window ------------------------------

def test_an_unannounced_opt_out_campaign_is_not_picked_up_by_the_scheduler(db, world):
    """
    The failure this guards against is silent and total: a campaign created with
    participation_mode="opt_out" but never announced - the wizard failing between
    the create and the announce is enough - sitting in "draft" with a publishing
    date. The scheduled-campaign branch of poll_and_queue_scheduled_publications
    would have launched it to every resolved channel the moment that date
    arrived, with no line-up and nobody able to withdraw.
    """
    from app.models.campaign import Campaign

    campaign = world["campaign"]
    campaign.status = "draft"
    campaign.publishing_mode = "scheduled"
    campaign.scheduled_at = _now() - timedelta(minutes=5)
    db.commit()

    # The exact filter the task runs.
    picked_up = (
        db.query(Campaign)
        .filter(
            Campaign.status == "draft",
            Campaign.publishing_mode == "scheduled",
            Campaign.participation_mode != "opt_out",
            Campaign.scheduled_at <= _now(),
        )
        .all()
    )

    assert campaign.id not in [c.id for c in picked_up]


def test_an_ordinary_scheduled_campaign_is_still_picked_up(db, world):
    """The exclusion above must not disable the normal scheduled path."""
    from app.models.campaign import Campaign

    campaign = world["campaign"]
    campaign.status = "draft"
    campaign.participation_mode = participation.MODE_AUTOMATIC
    campaign.publishing_mode = "scheduled"
    campaign.scheduled_at = _now() - timedelta(minutes=5)
    db.commit()

    picked_up = (
        db.query(Campaign)
        .filter(
            Campaign.status == "draft",
            Campaign.publishing_mode == "scheduled",
            Campaign.participation_mode != "opt_out",
            Campaign.scheduled_at <= _now(),
        )
        .all()
    )

    assert campaign.id in [c.id for c in picked_up]
