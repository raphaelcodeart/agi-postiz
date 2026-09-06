"""
Gmail channel via IMAP (receive) + SMTP (send), stdlib only - no Google Cloud
project/OAuth needed, unlike the Gmail API alternative (push notifications
would require a Cloud Pub/Sub topic and a users.watch() renewed every 7 days,
see docs/OMNICHANNEL_RESPONDER.md SS11). Trade-off accepted for this v1:
incoming mail is picked up by polling (poll_gmail_channels_task, see
app/tasks/omnichannel.py) instead of pushed instantly.

Auth: a Gmail "App Password" (Google Account > Security > App passwords,
requires 2-Step Verification on the account) - never the account's normal
login password. Stored encrypted in access_token_encrypted like every other
channel (see OmnichannelService.create_channel_account); external_account_id
holds the Gmail address itself, used as the IMAP/SMTP username.

Replies thread properly, both in this app's Inbox and in the real Gmail
mailbox: send_message's `reply_to` param (see Connector.send_message and
OmnichannelService.get_reply_context) carries the Subject/Message-ID of the
customer's original message, reused as Subject/In-Reply-To/References on the
outgoing mail (RFC 2822). Every reply also goes out through smtp.gmail.com
using the account's own credentials, which - a Gmail-specific SMTP behavior,
not a general one - automatically saves a copy to that account's own "Sent"
folder, exactly like sending from the Gmail web UI. Net effect: nothing sent
or received through this channel is hidden from the real Gmail mailbox, and
opening Gmail directly shows the same conversation as this app's Inbox.
Falls back to a fixed Subject ("Re: {account.name}") only when `reply_to` is
absent, which shouldn't normally happen - every reply here always follows an
inbound message.
"""
import email
import imaplib
import smtplib
from email.header import decode_header
from email.message import EmailMessage, Message
from email.utils import make_msgid, parseaddr
from typing import Any, Dict, List, Optional, Tuple
from app.integrations.omnichannel.connectors.base import Connector, NormalizedIncomingMessage, SendResult
from app.integrations.omnichannel.exceptions import ConnectorError

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    )


