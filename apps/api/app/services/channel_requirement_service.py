"""
Requisito "almeno N canali social collegati" per promoter.

Il progetto chiede a ogni promoter almeno ``settings.MIN_SOCIAL_CHANNELS_PER_USER``
canali social collegati e utilizzabili. Questo modulo risponde a due domande
dell'amministratore - chi e' sotto soglia, e chi e' gia' stato avvisato - e
spedisce l'avviso, uno alla volta o a tutti.

Cosa conta come "canale collegato": esattamente quello che una campagna
potrebbe usare, cioe' la stessa regola di ``campaign_resolver`` (connessione
``connected``, canale ``is_active``, non rimosso dall'utente, ``publication_mode``
diverso da ``disabled``). Un canale scollegato lato provider, o spento
dall'utente, non conta: avvisare qualcuno che ha due canali di cui uno morto
sarebbe corretto, non avvisarlo sarebbe un buco. Un canale segnalato come
duplicato e' forzato ``is_active=False`` da tasks/sync.py e quindi escluso da
solo, senza una regola a parte.

Il conteggio si fa in SQL per tutti gli utenti insieme (una GROUP BY), non
utente per utente: la pagina elenca potenzialmente ogni promoter della
piattaforma e un N+1 qui si sentirebbe subito.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.administrator import Administrator
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.user import User
from app.models.user_notification import KIND_CHANNEL_REQUIREMENT, UserNotification
from app.services import portal_emails

logger = logging.getLogger(__name__)


def required_channels() -> int:
    return settings.MIN_SOCIAL_CHANNELS_PER_USER


def cooldown_days() -> int:
    return settings.CHANNEL_NOTICE_COOLDOWN_DAYS


def _usable_channels_query(db: Session):
    """Canali che una campagna potrebbe usare, con l'utente a cui appartengono."""
    return (
        db.query(BufferConnection.user_id, SocialChannel.platform, SocialChannel.name)
        .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
        .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
        .filter(
            BufferConnection.status == "connected",
            SocialChannel.is_active.is_(True),
            SocialChannel.deleted_at.is_(None),
            SocialChannel.publication_mode != "disabled",
        )
    )


def usable_channels_by_user(
    db: Session, user_ids: Optional[List[uuid.UUID]] = None
) -> Dict[uuid.UUID, List[Tuple[str, str]]]:
    """``{user_id: [(piattaforma, nome), ...]}`` - assente = zero canali."""
    query = _usable_channels_query(db)
    if user_ids is not None:
        if not user_ids:
            return {}
        query = query.filter(BufferConnection.user_id.in_(user_ids))
    result: Dict[uuid.UUID, List[Tuple[str, str]]] = {}
    for user_id, platform, name in query.order_by(SocialChannel.platform, SocialChannel.name).all():
        result.setdefault(user_id, []).append((platform, name))
    return result


def _last_notices(db: Session, user_ids: List[uuid.UUID]) -> Dict[uuid.UUID, Tuple[datetime, int]]:
    """``{user_id: (ultimo invio, numero di invii)}`` per questo tipo di avviso."""
    if not user_ids:
        return {}
    rows = (
        db.query(
            UserNotification.user_id,
            func.max(UserNotification.sent_at),
            func.count(UserNotification.id),
        )
        .filter(
            UserNotification.kind == KIND_CHANNEL_REQUIREMENT,
            UserNotification.user_id.in_(user_ids),
        )
        .group_by(UserNotification.user_id)
        .all()
    )
    return {user_id: (last, count) for user_id, last, count in rows}


@dataclass
class UserBelowRequirement:
    user: User
    connected_channels: List[Tuple[str, str]] = field(default_factory=list)
    last_notified_at: Optional[datetime] = None
    notifications_count: int = 0

    @property
    def connected_count(self) -> int:
        return len(self.connected_channels)


