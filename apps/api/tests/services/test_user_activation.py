"""
When a portal account becomes eligible for campaigns.

The flag decides whether CampaignResolver can see a user at all, so getting it
wrong is silent in both directions: too strict and a promoter sits invisible
with a working dashboard, too loose and someone is published on behalf of the
platform without having asked to be.
"""
from datetime import datetime, timezone

from app.models.audit import AuditLog
from app.models.platform_settings import PlatformSettings
from app.models.user import User
from app.services import user_activation


def _user(db, status="inactive", email="u@example.test") -> User:
    user = User(
        name="Utente",
        email=email,
        status=status,
        self_registered_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


# --- the setting ------------------------------------------------------------

def test_registration_is_active_by_default(db):
    """
    No settings row means the feature has never been configured, and the answer
    then has to match the column default - otherwise behaviour changes the first
    time an administrator opens the settings page and presses Save.
    """
    assert db.query(PlatformSettings).first() is None
    assert user_activation.status_for_new_registration(db) == "active"


def test_an_operator_can_restore_the_manual_gate(db):
    db.add(PlatformSettings(auto_activate_new_users=False))
    db.commit()
    assert user_activation.status_for_new_registration(db) == "inactive"


def test_the_gate_can_be_switched_back_on(db):
    db.add(PlatformSettings(auto_activate_new_users=True))
    db.commit()
    assert user_activation.status_for_new_registration(db) == "active"


# --- activation on connecting a channel -------------------------------------

def test_connecting_a_channel_activates_a_waiting_account(db):
    """
    The path that clears accounts stranded by the old policy: completing a real
    OAuth flow is evidence no drive-by signup produces.
    """
    user = _user(db, status="inactive")
    assert user_activation.activate_on_channel_connection(db, user) is True
    assert user.status == "active"


def test_activation_is_recorded(db):
    """
    An account going live without anyone pressing a button still has to be
    answerable for - AGENTS.md rule 6 in spirit: every state change traceable.
    """
    user = _user(db, status="inactive")
    user_activation.activate_on_channel_connection(db, user)

    entry = db.query(AuditLog).filter(AuditLog.entity_id == user.id).one()
    assert entry.action == "user_auto_activate"
    assert entry.metadata_json["trigger"] == "channel_connected"


def test_connecting_a_channel_never_revives_a_suspended_account(db):
    """
    The one case that must not be automated away: "suspended" is a decision
    somebody made about this specific account, and connecting a channel is not
    an appeal against it.
    """
    user = _user(db, status="suspended")
    assert user_activation.activate_on_channel_connection(db, user) is False
    assert user.status == "suspended"


def test_activating_an_already_active_account_changes_nothing(db):
    user = _user(db, status="active")
    assert user_activation.activate_on_channel_connection(db, user) is False
    assert db.query(AuditLog).count() == 0


def test_activation_ignores_the_setting(db):
    """
    Deliberate: the setting guards against unvetted signups, and someone who has
    just authorised a real social account is evidence against being one. An
    operator who wants a hard gate has "suspended", which this never touches.
    """
    db.add(PlatformSettings(auto_activate_new_users=False))
    db.commit()
    user = _user(db, status="inactive")

    assert user_activation.activate_on_channel_connection(db, user) is True
    assert user.status == "active"
