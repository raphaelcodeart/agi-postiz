"""
WhatsApp via Maytapi (https://maytapi.com/whatsapp-api-documentation).

Perche' esiste, dato che un connettore WhatsApp c'e' gia' (connectors/whatsapp.py):
sono due cose diverse. Quello parla con la **Cloud API ufficiale di Meta**, che
richiede un numero business dedicato, la verifica dell'azienda e la App Review, e
fuori dalla finestra di 24 ore lascia mandare solo template approvati. Maytapi
collega invece un **numero WhatsApp normale** - quello personale
dell'amministratore, letteralmente il telefono in tasca - via QR code dalla loro
console, senza review e senza finestra dei template. Le due strade non si
sostituiscono a vicenda: restano entrambe registrate, e si sceglie per canale.

Credenziali, dalla console Maytapi (console.maytapi.com/settings/token):
- `api_token` -> l'unico segreto, in `access_token_encrypted` (cifrato a riposo).
- `product_id` e `phone_id` -> in `config_json`. Non sono segreti: indirizzano
  quale istanza/numero usare, esattamente come il Phone Number ID di
  connectors/whatsapp.py, e senza il token non aprono nulla.

**Verifica del webhook.** Maytapi non firma il payload (niente HMAC come
X-Hub-Signature-256 di Meta, niente header con segreto come Telegram): il loro
`/setWebhook` accetta un URL e basta. Il segreto sta quindi nell'URL stesso -
`/webhooks/maytapi/{channel_account_id}/{webhook_secret}` - che e' esattamente
l'uso per cui `OmniChannelAccount.webhook_secret` era stato pensato (vedi il
commento sulla colonna in models/omnichannel.py). In piu' `product_id`/`phone_id`
del payload devono corrispondere a quelli configurati: non e' una firma, ma
impedisce che il webhook di un'altra istanza Maytapi finisca in questa inbox.

**Forma dei payload** (verificata sull'esempio ufficiale
github.com/maytapi-com/whatsapp-api-nodejs-example, app.js, e sulla
documentazione linkata sopra - non ricostruita a memoria):

    invio   POST https://api.maytapi.com/api/{product_id}/{phone_id}/sendMessage
            header  x-maytapi-key: {api_token}
            body    {"to_number": "...", "type": "text", "message": "..."}

    webhook {"type": "message",
             "product_id": "...", "phone_id": 1,
             "message": {"type": "text", "text": "...", "id": "...", "fromMe": false},
             "user": {"id": "39333...@c.us", "name": "Mario", "phone": "39333..."},
             "conversation": "39333...@c.us"}

Il parsing resta comunque difensivo (`.get` ovunque, nessun campo dato per
scontato): un campo che cambia nome deve produrre un messaggio senza nome, non
un 500 su un endpoint pubblico.
"""
import hmac
from typing import Any, Dict, List, Optional

import httpx

from app.integrations.omnichannel.connectors.base import (
    Connector,
    NormalizedIncomingMessage,
    SendResult,
)
from app.integrations.omnichannel.exceptions import ConnectorError

MAYTAPI_API_BASE = "https://api.maytapi.com/api"

# Tipo di messaggio Maytapi -> tipo normalizzato (base.NormalizedIncomingMessage).
# Quelli non elencati diventano OTHER: il messaggio entra comunque in inbox, e
# l'operatore lo vede, invece di sparire perche' non sapevamo etichettarlo.
_MESSAGE_TYPES: Dict[str, str] = {
    "text": "TEXT",
    "image": "IMAGE",
    "video": "VIDEO",
    "audio": "AUDIO",
    "ptt": "VOICE",  # push-to-talk, il vocale di WhatsApp
    "document": "DOCUMENT",
    "location": "LOCATION",
    "vcard": "CONTACT",
    "contact": "CONTACT",
}

# Solo gli eventi di messaggio vanno ingeriti. Maytapi manda sullo stesso
# webhook anche "ack" (spunte di consegna/lettura), "status" (il telefono si e'
# connesso/disconnesso) ed "error": nessuno dei tre e' qualcosa che un cliente
# ha scritto.
_INGESTABLE_EVENT_TYPES = {"message"}


