from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.statistics_service import (
    ALL_METRIC_COLUMNS,
    STALE_SYNC_THRESHOLD,
    _impact_score,
    _platform_breakdown,
    _totals_dict,
    extract_metric_columns,
    needs_sync,
    timeseries,
)


def _metric_row(published_at=None, **overrides):
    values = {c: None for c in ALL_METRIC_COLUMNS}
    values.update(overrides)
    return SimpleNamespace(published_at=published_at, **values)


def test_extract_metric_columns_maps_known_types():
    metrics = [
        {"type": "reactions", "name": "Reactions", "value": 12.0, "unit": "count"},
        {"type": "engagementRate", "name": "Eng. Rate", "value": 3.5, "unit": "percentage"},
    ]
    columns = extract_metric_columns(metrics)
    assert columns == {"reactions": 12.0, "engagement_rate": 3.5}


def test_extract_metric_columns_ignores_unknown_types():
    metrics = [{"type": "some_future_metric_type", "name": "?", "value": 1.0, "unit": "count"}]
    assert extract_metric_columns(metrics) == {}


def test_needs_sync_when_never_synced():
    assert needs_sync(existing=None, force=False) is True


def test_needs_sync_forced_even_if_fresh():
    fresh = SimpleNamespace(last_synced_at=datetime.now(timezone.utc))
    assert needs_sync(existing=fresh, force=True) is True


def test_needs_sync_false_within_threshold():
    recent = SimpleNamespace(last_synced_at=datetime.now(timezone.utc) - timedelta(hours=1), last_sync_error=None)
    assert needs_sync(existing=recent, force=False) is False


def test_needs_sync_true_past_threshold():
    stale_at = datetime.now(timezone.utc) - STALE_SYNC_THRESHOLD - timedelta(minutes=1)
    stale = SimpleNamespace(last_synced_at=stale_at, last_sync_error=None)
    assert needs_sync(existing=stale, force=False) is True


def test_needs_sync_true_when_last_attempt_recorded_an_error_even_if_fresh():
    just_synced_but_failed = SimpleNamespace(
        last_synced_at=datetime.now(timezone.utc), last_sync_error="Post not found for id: x"
    )
    assert needs_sync(existing=just_synced_but_failed, force=False) is True


def test_totals_dict_sums_plain_metrics():
    rows = [_metric_row(views=100.0), _metric_row(views=50.0), _metric_row(views=None)]
    totals = _totals_dict(rows)
    assert totals["views"] == 150.0


def test_totals_dict_averages_engagement_rate_not_sums():
    rows = [_metric_row(engagement_rate=10.0), _metric_row(engagement_rate=20.0)]
    totals = _totals_dict(rows)
    assert totals["engagement_rate"] == 15.0


def test_totals_dict_missing_metric_stays_none():
    rows = [_metric_row(), _metric_row()]
    totals = _totals_dict(rows)
    assert totals["views"] is None
    assert totals["engagement_rate"] is None


def test_impact_score_ignores_engagement_rate():
    totals = {"views": 100.0, "reactions": 10.0, "engagement_rate": 99.0}
    assert _impact_score(totals) == 110.0


def test_impact_score_treats_missing_as_zero():
    totals = {c: None for c in ALL_METRIC_COLUMNS}
    assert _impact_score(totals) == 0


def test_timeseries_buckets_by_month_and_sorts_chronologically():
    rows = [
        _metric_row(published_at=datetime(2026, 7, 15, tzinfo=timezone.utc), views=10.0),
        _metric_row(published_at=datetime(2026, 8, 1, tzinfo=timezone.utc), views=20.0),
        _metric_row(published_at=datetime(2026, 7, 20, tzinfo=timezone.utc), views=5.0),
    ]
    points = timeseries(rows, "month")
    assert [p["period"] for p in points] == ["2026-07", "2026-08"]
    assert points[0]["post_count"] == 2
    assert points[0]["totals"]["views"] == 15.0
    assert points[1]["post_count"] == 1
    assert points[1]["totals"]["views"] == 20.0


def test_timeseries_buckets_by_year():
    rows = [
        _metric_row(published_at=datetime(2025, 12, 1, tzinfo=timezone.utc), views=1.0),
        _metric_row(published_at=datetime(2026, 1, 1, tzinfo=timezone.utc), views=2.0),
    ]
    points = timeseries(rows, "year")
    assert [p["period"] for p in points] == ["2025", "2026"]


def test_timeseries_excludes_posts_with_no_published_at():
    rows = [_metric_row(published_at=None, views=1.0)]
    assert timeseries(rows, "month") == []


def test_platform_breakdown_groups_by_platform_and_sums_totals():
    rows = [
        _metric_row(platform="instagram", views=100.0),
        _metric_row(platform="instagram", views=50.0),
        _metric_row(platform="facebook", views=10.0),
    ]
    breakdown = _platform_breakdown(rows)
    assert [b["platform"] for b in breakdown] == ["facebook", "instagram"]
    facebook, instagram = breakdown
    assert facebook["post_count"] == 1
    assert facebook["totals"]["views"] == 10.0
    assert instagram["post_count"] == 2
    assert instagram["totals"]["views"] == 150.0


def test_platform_breakdown_never_exposes_row_identifiers():
    """Public-site aggregation must never carry a user/channel id or name -
    only platform, post_count and totals may leave _platform_breakdown."""
    rows = [_metric_row(platform="tiktok", views=1.0)]
    breakdown = _platform_breakdown(rows)
    assert set(breakdown[0].keys()) == {"platform", "post_count", "totals"}
