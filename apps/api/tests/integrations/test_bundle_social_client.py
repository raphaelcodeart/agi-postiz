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
    PLATFORM_TO_BUNDLE,
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


def test_instagram_connected_directly_is_marked_profile():
    account = {"type": "INSTAGRAM", "instagramConnectionMethod": "INSTAGRAM"}
    assert ProductionBundleSocialClient._channel_type(account) == "profile"


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

    result = client.get_post_metrics("k", "post_1")
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
    result = client.get_post_metrics("k", "post_1")
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

    result = client.get_post_metrics("k", "p1")

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
