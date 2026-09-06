"""
Real WhatsApp Business connector via the WhatsApp Cloud API
(developers.facebook.com/docs/whatsapp/cloud-api) - a different API family
from Messenger/Instagram (different payload shape, different send format),
though webhook delivery/signature verification still goes through the same
Meta infrastructure (X-Hub-Signature-256, same scheme as facebook.py).

Requires, from the Meta App dashboard (App Review + Business Verification
for `whatsapp_business_messaging` before it can message real customers -
see docs/OMNICHANNEL_RESPONDER.md §11):
- a permanent access token (System User token with whatsapp_business_
  messaging permission)
- the App Secret, used to verify webhook signatures (same as Facebook/
  Instagram)
- the Phone Number ID (from WhatsApp Manager) - stored in the existing
  OmniChannelAccount.external_account_id column, NOT in the encrypted
  blob: it identifies which of the business's numbers to send from, it
  isn't a secret by itself.

access_token_encrypted stores `{"access_token": "...", "app_secret": "..."}`,
same two-secret JSON pattern as facebook.py.

IMPORTANT limitation (not implemented, spec section 46/self-imposed scope):
WhatsApp only allows free-form text replies within the 24-hour customer
service window after the customer's last message - outside that window,
only pre-approved message templates can be sent, which this module does
not implement (no template management UI/flow exists). Since every draft
here is always a reply to an inbound message the customer just sent, this
is normally not an issue in practice, but a very late approval (>24h after
the customer wrote) will be rejected by WhatsApp with an explicit error
surfaced as a FAILED draft, not a silent failure.
"""
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.omnichannel.connectors.base import Connector, NormalizedIncomingMessage, SendResult
from app.integrations.omnichannel.exceptions import ConnectorError

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppConnector(Connector):
    def _secrets(self) -> Dict[str, str]:
        if not self.access_token:
            raise ConnectorError("Nessun token configurato per questo canale WhatsApp")
        try:
            return json.loads(self.access_token)
        except json.JSONDecodeError:
            raise ConnectorError("Credenziali del canale WhatsApp corrotte o in un formato inatteso")

    def _access_token(self) -> str:
        token = self._secrets().get("access_token")
        if not token:
            raise ConnectorError("Nessun Access Token configurato per questo canale WhatsApp")
        return token

    def _phone_number_id(self) -> str:
        if not self.channel_account.external_account_id:
            raise ConnectorError("Nessun Phone Number ID configurato per questo canale WhatsApp")
        return self.channel_account.external_account_id

    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        """Same X-Hub-Signature-256 HMAC scheme as Facebook/Instagram - all three go through Meta's shared webhook infrastructure."""
        signature_header = headers.get("x-hub-signature-256", "")
        if not signature_header.startswith("sha256="):
            return False
        app_secret = self._secrets().get("app_secret")
        if not app_secret:
            return False
        expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature_header[len("sha256="):], expected)

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        """
        WhatsApp Cloud API webhook shape (developers.facebook.com/docs/whatsapp/
        cloud-api/webhooks): entry[].changes[].value.messages[] for inbound
        messages, entry[].changes[].value.statuses[] for delivery/read
        receipts on messages *we* sent - only "messages" is ever translated,
        statuses-only changes are silently skipped (nothing to ingest).
        """
        messages: List[NormalizedIncomingMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}

                for message in value.get("messages", []):
                    message_type_raw = (message.get("type") or "text").upper()
                    message_type = {"TEXT": "TEXT", "IMAGE": "IMAGE", "VIDEO": "VIDEO", "AUDIO": "AUDIO", "DOCUMENT": "DOCUMENT", "LOCATION": "LOCATION", "CONTACTS": "CONTACT"}.get(message_type_raw, "OTHER")
                    text = message.get("text", {}).get("body") if message_type == "TEXT" else None
                    attachments: List[Dict[str, Any]] = []
                    if message_type not in ("TEXT", "LOCATION", "CONTACT", "OTHER"):
                        media_ref = message.get(message.get("type"), {}).get("id")
                        if media_ref:
                            attachments.append({"type": message_type, "whatsapp_media_id": media_ref})

                    sender_id = message.get("from")
                    messages.append(NormalizedIncomingMessage(
                        external_user_id=str(sender_id),
                        text=text,
                        message_type=message_type,
                        external_message_id=message.get("id"),
                        customer_display_name=contacts.get(sender_id),
                        attachments=attachments,
                        metadata={"phone_number_id": value.get("metadata", {}).get("phone_number_id")},
                    ))
        return messages

    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        try:
            response = httpx.post(
                f"{GRAPH_API_BASE}/{self._phone_number_id()}/messages",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": external_user_id,
                    "type": "text",
                    "text": {"body": text},
                },
                timeout=30.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso WhatsApp: {str(e)}")

        data = response.json()
        if response.status_code != 200 or "error" in data:
            error_message = data.get("error", {}).get("message", "errore sconosciuto")
            raise ConnectorError(f"WhatsApp ha rifiutato l'invio: {error_message}", status_code=response.status_code)

        message_id = None
        if data.get("messages"):
            message_id = data["messages"][0].get("id")
        return SendResult(external_message_id=message_id, raw_response=data)

    def get_status(self) -> Dict[str, Any]:
        try:
            response = httpx.get(
                f"{GRAPH_API_BASE}/{self._phone_number_id()}",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                params={"fields": "display_phone_number,verified_name"},
                timeout=15.0,
            )
            data = response.json()
        except (httpx.RequestError, ConnectorError) as e:
            return {"status": "error", "detail": str(e)}

        if "error" in data:
            return {"status": "error", "detail": data["error"].get("message")}
        return {"status": "connected", "phone_number": data.get("display_phone_number"), "verified_name": data.get("verified_name")}