class GmailConnector(Connector):
    def _credentials(self) -> Tuple[str, str]:
        address = self.channel_account.external_account_id
        if not address or not self.access_token:
            raise ConnectorError("Indirizzo Gmail o App Password mancanti per questo canale")
        return address, self.access_token

    # --- Not applicable to this channel: Gmail has no inbound webhook, see
    # module docstring - ingestion happens through fetch_new_messages below,
    # called by poll_gmail_channels_task, never through these ABC methods.
    def verify_webhook(self, headers: Dict[str, str], path_secret: str, body: bytes = b"") -> bool:
        raise NotImplementedError("GmailConnector riceve via polling IMAP, non via webhook")

    def parse_webhook(self, payload: Dict[str, Any]) -> List[NormalizedIncomingMessage]:
        raise NotImplementedError("GmailConnector riceve via polling IMAP, non via webhook")

    def fetch_new_messages(self, since_uid: Optional[int]) -> Tuple[List[NormalizedIncomingMessage], Optional[int]]:
        """
        Incremental IMAP UID fetch. `since_uid=None` (first run for this
        channel account) reads only currently-unread mail, so connecting an
        existing mailbox never backfills its entire history - same principle
        as Telegram only receiving updates sent after setWebhook. Every run
        after that fetches everything with UID > since_uid regardless of its
        \\Seen flag, which is what makes this idempotent/resumable across
        restarts (state lives in omni_channel_accounts.config_json.last_uid,
        not in IMAP flags). Uses BODY.PEEK[] rather than RFC822 to fetch
        without marking messages as read in the real mailbox - a side effect
        a shared support inbox should never cause silently.
        """
        address, app_password = self._credentials()
        messages: List[NormalizedIncomingMessage] = []
        max_uid = since_uid

        try:
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
                imap.login(address, app_password)
                status, _ = imap.select("INBOX")
                if status != "OK":
                    raise ConnectorError("Impossibile aprire INBOX su Gmail")

                if since_uid is None:
                    search_status, data = imap.uid("search", None, "UNSEEN")
                else:
                    search_status, data = imap.uid("search", None, f"UID {since_uid + 1}:*")
                if search_status != "OK":
                    raise ConnectorError("Ricerca IMAP fallita")

                raw_uids = data[0].split() if data and data[0] else []
                # "UID N:*" ripete N stesso se non ci sono messaggi con UID
                # maggiore - va scartato esplicitamente per non ri-ingerire
                # l'ultimo messaggio già visto ad ogni esecuzione.
                uids = [int(uid) for uid in raw_uids if since_uid is None or int(uid) > since_uid]

                for uid in uids:
                    fetch_status, msg_data = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
                    if fetch_status != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)
                    normalized = self._normalize(parsed)
                    if normalized:
                        messages.append(normalized)
                    max_uid = uid if max_uid is None else max(max_uid, uid)
        except imaplib.IMAP4.error as e:
            raise ConnectorError(f"Errore IMAP verso Gmail: {str(e)}") from e

        return messages, max_uid

    def _normalize(self, parsed: Message) -> Optional[NormalizedIncomingMessage]:
        from_name, from_addr = parseaddr(_decode_header_value(parsed.get("From")))
        if not from_addr:
            return None

        text_body: Optional[str] = None
        html_body: Optional[str] = None
        if parsed.is_multipart():
            for part in parsed.walk():
                if "attachment" in str(part.get("Content-Disposition") or ""):
                    continue
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                decoded = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                if content_type == "text/plain" and text_body is None:
                    text_body = decoded
                elif content_type == "text/html" and html_body is None:
                    html_body = decoded
        else:
            payload = parsed.get_payload(decode=True)
            if payload is not None:
                charset = parsed.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if parsed.get_content_type() == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded

        return NormalizedIncomingMessage(
            external_user_id=from_addr.lower(),
            text=text_body or html_body or "",
            message_type="TEXT",
            external_message_id=parsed.get("Message-ID"),
            customer_display_name=from_name or None,
            attachments=[],
            metadata={
                "subject": _decode_header_value(parsed.get("Subject")),
                "message_id": parsed.get("Message-ID"),
                "html_body": html_body,
            },
        )

    def send_message(self, external_user_id: str, text: str, reply_to: Optional[Dict[str, Any]] = None) -> SendResult:
        """
        `reply_to` (see OmnichannelService.get_reply_context) is the metadata
        of the customer's last inbound message in this conversation - when
        present, its Subject/Message-ID are reused so the reply threads
        properly with real Gmail/RFC headers (In-Reply-To/References) and
        shows up as one conversation in Gmail's own UI, not a disconnected
        new email. Falls back to a fixed Subject only when there's nothing to
        thread against (shouldn't normally happen - every reply here is
        always in response to an inbound message).
        """
        address, app_password = self._credentials()

        original_subject = (reply_to or {}).get("subject")
        original_message_id = (reply_to or {}).get("message_id")
        if original_subject:
            subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
        else:
            subject = f"Re: {self.channel_account.name}"

        msg = EmailMessage()
        msg["From"] = address
        msg["To"] = external_user_id
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid()
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id
        msg.set_content(text)

        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.login(address, app_password)
                smtp.send_message(msg)
        except smtplib.SMTPException as e:
            raise ConnectorError(f"Errore SMTP verso Gmail: {str(e)}") from e

        return SendResult(external_message_id=msg["Message-ID"], raw_response=None)

    def get_status(self) -> Dict[str, Any]:
        try:
            address, app_password = self._credentials()
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
                imap.login(address, app_password)
        except (imaplib.IMAP4.error, ConnectorError) as e:
            return {"status": "error", "detail": str(e)}
        return {"status": "connected", "address": address}
