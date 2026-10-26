"""
Le due email che il portale manda ai promoter, dal token al messaggio in coda.

Sta fra gli endpoint e il resto perche' ognuna di queste email e' tre cose messe
insieme - un token, un URL e un testo - e sono tre cose che devono restare
coerenti: se il percorso del link cambia qui cambia una volta sola, invece che in
ogni endpoint che manda quel messaggio.

Due dettagli non ovvi, entrambi voluti:

1. Queste funzioni fanno ``commit``. Il token deve essere scritto **prima** che
   il messaggio entri in coda: l'ordine inverso lascerebbe un worker libero di
   spedire un link che il database non conosce ancora, e l'utente veloce che lo
   clicca si sentirebbe dire che non e' valido.
2. Un intoppo nell'accodamento non propaga. Se Redis non risponde, la
   registrazione dell'utente resta valida e l'email si puo' richiedere di nuovo;
   far fallire la registrazione per un'email non partita significherebbe far
   ricreare l'account a chi ce l'ha gia'.
"""
import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services import auth_tokens
from app.services.email import templates

logger = logging.getLogger(__name__)


def _enqueue(*, to_address: str, to_name: Optional[str], rendered: tuple) -> bool:
    subject, html_body, text_body = rendered
    # Import locale: importare i task di Celery in testa al modulo tirerebbe
    # dentro il broker anche a chi importa questo file solo per i template (i
    # test, per dirne una).
    from app.tasks.email import send_transactional_email

    try:
        send_transactional_email.delay(
            to_address=to_address,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to_name=to_name,
        )
        return True
    # Volutamente ampia: qualunque cosa vada storta nell'accodamento, il chiamante
    # non deve accorgersene (vedi la nota in testa al modulo).
    except Exception as exc:
        logger.error("Email '%s' non accodata per %s: %s", subject, to_address, exc)
        return False


def send_welcome_verification(db: Session, user: User) -> bool:
    """
    Email di benvenuto con il link di conferma dell'indirizzo.

    A chi era iscritto prima che la conferma esistesse va la variante per chi
    c'era gia' (``User.verification_retroactive``): stesso link, stesso
    consenso, ma senza accoglierlo come se l'account fosse appena nato.

    Restituisce False quando l'utente ha gia' chiesto troppi link nell'ultima
    ora: il chiamante lo dice all'utente invece di far finta di aver spedito.
    """
    if auth_tokens.rate_limited(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION):
        logger.warning("Troppe richieste di conferma per l'utente %s", user.id)
        return False

    raw_token = auth_tokens.issue(
        db,
        user,
        auth_tokens.PURPOSE_EMAIL_VERIFICATION,
        timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
    )
    db.commit()

    verify_url = (
        f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/verify-email?token={quote(raw_token)}"
    )
    return _enqueue(
        to_address=user.email,
        to_name=user.name,
        rendered=templates.welcome_email(
            user_name=user.name,
            verify_url=verify_url,
            retroactive=user.verification_retroactive,
        ),
    )


def send_password_reset(db: Session, user: User) -> bool:
    """Email con il link per scegliere una nuova password."""
    if auth_tokens.rate_limited(db, user, auth_tokens.PURPOSE_PASSWORD_RESET):
        logger.warning("Troppe richieste di reset per l'utente %s", user.id)
        return False

    raw_token = auth_tokens.issue(
        db,
        user,
        auth_tokens.PURPOSE_PASSWORD_RESET,
        timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
    )
    db.commit()

    reset_url = (
        f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/reset-password?token={quote(raw_token)}"
    )
    return _enqueue(
        to_address=user.email,
        to_name=user.name,
        rendered=templates.password_reset_email(user_name=user.name, reset_url=reset_url),
    )


def send_channel_requirement_notice(
    user: User, connected_channels: list, required_channels: int
) -> bool:
    """
    Avviso "hai meno canali social di quanti il progetto ne richieda".

    Nessun token e nessun commit, a differenza delle due sopra: il link porta
    alla pagina dei canali del portale, dove l'utente entra con le proprie
    credenziali. ``connected_channels`` sono coppie (piattaforma, nome) gia'
    filtrate dal chiamante con la regola di idoneita' delle campagne
    (services/channel_requirement_service.py): qui si impagina e si accoda.
    """
    channels_url = f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/channels"
    return _enqueue(
        to_address=user.email,
        to_name=user.name,
        rendered=templates.channel_requirement_email(
            user_name=user.name,
            connected_channels=connected_channels,
            required_channels=required_channels,
            channels_url=channels_url,
        ),
    )
