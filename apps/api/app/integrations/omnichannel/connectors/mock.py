"""
Dev/test connector - no external API involved. Used by the "Simula messaggio"
tool (api/v1/omnichannel_webhooks.py::simulate_message) to exercise the full
ingest -> AI draft -> approve -> send pipeline without any real WhatsApp/
Telegram/Instagram credentials, per product spec section 51.
"""
import uuid
from typing import Any, Dict, List, Optional
from app.integrations.omnichannel.connectors.base import Connector, NormalizedIncomingMessage, SendResult


class MockConnector(Connector):
    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        return True

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        return [
            NormalizedIncomingMessage(
                external_user_id=payload["external_user_id"],
                text=payload.get("text"),
                customer_display_name=payload.get("customer_name"),
                external_message_id=payload.get("external_message_id") or f"mock-{uuid.uuid4().hex}",
            )
        ]

    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        # Nothing actually goes anywhere - this only proves the approval/send
        # workflow transitions a draft all the way to SENT.
        return SendResult(external_message_id=f"mock-out-{uuid.uuid4().hex}")

    def get_status(self) -> Dict[str, Any]:
        return {"status": "connected", "note": "Mock connector - no real channel involved"}
