"""
Common interface every channel integration implements, so business logic
(app/services/omnichannel_service.py) never talks to a platform-specific API
directly. Adding a new channel later (Email, LinkedIn, WebChat, SMS...) means
writing one new class here - nothing else in the module changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.models.omnichannel import OmniChannelAccount


@dataclass
class NormalizedIncomingMessage:
    """The common shape every inbound webhook payload is translated into (see spec section 5)."""
    external_user_id: str
    text: Optional[str]
    message_type: str = "TEXT"  # TEXT, IMAGE, VIDEO, AUDIO, VOICE, DOCUMENT, LOCATION, CONTACT, OTHER
    external_message_id: Optional[str] = None
    customer_display_name: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    external_message_id: Optional[str]
    raw_response: Optional[Dict[str, Any]] = None


class Connector(ABC):
    """One instance per inbound/outbound call, constructed with the OmniChannelAccount row it operates on."""

    def __init__(self, channel_account: OmniChannelAccount, access_token: Optional[str]):
        self.channel_account = channel_account
        self.access_token = access_token

    @abstractmethod
    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        """
        Validates that an inbound webhook request actually came from the
        channel provider. `body` (the raw, unparsed request bytes) is only
        used by channels that sign the payload itself (e.g. Facebook's
        X-Hub-Signature-256 HMAC) rather than a static per-request header
        value (e.g. Telegram's secret token) - most implementations ignore it.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        """Translates a raw webhook body into zero or more normalized messages."""
        raise NotImplementedError

    @abstractmethod
    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        """
        Sends an approved reply to the customer through this channel.
        `reply_to` is the metadata (see NormalizedIncomingMessage.metadata) of
        the most recent inbound message in the conversation - see
        OmnichannelService.get_reply_context - used only by channels that need
        it to properly thread a reply (currently just Gmail: Subject/
        In-Reply-To/References, see connectors/gmail.py); every other channel
        ignores it.
        """
        raise NotImplementedError

    def get_contact(self, external_user_id: str) -> Optional[Dict[str, Any]]:
        """Best-effort profile lookup (display name, phone...) for a customer identity. Optional per channel."""
        return None

    def download_attachment(self, attachment_ref: str) -> Optional[bytes]:
        """Fetches raw attachment bytes given the channel-specific reference stored in metadata. Optional per channel."""
        return None

    def get_status(self) -> Dict[str, Any]:
        """Lightweight health check used by the channel accounts list page."""
        return {"status": self.channel_account.status}
