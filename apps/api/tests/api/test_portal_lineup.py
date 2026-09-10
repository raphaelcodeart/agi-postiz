"""
What a signed-in promoter sees on their line-up page.

Exercised over HTTP because the scoping is the feature: the page must show every
open campaign (including ones the user was not put in - that is what lets them
join) while never leaking another promoter's channels or decisions.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign
from app.models.publication import Publication
from app.models.user import User
from app.services import campaign_participation as participation


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture()
def promoters(db):
    def make(nome, email, platforms):
        user = User(name=nome, email=email, status="active", password_hash="x")
        db.add(user)
        db.flush()
        connection = BufferConnection(
            user_id=user.id, provider="bundle_social", status="connected",
            provider_account_ref=f"team_{nome}",
        )
        db.add(connection)
        db.flush()
        org = BufferOrganization(
            buffer_connection_id=connection.id, external_organization_id=f"org_{nome}", name=nome
        )
        db.add(org)
        db.flush()
        channels = []
        for platform in platforms:
            channel = SocialChannel(
                buffer_organization_id=org.id,
                external_channel_id=f"ext_{uuid.uuid4().hex[:8]}",
                provider="bundle_social", platform=platform,
                name=f"{nome} {platform}", is_active=True,
            )
            db.add(channel)
            channels.append(channel)
        db.flush()
        return user, connection, channels

    anna = make("Anna", "anna@example.test", ["instagram", "tiktok"])
    bruno = make("Bruno", "bruno@example.test", ["instagram"])
    db.commit()
    return {"anna": anna, "bruno": bruno}


def _announce_to_everyone(db, title="Campagna aperta"):
    """Announce with the targeting an administrator reaches for most often."""
    from app.services.campaign_resolver import CampaignResolver

    campaign = Campaign(
        title=title, default_text="Testo della campagna",
        targeting_mode="all_active_channels",
        participation_mode=participation.MODE_OPT_OUT,
        status="draft",
    )
    db.add(campaign)
    db.commit()
    channels = CampaignResolver.resolve_targets(db, campaign, {})
    participation.announce(db, campaign, channels)
    return campaign


def test_all_active_channels_puts_every_promoter_in_their_own_line_up(
    db, client, portal_token, promoters
):
    """
    The report that prompted this test: "with all users selected, nobody sees it".
    Each promoter must find the campaign already showing them as taking part,
    with their own channels and nobody else's.
    """
    campaign = _announce_to_everyone(db)

    for key, expected_channels in [("anna", 2), ("bruno", 1)]:
        user = promoters[key][0]
        response = client.get("/api/v1/portal/lineup", headers=portal_token(user))
        assert response.status_code == 200

        rows = response.json()
        mine = [row for row in rows if row["id"] == str(campaign.id)]
        assert mine, f"{key} non vede la campagna"
        assert mine[0]["included_count"] == expected_channels
        assert len(mine[0]["channels"]) == expected_channels
        assert mine[0]["phase"] == "open"


def test_the_line_up_never_shows_another_promoters_channels(db, client, portal_token, promoters):
    campaign = _announce_to_everyone(db)
    anna_channel_names = {c.name for c in promoters["anna"][2]}

    rows = client.get("/api/v1/portal/lineup", headers=portal_token(promoters["bruno"][0])).json()
    row = next(r for r in rows if r["id"] == str(campaign.id))

    assert not ({c["name"] for c in row["channels"]} & anna_channel_names)


def test_a_launched_campaign_stays_visible_as_history(db, client, portal_token, promoters):
    """
    A promoter asking "which campaigns am I in" means past ones too. Those often
    have no participant rows at all - anything published before the line-up
    existed went straight from targeting to publication - so the record is read
    from their own publications instead.
    """
    user, connection, channels = promoters["anna"]
    campaign = Campaign(
        title="Campagna gia' uscita", default_text="Testo",
        targeting_mode="all_active_channels", status="completed",
        participation_mode="automatic", started_at=_now() - timedelta(days=3),
    )
    db.add(campaign)
    db.flush()

    from app.models.campaign import CampaignTarget

    target = CampaignTarget(
        campaign_id=campaign.id, user_id=user.id,
        social_channel_id=channels[0].id, resolved_text="Testo", status="created",
    )
    db.add(target)
    db.flush()
    db.add(
        Publication(
            campaign_id=campaign.id, campaign_target_id=target.id, user_id=user.id,
            social_channel_id=channels[0].id, buffer_connection_id=connection.id,
            external_channel_id=channels[0].external_channel_id,
            status="published", idempotency_key=f"{campaign.id}:{channels[0].id}",
        )
    )
    db.commit()

    rows = client.get("/api/v1/portal/lineup", headers=portal_token(user)).json()
    row = next((r for r in rows if r["id"] == str(campaign.id)), None)

    assert row is not None, "una campagna gia' uscita deve restare nello storico del palinsesto"
    assert row["phase"] == "launched"
    published = [c for c in row["channels"] if c["published"]]
    assert len(published) == 1
    assert published[0]["name"] == channels[0].name


def test_history_is_not_shown_to_someone_who_was_not_in_it(db, client, portal_token, promoters):
    user, connection, channels = promoters["anna"]
    campaign = Campaign(
        title="Non mia", default_text="Testo", targeting_mode="all_active_channels",
        status="completed", participation_mode="automatic",
    )
    db.add(campaign)
    db.flush()

    from app.models.campaign import CampaignTarget

    target = CampaignTarget(
        campaign_id=campaign.id, user_id=user.id,
        social_channel_id=channels[0].id, resolved_text="t", status="created",
    )
    db.add(target)
    db.flush()
    db.add(
        Publication(
            campaign_id=campaign.id, campaign_target_id=target.id, user_id=user.id,
            social_channel_id=channels[0].id, buffer_connection_id=connection.id,
            external_channel_id=channels[0].external_channel_id,
            status="published", idempotency_key=f"{campaign.id}:{channels[0].id}",
        )
    )
    db.commit()

    rows = client.get("/api/v1/portal/lineup", headers=portal_token(promoters["bruno"][0])).json()
    assert all(r["id"] != str(campaign.id) for r in rows)


def test_a_draft_campaign_is_invisible_to_everyone(db, client, portal_token, promoters):
    """Until it is announced it is somebody's private draft."""
    db.add(Campaign(title="Bozza", default_text="t", status="draft",
                    participation_mode=participation.MODE_OPT_OUT))
    db.commit()

    rows = client.get("/api/v1/portal/lineup", headers=portal_token(promoters["anna"][0])).json()
    assert rows == []
