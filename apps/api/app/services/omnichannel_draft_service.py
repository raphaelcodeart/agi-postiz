"""
AI draft generation + human-in-the-loop approval workflow. This is the one
place in the whole module allowed to call Connector.send_message() - the AI
itself never has a path to the outside world (see spec section 13).

Concurrency notes (spec sections 64/65):
- approve_and_send() flips the draft to SENDING inside its own commit before
  doing the (slow, external) connector call, and only proceeds past a
  `SELECT ... FOR UPDATE` if the draft is still in an approvable state. A
  second concurrent "Approve & Send" click reads the already-SENDING/SENT
  status and is rejected with a 409 by the router - no message is ever sent
  twice from a double click.
- Draft generation always reads the conversation's message history fresh
  from the DB at generation time (see integrations/omnichannel/ai.py::
  build_conversation_messages), so a burst of near-simultaneous inbound
  messages can't make the AI answer from stale context - each generation
  task, whenever it actually runs, sees everything committed so far.

Auto-reply (OmniAIAgentConfig.response_mode == "AUTO_REPLY"): approve_and_send
accepts admin=None for this case, and generate_draft_for_message calls it
itself right after generation, with the exact same status-guarded/row-locked
path a human click would use - there is no separate "auto send" code path to
audit. The one rule that response_mode can never override: a draft flagged
HUMAN_REVIEW_REQUIRED (sensitive topic, see integrations/omnichannel/ai.py::
detect_sensitive_category) is never auto-sent, full stop - only
PENDING_APPROVAL drafts are eligible, checked before approve_and_send is ever
called for this path.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.integrations.omnichannel import ai as omni_ai
from app.integrations.omnichannel.connectors.registry import get_connector
from app.integrations.omnichannel.exceptions import ConnectorError
from app.models.administrator import Administrator
from app.models.omnichannel import OmniAIDraft, OmniAIUsage, OmniCustomerIdentity, OmniMessage
from app.services.ai_settings_service import get_openai_credentials
from app.services.omnichannel_service import OmnichannelService

_APPROVABLE_STATUSES = {"PENDING_APPROVAL", "EDITED", "HUMAN_REVIEW_REQUIRED"}
# FAILED can always be retried from the UI (e.g. missing API key at generation
# time, transient OpenAI error) - it just can't be edited or sent directly,
# only regenerated from scratch.
_REGENERATABLE_STATUSES = _APPROVABLE_STATUSES | {"FAILED"}

# Very rough gpt-4o-mini-class pricing used only for the cost-tracking
# dashboard (spec section 69/33) - not tied to billing/enforcement of any kind.
_EST_COST_PER_1K_INPUT = 0.00015
_EST_COST_PER_1K_OUTPUT = 0.0006


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens / 1000) * _EST_COST_PER_1K_INPUT + (output_tokens / 1000) * _EST_COST_PER_1K_OUTPUT, 6)


class OmnichannelDraftService:
    @staticmethod
    def generate_draft_for_message(db: Session, message_id: uuid.UUID) -> Optional[OmniAIDraft]:
        message = db.query(OmniMessage).filter(OmniMessage.id == message_id).first()
        if not message:
            return None
        conversation = message.conversation
        owner_id = message.owner_id
        agent_config = OmnichannelService.get_or_create_ai_agent_config(db, owner_id)

        draft = OmniAIDraft(owner_id=owner_id, conversation_id=conversation.id, source_message_id=message.id, status="GENERATING")
        db.add(draft)
        db.commit()
        db.refresh(draft)

        api_key, model = get_openai_credentials(db)
        if not api_key:
            draft.status = "FAILED"
            draft.failure_reason = "Nessuna API key OpenAI configurata (Impostazioni > AI)"
            conversation.status = "OPEN"
            db.commit()
            return draft

        sensitive_category = omni_ai.detect_sensitive_category(message.text, agent_config.sensitive_categories_json)

        try:
            result = omni_ai.generate_ai_reply(db, api_key, model, agent_config, conversation, message.text or "")
        except ConnectorError as e:
            draft.status = "FAILED"
            draft.failure_reason = e.message
            conversation.status = "OPEN"
            OmnichannelService.log_audit(db, owner_id, None, "AI_GENERATION_FAILED", "ai_draft", draft.id, {"error": e.message})
            db.commit()
            return draft

        draft.original_ai_text = result["text"]
        draft.model = result["model"]
        draft.prompt_version = "v1"
        draft.status = "HUMAN_REVIEW_REQUIRED" if sensitive_category else "PENDING_APPROVAL"
        draft.sensitive_category = sensitive_category

        db.add(OmniAIUsage(
            owner_id=owner_id, conversation_id=conversation.id, model=result["model"],
            input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
            estimated_cost=_estimate_cost(result["input_tokens"], result["output_tokens"]),
        ))

        conversation.status = "WAITING_APPROVAL"

        # Auto-reply only ever fires for a plain PENDING_APPROVAL draft - a
        # sensitive-topic HUMAN_REVIEW_REQUIRED draft is never eligible,
        # regardless of response_mode (see module docstring).
        should_auto_send = not sensitive_category and agent_config.response_mode == "AUTO_REPLY"
        if not should_auto_send:
            OmnichannelService.create_notification(
                db, owner_id, None, "ai_ready", "Bozza AI pronta per l'approvazione",
                (draft.original_ai_text or "")[:200], "conversation", conversation.id,
            )
        OmnichannelService.log_audit(db, owner_id, None, "AI_GENERATED", "ai_draft", draft.id, {"sensitive_category": sensitive_category, "auto_reply": should_auto_send})

        db.commit()
        db.refresh(draft)

        if should_auto_send:
            try:
                OmnichannelDraftService.approve_and_send(db, draft.id, admin=None)
                OmnichannelService.create_notification(
                    db, owner_id, None, "ai_auto_sent", "L'AI ha risposto automaticamente",
                    (draft.original_ai_text or "")[:200], "conversation", conversation.id,
                )
                db.commit()
            except ValueError:
                pass  # approve_and_send already left the draft in FAILED state and committed that itself
            db.refresh(draft)

        return draft

    @staticmethod
    def edit_draft(db: Session, draft: OmniAIDraft, edited_text: str, admin: Administrator) -> OmniAIDraft:
        if draft.status not in _APPROVABLE_STATUSES:
            raise ValueError(f"Non è possibile modificare una bozza con stato {draft.status}")
        draft.edited_text = edited_text
        draft.status = "EDITED"
        OmnichannelService.log_audit(db, draft.owner_id, admin.id, "AI_EDITED", "ai_draft", draft.id)
        db.commit()
        db.refresh(draft)
        return draft

    @staticmethod
    def regenerate(db: Session, draft: OmniAIDraft, admin: Administrator) -> OmniAIDraft:
        if draft.status not in _REGENERATABLE_STATUSES:
            raise ValueError(f"Non è possibile rigenerare una bozza con stato {draft.status}")
        conversation = draft.conversation
        agent_config = OmnichannelService.get_or_create_ai_agent_config(db, draft.owner_id)
        api_key, model = get_openai_credentials(db)
        if not api_key:
            raise ValueError("Nessuna API key OpenAI configurata")

        source_message = db.query(OmniMessage).filter(OmniMessage.id == draft.source_message_id).first() if draft.source_message_id else None
        latest_text = source_message.text if source_message else ""
        sensitive_category = omni_ai.detect_sensitive_category(latest_text, agent_config.sensitive_categories_json)

        result = omni_ai.generate_ai_reply(db, api_key, model, agent_config, conversation, latest_text or "")

        draft.original_ai_text = result["text"]
        draft.edited_text = None
        draft.model = result["model"]
        draft.status = "HUMAN_REVIEW_REQUIRED" if sensitive_category else "PENDING_APPROVAL"
        draft.sensitive_category = sensitive_category
        draft.failure_reason = None

        db.add(OmniAIUsage(
            owner_id=draft.owner_id, conversation_id=conversation.id, model=result["model"],
            input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
            estimated_cost=_estimate_cost(result["input_tokens"], result["output_tokens"]),
        ))
        OmnichannelService.log_audit(db, draft.owner_id, admin.id, "AI_REGENERATED", "ai_draft", draft.id)

        db.commit()
        db.refresh(draft)
        return draft

    @staticmethod
    def reject(db: Session, draft: OmniAIDraft, admin: Administrator) -> OmniAIDraft:
        if draft.status in {"SENT", "SENDING"}:
            raise ValueError(f"Non è possibile scartare una bozza con stato {draft.status}")
        draft.status = "REJECTED"
        draft.conversation.status = "OPEN"
        OmnichannelService.log_audit(db, draft.owner_id, admin.id, "AI_REJECTED", "ai_draft", draft.id)
        db.commit()
        db.refresh(draft)
        return draft

    @staticmethod
    def approve_and_send(db: Session, draft_id: uuid.UUID, admin: Optional[Administrator]) -> Tuple[OmniAIDraft, OmniMessage]:
        """admin=None means this is an AUTO_REPLY send, not a human click - see module docstring."""
        # Row lock: guards against a double "Approve & Send" click racing on the
        # same draft (spec section 65). Held only for this short status-check
        # and flip, never across the outbound network call below.
        draft = db.query(OmniAIDraft).filter(OmniAIDraft.id == draft_id).with_for_update().first()
        if not draft:
            raise ValueError("Bozza non trovata")
        if draft.status not in _APPROVABLE_STATUSES:
            raise ValueError(f"Bozza già in stato {draft.status}, impossibile approvare di nuovo")

        text_to_send = draft.edited_text or draft.original_ai_text
        if not text_to_send:
            raise ValueError("La bozza non contiene testo da inviare")

        draft.status = "SENDING"
        db.commit()

        conversation = draft.conversation
        channel_account = conversation.channel_account
        identity = (
            db.query(OmniCustomerIdentity)
            .filter(
                OmniCustomerIdentity.owner_id == draft.owner_id,
                OmniCustomerIdentity.customer_id == conversation.customer_id,
                OmniCustomerIdentity.channel == channel_account.channel,
            )
            .first()
        )
        if not identity:
            draft.status = "FAILED"
            draft.failure_reason = "Nessuna identità cliente trovata per questo canale"
            db.commit()
            raise ValueError(draft.failure_reason)

        connector = get_connector(channel_account)
        reply_to = OmnichannelService.get_reply_context(db, conversation.id)
        try:
            send_result = connector.send_message(identity.external_user_id, text_to_send, reply_to=reply_to)
        except ConnectorError as e:
            draft.status = "FAILED"
            draft.failure_reason = e.message
            OmnichannelService.log_audit(db, draft.owner_id, admin.id if admin else None, "MESSAGE_FAILED", "ai_draft", draft.id, {"error": e.message})
            db.commit()
            raise ValueError(e.message)

        now = datetime.now(timezone.utc)
        outbound_message = OmniMessage(
            owner_id=draft.owner_id,
            conversation_id=conversation.id,
            channel_account_id=channel_account.id,
            direction="outbound",
            sender_type="operator" if draft.edited_text else "ai",
            external_message_id=send_result.external_message_id,
            text=text_to_send,
            message_type="TEXT",
            status="sent",
        )
        db.add(outbound_message)

        draft.status = "SENT"
        if not draft.approved_at:
            draft.approved_at = now
        draft.approved_by = admin.id if admin else None
        draft.sent_at = now

        conversation.status = "WAITING_CUSTOMER"
        conversation.last_message_at = now
        conversation.unread_count = 0

        approval_action = "AI_APPROVED" if admin else "AI_AUTO_SENT"
        OmnichannelService.log_audit(db, draft.owner_id, admin.id if admin else None, approval_action, "ai_draft", draft.id)
        OmnichannelService.log_audit(db, draft.owner_id, admin.id if admin else None, "MESSAGE_SENT", "message", outbound_message.id)

        db.commit()
        db.refresh(draft)
        db.refresh(outbound_message)
        return draft, outbound_message
