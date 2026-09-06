"""
Portal authentication boundaries.

These tests guard the two properties that, if they break, are not bugs but
security incidents: an administrator token must not authenticate a portal
request (nor the reverse), and a freshly registered account must not become
targetable by campaigns on its own.
"""
import pytest

from app.core.security import (
    TOKEN_TYPE_ADMIN,
    TOKEN_TYPE_PORTAL_USER,
    SecurityService,
)


# --- token audience separation ---------------------------------------------

def test_admin_token_is_rejected_by_the_portal_audience():
    """
    The central control of the whole portal.

    Both audiences carry a UUID in `sub`; without the `typ` claim the only thing
    stopping an admin token here would be that the lookup happens to hit a
    different table. That is an accident. This asserts it is a decision.
    """
    admin_token = SecurityService.create_access_token(
        subject="11111111-1111-1111-1111-111111111111",
        token_type=TOKEN_TYPE_ADMIN,
    )
    assert SecurityService.verify_access_token(admin_token, expected_type=TOKEN_TYPE_PORTAL_USER) is None


def test_portal_token_is_rejected_by_the_admin_audience():
    """The reverse direction is the one that would be privilege escalation."""
    portal_token = SecurityService.create_access_token(
        subject="22222222-2222-2222-2222-222222222222",
        token_type=TOKEN_TYPE_PORTAL_USER,
    )
    assert SecurityService.verify_access_token(portal_token, expected_type=TOKEN_TYPE_ADMIN) is None


def test_each_token_validates_in_its_own_audience():
    subject = "33333333-3333-3333-3333-333333333333"
    for token_type in (TOKEN_TYPE_ADMIN, TOKEN_TYPE_PORTAL_USER):
        token = SecurityService.create_access_token(subject=subject, token_type=token_type)
        assert SecurityService.verify_access_token(token, expected_type=token_type) == subject


def test_legacy_token_without_type_claim_still_works_as_admin():
    """
    Sessions issued before the claim existed must not be invalidated: an admin
    logged in at deploy time should not be kicked out.
    """
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.core.config import settings

    legacy = jwt.encode(
        {
            "sub": "44444444-4444-4444-4444-444444444444",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    assert SecurityService.verify_access_token(legacy, expected_type=TOKEN_TYPE_ADMIN) is not None
    # ...but it must not be usable as a portal token, or the absence of a claim
    # would become a way to reach the portal audience.
    assert SecurityService.verify_access_token(legacy, expected_type=TOKEN_TYPE_PORTAL_USER) is None


def test_tampered_token_is_rejected():
    token = SecurityService.create_access_token(
        subject="55555555-5555-5555-5555-555555555555",
        token_type=TOKEN_TYPE_PORTAL_USER,
    )
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}xxxx"
    assert SecurityService.verify_access_token(tampered, expected_type=TOKEN_TYPE_PORTAL_USER) is None


# --- registration policy ----------------------------------------------------

def test_registration_default_status_keeps_user_out_of_campaigns():
    """
    A self-registered user must start "inactive".

    campaign_resolver only targets users with status "active", so if
    registration ever defaulted to active, anyone who can reach the public
    endpoint would insert themselves into the next campaign and get published
    on behalf of the platform.
    """
    import inspect
    from app.api.v1 import portal

    source = inspect.getsource(portal.register)
    assert 'status="inactive"' in source, (
        "La registrazione pubblica deve creare utenti inattivi: "
        "'active' li rende immediatamente bersaglio delle campagne."
    )


def test_registration_never_overwrites_an_existing_password():
    """
    Claiming an admin-created account is allowed; taking over an account that
    already has credentials is not.
    """
    import inspect
    from app.api.v1 import portal

    source = inspect.getsource(portal.register)
    assert "if existing.password_hash" in source
    assert "409" in source
