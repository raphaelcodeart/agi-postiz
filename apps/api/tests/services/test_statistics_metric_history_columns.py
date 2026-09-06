"""
Regression test for a real production bug (2026-08-26): stat_metric_history was
missing 3 of the 9 columns in ALL_METRIC_COLUMNS (likes, impressions, reach),
so _apply_metrics's **{c: columns.get(c) for c in ALL_METRIC_COLUMNS} unpacking
into StatMetricHistory(...) raised an unhandled TypeError on every single post
sync - even though the same unpacking into StatPostMetric (which does have all
the columns) had already succeeded a few lines above. This asserts both models
accept every column in ALL_METRIC_COLUMNS as a constructor kwarg, so a future
new metric type added to one without the other fails a test instead of prod.
"""
from app.models.statistics import StatMetricHistory, StatPostMetric
from app.services.statistics_service import ALL_METRIC_COLUMNS


def test_stat_post_metric_accepts_every_metric_column_kwarg():
    StatPostMetric(**{c: 1.0 for c in ALL_METRIC_COLUMNS})


def test_stat_metric_history_accepts_every_metric_column_kwarg():
    StatMetricHistory(**{c: 1.0 for c in ALL_METRIC_COLUMNS})
