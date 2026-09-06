"""
Real Telegram Bot API connector (https://core.telegram.org/bots/api) - the
only real external channel wired up in this first version, per product spec
section 36 priority order (Telegram first, easiest to validate end-to-end
without a Meta app review). Uses httpx directly, same style as
app/integrations/openai/client.py, no third-party Telegram SDK.
"""
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.omnichannel.connectors.base import Connector, NormalizedIncomingMessage, SendResult
from app.integrations.omnichannel.exceptions import ConnectorError

TELEGRAM_API_BASE = "https://api.telegram.org"

# Telegram update payloads carry at most one of these per message - the first
# one present decides message_type. Voice notes and generic audio files are
# distinguished (spec keeps VOICE and AUDIO as separate types).
_ATTACHMENT_KEYS = [
    ("photo", "IMAGE"),
    ("video", "VIDEO"),
    ("voice", "VOICE"),
    ("audio", "AUDIO"),
    ("document", "DOCUMENT"),
    ("location", "LOCATION"),
    ("contact", "CONTACT"),
]


class TelegramConnector(Connector):
    def _base_url(self) -> str:
        if not self.access_token:
            raise ConnectorError("Nessun bot token configurato per questo canale Telegram")
        return f"{TELEGRAM_API_BASE}/bot{self.access_token}"

    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        # Telegram echoes back the secret_token configured via setWebhook in
        # this header on every request - see register_webhook() below.
        return headers.get("x-telegram-bot-api-secret-token") == self.channel_account.webhook_secret

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        message = payload.get("message") or payload.get("edited_message")
        if not message:
            return []  # Non-message updates (e.g. callback_query) - nothing to ingest yet

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        external_user_id = str(chat.get("id"))
        display_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or from_user.get("username")

        message_type = "TEXT"
        attachments: List[Dict[str, Any]] = []
        for key, mtype in _ATTACHMENT_KEYS:
            if key in message:
                message_type = mtype
                value = message[key]
                # photo is a list of sizes - keep only the largest
                file_ref = value[-1] if isinstance(value, list) else value
                attachments.append({"type": mtype, "telegram_file_id": file_ref.get("file_id") if isinstance(file_ref, dict) else None})
                break

        return [
            NormalizedIncomingMessage(
                external_user_id=external_user_id,
                text=message.get("text") or message.get("caption"),
                message_type=message_type,
                external_message_id=str(message.get("message_id")),
                customer_display_name=display_name,
                attachments=attachments,
                metadata={"telegram_chat_id": chat.get("id")},
            )
        ]

    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        try:
            response = httpx.post(
                f"{self._base_url()}/sendMessage",
                json={"chat_id": external_user_id, "text": text},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso Telegram: {str(e)}")

        data = response.json()
        if not data.get("ok"):
            raise ConnectorError(f"Telegram ha rifiutato l'invio: {data.get('description', 'errore sconosciuto')}", status_code=response.status_code)

        return SendResult(external_message_id=str(data["result"]["message_id"]), raw_response=data)

    def get_status(self) -> Dict[str, Any]:
        try:
            response = httpx.get(f"{self._base_url()}/getMe", timeout=15.0)
            data = response.json()
        except httpx.RequestError as e:
            return {"status": "error", "detail": str(e)}

        if not data.get("ok"):
            return {"status": "error", "detail": data.get("description")}
        return {"status": "connected", "bot_username": data["result"].get("username")}

    def register_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """
        Not part of the Connector ABC (Telegram-specific setup step) - called
        once from the channel-account creation endpoint to point Telegram at
        our /webhooks/telegram/{channel_account_id} URL.
        """
        try:
            response = httpx.post(
                f"{self._base_url()}/setWebhook",
                json={"url": webhook_url, "secret_token": self.channel_account.webhook_secret},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso Telegram: {str(e)}")

        data = response.json()
        if not data.get("ok"):
            raise ConnectorError(f"Impossibile registrare il webhook Telegram: {data.get('description', 'errore sconosciuto')}", status_code=response.status_code)
        return data
