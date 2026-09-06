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


def test_toggle_off_leaves_text_unchanged_even_with_contacts_available():
    campaign = _campaign(include_personal_contacts=False)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts="Mario Rossi - 333 1234567")
    assert text == campaign.default_text


def test_toggle_on_appends_the_users_personal_contacts():
    campaign = _campaign(include_personal_contacts=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts="Mario Rossi - 333 1234567")
    assert text.startswith(campaign.default_text)
    assert "Mario Rossi - 333 1234567" in text


def test_toggle_on_but_user_has_no_contacts_leaves_text_unchanged():
    campaign = _campaign(include_personal_contacts=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts=None)
    assert text == campaign.default_text


def test_toggle_on_but_user_has_empty_string_contacts_leaves_text_unchanged():
    campaign = _campaign(include_personal_contacts=True)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts="")
    assert text == campaign.default_text


def test_personal_contacts_appended_right_after_referral_link():
    # The campaign wizard orders the two checkboxes "link referral" then
    # "contatti personali" - resolve_text_for_channel mirrors that ordering.
    campaign = _campaign(include_referral_link=True, include_personal_contacts=True)
    text = CampaignResolver.resolve_text_for_channel(
        campaign,
        _channel(),
        referral_link="https://ref.example.com/mario",
        personal_contacts="Mario Rossi - 333 1234567",
    )
    referral_index = text.index("ISCRIVITI QUI: https://ref.example.com/mario")
    contacts_index = text.index("Mario Rossi - 333 1234567")
    assert referral_index < contacts_index


def test_different_channels_never_mix_up_each_others_contacts():
    campaign = _campaign(include_personal_contacts=True)
    text_mario = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts="Mario - 111")
    text_luca = CampaignResolver.resolve_text_for_channel(campaign, _channel(), personal_contacts="Luca - 222")
    assert "Mario" in text_mario and "Luca" not in text_mario
    assert "Luca" in text_luca and "Mario" not in text_luca


def test_appended_contacts_can_push_text_over_the_twitter_character_limit():
    # Documents the intended interaction with PLATFORM_TEXT_LIMITS (enforced in
    # launch_campaign, not here) - same contract as the referral link tests.
    campaign = _campaign(include_personal_contacts=True, x_text="x" * 260)
    long_contacts = "Mario Rossi - " + ("0" * 40)
    text = CampaignResolver.resolve_text_for_channel(campaign, _channel("twitter"), personal_contacts=long_contacts)
    assert len(text) > PLATFORM_TEXT_LIMITS["twitter"]
