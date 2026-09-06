from types import SimpleNamespace
from app.services.campaign_resolver import CampaignResolver, PLATFORM_TEXT_LIMITS


def _campaign(include_referral_link=False, include_personal_contacts=False, **text_fields):
    defaults = dict(
        default_text="Guarda il nostro nuovo video!",
        instagram_text=None,
        facebook_text=None,
        linkedin_text=None,
        tiktok_text=None,
        x_text=None,
        threads_text=None,
        youtube_description=None,
    )
    defaults.update(text_fields)
    return SimpleNamespace(
        include_referral_link=include_referral_link,
        include_personal_contacts=include_personal_contacts,
        **defaults,
    )


def _channel(platform="instagram"):
    return SimpleNamespace(platform=platform)


def test_toggle_off_leaves_text_unchanged_even_with_a_link_available():
    campaign = _campaign(include_referral_link=False)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link="https://ref.example.com/mario")
    assert text == campaign.default_text
    assert "ISCRIVITI" not in text


def test_toggle_on_appends_the_users_referral_link():
    campaign = _campaign(include_referral_link=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link="https://ref.example.com/mario")
    assert text.startswith(campaign.default_text)
    assert "ISCRIVITI QUI: https://ref.example.com/mario" in text


def test_toggle_on_but_user_has_no_link_leaves_text_unchanged():
    campaign = _campaign(include_referral_link=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link=None)
    assert text == campaign.default_text


def test_toggle_on_but_user_has_empty_string_link_leaves_text_unchanged():
    campaign = _campaign(include_referral_link=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link="")
    assert text == campaign.default_text


def test_link_appended_after_platform_specific_text():
    campaign = _campaign(include_referral_link=True, instagram_text="Testo speciale per Instagram")
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel("instagram"), referral_link="https://ref.example.com/mario")
    assert text.startswith("Testo speciale per Instagram")
    assert "https://ref.example.com/mario" in text


def test_link_appended_after_channel_override_text():
    campaign = _campaign(include_referral_link=True)
    text = CampaignResolver.resolve_text_for_channel(
        campaign, _channel(), channel_override_text="Testo scritto a mano per questo canale", referral_link="https://ref.example.com/mario"
    )
    assert text.startswith("Testo scritto a mano per questo canale")
    assert "https://ref.example.com/mario" in text


def test_different_channels_never_mix_up_each_others_link():
    # Each call is independent and stateless - simulates two channels belonging
    # to two different users in the same campaign launch loop, confirming a
    # channel can never end up with another user's referral_link.
    campaign = _campaign(include_referral_link=True)
    text_mario = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link="https://ref.example.com/mario")
    text_luca = CampaignResolver.resolve_text_for_channel(campaign, _channel(), referral_link="https://ref.example.com/luca")
    assert "mario" in text_mario and "luca" not in text_mario
    assert "luca" in text_luca and "mario" not in text_luca


def test_appended_link_can_push_text_over_the_twitter_character_limit():
    # Documents the intended interaction with PLATFORM_TEXT_LIMITS (enforced in
    # launch_campaign, not here): resolve_text_for_channel doesn't truncate or
    # validate anything itself, so a long link can legitimately push a target
    # over its platform's limit - launch_campaign's existing length check on the
    # resolved text catches this exactly like any other over-limit text.
    campaign = _campaign(include_referral_link=True, x_text="x" * 260)
    long_link = "https://ref.example.com/" + ("a" * 40)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel("twitter"), referral_link=long_link)
    assert len(text) > PLATFORM_TEXT_LIMITS["twitter"]
