"""
Invio SMTP delle email di sistema.

Solo stdlib (``smtplib`` + ``email.message``): mandare due messaggi a testa a chi
si registra non giustifica una dipendenza in piu' nell'immagine dell'API, e
smtplib fa esattamente questo lavoro da vent'anni.

Da non confondere con
``app/integrations/omnichannel/connectors/gmail.py``: quello spedisce *per conto
del cliente*, con le credenziali della sua casella, come risposta a una
conversazione. Questo spedisce *come AGI Post*, con la casella di servizio. Due
mittenti, due configurazioni, nessun codice in comune di proposito - unirli
vorrebbe dire che un errore di configurazione del secondo manda email di sistema
dall'indirizzo di un cliente.

Riservatezza (AGENTS.md regola 10): qui non si registra mai la password SMTP ne'
il contenuto del messaggio, che per definizione contiene i link segreti di
conferma e di reset. Nei log finiscono solo destinatario e oggetto.
"""
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional, Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """SMTP non configurato: il messaggio non e' stato nemmeno tentato."""


class EmailDeliveryError(RuntimeError):
    """Il server SMTP ha rifiutato il messaggio o e' irraggiungibile."""


@dataclass(frozen=True)
class InlineImage:
    """
    Immagine incorporata nel messaggio e referenziata dall'HTML via ``cid:``.

    Allegata invece che linkata a un URL pubblico per due motivi: il logo si vede
    anche con il caricamento delle immagini remote disattivato, e un'immagine
    remota in un'email e' indistinguibile da un pixel di tracciamento - sia per
    chi la riceve sia per i filtri antispam.
    """

    cid: str           # senza parentesi angolari: e' la forma usata nell'HTML
    content: bytes
    subtype: str = "png"


def is_enabled() -> bool:
    return settings.email_enabled


def _connect() -> smtplib.SMTP:
    context = ssl.create_default_context()

    if settings.SMTP_USE_SSL:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
            context=context,
        )
    else:
        smtp = smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
        )
        smtp.ehlo()
        # STARTTLS non negoziabile: se il server non lo offre si interrompe qui
        # invece di autenticarsi in chiaro. Un provider che non supporta TLS sulla
        # 587 e' un provider da cambiare, non un caso da gestire.
        if not smtp.has_extn("starttls"):
            smtp.close()
            raise EmailDeliveryError(
                f"{settings.SMTP_HOST}:{settings.SMTP_PORT} non offre STARTTLS; "
                "invio interrotto per non trasmettere le credenziali in chiaro."
            )
        smtp.starttls(context=context)
        smtp.ehlo()

    if settings.SMTP_USERNAME:
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

    return smtp


def send_email(
    *,
    to_address: str,
    subject: str,
    html_body: str,
    text_body: str,
    to_name: Optional[str] = None,
    inline_images: Sequence[InlineImage] = (),
) -> None:
    """
    Spedisce un messaggio multipart (testo + HTML + immagini incorporate).

    Solleva ``EmailNotConfiguredError`` se manca la configurazione e
    ``EmailDeliveryError`` se l'invio fallisce: due casi distinti perche' il
    chiamante deve trattarli in modo diverso - il primo non migliora ritentando,
    il secondo spesso si'.
    """
    if not is_enabled():
        raise EmailNotConfiguredError(
            "SMTP non configurato (SMTP_HOST / EMAIL_FROM_ADDRESS): "
            f"email '{subject}' non inviata a {to_address}."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS))
    message["To"] = formataddr((to_name, to_address)) if to_name else to_address
    if settings.EMAIL_REPLY_TO:
        message["Reply-To"] = settings.EMAIL_REPLY_TO
    # Message-ID esplicito, ancorato al dominio del mittente: senza, alcuni
    # server ne generano uno con il nome host del container, che non esiste
    # nel DNS pubblico e costa punti nei filtri antispam.
    message["Message-ID"] = make_msgid(domain=settings.EMAIL_FROM_ADDRESS.split("@")[-1])
    # Queste sono email di servizio, non campagne: dichiararlo evita che un
    # autorisponditore ci risponda e che vengano contate come invii di massa.
    message["Auto-Submitted"] = "auto-generated"

    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    if inline_images:
        # La parte HTML e' l'ultima aggiunta; le immagini vanno agganciate a
        # QUELLA, cosi' il messaggio risulta multipart/alternative[text, related[
        # html, immagini]] - la struttura che i client sanno leggere: chi mostra
        # solo testo non si ritrova un allegato, chi mostra l'HTML risolve i cid.
        html_part = message.get_payload()[-1]
        for image in inline_images:
            html_part.add_related(
                image.content,
                maintype="image",
                subtype=image.subtype,
                cid=f"<{image.cid}>",
                disposition="inline",
                filename=f"{image.cid}.{image.subtype}",
            )

    try:
        with _connect() as smtp:
            smtp.send_message(message)
    except EmailDeliveryError:
        raise
    except (smtplib.SMTPException, OSError) as exc:
        # str(exc) di un errore SMTP contiene la risposta del server, non le
        # credenziali; il corpo del messaggio non viene mai incluso.
        raise EmailDeliveryError(
            f"Invio a {to_address} fallito ({exc.__class__.__name__}): {exc}"
        ) from exc

    logger.info("Email '%s' inviata a %s", subject, to_address)
