from typing import Type
from app.core.security import EncryptionService
from app.integrations.omnichannel.connectors.base import Connector
from app.integrations.omnichannel.connectors.mock import MockConnector
from app.integrations.omnichannel.connectors.telegram import TelegramConnector
from app.integrations.omnichannel.connectors.facebook import FacebookConnector
from app.integrations.omnichannel.connectors.instagram import InstagramConnector
from app.integrations.omnichannel.connectors.whatsapp import WhatsAppConnector
from app.integrations.omnichannel.connectors.maytapi import MaytapiConnector
from app.integrations.omnichannel.connectors.gmail import GmailConnector
from app.integrations.omnichannel.connectors.whatsapp_myagi import MyAgiWhatsAppConnector
from app.models.omnichannel import OmniChannelAccount

_CONNECTOR_CLASSES: dict[str, Type[Connector]] = {
    "mock": MockConnector,
    "telegram": TelegramConnector,
    "whatsapp": WhatsAppConnector,
    # Numero WhatsApp normale collegato via QR dalla console Maytapi, distinto
    # da "whatsapp" (Cloud API ufficiale di Meta, numero business + App Review)
    # - vedi il docstring di connectors/maytapi.py per il perche' convivono.
    "whatsapp_maytapi": MaytapiConnector,
    # Stesso meccanismo di Maytapi (numero normale via QR) ma sul nostro
    # gateway WAHA in docker-compose: vedi integrations/myagi/.
    "whatsapp_myagi": MyAgiWhatsAppConnector,
    "instagram": InstagramConnector,
    "facebook": FacebookConnector,
    "gmail": GmailConnector,
}

SUPPORTED_CHANNELS = list(_CONNECTOR_CLASSES.keys())


def get_connector(channel_account: OmniChannelAccount) -> Connector:
    """Factory: builds the right Connector for a channel account, decrypting its token if present."""
    connector_class = _CONNECTOR_CLASSES.get(channel_account.channel)
    if not connector_class:
        raise ValueError(f"Canale non supportato: {channel_account.channel}")

    access_token = (
        EncryptionService.decrypt(channel_account.access_token_encrypted)
        if channel_account.access_token_encrypted
        else None
    )
    return connector_class(channel_account, access_token)
