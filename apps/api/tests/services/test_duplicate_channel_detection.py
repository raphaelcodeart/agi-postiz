"""
Cross-provider duplicate detection.

The failure this prevents is the worst kind in this system: the same real social
account connected twice - once directly, once through the owner's Buffer key -
means every campaign posts twice on a client's actual profile. Visible to their
audience, immediately.

The match is a heuristic, because the two providers describe an account
differently: Buffer reports the handle and the public profile URL, bundle.social
reports the platform's own numeric id and no URL at all. These tests pin the
signals it relies on.
"""
from app.tasks.sync import _identity_keys


def test_buffer_and_provider_payloads_share_a_key_for_the_same_page():
    """
    A real pairing: bundle.social returns the Facebook page id as the username,
    while Buffer returns the page name plus a profile URL ending in that same id.
    The page id is the overlap.
    """
    from_provider = {
        "username": "1079774881896273",
        "name": "Agi Social",
        "raw": {"external_id": "1079774881896273"},
    }
    from_buffer = {
        "username": "Agi Social",
        "name": "Agi Social",
        "external_link": "https://facebook.com/1079774881896273",
    }

    assert _identity_keys("facebook", from_provider) & _identity_keys("facebook", from_buffer)


def test_matching_on_handle_alone_still_works():
    """Platforms where both sides report the handle, e.g. X or Instagram."""
    a = {"username": "@mario.rossi", "name": "Mario Rossi"}
    b = {"username": "mario.rossi", "name": "Mario Rossi Ufficiale"}
    assert _identity_keys("instagram", a) & _identity_keys("instagram", b)


def test_handles_are_normalized():
    """Case and a leading @ must not defeat the match."""
    assert _identity_keys("x", {"username": "@MarioRossi"}) == _identity_keys("x", {"username": "mariorossi"})


def test_different_accounts_do_not_match():
    a = {"username": "mario.rossi", "name": "Mario Rossi"}
    b = {"username": "giulia.bianchi", "name": "Giulia Bianchi"}
    assert not (_identity_keys("instagram", a) & _identity_keys("instagram", b))


def test_same_handle_on_different_platforms_is_not_a_duplicate():
    """
    Keys are namespaced by platform: the same person owning @mario on Instagram
    and on X has two channels, not one connected twice.
    """
    payload = {"username": "mario"}
    assert not (_identity_keys("instagram", payload) & _identity_keys("x", payload))


def test_profile_url_query_string_is_ignored():
    a = {"external_link": "https://facebook.com/AgiSocial?ref=share"}
    b = {"username": "agisocial"}
    assert _identity_keys("facebook", a) & _identity_keys("facebook", b)


def test_empty_payload_yields_no_keys():
    """
    No identifying signal means no match: better a missed duplicate an admin can
    spot than a false positive blocking a legitimate channel automatically.
    """
    assert _identity_keys("facebook", {}) == set()
    assert _identity_keys("facebook", {"username": None, "name": None}) == set()


# --- removed channels ---------------------------------------------------------

def test_removed_channels_are_excluded_everywhere_they_matter():
    """
    A channel removed by its owner must disappear from every list that invites
    action on it, and from campaign targeting - but NOT from the statistics
    drill-down, which is the reason the row survives at all.

    Checked by reading the queries: exercising them needs a database, and the
    property worth locking down is that the filter is present at all - it was
    missing from the admin listing, where a removed channel showed up looking
    exactly like a live one.
    """
    import inspect
    from app.api.v1 import buffer as buffer_api
    from app.api.v1 import portal as portal_api
    from app.services import campaign_resolver

    # Admin listing: excluded unless explicitly asked for.
    admin_src = inspect.getsource(buffer_api.list_channels)
    assert "include_removed" in admin_src
    assert "SocialChannel.deleted_at.is_(None)" in admin_src

    # Portal listing: the owner's own view, always excluded.
    portal_src = inspect.getsource(portal_api._user_channels_query)
    assert "SocialChannel.deleted_at.is_(None)" in portal_src

    # Campaign targeting: the one that would actually publish to it.
    resolver_src = inspect.getsource(campaign_resolver.CampaignResolver.resolve_targets)
    assert "SocialChannel.deleted_at.is_(None)" in resolver_src