def list_users_below_requirement(
    db: Session,
    *,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> List[UserBelowRequirement]:
    """
    Gli utenti (non cancellati) con meno canali utilizzabili del richiesto.

    Senza ``status_filter`` include anche inattivi e sospesi: la pagina mostra
    lo stato accanto a ogni nome e lascia all'amministratore la scelta di chi
    avvisare. Ordinati per numero di canali (prima chi non ne ha nessuno) e poi
    per nome.
    """
    query = db.query(User).filter(User.deleted_at.is_(None))
    if status_filter:
        query = query.filter(User.status == status_filter)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(User.name.ilike(pattern), User.email.ilike(pattern), User.company_name.ilike(pattern))
        )
    users = query.order_by(User.name).all()
    if not users:
        return []

    user_ids = [u.id for u in users]
    channels = usable_channels_by_user(db, user_ids)
    threshold = required_channels()
    below = [u for u in users if len(channels.get(u.id, [])) < threshold]
    notices = _last_notices(db, [u.id for u in below])

    rows = []
    for user in below:
        last, count = notices.get(user.id, (None, 0))
        rows.append(
            UserBelowRequirement(
                user=user,
                connected_channels=channels.get(user.id, []),
                last_notified_at=last,
                notifications_count=count,
            )
        )
    rows.sort(key=lambda r: (r.connected_count, r.user.name.lower()))
    return rows


def count_users_below_requirement(db: Session) -> int:
    """Per il contatore sulla lista Utenti: solo utenti attivi, quelli che le campagne cercano."""
    return len(list_users_below_requirement(db, status_filter="active"))


class EmailDisabledError(RuntimeError):
    """SMTP non configurato: l'avviso non puo' partire e non va registrato."""


def notify_user(db: Session, user: User, admin: Administrator) -> UserNotification:
    """
    Spedisce l'avviso a un utente e ne registra l'invio.

    Sempre, anche se l'utente e' stato avvisato un minuto fa: il pulsante
    singolo e' una scelta esplicita dell'amministratore su una persona precisa,
    il cooldown vale solo per l'invio a tutti. Non controlla la soglia: chi
    chiama ha appena visto la lista, e un utente che nel frattempo ha
    collegato il secondo canale riceve un messaggio che gli dice che ora e' a
    posto, non un errore.
    """
    if not settings.email_enabled:
        raise EmailDisabledError(
            "Invio email non configurato (SMTP_HOST / EMAIL_FROM_ADDRESS): nessun avviso inviato."
        )

    channels = usable_channels_by_user(db, [user.id]).get(user.id, [])
    threshold = required_channels()
    queued = portal_emails.send_channel_requirement_notice(user, channels, threshold)
    if not queued:
        # _enqueue ha gia' loggato: qui si trasforma in un errore per il
        # chiamante, perche' un avviso non accodato non va registrato come
        # inviato.
        raise RuntimeError("Email non accodata: coda dei task non raggiungibile.")

    notice = UserNotification(
        user_id=user.id,
        kind=KIND_CHANNEL_REQUIREMENT,
        sent_by_administrator_id=admin.id,
        email=user.email,
        metadata_json={
            "connected_channels": len(channels),
            "required_channels": threshold,
            "platforms": [platform for platform, _ in channels],
        },
    )
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return notice


@dataclass
class BulkNotifyResult:
    sent: List[uuid.UUID] = field(default_factory=list)
    skipped_recent: List[uuid.UUID] = field(default_factory=list)
    failed: List[uuid.UUID] = field(default_factory=list)


def notify_all(
    db: Session,
    admin: Administrator,
    *,
    status_filter: Optional[str] = "active",
    skip_notified_within_days: Optional[int] = None,
) -> BulkNotifyResult:
    """
    Avvisa tutti gli utenti sotto soglia, saltando chi e' stato avvisato da poco.

    ``skip_notified_within_days`` a 0 disattiva il cooldown (l'amministratore
    lo chiede esplicitamente dalla dashboard); None usa il valore configurato.
    Un errore su un destinatario non ferma gli altri: l'esito dice chi ha
    ricevuto, chi e' stato saltato e per chi e' andata male.
    """
    if not settings.email_enabled:
        raise EmailDisabledError(
            "Invio email non configurato (SMTP_HOST / EMAIL_FROM_ADDRESS): nessun avviso inviato."
        )

    days = cooldown_days() if skip_notified_within_days is None else skip_notified_within_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None

    result = BulkNotifyResult()
    for row in list_users_below_requirement(db, status_filter=status_filter):
        if cutoff and row.last_notified_at and row.last_notified_at >= cutoff:
            result.skipped_recent.append(row.user.id)
            continue
        try:
            notify_user(db, row.user, admin)
            result.sent.append(row.user.id)
        except Exception as exc:
            logger.error("Avviso canali non inviato a %s: %s", row.user.id, exc)
            db.rollback()
            result.failed.append(row.user.id)
    return result
