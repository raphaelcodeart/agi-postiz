"""
Advertising disclosure on campaign text.

An affiliate link makes a post commercial communication: the promoter earns a
commission, which is an economic benefit, whether or not anyone pays them
directly. Declaring it is the advertiser's responsibility as much as the
promoter's - and since the text is written centrally, the control belongs in the
system rather than in each collaborator's memory.
"""
from types import SimpleNamespace

from app.services.campaign_resolver import CampaignResolver


def _campaign(**flags):
    base = {
        "default_text": "Guarda questo prodotto",
        "instagram_text": None, "facebook_text": None, "linkedin_text": None,
        "tiktok_text": None, "x_text": None, "threads_text": None,
        "youtube_description": None, "youtube_title": None,
        "include_referral_link": False,
        "include_personal_contacts": False,
        "include_affiliate_disclosure": False,
    }
    base.update(flags)
    return SimpleNamespace(**base)


def _channel(platform="instagram"):
    return SimpleNamespace(platform=platform)


DISCLOSURE = "Link affiliato: se acquisti ricevo una commissione. #adv"


def test_disclosure_is_absent_when_the_option_is_off():
    """Default off: existing campaigns must read exactly as before."""
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(), _channel(), None, None, None, DISCLOSURE
    )
    assert DISCLOSURE not in text
    assert text == "Guarda questo prodotto"


def test_disclosure_is_appended_when_the_option_is_on():
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(include_affiliate_disclosure=True), _channel(), None, None, None, DISCLOSURE
    )
    assert text.endswith(DISCLOSURE)


def test_disclosure_follows_the_referral_link():
    """
    Order matters for readability: the disclosure has to sit next to the thing
    it declares. On Instagram and TikTok anything far down the caption is hidden
    behind "... more", and a disclosure nobody sees is not a disclosure.
    """
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(include_referral_link=True, include_affiliate_disclosure=True),
        _channel(), None, "https://esempio.it/mario", None, DISCLOSURE,
    )
    assert text.index("https://esempio.it/mario") < text.index(DISCLOSURE)


def test_disclosure_comes_last_of_the_three_appends():
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(
            include_referral_link=True,
            include_personal_contacts=True,
            include_affiliate_disclosure=True,
        ),
        _channel(), None, "https://esempio.it/mario", "Mario Rossi - 333 1234567", DISCLOSURE,
    )
    assert text.index("Mario Rossi") < text.index(DISCLOSURE)
    assert text.endswith(DISCLOSURE)


def test_nothing_is_appended_when_no_wording_was_supplied():
    """
    The flag alone must not produce a dangling separator: a campaign that looks
    like it declared something while declaring nothing is the worst outcome.
    """
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(include_affiliate_disclosure=True), _channel(), None, None, None, None
    )
    assert text == "Guarda questo prodotto"


def test_a_channel_override_still_receives_the_disclosure():
    """
    Per-channel custom text must not become a way to lose the declaration -
    otherwise the one post someone hand-wrote is the one that is non-compliant.
    """
    text = CampaignResolver.resolve_text_for_channel(
        _campaign(include_affiliate_disclosure=True),
        _channel(), "Testo scritto a mano", None, None, DISCLOSURE,
    )
    assert text.startswith("Testo scritto a mano")
    assert text.endswith(DISCLOSURE)


def test_defaults_exist_so_switching_the_option_on_always_declares_something():
    from app.models.platform_settings import (
        DEFAULT_AFFILIATE_DISCLOSURE,
        DEFAULT_AFFILIATE_DISCLOSURE_SHORT,
    )

    # An explicit sentence, not a bare hashtag: a "#adv" buried among fifteen
    # other tags is exactly what regulators consider insufficient.
    assert "commissione" in DEFAULT_AFFILIATE_DISCLOSURE
    assert "#adv" in DEFAULT_AFFILIATE_DISCLOSURE
    # The short form still has to say something, not just be shorter.
    assert "#adv" in DEFAULT_AFFILIATE_DISCLOSURE_SHORT
    assert len(DEFAULT_AFFILIATE_DISCLOSURE_SHORT) < len(DEFAULT_AFFILIATE_DISCLOSURE)
