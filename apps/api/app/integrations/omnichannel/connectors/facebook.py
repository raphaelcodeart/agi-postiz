"""
Real Facebook Messenger connector via the Meta Graph API (Send API +
Messenger webhooks - developers.facebook.com/docs/messenger-platform).
Same httpx-direct style as telegram.py/openai/client.py, no SDK.

Requires, from the Meta App dashboard (App Review + Business Verification
for the pages_messaging permission before it can message real customers -
see docs/OMNICHANNEL_RESPONDER.md §11):
- a Page Access Token (long-lived, generated per-Page after connecting it
  to the app)
- the App Secret (App Dashboard > Settings > Basic), used to verify that
  webhook payloads really came from Meta

OmniChannelAccount.access_token_encrypted stores BOTH, JSON-encoded
(`{"access_token": "...", "app_secret": "..."}`) rather than a single string
like Telegram - Messenger (and Instagram/WhatsApp, which share this same
class hierarchy, see instagram.py/whatsapp.py) need two distinct secrets:
one to send, one to verify inbound webhook signatures. See
OmniChannelAccountCreate.app_secret / OmnichannelService.create_channel_account.

Instagram Direct messaging (see instagram.py) runs on this exact same Graph
API infrastructure since Meta unified Messenger + Instagram messaging
(developers.facebook.com/docs/messenger-platform/instagram) - same webhook
shape, same /me/messages Send API, same signature scheme - so
InstagramConnector simply subclasses this class with zero logic changes.
"""
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.omnichannel.connectors.base import Connector, NormalizedIncomingMessage, SendResult
from app.integrations.omnichannel.exceptions import ConnectorError

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class FacebookConnector(Connector):
    # Overridden by InstagramConnector purely for clearer error/status
    # messages - every method below is identical for both channels.
    channel_label = "Facebook"

    def _secrets(self) -> Dict[str, str]:
        if not self.access_token:
            raise ConnectorError(f"Nessun token configurato per questo canale {self.channel_label}")
        try:
            return json.loads(self.access_token)
        except json.JSONDecodeError:
            raise ConnectorError(f"Credenziali del canale {self.channel_label} corrotte o in un formato inatteso")

    def _page_access_token(self) -> str:
        token = self._secrets().get("access_token")
        if not token:
            raise ConnectorError(f"Nessun Access Token configurato per questo canale {self.channel_label}")
        return token

    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        """
        Only used for the POST (message delivery) path - the GET verification
        handshake (hub.mode/hub.verify_token/hub.challenge) is checked
        separately in api/v1/omnichannel_webhooks.py against path_secret
        (channel_account.webhook_secret, same field Telegram reuses for its
        own secret token) before this is ever called.

        Verifies X-Hub-Signature-256: HMAC-SHA256 of the raw body, keyed with
        the App Secret - developers.facebook.com/docs/messenger-platform/
        webhooks#security. Constant-time compare against timing attacks.
        """
        signature_header = headers.get("x-hub-signature-256", "")
        if not signature_header.startswith("sha256="):
            return False
        app_secret = self._secrets().get("app_secret")
        if not app_secret:
            return False
        expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature_header[len("sha256="):], expected)

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        messages: List[NormalizedIncomingMessage] = []
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                message = event.get("message")
                # Skip delivery/read receipts, postbacks, and echoes of our
                # own outbound sends (message.is_echo=true) - only genuine
                # inbound customer text/attachments become a NormalizedIncomingMessage.
                if not message or message.get("is_echo"):
                    continue

                message_type = "TEXT"
                attachments: List[Dict[str, Any]] = []
                for attachment in message.get("attachments", []):
                    attachment_type = (attachment.get("type") or "OTHER").upper()
                    message_type = {"IMAGE": "IMAGE", "VIDEO": "VIDEO", "AUDIO": "AUDIO", "FILE": "DOCUMENT"}.get(attachment_type, "OTHER")
                    attachments.append({"type": message_type, "url": attachment.get("payload", {}).get("url")})
                    break  # one message_type per message, same simplification as telegram.py

                messages.append(NormalizedIncomingMessage(
                    external_user_id=str(event.get("sender", {}).get("id")),
                    text=message.get("text"),
                    message_type=message_type,
                    external_message_id=message.get("mid"),
                    attachments=attachments,
                    metadata={"page_id": entry.get("id")},
                ))
        return messages

    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        try:
            response = httpx.post(
                f"{GRAPH_API_BASE}/me/messages",
                params={"access_token": self._page_access_token()},
                json={
                    "recipient": {"id": external_user_id},
                    "message": {"text": text},
                    # RESPONSE = replying to a message the customer sent us -
                    # the only messaging_type this module ever uses (no
                    # proactive/marketing sends), matches how every draft
                    # here always originates from an inbound customer message.
                    "messaging_type": "RESPONSE",
                },
                timeout=30.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso {self.channel_label}: {str(e)}")

        data = response.json()
        if response.status_code != 200 or "error" in data:
            error_message = data.get("error", {}).get("message", "errore sconosciuto")
            raise ConnectorError(f"{self.channel_label} ha rifiutato l'invio: {error_message}", status_code=response.status_code)

        return SendResult(external_message_id=data.get("message_id"), raw_response=data)

    def get_status(self) -> Dict[str, Any]:
        try:
            response = httpx.get(f"{GRAPH_API_BASE}/me", params={"access_token": self._page_access_token(), "fields": "name"}, timeout=15.0)
            data = response.json()
        except (httpx.RequestError, ConnectorError) as e:
            return {"status": "error", "detail": str(e)}

        if "error" in data:
            return {"status": "error", "detail": data["error"].get("message")}
        return {"status": "connected", "page_name": data.get("name")}
