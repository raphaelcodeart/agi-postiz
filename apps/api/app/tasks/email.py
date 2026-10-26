"""
Invio asincrono delle email di sistema.

Perche' passare da Celery e non spedire dentro la richiesta HTTP: una connessione
SMTP puo' metterci secondi, e ogni secondo li aspetterebbe l'utente fermo sul
pulsante "Crea il mio account". Peggio ancora, un server di posta lento o
temporaneamente irraggiungibile farebbe fallire una registrazione che era invece
andata a buon fine - l'account c'e', ma l'utente vede un errore e ne crea un
altro. Scrivere l'utente e spedirgli l'email sono due cose con affidabilita'
diverse, e vanno separate.

I due tipi di errore si trattano in modo opposto, ed e' il motivo per cui il
task li distingue invece di catturare Exception:

- SMTP non configurato: ritentare non cambia niente. Finisce nei log come errore
  (in produzione lo e' davvero) e il task si ferma.
- consegna fallita: quasi sempre passeggero. Si ritenta con attese crescenti.

Il contenuto del messaggio non viene mai registrato: contiene i link di conferma
e di reset, che sono credenziali a tutti gli effetti (AGENTS.md regola 10).
"""
from typing import Optional

from celery.utils.log import get_task_logger

from app.services.email import (
    EmailDeliveryError,
    EmailNotConfiguredError,
    send_email,
)
from app.services.email.templates import logo_image
from app.workers.celery_app import celery

logger = get_task_logger(__name__)


@celery.task(
    name="app.tasks.email.send_transactional_email",
    bind=True,
    max_retries=4,
    # 1, 5, 15 e 45 minuti: un server di posta che non risponde da tre quarti
    # d'ora non e' un intoppo, e continuare a bussare non aiuta nessuno.
    retry_backoff=60,
    retry_backoff_max=2700,
    retry_jitter=True,
)
def send_transactional_email(
    self,
    to_address: str,
    subject: str,
    html_body: str,
    text_body: str,
    to_name: Optional[str] = None,
    with_logo: bool = True,
) -> None:
    logo = logo_image() if with_logo else None

    try:
        send_email(
            to_address=to_address,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to_name=to_name,
            inline_images=[logo] if logo else (),
        )
    except EmailNotConfiguredError as exc:
        logger.error("Email non inviata: %s", exc)
        return
    except EmailDeliveryError as exc:
        logger.warning(
            "Consegna a %s fallita (tentativo %s/%s): %s",
            to_address,
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        raise self.retry(exc=exc)
