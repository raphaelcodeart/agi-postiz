"""
bundle.social production client: contract mapping.

Every fixture here is shaped from a response observed against the live API on
2026-09-06, not invented (AGENTS.md rule 14). The tests exercise the translation
layer - platform names, channel shape, post body, metric names - because that is
where a wrong assumption survives review and fails on a real campaign.
"""
from datetime import datetime, timezone

import pytest

from app.integrations.buffer.exceptions import BufferApiError
from app.integrations.bundle_social.prod_client import (
    BUNDLE_TO_PLATFORM,
    PLATFORM_TEXT_MAX_CHARS,
    PLATFORM_TO_BUNDLE,
    YOUTUBE_TITLE_MAX_CHARS,
    ProductionBundleSocialClient,
)


# --- platform naming --------------------------------------------------------

def test_x_and_twitter_both_map_to_the_provider_enum():
    """
    Internally the platform is "twitter" - that is what Buffer reports and what
    campaign_resolver keys on. Accepting "x" too means a channel labelled either
    way still publishes instead of failing as unsupported.
    """
    assert PLATFORM_TO_BUNDLE["twitter"] == "TWITTER"
    assert PLATFORM_TO_BUNDLE["x"] == "TWITTER"
    # ...and the reverse map keeps the internal name, never "x".
    assert BUNDLE_TO_PLATFORM["TWITTER"] == "twitter"


def test_reverse_mapping_is_complete_for_core_platforms():
    for bundle_type in ("INSTAGRAM", "FACEBOOK", "TIKTOK", "YOUTUBE", "LINKEDIN"):
        platform = BUNDLE_TO_PLATFORM[bundle_type]
        assert PLATFORM_TO_BUNDLE[platform] == bundle_type


# --- channel shape ----------------------------------------------------------

def _client(account_ref="team_1"):
    return ProductionBundleSocialClient(account_ref=account_ref)


def test_instagram_connected_via_facebook_is_marked_business():
    """
    campaign_resolver excludes Instagram personal profiles proactively: they can
    never publish through an API, by Meta's rules. That guard reads channel_type,
    so it has to keep working for channels from this provider too.
    """
    account = {"type": "INSTAGRAM", "instagramConnectionMethod": "FACEBOOK"}
    assert ProductionBundleSocialClient._channel_type(account) == "business"


def test_instagram_connected_directly_is_also_business():
    """
    Regression test for the bug that made Instagram look like it "required a
    Facebook Page". ``instagramConnectionMethod: "INSTAGRAM"`` means the account
    authorised through Instagram API with Instagram Login - a Business/Creator
    account publishing without a Page, which Meta has allowed since 2024.

    This used to return "profile", which campaign_resolver reads as "personal
    account, can never publish" and excludes before making any call. Every real
    Instagram account in this deployment connects this way, so every one of them
    was being rejected for a limitation that does not exist.
    """
    account = {"type": "INSTAGRAM", "instagramConnectionMethod": "INSTAGRAM"}
    assert ProductionBundleSocialClient._channel_type(account) == "business"


def test_no_instagram_connection_method_is_still_business():
    """A missing method must not fall back to the excluding value."""
    assert ProductionBundleSocialClient._channel_type({"type": "INSTAGRAM"}) == "business"


# --- YouTube title/description ---------------------------------------------
#
# bundle.social's ``data.YOUTUBE.text`` is the video TITLE (max 100 chars) and
# the caption goes in ``description``. The client used to send the caption as
# ``text`` - rejected with "Max 100 characters allowed" on every attempt - and
# the title under a ``title`` key the schema does not define, which was dropped.

def _capture(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: (captured.update(k.get("json_body") or {}), {"id": "p", "errors": {}})[1],
    )
    return captured


