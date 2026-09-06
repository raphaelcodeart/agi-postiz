"""
Modulo Statistiche - tabelle isolate (prefisso `stat_`), separate dal resto
dello schema: l'unico aggancio verso le tabelle esistenti sono le foreign key
verso publications/campaigns/users/social_channels/buffer_connections, tutte
usate in sola lettura. Nessuna relationship viene aggiunta sui modelli
esistenti (User, Campaign, Publication, SocialChannel) - vedi docs/STATISTICS.md.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class StatSyncRun(Base):
    """
    Una riga per ogni sincronizzazione lanciata (bottone "Sincronizza" a uno
    dei 3 livelli). Alimenta la UI di progresso e l'etichetta "Ultima
    sincronizzazione" mostrata a ogni livello della dashboard Statistiche.
    """
    __tablename__ = "stat_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # global, user, campaign
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope_campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True)

    # queued, running, completed, completed_with_errors, failed
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    total_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    synced_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Post saltati perche' sincronizzati di recente (guardia anti-spreco, vedi
    # docs/STATISTICS.md) - non e' un errore, solo un post gia' aggiornato.
    skipped_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_stat_sync_runs_scope_user", "scope_user_id"),
        Index("idx_stat_sync_runs_scope_campaign", "scope_campaign_id"),
        Index("idx_stat_sync_runs_started_at", "started_at"),
    )


class StatPostMetric(Base):
    """
    Ultimo snapshot noto delle metriche Buffer per una pubblicazione (1:1 con
    Publication). user_id/social_channel_id/campaign_id/buffer_connection_id
    sono denormalizzati da Publication per rendere le aggregazioni (totali per
    utente/canale/campagna) query dirette senza join multipli.
    """
    __tablename__ = "stat_post_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    social_channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("social_channels.id", ondelete="CASCADE"), nullable=False)
    buffer_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buffer_connections.id", ondelete="CASCADE"), nullable=False)

    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_post_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Colonne denormalizzate per le metriche piu' comuni (vedi
    # lib/metric-config.ts sul frontend per l'elenco completo dei tipi noti) -
    # permettono SUM/ORDER BY via SQL senza dover deserializzare il JSONB.
    # Nullable: non ogni piattaforma riporta ogni tipo di metrica.
    reactions: Mapped[float | None] = mapped_column(Float, nullable=True)
    likes: Mapped[float | None] = mapped_column(Float, nullable=True)
    views: Mapped[float | None] = mapped_column(Float, nullable=True)
    impressions: Mapped[float | None] = mapped_column(Float, nullable=True)
    reach: Mapped[float | None] = mapped_column(Float, nullable=True)
    follows: Mapped[float | None] = mapped_column(Float, nullable=True)
    clicks: Mapped[float | None] = mapped_column(Float, nullable=True)
    comments: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Percentuale (0-100) - non va mai sommata tra canali, solo mediata (stessa
    # regola gia' applicata in app/api/v1/campaigns.py::get_campaign_metrics).
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Payload grezzo completo cosi' com'e' arrivato da Buffer (PostMetric[]),
    # per non perdere tipi di metrica futuri/non ancora mappati sopra.
    metrics_raw: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # metricsUpdatedAt di Buffer stesso (quando Buffer ha calcolato questi
    # valori), distinto da last_synced_at (quando NOI li abbiamo scaricati).
    metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_sync_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stat_sync_runs.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("publication_id", name="uq_stat_post_metrics_publication"),
        Index("idx_stat_post_metrics_user_id", "user_id"),
        Index("idx_stat_post_metrics_campaign_id", "campaign_id"),
        Index("idx_stat_post_metrics_social_channel_id", "social_channel_id"),
        Index("idx_stat_post_metrics_last_synced_at", "last_synced_at"),
    )


class StatMetricHistory(Base):
    """
    Storico append-only: una riga per ogni sync riuscito di un post (oltre
    all'ultimo snapshot in StatPostMetric). Costo trascurabile per riga, ma
    abilita in futuro grafici di andamento nel tempo senza dover ridisegnare
    lo schema - non ancora usato dalla UI v1.
    """
    __tablename__ = "stat_metric_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Stesso identico set di colonne di StatPostMetric sopra (vedi
    # ALL_METRIC_COLUMNS in statistics_service.py): _apply_metrics
    # (app/tasks/statistics.py) scrive entrambe le righe da un unico
    # **{c: columns.get(c) for c in ALL_METRIC_COLUMNS}, quindi le due tabelle
    # devono restare in sync sulle colonne o quella chiamata solleva un
    # TypeError non gestito (bug reale osservato in produzione il 2026-08-26:
    # "likes"/"impressions"/"reach" mancavano qui, causando un 500 sul
    # refresh di ogni post pur avendo gia' scritto le metriche corrette su
    # StatPostMetric un attimo prima - vedi git blame per il fix).
    reactions: Mapped[float | None] = mapped_column(Float, nullable=True)
    likes: Mapped[float | None] = mapped_column(Float, nullable=True)
    views: Mapped[float | None] = mapped_column(Float, nullable=True)
    impressions: Mapped[float | None] = mapped_column(Float, nullable=True)
    reach: Mapped[float | None] = mapped_column(Float, nullable=True)
    follows: Mapped[float | None] = mapped_column(Float, nullable=True)
    clicks: Mapped[float | None] = mapped_column(Float, nullable=True)
    comments: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_raw: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_stat_metric_history_publication_synced", "publication_id", "synced_at"),
    )