class MaytapiConnector(Connector):
    # ---- configurazione -----------------------------------------------------
    def _config(self) -> Dict[str, Any]:
        return self.channel_account.config_json or {}

    def _product_id(self) -> str:
        product_id = str(self._config().get("product_id") or "").strip()
        if not product_id:
            raise ConnectorError("Nessun Product ID configurato per questo canale Maytapi")
        return product_id

    def _phone_id(self) -> str:
        phone_id = str(self._config().get("phone_id") or "").strip()
        if not phone_id:
            raise ConnectorError("Nessun Phone ID configurato per questo canale Maytapi")
        return phone_id

    def _api_token(self) -> str:
        if not self.access_token:
            raise ConnectorError("Nessun API Token configurato per questo canale Maytapi")
        return self.access_token

    def _instance_url(self) -> str:
        return f"{MAYTAPI_API_BASE}/{self._product_id()}/{self._phone_id()}"

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "x-maytapi-key": self._api_token()}

    # ---- ingresso -----------------------------------------------------------
    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        """
        Maytapi non firma il payload, quindi l'unica prova che la richiesta
        venga da noi e' il segreto nell'URL. `compare_digest` e non `==`: il
        confronto di un segreto va fatto a tempo costante anche quando la
        differenza di tempo sembra impraticabile da misurare.
        """
        if not path_secret:
            return False
        return hmac.compare_digest(str(path_secret), self.channel_account.webhook_secret)

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        if payload.get("type") not in _INGESTABLE_EVENT_TYPES:
            return []

        # Difesa in profondita' sopra al segreto nell'URL: se il payload dice di
        # appartenere a un'altra istanza Maytapi, non e' roba di questo canale.
        config = self._config()
        if config.get("product_id") and str(payload.get("product_id") or "") != str(config["product_id"]):
            return []
        if config.get("phone_id") and str(payload.get("phone_id") or "") != str(config["phone_id"]):
            return []

        message = payload.get("message") or {}

        # Il punto piu' importante di tutto il file. Maytapi rimanda sul webhook
        # anche i messaggi partiti dal telefono stesso, comprese le risposte che
        # abbiamo appena inviato noi (fromMe=true). Ingerirle significherebbe
        # trattare la nostra stessa risposta come un messaggio del cliente,
        # generarci sopra una bozza AI e - con l'autorisponditore acceso -
        # rispondere a noi stessi all'infinito.
        if message.get("fromMe"):
            return []

        user = payload.get("user") or {}
        # `conversation` e' il JID della chat ("39333...@c.us"), stabile e sempre
        # presente; `user.id` e' lo stesso valore per una chat 1-a-1. Si preferisce
        # il primo, col secondo come ripiego: e' l'identita' su cui poggia la
        # risoluzione del cliente, quindi deve cambiare il meno possibile.
        external_user_id = str(payload.get("conversation") or user.get("id") or user.get("phone") or "").strip()
        if not external_user_id:
            return []

        raw_type = str(message.get("type") or "text").lower()
        message_type = _MESSAGE_TYPES.get(raw_type, "OTHER")
        # Per gli allegati WhatsApp mette la didascalia in `text` (o `caption`):
        # va tenuta, e' spesso l'unica cosa scritta dal cliente.
        text = message.get("text") or message.get("caption")

        attachments: List[Dict[str, Any]] = []
        if message_type not in ("TEXT", "LOCATION", "CONTACT", "OTHER"):
            media_url = message.get("url")
            if media_url:
                attachments.append({"type": message_type, "url": media_url, "mime_type": message.get("mime")})

        return [
            NormalizedIncomingMessage(
                external_user_id=external_user_id,
                text=text,
                message_type=message_type,
                external_message_id=str(message["id"]) if message.get("id") else None,
                customer_display_name=user.get("name") or user.get("phone"),
                attachments=attachments,
                metadata={
                    "maytapi_phone_id": payload.get("phone_id"),
                    "maytapi_conversation": payload.get("conversation"),
                    # Il numero in chiaro, utile nella scheda cliente: `conversation`
                    # e' un JID, non un numero componibile.
                    "whatsapp_phone": user.get("phone"),
                },
            )
        ]

    # ---- uscita -------------------------------------------------------------
    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        try:
            response = httpx.post(
                f"{self._instance_url()}/sendMessage",
                headers=self._headers(),
                json={"to_number": external_user_id, "type": "text", "message": text},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso Maytapi: {str(e)}")

        try:
            data = response.json()
        except ValueError:
            raise ConnectorError(
                f"Risposta non leggibile da Maytapi (HTTP {response.status_code})",
                status_code=response.status_code,
            )

        # Maytapi risponde 200 anche quando rifiuta: l'esito sta in `success`,
        # non nel codice HTTP. Guardare solo lo status code farebbe passare per
        # inviato un messaggio mai partito - ed e' esattamente il caso in cui
        # AGENTS.md ss2 (mai ritentare un invio riuscito) smetterebbe di valere,
        # perche' non sapremmo piu' quali invii sono riusciti davvero.
        if response.status_code >= 400 or not data.get("success", False):
            detail = data.get("message") or data.get("error") or "errore sconosciuto"
            raise ConnectorError(f"Maytapi ha rifiutato l'invio: {detail}", status_code=response.status_code)

        sent = data.get("data") or {}
        message_id = sent.get("msgId") or sent.get("id") or data.get("msgId")
        return SendResult(
            external_message_id=str(message_id) if message_id else None,
            raw_response=data,
        )

    # ---- stato --------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """
        Interroga lo stato dell'istanza. Conta soprattutto sapere se il telefono
        e' ancora appaiato: una sessione WhatsApp collegata via QR cade da sola
        (telefono spento a lungo, logout dall'app), e senza questo la prima
        avvisaglia sarebbe una risposta che non parte.
        """
        try:
            response = httpx.get(f"{self._instance_url()}/status", headers=self._headers(), timeout=15.0)
            data = response.json()
        except (httpx.RequestError, ValueError, ConnectorError) as e:
            return {"status": "error", "detail": str(e)}

        if response.status_code >= 400 or not data.get("success", True):
            return {"status": "error", "detail": data.get("message") or f"HTTP {response.status_code}"}

        instance = (data.get("status") or {}) if isinstance(data.get("status"), dict) else {}
        logged_in = instance.get("loggedIn")
        if logged_in is False:
            return {
                "status": "error",
                "detail": "Il numero non risulta collegato: riappaia il telefono dalla console Maytapi.",
            }
        return {
            "status": "connected",
            "phone_number": instance.get("phone_number") or instance.get("number"),
            "logged_in": logged_in,
        }

    def register_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """
        Punta Maytapi al nostro endpoint. Non fa parte della ABC Connector (e'
        un passo di setup specifico del canale, come
        TelegramConnector.register_webhook) ed e' chiamato dallo stesso endpoint
        "Registra webhook" della lista canali.

        Il webhook e' per **prodotto**, non per singolo numero: registrarlo
        sovrascrive quello di tutti i numeri della stessa istanza Maytapi. Con
        un numero solo - il caso per cui questo canale esiste - e' irrilevante,
        ma va detto qui invece che scoperto dopo.
        """
        try:
            response = httpx.post(
                f"{MAYTAPI_API_BASE}/{self._product_id()}/setWebhook",
                headers=self._headers(),
                json={"webhook": webhook_url},
                timeout=30.0,
            )
            data = response.json()
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso Maytapi: {str(e)}")
        except ValueError:
            raise ConnectorError(
                f"Risposta non leggibile da Maytapi (HTTP {response.status_code})",
                status_code=response.status_code,
            )

        if response.status_code >= 400 or not data.get("success", False):
            detail = data.get("message") or data.get("error") or "errore sconosciuto"
            raise ConnectorError(f"Impossibile registrare il webhook Maytapi: {detail}", status_code=response.status_code)
        return data