def test_youtube_maps_title_and_description_to_the_right_fields(monkeypatch):
    client = _client()
    captured = _capture(client, monkeypatch)

    client.create_post(
        api_key="k", channel_id="sa", text="Descrizione lunga del video",
        platform="youtube", youtube_title="Il mio titolo",
    )

    youtube = captured["data"]["YOUTUBE"]
    assert youtube["text"] == "Il mio titolo"
    assert youtube["description"] == "Descrizione lunga del video"
    # The key the schema ignores must not be what carries the title any more.
    assert youtube.get("title") is None


def test_youtube_title_derived_from_a_long_caption_is_clipped_to_100(monkeypatch):
    """
    With no youtube_title set the title is derived from the caption, which is
    routinely longer than YouTube's 100-character limit. Truncating publishes a
    sensibly-titled video; sending it whole fails the campaign permanently.
    """
    client = _client()
    captured = _capture(client, monkeypatch)

    client.create_post(api_key="k", channel_id="sa", text="A" * 400, platform="youtube")

    youtube = captured["data"]["YOUTUBE"]
    assert len(youtube["text"]) <= YOUTUBE_TITLE_MAX_CHARS
    assert youtube["text"].endswith("\u2026")
    # The caption itself is untouched - only the derived title was shortened.
    assert youtube["description"] == "A" * 400


def test_youtube_without_any_text_still_gets_a_title(monkeypatch):
    client = _client()
    captured = _capture(client, monkeypatch)
    client.create_post(api_key="k", channel_id="sa", text="", platform="youtube")
    assert captured["data"]["YOUTUBE"]["text"] == "Video"


def test_disconnected_channel_rejection_is_explained(monkeypatch):
    """
    "No social accounts selected" reads like a malformed request; it actually
    means the team no longer holds an account of that platform. Reporting it
    verbatim sent an administrator looking for a bug in the payload instead of
    asking the user to reconnect.
    """
    client = _client()

    def fake_request(*a, **k):
        raise BufferApiError(
            'Richiesta bundle.social rifiutata: {"statusCode":400,"message":"No social accounts selected"}',
            status_code=400,
            category="validation_failed",
        )

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(BufferApiError) as excinfo:
        client.create_post(api_key="k", channel_id="sa", text="t", platform="linkedin")

    assert excinfo.value.category == "channel_disconnected"
    assert "ricollegarlo" in excinfo.value.message


def test_sync_channels_maps_a_real_account_payload(monkeypatch):
    team_payload = {
        "id": "team_1",
        "name": "Mario Rossi",
        "socialAccounts": [
            {
                "id": "sa_abc",
                "type": "INSTAGRAM",
                "username": "mario.rossi",
                "displayName": "Mario Rossi",
                "avatarUrl": "https://example.com/a.jpg",
                "externalId": "17841400000000000",
                "instagramConnectionMethod": "FACEBOOK",
                "deletedAt": None,
            },
            # Soft-deleted accounts must not come back as live channels.
            {"id": "sa_gone", "type": "TIKTOK", "username": "old", "deletedAt": "2026-09-01T00:00:00Z"},
        ],
    }
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: team_payload)

    channels = client.sync_channels("key", "team_1")

    assert len(channels) == 1
    channel = channels[0]
    assert channel["id"] == "sa_abc"
    assert channel["platform"] == "instagram"
    assert channel["username"] == "mario.rossi"
    assert channel["channel_type"] == "business"
    # No public profile URL exists in the payload, so none is invented.
    assert channel["external_link"] is None


# --- post body --------------------------------------------------------------

def test_create_post_builds_the_six_required_fields(monkeypatch):
    """The live API itself named these six as required."""
    captured = {}
    client = _client()

    def fake_request(api_key, method, path, *, params=None, json_body=None):
        captured.update(json_body or {})
        return {"id": "post_1", "status": "SCHEDULED", "errors": {}}

    monkeypatch.setattr(client, "_request", fake_request)
    client.create_post(api_key="k", channel_id="sa_abc", text="ciao", platform="instagram")

    for field in ("teamId", "title", "postDate", "status", "socialAccountTypes", "data"):
        assert field in captured, f"campo obbligatorio mancante: {field}"
    assert captured["socialAccountTypes"] == ["INSTAGRAM"]
    assert captured["data"]["INSTAGRAM"]["text"] == "ciao"


