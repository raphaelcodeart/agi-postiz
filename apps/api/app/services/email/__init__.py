"""
Email transazionali del portale.

``mailer`` sa spedire, ``templates`` sa cosa spedire. Restano separati perche'
sono due mestieri diversi: il primo e' SMTP, TLS e MIME, il secondo e' testo e
impaginazione, e chi ritocca una frase dell'email di benvenuto non deve trovarsi
davanti una connessione.
"""
from app.services.email.mailer import (
    EmailDeliveryError,
    EmailNotConfiguredError,
    InlineImage,
    is_enabled,
    send_email,
)

__all__ = [
    "EmailDeliveryError",
    "EmailNotConfiguredError",
    "InlineImage",
    "is_enabled",
    "send_email",
]
