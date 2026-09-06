"""
Logica di sola-lettura e di supporto al sync per il modulo Statistiche (vedi
docs/STATISTICS.md). Le chiamate reali a Buffer e l'orchestrazione
Celery/RateLimiter vivono in app/tasks/statistics.py, che usa gli helper di
questo file per decidere cosa sincronizzare e come scrivere il risultato.
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign
from app.models.publication import Publication
from app.models.statistics import StatPostMetric
from app.models.user import User

# Mappa tipo-metrica Buffer -> colonna denormalizzata su StatPostMetric /
# StatMetricHistory. Stessi tipi noti gia' elencati in
# apps/dashboard/lib/metric-config.ts (tenere allineati se cambia uno dei due).
METRIC_TYPE_TO_COLUMN: dict[str, str] = {
    "reactions": "reactions",
    "likes": "likes",
    "views": "views",
    "impressions": "impressions",
    "reach": "reach",
    "follows": "follows",
    "clicks": "clicks",
    "comments": "comments",
    "shares": "shares",
    "engagementRate": "engagement_rate",
}

# Solo engagementRate e' una percentuale (0-100): va mediata, mai sommata tra
# canali/post - stessa regola gia' applicata in app/api/v1/campaigns.py.
PERCENTAGE_METRIC_TYPES = {"engagementRate"}

# Buffer aggiorna le metriche una volta al giorno (vedi
# app/integrations/buffer/client.py) - non ha senso ri-scaricare un post
# sincronizzato meno di questo tempo fa durante un sync di scope ampio
# (utente/campagna/tutti). Il refresh del singolo post bypassa questa guardia
# perche' e' un'azione esplicita dell'amministratore su un solo post.
STALE_SYNC_THRESHOLD = timedelta(hours=20)

NUMERIC_METRIC_COLUMNS = [c for c in METRIC_TYPE_TO_COLUMN.values() if c != "engagement_rate"]
ALL_METRIC_COLUMNS = NUMERIC_METRIC_COLUMNS + ["engagement_rate"]


def extract_metric_columns(metrics: list[dict[str, Any]]) -> dict[str, float]:
    """Turns Buffer's raw metrics list into a {column_name: value} dict for
    known types. Unknown types are dropped here but preserved as-is in the
    metrics_raw JSONB column by the caller."""
    result: dict[str, float] = {}
    for m in metrics:
        column = METRIC_TYPE_TO_COLUMN.get(m.get("type", ""))
        if column:
            result[column] = m.get("value")
    return result


def needs_sync(existing: StatPostMetric | None, force: bool) -> bool:
    """Whether a publication should be (re)fetched from Buffer right now.

    A row left with a recorded last_sync_error is always eligible, regardless
    of last_synced_at: the staleness guard exists to avoid re-downloading
    metrics that already succeeded recently, not to lock in a failure for the
    next STALE_SYNC_THRESHOLD (real incident, 2026-08-26 - a since-fixed bug
    made every post's sync attempt record an error right after last_synced_at
    was already stamped, so a plain "Sincronizza tutto" wouldn't have retried
    any of them for another ~20h even though every one of them needed it).
    """
    if force or existing is None or existing.last_synced_at is None:
        return True
    if existing.last_sync_error is not None:
        return True
    return datetime.now(UTC) - existing.last_synced_at > STALE_SYNC_THRESHOLD


def eligible_publications(
    db: Session, *, user_id: uuid.UUID | None = None, campaign_id: uuid.UUID | None = None
) -> list[Publication]:
    """Publications that can carry real Buffer metrics: sent successfully and
    carrying a real external_post_id - same filter already used by the live
    metrics endpoints in campaigns.py/publications.py."""
    query = db.query(Publication).filter(
        Publication.status.in_(["published", "scheduled"]),
        Publication.external_post_id.isnot(None),
    )
    if user_id is not None:
        query = query.filter(Publication.user_id == user_id)
    if campaign_id is not None:
        query = query.filter(Publication.campaign_id == campaign_id)
    return query.all()


def _totals_dict(rows: Sequence[Any]) -> dict[str, float | None]:
    """Aggregates a list of ORM rows (StatPostMetric or an aggregate query
    result) exposing the metric columns: sums plain counts, averages the
    percentage ones. A metric absent from every row stays None (not 0), same
    convention as CampaignMetricsResponse.totals."""
    totals: dict[str, float | None] = {}
    for column in NUMERIC_METRIC_COLUMNS:
        values = [getattr(r, column) for r in rows if getattr(r, column) is not None]
        totals[column] = sum(values) if values else None
    values = [r.engagement_rate for r in rows if r.engagement_rate is not None]
    totals["engagement_rate"] = (sum(values) / len(values)) if values else None
    return totals


def _impact_score(totals: dict[str, float | None]) -> float:
    """Sums every non-percentage total into one number, used only to rank
    users/channels in the dashboard - never shown to the admin as a metric of
    its own, since blending different metric types (views+likes+...) has no
    real-world unit."""
    return sum(v for k, v in totals.items() if k != "engagement_rate" and v is not None)


def timeseries(rows: Sequence[Any], granularity: str) -> list[dict[str, Any]]:
    """Buckets rows (StatPostMetric) into a monthly ("YYYY-MM") or annual
    ("YYYY") trend, keyed by each post's published_at - i.e. when the content
    went out, not when we last synced its metrics from Buffer. Posts with no
    published_at yet (still queued/scheduled with an unknown date) are
    excluded - there's no meaningful bucket for them. Reuses _totals_dict for
    each bucket's aggregation, so the sum-vs-average-per-metric rule (see
    module docstring) is identical to every other totals computation here.
    Returns buckets sorted chronologically, oldest first - ready to feed a
    chart's x-axis in order without the caller re-sorting.
    """
    fmt = "%Y-%m" if granularity == "month" else "%Y"
    buckets: dict[str, list[Any]] = {}
    for row in rows:
        if row.published_at is None:
            continue
        key = row.published_at.strftime(fmt)
        buckets.setdefault(key, []).append(row)

    return [
        {"period": key, "post_count": len(buckets[key]), "totals": _totals_dict(buckets[key])}
        for key in sorted(buckets.keys())
    ]


def _platform_breakdown(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """Groups metric rows by platform - post count + totals only, no
    user/channel identifier ever included. Used by build_public_summary
    (app/api/v1/public_stats.py) so the public marketing site's chart never
    sees anything more granular than "this platform, this many posts, these
    totals"."""
    by_platform: dict[str, list[Any]] = {}
    for row in rows:
        by_platform.setdefault(row.platform, []).append(row)
    return [
        {"platform": platform, "post_count": len(platform_rows), "totals": _totals_dict(platform_rows)}
        for platform, platform_rows in sorted(by_platform.items())
    ]