def test_instagram_long_video_becomes_a_reel(monkeypatch):
    """Same rule the Buffer client applies: over a minute cannot be a feed post."""
    captured = {}
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: (captured.update(k.get("json_body") or {}), {"id": "p", "errors": {}})[1],
    )

    client.create_post(
        api_key="k", channel_id="sa", text="t", platform="instagram",
        media_type="video", video_duration_seconds=180.0,
    )
    assert captured["data"]["INSTAGRAM"]["type"] == "REEL"


def test_instagram_short_video_stays_a_post(monkeypatch):
    captured = {}
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: (captured.update(k.get("json_body") or {}), {"id": "p", "errors": {}})[1],
    )
    client.create_post(
        api_key="k", channel_id="sa", text="t", platform="instagram",
        media_type="video", video_duration_seconds=30.0,
    )
    assert captured["data"]["INSTAGRAM"]["type"] == "POST"


def test_per_platform_error_in_a_200_is_raised(monkeypatch):
    """
    A 200 does not mean the post went out: per-platform failures come back in
    `errors`. Treating that as success would mark a publication published when
    nothing was posted - and rule 2 forbids retrying a "successful" one.
    """
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: {"id": "p", "errors": {"INSTAGRAM": "Media non valido"}},
    )
    with pytest.raises(BufferApiError) as exc:
        client.create_post(api_key="k", channel_id="sa", text="t", platform="instagram")
    assert "Media non valido" in exc.value.message


def test_create_post_without_a_team_fails_clearly(monkeypatch):
    client = ProductionBundleSocialClient(account_ref=None)
    with pytest.raises(BufferApiError) as exc:
        client.create_post(api_key="k", channel_id="sa", text="t", platform="instagram")
    assert exc.value.category == "configuration_error"


def test_unsupported_platform_is_rejected_before_the_call():
    client = _client()
    with pytest.raises(BufferApiError) as exc:
        client.create_post(api_key="k", channel_id="sa", text="t", platform="myspace")
    assert exc.value.category == "validation_failed"


# --- metrics ----------------------------------------------------------------

def test_metrics_map_onto_the_keys_the_statistics_module_stores(monkeypatch):
    """
    The parity question the whole provider decision hung on.

    likes/comments/shares/views/impressions map straight across; reach comes from
    impressionsUnique, which IS unique impressions. clicks, follows and
    engagement_rate are simply not provided, and must stay absent rather than be
    derived from something that means something else.
    """
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: {
        "post": {"externalData": {"INSTAGRAM": {"permalink": "https://instagram.com/p/xyz"}}},
        "items": [
            {"likes": 1, "comments": 1, "shares": 1, "views": 1, "impressions": 1, "impressionsUnique": 1},
            {
                "likes": 120, "comments": 8, "shares": 3, "saves": 11,
                "views": 4500, "impressions": 5200, "impressionsUnique": 3900,
                "updatedAt": "2026-09-06T22:00:00Z",
            },
        ],
    })

    result = client.get_post_metrics("k", "post_1", platform="instagram")
    metrics = {m["type"]: m["value"] for m in result["metrics"]}

    # Latest snapshot wins - the API appends a row per refresh.
    assert metrics["likes"] == 120
    assert metrics["impressions"] == 5200
    assert metrics["reach"] == 3900
    assert metrics["views"] == 4500

    assert "clicks" not in metrics
    assert "follows" not in metrics
    assert "engagement_rate" not in metrics

    # Nothing is lost: the untranslated fields stay available.
    assert result["raw"]["saves"] == 11
    assert result["external_link"] == "https://instagram.com/p/xyz"


