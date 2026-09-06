"""
Business logic for message ingestion, customer/conversation resolution and
supporting CRM records (notes, tags, notifications, audit log) for the
Omnichannel Responder module. Draft/approval workflow lives in
omnichannel_draft_service.py - kept separate because it has its own
concurrency/idempotency concerns (see that file's docstring).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.core.security import EncryptionService
from app.integrations.omnichannel.connectors.base import NormalizedIncomingMessage
from app.models.omnichannel import (
    OmniAIAgentConfig,
    OmniAuditLog,
    OmniChannelAccount,
    OmniConversation,
    OmniCustomer,
    OmniCustomerIdentity,
    OmniInternalNote,
    OmniMessage,
    OmniNotification,
)
from app.schemas.schemas import OmniChannelAccountCreate, OmniChannelAccountUpdate

# Conversation statuses that should be reopened (not appended to silently) when
# a new inbound message arrives.
_TERMINAL_STATUSES = {"RESOLVED", "ARCHIVED"}


class OmnichannelService:
    @staticmethod
    def get_or_create_ai_agent_config(db: Session, owner_id: uuid.UUID) -> OmniAIAgentConfig:
        config = db.query(OmniAIAgentConfig).filter(OmniAIAgentConfig.owner_id == owner_id).first()
        if config:
            return config
        config = OmniAIAgentConfig(owner_id=owner_id)
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def create_channel_account(db: Session, owner_id: uuid.UUID, payload: OmniChannelAccountCreate) -> OmniChannelAccount:
        # Meta channels (Facebook/Instagram/WhatsApp) need two secrets - an
        # access token to send, an App Secret to verify inbound webhook
        # signatures - where Telegram/mock need one. Combined into a single
        # encrypted JSON blob so the access_token_encrypted column stays the
        # same shape for every channel. See connectors/facebook.py,
        # connectors/whatsapp.py. WhatsApp's Phone Number ID goes in the
        # existing external_account_id column instead (not a secret).
        if payload.channel in ("facebook", "instagram", "whatsapp") and payload.access_token:
            secret_payload = json.dumps({"access_token": payload.access_token, "app_secret": payload.app_secret or ""})
            access_token_encrypted = EncryptionService.encrypt(secret_payload)
        else:
            access_token_encrypted = EncryptionService.encrypt(payload.access_token) if payload.access_token else None

        account = OmniChannelAccount(
            owner_id=owner_id,
            channel=payload.channel,
            name=payload.name,
            external_account_id=payload.external_account_id,
            access_token_encrypted=access_token_encrypted,
            config_json=payload.config,
            status="pending",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def update_channel_account(db: Session, account: OmniChannelAccount, payload: OmniChannelAccountUpdate) -> OmniChannelAccount:
        """
        Completes/rotates credentials on an existing channel account - see
        OmniChannelAccountUpdate docstring for why this exists (WhatsApp/Meta
        channels can only be created with real credentials in hand today, but
        the webhook_secret an admin needs for Meta's Webhooks screen is only
        generated once the row exists, and channel-account creation has no
        other way to get it early).
        """
        if payload.name is not None:
            account.name = payload.name
        if payload.external_account_id is not None:
            account.external_account_id = payload.external_account_id
        if payload.config is not None:
            account.config_json = payload.config

        is_meta = account.channel in ("facebook", "instagram", "whatsapp")
        if payload.access_token:
            if is_meta:
                secret_payload = json.dumps({"access_token": payload.access_token, "app_secret": payload.app_secret or ""})
                account.access_token_encrypted = EncryptionService.encrypt(secret_payload)
            else:
                account.access_token_encrypted = EncryptionService.encrypt(payload.access_token)
        elif payload.app_secret and is_meta:
            # App Secret rotated without retyping the access_token - merge into
            # the existing encrypted blob rather than requiring both every time.
            existing = json.loads(EncryptionService.decrypt(account.access_token_encrypted)) if account.access_token_encrypted else {}
            existing["app_secret"] = payload.app_secret
            account.access_token_encrypted = EncryptionService.encrypt(json.dumps(existing))

        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def toggle_channel_account_status(db: Session, account: OmniChannelAccount) -> OmniChannelAccount:
        """
        On/off switch for receiving messages (channels/page.tsx toggle) -
        reuses the `status` column's "disabled" value (already documented on
        the model, previously never actually set or checked anywhere) rather
        than a new field. omnichannel_webhooks.py skips ingestion when status
        is "disabled", after signature verification, but the GET
        subscription handshake (_meta_webhook_verify) is unaffected - that's
        one-time setup, not "receiving messages".
        """
        account.status = "connected" if account.status == "disabled" else "disabled"
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def _find_or_create_customer(db: Session, owner_id: uuid.UUID, channel: str, external_user_id: str, display_name: Optional[str]) -> OmniCustomer:
        identity = (
            db.query(OmniCustomerIdentity)
            .filter(
                OmniCustomerIdentity.owner_id == owner_id,
                OmniCustomerIdentity.channel == channel,
                OmniCustomerIdentity.external_user_id == external_user_id,
            )
            .first()
        )
        if identity:
            return identity.customer

        customer = OmniCustomer(owner_id=owner_id, name=display_name)
        db.add(customer)
        db.flush()  # assign customer.id before the identity FK needs it

        identity = OmniCustomerIdentity(
            owner_id=owner_id,
            customer_id=customer.id,
            channel=channel,
            external_user_id=external_user_id,
            display_name=display_name,
        )
        db.add(identity)
        return customer

    @staticmethod
    def _find_or_create_conversation(db: Session, owner_id: uuid.UUID, channel_account: OmniChannelAccount, customer: OmniCustomer) -> OmniConversation:
        conversation = (
            db.query(OmniConversation)
            .filter(
                OmniConversation.owner_id == owner_id,
                OmniConversation.channel_account_id == channel_account.id,
                OmniConversation.customer_id == customer.id,
            )
            .order_by(OmniConversation.created_at.desc())
            .first()
        )
        if conversation and conversation.status not in _TERMINAL_STATUSES:
            return conversation

        conversation = OmniConversation(
            owner_id=owner_id,
            channel_account_id=channel_account.id,
            customer_id=customer.id,
            status="NEW",
        )
        db.add(conversation)
        db.flush()
        return conversation

    @staticmethod
    def ingest_message(db: Session, channel_account: OmniChannelAccount, normalized: NormalizedIncomingMessage) -> Optional[OmniMessage]:
        """
        Normalizes an inbound webhook event into customer/conversation/message
        rows. Returns None (no-op) if external_message_id was already ingested
        for this channel account - webhook idempotency per spec section 29,
        enforced here AND by the DB unique constraint as a hard backstop.
        """
        owner_id = channel_account.owner_id

        if normalized.external_message_id:
            existing = (
                db.query(OmniMessage)
                .filter(
                    OmniMessage.channel_account_id == channel_account.id,
                    OmniMessage.external_message_id == normalized.external_message_id,
                )
                .first()
            )
            if existing:
                return None

        customer = OmnichannelService._find_or_create_customer(
            db, owner_id, channel_account.channel, normalized.external_user_id, normalized.customer_display_name
        )
        conversation = OmnichannelService._find_or_create_conversation(db, owner_id, channel_account, customer)

        message = OmniMessage(
            owner_id=owner_id,
            conversation_id=conversation.id,
            channel_account_id=channel_account.id,
            direction="inbound",
            sender_type="customer",
            external_message_id=normalized.external_message_id,
            text=normalized.text,
            message_type=normalized.message_type,
            attachments_json=normalized.attachments or None,
            metadata_json=normalized.metadata or None,
            status="received",
        )
        db.add(message)

        now = datetime.now(timezone.utc)
        conversation.last_message_at = now
        conversation.unread_count = (conversation.unread_count or 0) + 1
        # A blocked customer's messages are still recorded (nothing silently
        # lost) but filed straight into SPAM instead of triggering AI
        # processing. If auto_generate_draft is off, the conversation just
        # goes to OPEN (needs attention, but no AI is running) instead of
        # AI_PROCESSING - the caller (_ingest_and_trigger) makes the matching
        # decision on whether to actually enqueue generate_ai_draft_task,
        # checking the exact same two conditions.
        if customer.is_blocked:
            conversation.status = "SPAM"
        else:
            agent_config = OmnichannelService.get_or_create_ai_agent_config(db, owner_id)
            conversation.status = "AI_PROCESSING" if agent_config.auto_generate_draft else "OPEN"
        customer.last_contact_at = now
        if normalized.customer_display_name and not customer.name:
            customer.name = normalized.customer_display_name

        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def ingest_messages_and_trigger_ai(db: Session, channel_account: OmniChannelAccount, messages: List[NormalizedIncomingMessage]) -> List[OmniMessage]:
        """
        Shared by every inbound entrypoint - the Telegram/Meta webhooks
        (app/api/v1/omnichannel_webhooks.py) and the Gmail poller
        (app/tasks/omnichannel.py::poll_gmail_channels_task) - so there is
        exactly one place deciding "does this new message get an AI draft
        queued", regardless of whether it arrived via push or pull. Local
        import of generate_ai_draft_task avoids a circular import: tasks/
        omnichannel.py imports this service at module level to call this very
        method.
        """
        from app.tasks.omnichannel import generate_ai_draft_task

        triggered = []
        for normalized in messages:
            message = OmnichannelService.ingest_message(db, channel_account, normalized)
            if message:
                customer = message.conversation.customer
                agent_config = OmnichannelService.get_or_create_ai_agent_config(db, channel_account.owner_id)
                if not customer.is_blocked and agent_config.auto_generate_draft:
                    generate_ai_draft_task.delay(str(message.id))
                triggered.append(message)
        return triggered

    @staticmethod
    def get_reply_context(db: Session, conversation_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        Metadata of the most recent inbound message in a conversation, passed
        to Connector.send_message so channels that need it to properly thread
        a reply (currently only Gmail - Subject/In-Reply-To/References, see
        connectors/gmail.py) have something to work with. Every other
        channel's send_message ignores this. Returns None if the conversation
        somehow has no inbound message yet, or that message never set
        metadata_json (e.g. Telegram messages don't carry a subject/thread id).
        """
        last_inbound = (
            db.query(OmniMessage)
            .filter(OmniMessage.conversation_id == conversation_id, OmniMessage.direction == "inbound")
            .order_by(OmniMessage.created_at.desc())
            .first()
        )
        return last_inbound.metadata_json if last_inbound else None

    @staticmethod
    def add_internal_note(db: Session, conversation: OmniConversation, admin_id: uuid.UUID, text: str, mentions: Optional[List[str]]) -> OmniInternalNote:
        note = OmniInternalNote(
            owner_id=conversation.owner_id,
            conversation_id=conversation.id,
            admin_id=admin_id,
            text=text,
            mentions_json=mentions,
        )
        db.add(note)
        for mention in mentions or []:
            OmnichannelService.create_notification(
                db, conversation.owner_id, None, "mention",
                f"Sei stato menzionato in una conversazione", text[:200],
                "conversation", conversation.id,
            )
        db.commit()
        db.refresh(note)
        return note

    @staticmethod
    def create_notification(
        db: Session, owner_id: uuid.UUID, admin_id: Optional[uuid.UUID], type_: str,
        title: str, body: Optional[str], entity_type: Optional[str], entity_id: Optional[uuid.UUID],
    ) -> OmniNotification:
        notification = OmniNotification(
            owner_id=owner_id, admin_id=admin_id, type=type_, title=title, body=body,
            entity_type=entity_type, entity_id=entity_id,
        )
        db.add(notification)
        return notification

    @staticmethod
    def log_audit(
        db: Session, owner_id: uuid.UUID, admin_id: Optional[uuid.UUID], action: str,
        entity_type: str, entity_id: Optional[uuid.UUID], metadata: Optional[Dict[str, Any]] = None,
    ) -> OmniAuditLog:
        audit = OmniAuditLog(owner_id=owner_id, admin_id=admin_id, action=action, entity_type=entity_type, entity_id=entity_id, metadata_json=metadata)
        db.add(audit)
        return audit