def build_public_summary(db: Session) -> dict[str, Any]:
    """Anonymous, aggregate-only snapshot for the public marketing site
    (agimarketing.app) - see app/api/v1/public_stats.py. Deliberately never
    touches User/SocialChannel names or ids: only platform-level totals and
    plain counts leave this function."""
    rows = db.query(StatPostMetric).all()
    campaign_count = db.query(Campaign).filter(Campaign.status == "completed").count()
    channel_count = db.query(SocialChannel).filter(SocialChannel.is_active.is_(True)).count()
    active_user_count = (
        db.query(User).filter(User.status == "active", User.deleted_at.is_(None)).count()
    )
    last_synced_at = max(
        (r.last_synced_at for r in rows if r.last_synced_at is not None), default=None
    )

    return {
        "post_count": len(rows),
        "campaign_count": campaign_count,
        "channel_count": channel_count,
        "active_user_count": active_user_count,
        "totals": _totals_dict(rows),
        "platforms": _platform_breakdown(rows),
        "last_synced_at": last_synced_at,
    }


def build_dashboard(db: Session) -> dict[str, Any]:
    rows = (
        db.query(StatPostMetric, User.name, User.company_name)
        .join(User, User.id == StatPostMetric.user_id)
        .all()
    )
    metrics_rows = [r[0] for r in rows]
    totals = _totals_dict(metrics_rows)

    by_user: dict[uuid.UUID, dict[str, Any]] = {}
    channels_seen: set = set()
    platform_counts: dict[str, set] = {}

    for metric, user_name, company_name in rows:
        bucket = by_user.setdefault(
            metric.user_id,
            {"user_name": user_name, "company_name": company_name, "rows": [], "channels": set()},
        )
        bucket["rows"].append(metric)
        bucket["channels"].add(metric.social_channel_id)
        channels_seen.add(metric.social_channel_id)
        platform_counts.setdefault(metric.platform, set()).add(metric.social_channel_id)

    users = []
    for user_id, bucket in by_user.items():
        user_totals = _totals_dict(bucket["rows"])
        last_synced = max(
            (r.last_synced_at for r in bucket["rows"] if r.last_synced_at is not None), default=None
        )
        users.append(
            {
                "user_id": user_id,
                "user_name": bucket["user_name"],
                "company_name": bucket["company_name"],
                "channel_count": len(bucket["channels"]),
                "post_count": len(bucket["rows"]),
                "totals": user_totals,
                "last_synced_at": last_synced,
                "_score": _impact_score(user_totals),
            }
        )
    users.sort(key=lambda u: (u["_score"], u["post_count"]), reverse=True)
    for u in users:
        del u["_score"]

    last_synced_at = max(
        (m.last_synced_at for m in metrics_rows if m.last_synced_at is not None), default=None
    )

    return {
        "totals": totals,
        "user_count": len(by_user),
        "channel_count": len(channels_seen),
        "post_count": len(metrics_rows),
        "platform_distribution": {p: len(chs) for p, chs in platform_counts.items()},
        "users": users,
        "last_synced_at": last_synced_at,
        "timeseries_monthly": timeseries(metrics_rows, "month"),
        "timeseries_yearly": timeseries(metrics_rows, "year"),
    }