def test_metrics_absent_yet_returns_an_empty_result(monkeypatch):
    """Fresh posts have no analytics for hours; that is not an error."""
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: {"items": []})
    result = client.get_post_metrics("k", "post_1", platform="instagram")
    assert result["metrics"] == []


# --- contract with the statistics module -------------------------------------

def test_metrics_use_the_key_the_statistics_module_indexes_by():
    """
    The silent-failure guard.

    extract_metric_columns looks metrics up by m["type"]. Emitting them under
    any other key drops every single one without raising: the sync reports
    success, the dashboard shows zeros, and nothing says why. This was actually
    wrong once - the client emitted "name" - and only reading the consumer
    caught it.
    """
    from app.services.statistics_service import METRIC_TYPE_TO_COLUMN, extract_metric_columns

    client = _client()
    import types as _t
    client._request = _t.MethodType(  # type: ignore[method-assign]
        lambda self, *a, **k: {
            "items": [{
                "likes": 10, "comments": 2, "shares": 1,
                "views": 100, "impressions": 120, "impressionsUnique": 90,
            }]
        },
        client,
    )

    result = client.get_post_metrics("k", "p1", platform="instagram")

    # Every emitted type must be one the statistics module actually knows...
    for metric in result["metrics"]:
        assert "type" in metric, "la chiave deve essere 'type', non 'name'"
        assert metric["type"] in METRIC_TYPE_TO_COLUMN, f"tipo sconosciuto: {metric['type']}"

    # ...and must survive the real extraction, not just look right.
    columns = extract_metric_columns(result["metrics"])
    assert columns["likes"] == 10
    assert columns["impressions"] == 120
    assert columns["reach"] == 90
    assert columns["views"] == 100


def test_metrics_send_the_platform_type_the_endpoint_requires(monkeypatch):
    """
    Regression test for the reason every statistic read zero.

    ``platformType`` reads like an optional filter and is not: without it the
    endpoint answers 400 Request Validation Error, the sync records a per-post
    failure, and the dashboard fills with zeroes explaining nothing.
    """
    client = _client()
    captured = {}

    def fake_request(api_key, method, path, *, params=None, json_body=None):
        captured["path"] = path
        captured["params"] = params or {}
        return {"items": []}

    monkeypatch.setattr(client, "_request", fake_request)
    client.get_post_metrics("k", "post_1", platform="instagram")

    assert captured["params"].get("platformType") == "INSTAGRAM"
    assert captured["params"].get("postId") == "post_1"


def test_metrics_without_a_platform_fail_before_the_call(monkeypatch):
    """
    Better a clear refusal here than a provider 400 recorded as a mystery
    per-post sync error.
    """
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: pytest.fail("non deve chiamare l'API"))

    with pytest.raises(BufferApiError):
        client.get_post_metrics("k", "post_1")


def test_metrics_report_that_the_post_actually_went_live(monkeypatch):
    """
    The statistics sync is the only moment we ask the provider about a post it
    already accepted, so it is where "scheduled" finally becomes "published".
    Without these fields every publication stayed "scheduled" forever, with no
    permalink and no publication date - which is what production looked like.
    """
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: {
        "post": {"status": "POSTED", "postedDate": "2026-09-09T14:06:23.932Z"},
        "profilePost": {
            "permalink": "https://www.instagram.com/reel/DdEb4Y1kbaq/",
            "publishedAt": "2026-09-09T14:06:23.967Z",
            "thumbnail": "https://example.test/thumb.jpg",
        },
        "items": [{"likes": 1, "views": 65, "impressions": 65, "impressionsUnique": 60}],
    })

    result = client.get_post_metrics("k", "post_1", platform="instagram")

    assert result["post_status"] == "POSTED"
    assert result["published_at"] == "2026-09-09T14:06:23.967Z"
    assert result["external_link"] == "https://www.instagram.com/reel/DdEb4Y1kbaq/"
    assert {m["type"]: m["value"] for m in result["metrics"]}["views"] == 65


