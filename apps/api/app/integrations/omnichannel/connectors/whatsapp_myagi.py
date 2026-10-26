"""
WhatsApp via myAGI: numero normale collegato via QR al NOSTRO gateway
(integrations/myagi/waha.py) invece che a Maytapi.

Perche' un terzo connettore WhatsApp. `whatsapp` e' la Cloud API ufficiale di
Meta (numero business, verifica, template); `whatsapp_maytapi` e' un numero
normale ma il client "WhatsApp Web" gira dai server di Maytapi, a pagamento;
questo e' lo stesso meccanismo di Maytapi fatto girare in casa (WAHA, in
docker-compose). Le tre strade convivono e si scelgono per canale: niente di
quello che c'era cambia.

Credenziali: nessuna per canale. La chiave del gateway e' dell'installazione
(MYAGI_WA_API_KEY) e il legame canale <-> sessione WAHA e' il nome della
sessione, derivato dall'id del canale. In `config_json` finiscono solo dati
di comodo scritti dal gateway (numero collegato, nome profilo).

**Verifica del webhook**, due prove indipendenti:
1. il segreto del canale nel path (`/webhooks/myagi/{id}/{webhook_secret}`),
   come per Maytapi: funziona qualunque cosa faccia il gateway;
2. la firma HMAC-SHA512 del corpo che WAHA mette in `X-Webhook-Hmac` quando la
   sessione e' configurata con `hmac.key` (waha.py::_session_config, la chiave
   e' lo stesso webhook_secret). Se l'header c'e' DEVE combaciare; se manca si
   accetta sulla sola prova 1 (gateway piu' vecchio o configurato a mano).

**Payload** (`message` event, documentazione WAHA "Receive messages"):

    {"event": "message", "session": "agi_...",
     "payload": {"id": "false_3933...@c.us_AAAA", "timestamp": 1667561485,
                 "from": "3933...@c.us", "fromMe": false, "to": "...",
                 "body": "Ciao", "hasMedia": false,
                 "media": {"url": "...", "mimetype": "image/jpeg", "filename": "..."},
                 "_data": {...}}}

Come per Maytapi, `fromMe` e' il campo piu' importante del file: WAHA rimanda
sul webhook anche quello che parte dal telefono, comprese le nostre risposte.
"""
import hashlib
import hmac
from typing import Any, Dict, List, Optional

from app.integrations.myagi import waha
from app.integrations.omnichannel.connectors.base import (
    Connector,
    NormalizedIncomingMessage,
    SendResult,
)
from app.integrations.omnichannel.exceptions import ConnectorError

_INGESTABLE_EVENTS = {"message"}

# mimetype -> tipo normalizzato. Vocali WhatsApp arrivano come audio/ogg; non
# distinguiamo VOICE da AUDIO perche' il payload non lo dice in modo stabile.
_MIME_TYPES = (
    ("image/", "IMAGE"),
    ("video/", "VIDEO"),
    ("audio/", "AUDIO"),
)


def _message_type(payload: Dict[str, Any]) -> str:
    if payload.get("location"):
        return "LOCATION"
    if payload.get("vCards"):
        return "CONTACT"
    if not payload.get("hasMedia"):
        return "TEXT"
    mimetype = str(((payload.get("media") or {}).get("mimetype")) or "").lower()
    for prefix, kind in _MIME_TYPES:
        if mimetype.startswith(prefix):
            return kind
    return "DOCUMENT"


class MyAgiWhatsAppConnector(Connector):
    def _session_name(self) -> str:
        return waha.session_name_for(self.channel_account.id)

    def _client(self) -> waha.WahaClient:
        return waha.WahaClient()

    # ---- ingresso -----------------------------------------------------------
    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        secret = self.channel_account.webhook_secret or ""
        if not path_secret or not secret or not hmac.compare_digest(str(path_secret), secret):
            return False
        signature = headers.get("x-webhook-hmac")
        if signature:
            expected = hmac.new(secret.encode("utf-8"), body or b"", hashlib.sha512).hexdigest()
            return hmac.compare_digest(signature.strip().lower(), expected)
        return True

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        if payload.get("event") not in _INGESTABLE_EVENTS:
            return []
        # La sessione nel payload deve essere quella di questo canale: un
        # webhook configurato per sbaglio su un'altra sessione non deve
        # mescolare le chat di due numeri.
        if payload.get("session") and payload.get("session") != self._session_name():
            return []

        message = payload.get("payload") or {}
        if message.get("fromMe"):
            return []
        sender = str(message.get("from") or "").strip()
        if not sender:
            return []
        # Gruppi, liste broadcast e status: non sono conversazioni con un
        # cliente, e rispondere in un gruppo per sbaglio sarebbe il peggior
        # modo di scoprirlo.
        if sender.endswith("@g.us") or sender.endswith("@broadcast") or sender.startswith("status@"):
            return []

        message_type = _message_type(message)
        body = message.get("body")
        text = body if isinstance(body, str) and body.strip() else None

        attachments: List[Dict[str, Any]] = []
        media = message.get("media") or {}
        if message.get("hasMedia") and media.get("url"):
            attachments.append({"type": message_type, "url": media["url"], "mime_type": media.get("mimetype"), "filename": media.get("filename")})

        raw = message.get("_data") or {}
        display_name = raw.get("notifyName") or raw.get("pushName") or raw.get("name") or message.get("notifyName")

        return [
            NormalizedIncomingMessage(
                external_user_id=sender,
                text=text,
                message_type=message_type,
                external_message_id=str(message["id"]) if message.get("id") else None,
                customer_display_name=display_name,
                attachments=attachments,
                metadata={
                    "myagi_session": payload.get("session"),
                    "whatsapp_phone": sender.split("@", 1)[0],
                    "timestamp": message.get("timestamp"),
                },
            )
        ]

    # ---- uscita -------------------------------------------------------------
    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        data = self._client().send_text(self._session_name(), waha.normalize_chat_id(external_user_id), text)
        message_id = data.get("id")
        if isinstance(message_id, dict):
            message_id = message_id.get("_serialized") or message_id.get("id")
        return SendResult(external_message_id=str(message_id) if message_id else None, raw_response=data)

    # ---- stato --------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        try:
            session = self._client().get_session(self._session_name())
        except ConnectorError as e:
            return {"status": "error", "detail": e.message}
        if session is None:
            return {"status": "error", "detail": "Sessione non presente sul gateway myAGI: avviala dalla pagina myAGI."}
        waha_status = str(session.get("status") or "")
        me = session.get("me") or {}
        result = {
            "status": "connected" if waha_status == "WORKING" else "error",
            "waha_status": waha_status,
            "phone_number": str(me.get("id") or "").split("@", 1)[0] or None,
            "push_name": me.get("pushName"),
        }
        if waha_status == "SCAN_QR_CODE":
            result["detail"] = "In attesa della scansione del QR code (pagina myAGI)."
        elif waha_status not in ("WORKING",):
            result["detail"] = f"Stato sessione: {waha_status or 'sconosciuto'}"
        return result