def build_user_detail(db: Session, user_id: uuid.UUID) -> dict[str, Any] | None:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        return None

    rows = (
        db.query(StatPostMetric, SocialChannel.name, SocialChannel.username, SocialChannel.platform)
        .join(SocialChannel, SocialChannel.id == StatPostMetric.social_channel_id)
        .filter(StatPostMetric.user_id == user_id)
        .all()
    )
    metrics_rows = [r[0] for r in rows]

    by_channel: dict[uuid.UUID, dict[str, Any]] = {}
    for metric, channel_name, username, platform in rows:
        bucket = by_channel.setdefault(
            metric.social_channel_id,
            {"channel_name": channel_name, "username": username, "platform": platform, "rows": []},
        )
        bucket["rows"].append(metric)

    channels = []
    for channel_id, bucket in by_channel.items():
        channel_totals = _totals_dict(bucket["rows"])
        last_synced = max(
            (r.last_synced_at for r in bucket["rows"] if r.last_synced_at is not None), default=None
        )
        channels.append(
            {
                "social_channel_id": channel_id,
                "channel_name": bucket["channel_name"],
                "username": bucket["username"],
                "platform": bucket["platform"],
                "post_count": len(bucket["rows"]),
                "totals": channel_totals,
                "last_synced_at": last_synced,
                "_score": _impact_score(channel_totals),
            }
        )
    channels.sort(key=lambda c: (c["_score"], c["post_count"]), reverse=True)
    for c in channels:
        del c["_score"]

    last_synced_at = max(
        (m.last_synced_at for m in metrics_rows if m.last_synced_at is not None), default=None
    )

    return {
        "user_id": user.id,
        "user_name": user.name,
        "company_name": user.company_name,
        "totals": _totals_dict(metrics_rows),
        "channels": channels,
        "last_synced_at": last_synced_at,
        "timeseries_monthly": timeseries(metrics_rows, "month"),
        "timeseries_yearly": timeseries(metrics_rows, "year"),
    }


def build_channel_detail(
    db: Session, user_id: uuid.UUID, channel_id: uuid.UUID
) -> dict[str, Any] | None:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    # Verifica che il canale appartenga davvero a questo utente (stesso join
    # gia' usato in app/api/v1/buffer.py::list_channels), non solo che esista.
    channel = (
        db.query(SocialChannel)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(SocialChannel.id == channel_id, BufferConnection.user_id == user_id)
        .first()
    )
    if not user or not channel:
        return None

    rows = (
        db.query(StatPostMetric, Campaign.title)
        .join(Campaign, Campaign.id == StatPostMetric.campaign_id)
        .filter(StatPostMetric.user_id == user_id, StatPostMetric.social_channel_id == channel_id)
        .order_by(StatPostMetric.published_at.desc().nullslast())
        .all()
    )
    metrics_rows = [r[0] for r in rows]

    posts = [
        {
            "publication_id": metric.publication_id,
            "campaign_id": metric.campaign_id,
            "campaign_title": campaign_title,
            "platform": metric.platform,
            "external_post_url": metric.external_post_url,
            "published_at": metric.published_at,
            "metrics": {c: getattr(metric, c) for c in ALL_METRIC_COLUMNS},
            "last_synced_at": metric.last_synced_at,
            "last_sync_error": metric.last_sync_error,
        }
        for metric, campaign_title in rows
    ]

    last_synced_at = max(
        (m.last_synced_at for m in metrics_rows if m.last_synced_at is not None), default=None
    )

    return {
        "social_channel_id": channel.id,
        "channel_name": channel.name,
        "username": channel.username,
        "platform": channel.platform,
        "user_id": user.id,
        "user_name": user.name,
        "totals": _totals_dict(metrics_rows),
        "posts": posts,
        "last_synced_at": last_synced_at,
        "timeseries_monthly": timeseries(metrics_rows, "month"),
        "timeseries_yearly": timeseries(metrics_rows, "year"),
    }