def test_publication_state_is_reported_even_with_no_metrics_yet(monkeypatch):
    """
    A post published minutes ago has an empty analytics list. The confirmation
    that it went out must not be withheld until the numbers arrive - otherwise
    a freshly published post stays "scheduled" for a day.
    """
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *a, **k: {
        "post": {"status": "POSTED", "postedDate": "2026-09-09T14:06:23.932Z"},
        "profilePost": {"permalink": "https://x.test/p/1"},
        "items": [],
    })

    result = client.get_post_metrics("k", "post_1", platform="instagram")

    assert result["metrics"] == []
    assert result["post_status"] == "POSTED"
    assert result["external_link"] == "https://x.test/p/1"


def test_permalink_is_read_from_external_data():
    """
    The public post URL lives at externalData.<PLATFORM>.permalink, not at a
    top-level field. Getting this wrong costs nothing loudly - the link simply
    never appears in the dashboard.
    """
    post = {"externalData": {"FACEBOOK": {"permalink": "https://facebook.com/123/posts/456"}}}
    assert ProductionBundleSocialClient._permalink_from(post) == "https://facebook.com/123/posts/456"


def test_permalink_absent_returns_none_without_raising():
    assert ProductionBundleSocialClient._permalink_from({}) is None
    assert ProductionBundleSocialClient._permalink_from({"externalData": {}}) is None
    assert ProductionBundleSocialClient._permalink_from({"externalData": {"X": {}}}) is None


def test_a_past_scheduled_date_is_published_now(monkeypatch):
    """
    The provider rejects a postDate more than 10 minutes in the past. A campaign
    scheduled for 9:00 whose targets are still draining the publishing queue at
    10:30 would otherwise fail every remaining one - which is exactly what
    happened on the first real campaign.
    """
    from datetime import timedelta

    captured = {}
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: (captured.update(k.get("json_body") or {}), {"id": "p", "errors": {}})[1],
    )

    past = datetime.now(timezone.utc) - timedelta(hours=3)
    client.create_post(api_key="k", channel_id="sa", text="t", platform="facebook", scheduled_at=past)

    sent = datetime.fromisoformat(captured["postDate"].replace("Z", "+00:00"))
    assert sent > past, "una data passata deve diventare adesso"
    assert (datetime.now(timezone.utc) - sent).total_seconds() < 60


def test_a_future_scheduled_date_is_preserved(monkeypatch):
    """Clamping must not turn a genuinely scheduled post into an immediate one."""
    from datetime import timedelta

    captured = {}
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: (captured.update(k.get("json_body") or {}), {"id": "p", "errors": {}})[1],
    )

    future = datetime.now(timezone.utc) + timedelta(days=2)
    client.create_post(api_key="k", channel_id="sa", text="t", platform="facebook", scheduled_at=future)

    sent = datetime.fromisoformat(captured["postDate"].replace("Z", "+00:00"))
    assert abs((sent - future).total_seconds()) < 2


def test_a_disconnected_channel_is_explained_when_fetching_metrics(monkeypatch):
    """
    Same treatment as the publishing path. Left raw, this reached the Errori page
    as `{"statusCode":400,"message":"Team does not have a Tiktok account"}` -
    accurate, and useless to whoever has to act on it.
    """
    client = _client()

    def fake_request(*a, **k):
        raise BufferApiError(
            'Richiesta bundle.social rifiutata: {"statusCode":400,"message":"Team does not have a Tiktok account"}',
            status_code=400,
            category="validation_failed",
        )

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(BufferApiError) as excinfo:
        client.get_post_metrics("k", "p1", platform="tiktok")

    assert excinfo.value.category == "channel_disconnected"
    assert "ricollegarlo" in excinfo.value.message


