"""
Motore di sincronizzazione del modulo Statistiche (vedi docs/STATISTICS.md).

Design per consumare poche richieste verso Buffer:
- ogni post viene ri-scaricato al massimo una volta ogni STALE_SYNC_THRESHOLD
  (vedi statistics_service.needs_sync) - un secondo click su "Sincronizza"
  subito dopo il primo non genera nuove chiamate.
- la cadenza fra due richieste sulla STESSA connessione Buffer (stessa API key
  cliente) e' quella gia' configurata per la pubblicazione
  (PAUSE_BETWEEN_REQUESTS_SECONDS) - riusiamo lo stesso RateLimiter Redis
  (app/services/rate_limiter.py) di app/tasks/publication.py, cosi' il sync
  non compete mai con una campagna in corso di pubblicazione sulla stessa
  connessione.
- il worker Celery e' condiviso con la pubblicazione e l'omnichannel responder
  (worker -c 4 in produzione, docker-compose.prod.yml - -c 1 in sviluppo): un
  singolo task che scorresse centinaia di post con time.sleep() per il
  pacing bloccherebbe processi paralleli o, in dev, l'unico worker per
  l'intera durata del sync. Per questo la sincronizzazione di uno scope
  (utente/campagna/tutti) NON esegue un loop bloccante: dispatcha un task
  Celery indipendente per ogni post con un countdown scaglionato per
  connessione (vedi _dispatch_sync) - il worker resta libero di processare
  nel frattempo una pubblicazione in coda o un messaggio omnichannel in
  arrivo, invece di restare fermo ad aspettare. Essendo la concorrenza reale
  > 1 in produzione, l'incremento dei contatori su StatSyncRun usa un UPDATE
  SQL atomico (vedi sync_publication_metrics_task), non un semplice
  `+= 1` in ORM che perderebbe incrementi sotto esecuzione parallela.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy import update as sa_update

from app.core.config import settings
from app.core.security import EncryptionService
from app.db.session import SessionLocal
from app.integrations.buffer.exceptions import BufferApiError, BufferRateLimitError
from app.integrations.buffer.service import get_buffer_client
from app.models.publication import Publication
from app.models.statistics import StatMetricHistory, StatPostMetric, StatSyncRun
from app.services.rate_limiter import RateLimiter
from app.services.statistics_service import (
    ALL_METRIC_COLUMNS,
    eligible_publications,
    extract_metric_columns,
    needs_sync,
)
from app.workers.celery_app import celery

logger = get_task_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_buffer_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get_or_create_row(db, pub: Publication) -> StatPostMetric:
    row = db.query(StatPostMetric).filter(StatPostMetric.publication_id == pub.id).first()
    if row is None:
        row = StatPostMetric(
            publication_id=pub.id,
            campaign_id=pub.campaign_id,
            user_id=pub.user_id,
            social_channel_id=pub.social_channel_id,
            buffer_connection_id=pub.buffer_connection_id,
            platform=pub.social_channel.platform if pub.social_channel else "unknown",
            external_post_id=pub.external_post_id,
        )
        db.add(row)
        db.flush()
    return row


def _apply_metrics(db, pub: Publication, sync_run_id: uuid.UUID | None, result: dict[str, Any]) -> None:
    metrics: list[dict[str, Any]] = result.get("metrics", [])
    columns = extract_metric_columns(metrics)
    row = _get_or_create_row(db, pub)

    # Stesso backfill gia' fatto dagli endpoint di metriche live (campaigns.py/
    # publications.py): externalLink di Buffer spesso arriva vuoto subito dopo
    # la creazione del post e si popola solo in seguito.
    external_link = result.get("external_link")
    if external_link and not pub.external_post_url:
        pub.external_post_url = external_link

    now = utc_now()
    row.external_post_url = pub.external_post_url or row.external_post_url
    row.published_at = pub.published_at or pub.scheduled_at
    for column in ALL_METRIC_COLUMNS:
        if column in columns:
            setattr(row, column, columns[column])
    row.metrics_raw = metrics
    row.metrics_updated_at = _parse_buffer_datetime(result.get("metrics_updated_at"))
    row.last_synced_at = now
    row.last_sync_error = None
    row.last_sync_run_id = sync_run_id

    db.add(
        StatMetricHistory(
            publication_id=pub.id,
            synced_at=now,
            metrics_raw=metrics,
            **{c: columns.get(c) for c in ALL_METRIC_COLUMNS},
        )
    )


def _record_sync_error(db, pub: Publication, message: str) -> None:
    row = _get_or_create_row(db, pub)
    row.last_sync_error = message[:1000]


class SyncBusyError(Exception):
    """Raised when the Buffer connection is currently locked by another sync
    or publish job - the caller (statistics.py's single-post endpoint) turns
    this into a 429 asking the admin to retry shortly."""


def sync_publication_now(db, pub: Publication) -> StatPostMetric:
    """Synchronous single-post refresh for the per-row "aggiorna" button in
    the channel drill-down (bypasses the staleness guard - it's an explicit,
    single-post action). No StatSyncRun involved: one Buffer call, one HTTP
    request/response, same shape as the existing live metrics endpoints in
    campaigns.py/publications.py but persisted."""
    rate_limiter = RateLimiter()
    if not rate_limiter.acquire_lock(pub.buffer_connection_id):
        raise SyncBusyError("Connessione Buffer occupata da un'altra sincronizzazione, riprova tra poco.")

    try:
        client = get_buffer_client()
        token = EncryptionService.decrypt(pub.buffer_connection.access_token_encrypted) if pub.buffer_connection else ""
        if not token:
            raise BufferApiError("Connessione Buffer non disponibile", category="auth_error")

        result = client.get_post_metrics(token, pub.external_post_id)
        _apply_metrics(db, pub, sync_run_id=None, result=result)
        db.commit()
    except BufferRateLimitError as e:
        rate_limiter.pause_connection(pub.buffer_connection_id, duration_seconds=60)
        _record_sync_error(db, pub, str(e))
        db.commit()
        raise
    except Exception as e:
        _record_sync_error(db, pub, str(e))
        db.commit()
        raise
    finally:
        rate_limiter.release_lock(pub.buffer_connection_id)

    return db.query(StatPostMetric).filter(StatPostMetric.publication_id == pub.id).first()


@celery.task(name="app.tasks.statistics.sync_publication_metrics", bind=True, max_retries=20)
def sync_publication_metrics_task(self, publication_id_str: str, sync_run_id_str: str, force: bool = False) -> None:
    """Atomic unit: syncs one publication's metrics from Buffer and folds the
    result into the parent StatSyncRun counters. Same acquire/release-lock
    idiom as app.tasks.publication.process_publication_task."""
    db = SessionLocal()
    rate_limiter = RateLimiter()
    try:
        pub = db.query(Publication).filter(Publication.id == uuid.UUID(publication_id_str)).first()
        run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(sync_run_id_str)).first()
        if not pub or not run:
            logger.info("Publication or sync run missing, skipping (%s / %s)", publication_id_str, sync_run_id_str)
            return

        if not rate_limiter.acquire_lock(pub.buffer_connection_id):
            self.retry(countdown=settings.PAUSE_BETWEEN_REQUESTS_SECONDS)
            return

        synced = False
        try:
            client = get_buffer_client()
            token = EncryptionService.decrypt(pub.buffer_connection.access_token_encrypted) if pub.buffer_connection else ""
            if not token:
                raise BufferApiError("Connessione Buffer non disponibile", category="auth_error")

            result = client.get_post_metrics(token, pub.external_post_id)
            _apply_metrics(db, pub, run.id, result)
            synced = True
        except BufferRateLimitError as e:
            rate_limiter.pause_connection(pub.buffer_connection_id, duration_seconds=60)
            _record_sync_error(db, pub, str(e))
        except Exception as e:
            _record_sync_error(db, pub, str(e))
        finally:
            rate_limiter.release_lock(pub.buffer_connection_id)

        # Incremento atomico a livello di riga (UPDATE ... SET col = col + 1),
        # non un read-modify-write in Python: il worker di produzione gira a
        # concorrenza 4 (docker-compose.prod.yml, worker -c 4), quindi piu'
        # task di questo stesso sync run possono davvero incrementare i
        # contatori in parallelo - un semplice `run.synced_posts += 1` in
        # ORM perderebbe incrementi sotto concorrenza reale. Postgres
        # serializza gli UPDATE concorrenti sulla stessa riga via row lock,
        # quindi questo resta corretto qualunque sia la concorrenza del worker.
        db.execute(
            sa_update(StatSyncRun)
            .where(StatSyncRun.id == run.id)
            .values(
                synced_posts=StatSyncRun.synced_posts + (1 if synced else 0),
                failed_posts=StatSyncRun.failed_posts + (0 if synced else 1),
            )
        )
        db.commit()
        db.refresh(run)

        # Puo' capitare che due task dello stesso run soddisfino entrambi
        # questa condizione quasi insieme (es. gli ultimi due post finiscono
        # a pochi ms di distanza): innocuo, scrivono lo stesso stato finale -
        # a differenza dei contatori sopra, non serve un incremento atomico
        # per un valore idempotente.
        if run.synced_posts + run.failed_posts + run.skipped_posts >= run.total_posts:
            run.status = "completed" if run.failed_posts == 0 else "completed_with_errors"
            run.finished_at = utc_now()
            db.commit()
    finally:
        db.close()


def _dispatch_sync(db, run: StatSyncRun, publications: list[Publication], force: bool) -> None:
    run.total_posts = len(publications)
    run.status = "running"
    db.commit()

    # Scala la partenza di ogni post sulla stessa connessione Buffer di
    # PAUSE_BETWEEN_REQUESTS_SECONDS, ma lascia partire subito i post di
    # connessioni diverse (client diversi = API key diverse, nessun motivo di
    # farli aspettare l'uno per l'altro).
    next_slot: dict[uuid.UUID, int] = {}
    dispatched = 0

    for pub in publications:
        existing = db.query(StatPostMetric).filter(StatPostMetric.publication_id == pub.id).first()
        if not needs_sync(existing, force):
            run.skipped_posts += 1
            continue

        countdown = next_slot.get(pub.buffer_connection_id, 0)
        next_slot[pub.buffer_connection_id] = countdown + settings.PAUSE_BETWEEN_REQUESTS_SECONDS
        sync_publication_metrics_task.apply_async(
            args=[str(pub.id), str(run.id), force],
            countdown=countdown,
        )
        dispatched += 1

    if dispatched == 0:
        # Tutto gia' aggiornato di recente (o nessun post eleggibile): niente
        # da scaricare, il run si chiude subito senza toccare Buffer.
        run.status = "completed"
        run.finished_at = utc_now()

    db.commit()


@celery.task(name="app.tasks.statistics.sync_user_statistics")
def sync_user_statistics_task(sync_run_id_str: str, user_id_str: str, force: bool = False) -> None:
    db = SessionLocal()
    try:
        run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(sync_run_id_str)).first()
        if not run:
            return
        pubs = eligible_publications(db, user_id=uuid.UUID(user_id_str))
        _dispatch_sync(db, run, pubs, force)
    finally:
        db.close()


@celery.task(name="app.tasks.statistics.sync_campaign_statistics")
def sync_campaign_statistics_task(sync_run_id_str: str, campaign_id_str: str, force: bool = False) -> None:
    db = SessionLocal()
    try:
        run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(sync_run_id_str)).first()
        if not run:
            return
        pubs = eligible_publications(db, campaign_id=uuid.UUID(campaign_id_str))
        _dispatch_sync(db, run, pubs, force)
    finally:
        db.close()


@celery.task(name="app.tasks.statistics.sync_all_statistics")
def sync_all_statistics_task(sync_run_id_str: str, force: bool = False) -> None:
    db = SessionLocal()
    try:
        run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(sync_run_id_str)).first()
        if not run:
            return
        pubs = eligible_publications(db)
        _dispatch_sync(db, run, pubs, force)
    finally:
        db.close()