def test_a_post_that_never_went_out_is_explained(monkeypatch):
    """
    "Post doesn't have external ID for that platform" means the provider took the
    post but it never reached the network - so there is nothing to measure. That
    is a different problem from a broken connection, and says so.
    """
    client = _client()

    def fake_request(*a, **k):
        raise BufferApiError(
            'Richiesta bundle.social rifiutata: {"statusCode":400,"message":"Post doesn\'t have external ID for that platform"}',
            status_code=400,
            category="validation_failed",
        )

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(BufferApiError) as excinfo:
        client.get_post_metrics("k", "p1", platform="twitter")

    assert excinfo.value.category == "not_published"


def test_an_unrecognised_error_is_left_alone(monkeypatch):
    """Inventing an explanation for an error we have never seen is worse than
    showing the raw one."""
    client = _client()

    def fake_request(*a, **k):
        raise BufferApiError("Qualcosa di completamente nuovo", status_code=400, category="validation_failed")

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(BufferApiError) as excinfo:
        client.get_post_metrics("k", "p1", platform="instagram")

    assert excinfo.value.message == "Qualcosa di completamente nuovo"
    assert excinfo.value.category == "validation_failed"


def test_metrics_come_from_the_newest_snapshot_not_the_first_listed(monkeypatch):
    """bundle.social returns every analytics snapshot it has taken, NEWEST
    FIRST. Reading items[-1] took the oldest one - written seconds after
    publishing, when every counter is still 0 - so the dashboard showed a post
    frozen at its day-one figures while the provider had current ones.

    Fixture shaped from the live response for a real Instagram post on
    2026-09-14: six daily snapshots, 65 views on day one, 69 today.
    """
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: {
            "post": {"status": "POSTED"},
            "profilePost": {"publishedAt": "2026-09-08T13:14:56.043Z"},
            "items": [
                {"createdAt": "2026-09-14T13:21:53.363Z", "updatedAt": "2026-09-14T13:21:53.363Z",
                 "views": 69, "impressions": 69, "impressionsUnique": 41, "likes": 1, "comments": 0, "shares": 0},
                {"createdAt": "2026-09-10T13:17:22.055Z", "updatedAt": "2026-09-10T13:17:22.055Z",
                 "views": 68, "impressions": 68, "impressionsUnique": 40, "likes": 1, "comments": 0, "shares": 0},
                {"createdAt": "2026-09-09T13:15:43.276Z", "updatedAt": "2026-09-09T13:15:43.276Z",
                 "views": 65, "impressions": 65, "impressionsUnique": 39, "likes": 1, "comments": 0, "shares": 0},
            ],
        },
    )

    result = client.get_post_metrics("k", "p1", platform="instagram")
    by_type = {m["type"]: m["value"] for m in result["metrics"]}

    assert by_type["views"] == 69
    assert by_type["impressions"] == 69
    assert by_type["reach"] == 41
    assert result["metrics_updated_at"] == "2026-09-14T13:21:53.363Z"


def test_the_newest_snapshot_wins_whatever_order_the_api_lists_them_in(monkeypatch):
    """The fix must not simply swap one positional assumption for the other:
    the same figures have to come back if the provider ever lists them
    oldest-first instead."""
    client = _client()
    monkeypatch.setattr(
        client, "_request",
        lambda *a, **k: {
            "post": {"status": "POSTED"},
            "profilePost": {},
            "items": [
                {"createdAt": "2026-09-09T13:15:43.276Z", "updatedAt": "2026-09-09T13:15:43.276Z", "views": 65},
                {"createdAt": "2026-09-14T13:21:53.363Z", "updatedAt": "2026-09-14T13:21:53.363Z", "views": 69},
                {"createdAt": "2026-09-10T13:17:22.055Z", "updatedAt": "2026-09-10T13:17:22.055Z", "views": 68},
            ],
        },
    )

    result = client.get_post_metrics("k", "p1", platform="instagram")

    assert {m["type"]: m["value"] for m in result["metrics"]}["views"] == 69
