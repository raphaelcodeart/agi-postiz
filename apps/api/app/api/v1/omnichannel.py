"""
Omnichannel Responder - main CRUD/workflow API. Every query below is scoped
to `admin.id` (owner_id): this dashboard's only login identity is
Administrator (see app/api/v1/auth.py::get_current_admin), so "the user who
is logged in" and "the owner of this data" are the same id - the single
link required by this module's isolation rule. If this ever becomes
multi-admin, nothing here needs to change: every filter already scopes by
owner_id, never returning another admin's rows.

Webhooks (inbound channel traffic) live in a separate router -
omnichannel_webhooks.py - kept apart because it's unauthenticated (Telegram
can't send a JWT) and has its own verification story.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.omnichannel import (
    OmniAIDraft,
    OmniChannelAccount,
    OmniConversation,
    OmniCustomer,
    OmniKnowledgeChunk,
    OmniKnowledgeDocument,
    OmniMessage,
    OmniNotification,
    OmniTag,
    omni_conversation_tags,
)
from app.integrations.omnichannel.connectors.registry import get_connector, SUPPORTED_CHANNELS
from app.integrations.omnichannel.connectors.telegram import TelegramConnector
from app.integrations.omnichannel.exceptions import ConnectorError
from app.services.omnichannel_service import OmnichannelService
from app.services.omnichannel_draft_service import OmnichannelDraftService
from app.core.config import settings
from app.schemas.schemas import (
    OmniChannelAccountCreate,
    OmniChannelAccountUpdate,
    OmniChannelAccountResponse,
    OmniConversationListItem,
    OmniConversationDetailResponse,
    OmniConversationAssignRequest,
    OmniCustomerResponse,
    OmniCustomerUpdate,
    OmniMessageCreate,
    OmniMessageResponse,
    OmniBroadcastRequest,
    OmniBroadcastResult,
    OmniBroadcastFailure,
    OmniAIDraftResponse,
    OmniAIDraftEditRequest,
    OmniAIAgentConfigResponse,
    OmniAIAgentConfigUpdate,
    OmniKnowledgeDocumentCreate,
    OmniKnowledgeDocumentResponse,
    OmniTagCreate,
    OmniTagResponse,
    OmniInternalNoteCreate,
    OmniInternalNoteResponse,
    OmniNotificationResponse,
)

router = APIRouter()


def _owned_channel_account(db: Session, admin: Administrator, account_id: uuid.UUID) -> OmniChannelAccount:
    account = db.query(OmniChannelAccount).filter(OmniChannelAccount.id == account_id, OmniChannelAccount.owner_id == admin.id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Canale non trovato")
    return account


def _owned_conversation(db: Session, admin: Administrator, conversation_id: uuid.UUID) -> OmniConversation:
    conversation = (
        db.query(OmniConversation)
        .options(joinedload(OmniConversation.customer), joinedload(OmniConversation.channel_account))
        .filter(OmniConversation.id == conversation_id, OmniConversation.owner_id == admin.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    return conversation


def _owned_draft(db: Session, admin: Administrator, draft_id: uuid.UUID) -> OmniAIDraft:
    draft = db.query(OmniAIDraft).filter(OmniAIDraft.id == draft_id, OmniAIDraft.owner_id == admin.id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Bozza AI non trovata")
    return draft


# ==============================================================================
# Channel accounts
# ==============================================================================
@router.get("/channel-accounts", response_model=List[OmniChannelAccountResponse])
def list_channel_accounts(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    accounts = db.query(OmniChannelAccount).filter(OmniChannelAccount.owner_id == admin.id).order_by(OmniChannelAccount.created_at.desc()).all()

    # One conversation per customer who has ever written in on that channel
    # (see OmniConversation - a new conversation is only opened for a genuinely
    # new customer/topic, not one per message), so "how many people wrote to
    # us on this channel" is exactly a count of conversations, grouped by
    # channel_account_id in a single query rather than one COUNT per account.
    counts = dict(
        db.query(OmniConversation.channel_account_id, func.count(OmniConversation.id))
        .filter(OmniConversation.owner_id == admin.id)
        .group_by(OmniConversation.channel_account_id)
        .all()
    )
    for account in accounts:
        account.conversation_count = counts.get(account.id, 0)
    return accounts


@router.get("/channel-accounts/supported", response_model=List[str])
def list_supported_channels():
    return SUPPORTED_CHANNELS


@router.post("/channel-accounts", response_model=OmniChannelAccountResponse, status_code=status.HTTP_201_CREATED)
def create_channel_account(payload: OmniChannelAccountCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    if payload.channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Canale non supportato: {payload.channel}")
    account = OmnichannelService.create_channel_account(db, admin.id, payload)
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "channel_account", account.id, {"action": "created", "channel": account.channel})
    db.commit()
    return account


@router.put("/channel-accounts/{account_id}", response_model=OmniChannelAccountResponse)
def update_channel_account(account_id: uuid.UUID, payload: OmniChannelAccountUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Fills in or rotates a channel account's credentials after creation - e.g.
    a WhatsApp/Meta channel created with blank credentials just to obtain its
    webhook_secret for Meta's Webhooks screen (see OmniChannelAccountUpdate).
    """
    account = _owned_channel_account(db, admin, account_id)
    account = OmnichannelService.update_channel_account(db, account, payload)
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "channel_account", account.id, {"action": "updated", "channel": account.channel})
    db.commit()
    return account


@router.post("/channel-accounts/{account_id}/toggle", response_model=OmniChannelAccountResponse)
def toggle_channel_account(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """On/off switch to temporarily stop receiving messages from a channel (e.g. pause a Telegram bot for a few days) without deleting it - see OmnichannelService.toggle_channel_account_status."""
    account = _owned_channel_account(db, admin, account_id)
    account = OmnichannelService.toggle_channel_account_status(db, account)
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "channel_account", account.id, {"action": "status_toggled", "status": account.status})
    db.commit()
    return account


@router.get("/channel-accounts/{account_id}/status")
def get_channel_account_status(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    account = _owned_channel_account(db, admin, account_id)
    connector = get_connector(account)
    result = connector.get_status()
    account.status = result.get("status", account.status)
    db.commit()
    return result


@router.post("/channel-accounts/{account_id}/register-webhook")
def register_channel_webhook(account_id: uuid.UUID, public_base_url: str, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Points the channel provider at our webhook endpoint. Only meaningful for
    Telegram right now (the only real connector) - WhatsApp/Instagram/
    Facebook webhook registration happens through the Meta App dashboard,
    outside this API, once those connectors are implemented for real.
    """
    account = _owned_channel_account(db, admin, account_id)
    if account.channel != "telegram":
        raise HTTPException(status_code=400, detail="La registrazione automatica del webhook è disponibile solo per Telegram in questa versione")

    connector = get_connector(account)
    if not isinstance(connector, TelegramConnector):
        raise HTTPException(status_code=400, detail="Connettore non valido per questo canale")

    webhook_url = f"{public_base_url.rstrip('/')}{settings.API_V1_STR}/omnichannel-responder/webhooks/telegram/{account.id}"
    try:
        connector.register_webhook(webhook_url)
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message)

    account.status = "connected"
    db.commit()
    return {"webhook_url": webhook_url, "status": "connected"}


@router.delete("/channel-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel_account(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Cascades to every conversation/message/draft/note for this channel at
    the database level (see OmniChannelAccount.conversations' passive_deletes
    docstring in models/omnichannel.py for why that matters here). The
    try/except is a defensive backstop, not the actual fix - it turns any
    unforeseen future FK constraint into a clear 409 instead of a raw 500,
    it doesn't paper over the passive_deletes bug itself.
    """
    account = _owned_channel_account(db, admin, account_id)
    db.delete(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Impossibile eliminare il canale: dati collegati non rimovibili automaticamente.")
    return


# ==============================================================================
# Conversations
# ==============================================================================
@router.get("/conversations", response_model=List[OmniConversationListItem])
def list_conversations(
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = None,
    channel_account_id: Optional[uuid.UUID] = None,
    assigned_admin_id: Optional[uuid.UUID] = None,
    tag_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    query = (
        db.query(OmniConversation)
        .options(joinedload(OmniConversation.customer).joinedload(OmniCustomer.identities), joinedload(OmniConversation.channel_account), joinedload(OmniConversation.tags))
        .filter(OmniConversation.owner_id == admin.id)
    )
    if status_filter:
        query = query.filter(OmniConversation.status == status_filter)
    if channel:
        query = query.join(OmniChannelAccount).filter(OmniChannelAccount.channel == channel)
    if channel_account_id:
        # Distinguishes two connected accounts of the *same* channel type
        # (e.g. two different Telegram bots) - `channel` alone can't, since
        # both would report channel="telegram".
        query = query.filter(OmniConversation.channel_account_id == channel_account_id)
    if assigned_admin_id:
        query = query.filter(OmniConversation.assigned_admin_id == assigned_admin_id)
    if tag_id:
        query = query.filter(OmniConversation.tags.any(OmniTag.id == tag_id))
    if search:
        like = f"%{search}%"
        query = query.join(OmniCustomer).filter(
            or_(OmniCustomer.name.ilike(like), OmniCustomer.phone.ilike(like), OmniCustomer.email.ilike(like))
        )

    conversations = query.order_by(OmniConversation.last_message_at.desc().nullslast(), OmniConversation.created_at.desc()).offset(skip).limit(limit).all()

    items = []
    for conv in conversations:
        last_message = (
            db.query(OmniMessage).filter(OmniMessage.conversation_id == conv.id).order_by(OmniMessage.created_at.desc()).first()
        )
        items.append(OmniConversationListItem(
            id=conv.id,
            status=conv.status,
            channel=conv.channel_account.channel,
            channel_account_name=conv.channel_account.name,
            customer=conv.customer,
            assigned_admin_id=conv.assigned_admin_id,
            unread_count=conv.unread_count,
            last_message_at=conv.last_message_at,
            last_message_preview=(last_message.text[:200] if last_message and last_message.text else None),
            tags=conv.tags,
        ))
    return items


@router.get("/conversations/pending-count")
def get_pending_count(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Cheap single-query count for the sidebar notification dot: conversations
    needing attention right now - either a draft waiting for approval, or
    unread messages (including on an older conversation where the customer
    asked something new after it had already been dealt with). Registered
    before /conversations/{conversation_id} so "pending-count" is never
    misread as a conversation id (it would fail UUID validation anyway).
    """
    count = (
        db.query(OmniConversation)
        .filter(
            OmniConversation.owner_id == admin.id,
            or_(OmniConversation.status == "WAITING_APPROVAL", OmniConversation.unread_count > 0),
        )
        .count()
    )
    return {"count": count}


@router.get("/conversations/{conversation_id}", response_model=OmniConversationDetailResponse)
def get_conversation_detail(conversation_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    if conversation.unread_count:
        conversation.unread_count = 0
        db.commit()
        db.refresh(conversation)
    return OmniConversationDetailResponse(
        id=conversation.id,
        status=conversation.status,
        channel=conversation.channel_account.channel,
        channel_account_id=conversation.channel_account_id,
        channel_account_name=conversation.channel_account.name,
        customer=conversation.customer,
        assigned_admin_id=conversation.assigned_admin_id,
        unread_count=conversation.unread_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        tags=conversation.tags,
        messages=conversation.messages,
        drafts=sorted(conversation.drafts, key=lambda d: d.created_at),
        notes=conversation.notes,
    )


@router.post("/conversations/{conversation_id}/assign", response_model=OmniConversationDetailResponse)
def assign_conversation(conversation_id: uuid.UUID, payload: OmniConversationAssignRequest, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    conversation.assigned_admin_id = payload.assigned_admin_id
    OmnichannelService.log_audit(db, admin.id, admin.id, "ASSIGNMENT_CHANGED", "conversation", conversation.id, {"assigned_admin_id": str(payload.assigned_admin_id) if payload.assigned_admin_id else None})
    if payload.assigned_admin_id:
        OmnichannelService.create_notification(db, admin.id, payload.assigned_admin_id, "conversation_assigned", "Ti è stata assegnata una conversazione", None, "conversation", conversation.id)
    db.commit()
    return get_conversation_detail(conversation_id, db, admin)


@router.post("/conversations/{conversation_id}/resolve", response_model=OmniConversationDetailResponse)
def resolve_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    conversation.status = "RESOLVED"
    db.commit()
    return get_conversation_detail(conversation_id, db, admin)


@router.post("/conversations/{conversation_id}/archive", response_model=OmniConversationDetailResponse)
def archive_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    conversation.status = "ARCHIVED"
    db.commit()
    return get_conversation_detail(conversation_id, db, admin)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Permanently deletes the conversation and everything tied to it - messages,
    AI drafts, internal notes, tag associations - via the ondelete=CASCADE FKs
    already on those tables (see app/models/omnichannel.py). Irreversible;
    the frontend confirms explicitly before calling this. omni_ai_usage rows
    survive (ondelete=SET NULL) so cost-tracking history isn't lost.
    """
    conversation = _owned_conversation(db, admin, conversation_id)
    OmnichannelService.log_audit(
        db, admin.id, admin.id, "CONVERSATION_DELETED", "conversation", conversation.id,
        {"channel": conversation.channel_account.channel, "customer_id": str(conversation.customer_id)},
    )
    db.delete(conversation)
    db.commit()
    return


@router.post("/conversations/{conversation_id}/tags/{tag_id}", response_model=OmniConversationDetailResponse)
def add_conversation_tag(conversation_id: uuid.UUID, tag_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    tag = db.query(OmniTag).filter(OmniTag.id == tag_id, OmniTag.owner_id == admin.id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag non trovato")

    # Deliberately NOT conversation.tags.append(tag): SQLAlchemy's automatic
    # secondary-table sync only ever writes the two association columns, and
    # would violate omni_conversation_tags.owner_id's NOT NULL constraint (see
    # its column comment in app/models/omnichannel.py). Insert explicitly instead.
    already_tagged = db.execute(
        select(omni_conversation_tags.c.tag_id).where(
            omni_conversation_tags.c.conversation_id == conversation.id,
            omni_conversation_tags.c.tag_id == tag_id,
        )
    ).first()
    if not already_tagged:
        db.execute(insert(omni_conversation_tags).values(owner_id=admin.id, conversation_id=conversation.id, tag_id=tag.id))
        db.commit()
    return get_conversation_detail(conversation_id, db, admin)


@router.delete("/conversations/{conversation_id}/tags/{tag_id}", response_model=OmniConversationDetailResponse)
def remove_conversation_tag(conversation_id: uuid.UUID, tag_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    conversation.tags = [t for t in conversation.tags if t.id != tag_id]
    db.commit()
    return get_conversation_detail(conversation_id, db, admin)


@router.post("/conversations/{conversation_id}/notes", response_model=OmniInternalNoteResponse, status_code=status.HTTP_201_CREATED)
def add_note(conversation_id: uuid.UUID, payload: OmniInternalNoteCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversation = _owned_conversation(db, admin, conversation_id)
    return OmnichannelService.add_internal_note(db, conversation, admin.id, payload.text, payload.mentions)


@router.post("/conversations/{conversation_id}/messages", response_model=OmniMessageResponse, status_code=status.HTTP_201_CREATED)
def send_manual_message(conversation_id: uuid.UUID, payload: OmniMessageCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Operator sends a free-form message directly, bypassing the AI draft workflow entirely."""
    conversation = _owned_conversation(db, admin, conversation_id)
    channel_account = conversation.channel_account
    from app.models.omnichannel import OmniCustomerIdentity
    identity = db.query(OmniCustomerIdentity).filter(
        OmniCustomerIdentity.owner_id == admin.id,
        OmniCustomerIdentity.customer_id == conversation.customer_id,
        OmniCustomerIdentity.channel == channel_account.channel,
    ).first()
    if not identity:
        raise HTTPException(status_code=400, detail="Nessuna identità cliente trovata per questo canale")

    connector = get_connector(channel_account)
    reply_to = OmnichannelService.get_reply_context(db, conversation.id)
    try:
        send_result = connector.send_message(identity.external_user_id, payload.text, reply_to=reply_to)
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message)

    message = OmniMessage(
        owner_id=admin.id, conversation_id=conversation.id, channel_account_id=channel_account.id,
        direction="outbound", sender_type="operator", external_message_id=send_result.external_message_id,
        text=payload.text, message_type="TEXT", status="sent",
    )
    db.add(message)
    conversation.status = "WAITING_CUSTOMER"
    conversation.last_message_at = datetime.now(timezone.utc)
    OmnichannelService.log_audit(db, admin.id, admin.id, "MESSAGE_SENT", "message", message.id)
    db.commit()
    db.refresh(message)
    return message


@router.post("/conversations/{conversation_id}/generate-draft", response_model=OmniAIDraftResponse, status_code=status.HTTP_201_CREATED)
def generate_draft_on_demand(conversation_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Manual trigger for AI Agent config.auto_generate_draft=False: generates a
    draft for the latest inbound customer message in this conversation, on
    the operator's explicit request instead of automatically. Calls the
    exact same generate_draft_for_message() an automatic ingest would have
    used - no separate/simplified code path, so sensitive-topic detection,
    AUTO_REPLY, everything behaves identically either way (see
    OmniAIAgentConfig.auto_generate_draft docstring).
    """
    conversation = _owned_conversation(db, admin, conversation_id)
    if conversation.customer.is_blocked:
        raise HTTPException(status_code=400, detail="Questo cliente è bloccato: non è possibile generare risposte AI per lui")

    latest_inbound = (
        db.query(OmniMessage)
        .filter(OmniMessage.conversation_id == conversation.id, OmniMessage.direction == "inbound")
        .order_by(OmniMessage.created_at.desc())
        .first()
    )
    if not latest_inbound:
        raise HTTPException(status_code=400, detail="Nessun messaggio del cliente per cui generare una risposta")

    # Idempotent: if a non-rejected draft already exists for this exact
    # message (e.g. a second click), return it instead of generating a
    # duplicate and spending another OpenAI call for nothing.
    existing = (
        db.query(OmniAIDraft)
        .filter(OmniAIDraft.source_message_id == latest_inbound.id, OmniAIDraft.status != "REJECTED")
        .order_by(OmniAIDraft.created_at.desc())
        .first()
    )
    if existing:
        return existing

    draft = OmnichannelDraftService.generate_draft_for_message(db, latest_inbound.id)
    if not draft:
        raise HTTPException(status_code=500, detail="Impossibile generare la bozza")
    return draft


# Hard cap on a single broadcast request - keeps this a synchronous,
# immediate-feedback request (the admin sees exactly who succeeded/failed
# right away) instead of needing a background task + polling. Deliberately
# conservative: this is a manual, occasional admin action on a small/medium
# contact list, not a marketing blast tool - see docs/OMNICHANNEL_RESPONDER.md
# §5 (broadcast) for the reasoning and the WhatsApp/Meta 24h-window caveat.
_MAX_BROADCAST_RECIPIENTS = 50


@router.post("/broadcast", response_model=OmniBroadcastResult)
def send_broadcast(payload: OmniBroadcastRequest, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Sends the same free-form text to many existing conversations at once -
    "message everyone who's contacted me". Uses the inbox itself as the
    address book (every OmniConversation already ties a customer to a
    channel + identity) rather than introducing a separate contacts concept.

    Blocked customers are always skipped, even if explicitly selected -
    blocking must never be bypassable by a bulk action. ARCHIVED/SPAM
    conversations are excluded from "send to everyone" by default, but an
    explicit conversation_ids selection can still target an ARCHIVED one
    deliberately (SPAM/blocked customers are excluded no matter what).

    Runs synchronously with a hard recipient cap (_MAX_BROADCAST_RECIPIENTS)
    - see that constant's comment for why this isn't a background task.
    """
    from app.models.omnichannel import OmniCustomerIdentity

    query = (
        db.query(OmniConversation)
        .options(joinedload(OmniConversation.customer), joinedload(OmniConversation.channel_account))
        .filter(OmniConversation.owner_id == admin.id)
    )
    if payload.conversation_ids:
        query = query.filter(OmniConversation.id.in_(payload.conversation_ids))
    else:
        query = query.filter(OmniConversation.status.notin_(["ARCHIVED", "SPAM"]))
    conversations = query.all()

    if len(conversations) > _MAX_BROADCAST_RECIPIENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Troppi destinatari selezionati ({len(conversations)}): massimo {_MAX_BROADCAST_RECIPIENTS} per singolo invio multiplo.",
        )

    sent = 0
    failures: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for conversation in conversations:
        if conversation.customer.is_blocked:
            continue  # never bypassable by selection, see docstring

        identity = db.query(OmniCustomerIdentity).filter(
            OmniCustomerIdentity.owner_id == admin.id,
            OmniCustomerIdentity.customer_id == conversation.customer_id,
            OmniCustomerIdentity.channel == conversation.channel_account.channel,
        ).first()
        if not identity:
            failures.append({"conversation_id": conversation.id, "customer_name": conversation.customer.name, "channel": conversation.channel_account.channel, "error": "Nessuna identità cliente trovata per questo canale"})
            continue

        try:
            connector = get_connector(conversation.channel_account)
            reply_to = OmnichannelService.get_reply_context(db, conversation.id)
            send_result = connector.send_message(identity.external_user_id, payload.text, reply_to=reply_to)
        except ConnectorError as e:
            failures.append({"conversation_id": conversation.id, "customer_name": conversation.customer.name, "channel": conversation.channel_account.channel, "error": e.message})
            continue

        db.add(OmniMessage(
            owner_id=admin.id, conversation_id=conversation.id, channel_account_id=conversation.channel_account_id,
            direction="outbound", sender_type="operator", external_message_id=send_result.external_message_id,
            text=payload.text, message_type="TEXT", status="sent",
        ))
        conversation.status = "WAITING_CUSTOMER"
        conversation.last_message_at = now
        sent += 1

    OmnichannelService.log_audit(
        db, admin.id, admin.id, "BROADCAST_SENT", "conversation", None,
        {"total_targeted": len(conversations), "sent": sent, "failed": len(failures), "text_preview": payload.text[:200]},
    )
    db.commit()

    return OmniBroadcastResult(total_targeted=len(conversations), sent=sent, failed=len(failures), failures=[OmniBroadcastFailure(**f) for f in failures])


# ==============================================================================
# Customers
# ==============================================================================
@router.get("/customers/{customer_id}", response_model=OmniCustomerResponse)
def get_customer(customer_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    customer = db.query(OmniCustomer).filter(OmniCustomer.id == customer_id, OmniCustomer.owner_id == admin.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return customer


@router.patch("/customers/{customer_id}", response_model=OmniCustomerResponse)
def update_customer(customer_id: uuid.UUID, payload: OmniCustomerUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    customer = db.query(OmniCustomer).filter(OmniCustomer.id == customer_id, OmniCustomer.owner_id == admin.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    OmnichannelService.log_audit(db, admin.id, admin.id, "CUSTOMER_UPDATED", "customer", customer.id)
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/customers/{customer_id}/block", response_model=OmniCustomerResponse)
def block_customer(customer_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Blocks a customer: their future messages are still recorded (nothing
    silently lost) but the conversation is filed straight into SPAM and no
    AI draft is ever generated for it (see OmniCustomer.is_blocked
    docstring). Does not touch existing conversations/messages/drafts.
    """
    customer = db.query(OmniCustomer).filter(OmniCustomer.id == customer_id, OmniCustomer.owner_id == admin.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    customer.is_blocked = True
    OmnichannelService.log_audit(db, admin.id, admin.id, "CUSTOMER_BLOCKED", "customer", customer.id)
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/customers/{customer_id}/unblock", response_model=OmniCustomerResponse)
def unblock_customer(customer_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    customer = db.query(OmniCustomer).filter(OmniCustomer.id == customer_id, OmniCustomer.owner_id == admin.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    customer.is_blocked = False
    OmnichannelService.log_audit(db, admin.id, admin.id, "CUSTOMER_UNBLOCKED", "customer", customer.id)
    db.commit()
    db.refresh(customer)
    return customer


# ==============================================================================
# Tags
# ==============================================================================
@router.get("/tags", response_model=List[OmniTagResponse])
def list_tags(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return db.query(OmniTag).filter(OmniTag.owner_id == admin.id).order_by(OmniTag.name).all()


@router.post("/tags", response_model=OmniTagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(payload: OmniTagCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    existing = db.query(OmniTag).filter(OmniTag.owner_id == admin.id, OmniTag.name == payload.name).first()
    if existing:
        return existing
    tag = OmniTag(owner_id=admin.id, name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


# ==============================================================================
# AI drafts - approve / edit / regenerate / reject
# ==============================================================================
@router.patch("/drafts/{draft_id}", response_model=OmniAIDraftResponse)
def edit_draft(draft_id: uuid.UUID, payload: OmniAIDraftEditRequest, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    draft = _owned_draft(db, admin, draft_id)
    try:
        return OmnichannelDraftService.edit_draft(db, draft, payload.edited_text, admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/drafts/{draft_id}/approve", response_model=OmniAIDraftResponse)
def approve_draft(draft_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    _owned_draft(db, admin, draft_id)  # 404 check before the service's own row lock
    try:
        draft, _message = OmnichannelDraftService.approve_and_send(db, draft_id, admin)
        return draft
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/drafts/{draft_id}/regenerate", response_model=OmniAIDraftResponse)
def regenerate_draft(draft_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    draft = _owned_draft(db, admin, draft_id)
    try:
        return OmnichannelDraftService.regenerate(db, draft, admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/drafts/{draft_id}/reject", response_model=OmniAIDraftResponse)
def reject_draft(draft_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    draft = _owned_draft(db, admin, draft_id)
    try:
        return OmnichannelDraftService.reject(db, draft, admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# AI Agent configuration
# ==============================================================================
@router.get("/ai-agent", response_model=OmniAIAgentConfigResponse)
def get_ai_agent_config(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return OmnichannelService.get_or_create_ai_agent_config(db, admin.id)


@router.put("/ai-agent", response_model=OmniAIAgentConfigResponse)
def update_ai_agent_config(payload: OmniAIAgentConfigUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    config = OmnichannelService.get_or_create_ai_agent_config(db, admin.id)
    updates = payload.model_dump(exclude_unset=True)

    if "response_mode" in updates and updates["response_mode"] not in ("MANUAL", "APPROVAL_REQUIRED", "AUTO_REPLY"):
        raise HTTPException(status_code=400, detail=f"response_mode non valido: {updates['response_mode']}")

    previous_response_mode = config.response_mode
    field_map = {"allowed_topics": "allowed_topics_json", "forbidden_topics": "forbidden_topics_json", "sensitive_categories": "sensitive_categories_json"}
    for field, value in updates.items():
        setattr(config, field_map.get(field, field), value)

    # response_mode toggles whether the AI can send messages to real customers
    # on its own - worth its own explicit, easy-to-find audit entry beyond the
    # generic SETTINGS_CHANGED below.
    if "response_mode" in updates and updates["response_mode"] != previous_response_mode:
        OmnichannelService.log_audit(
            db, admin.id, admin.id, "AI_RESPONSE_MODE_CHANGED", "ai_agent_config", config.id,
            {"from": previous_response_mode, "to": updates["response_mode"]},
        )

    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "ai_agent_config", config.id)
    db.commit()
    db.refresh(config)
    return config


# ==============================================================================
# Knowledge base (keyword-search RAG - see integrations/omnichannel/ai.py)
# ==============================================================================
def _chunk_text(text: str, max_len: int = 500) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    for paragraph in paragraphs:
        while len(paragraph) > max_len:
            cut = paragraph.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if paragraph:
            chunks.append(paragraph)
    return chunks


@router.get("/knowledge-base", response_model=List[OmniKnowledgeDocumentResponse])
def list_knowledge_documents(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return db.query(OmniKnowledgeDocument).filter(OmniKnowledgeDocument.owner_id == admin.id).order_by(OmniKnowledgeDocument.created_at.desc()).all()


@router.post("/knowledge-base", response_model=OmniKnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_document(payload: OmniKnowledgeDocumentCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    document = OmniKnowledgeDocument(
        owner_id=admin.id, title=payload.title, source_type=payload.source_type,
        content_text=payload.content_text, source_url=payload.source_url, status="ready",
    )
    db.add(document)
    db.flush()

    if payload.content_text:
        for index, chunk_content in enumerate(_chunk_text(payload.content_text)):
            db.add(OmniKnowledgeChunk(owner_id=admin.id, document_id=document.id, chunk_index=index, content=chunk_content))

    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "knowledge_document", document.id, {"action": "created"})
    db.commit()
    db.refresh(document)
    return document


@router.delete("/knowledge-base/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_document(document_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    document = db.query(OmniKnowledgeDocument).filter(OmniKnowledgeDocument.id == document_id, OmniKnowledgeDocument.owner_id == admin.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    db.delete(document)
    db.commit()
    return


# ==============================================================================
# Notifications
# ==============================================================================
@router.get("/notifications", response_model=List[OmniNotificationResponse])
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    query = db.query(OmniNotification).filter(
        OmniNotification.owner_id == admin.id,
        or_(OmniNotification.admin_id == admin.id, OmniNotification.admin_id.is_(None)),
    )
    if unread_only:
        query = query.filter(OmniNotification.read_at.is_(None))
    return query.order_by(OmniNotification.created_at.desc()).limit(limit).all()


@router.post("/notifications/{notification_id}/read", response_model=OmniNotificationResponse)
def mark_notification_read(notification_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    notification = db.query(OmniNotification).filter(OmniNotification.id == notification_id, OmniNotification.owner_id == admin.id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification


# ==============================================================================
# Analytics (spec sections 33/34) - AI acceptance/edit/rejection rate
# ==============================================================================
@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    conversations_total = db.query(OmniConversation).filter(OmniConversation.owner_id == admin.id).count()
    open_statuses = ["NEW", "OPEN", "AI_PROCESSING", "WAITING_APPROVAL", "WAITING_CUSTOMER"]
    conversations_open = db.query(OmniConversation).filter(OmniConversation.owner_id == admin.id, OmniConversation.status.in_(open_statuses)).count()

    messages_received = db.query(OmniMessage).filter(OmniMessage.owner_id == admin.id, OmniMessage.direction == "inbound").count()
    messages_sent = db.query(OmniMessage).filter(OmniMessage.owner_id == admin.id, OmniMessage.direction == "outbound").count()

    drafts_sent_unedited = db.query(OmniAIDraft).filter(OmniAIDraft.owner_id == admin.id, OmniAIDraft.status == "SENT", OmniAIDraft.edited_text.is_(None)).count()
    drafts_sent_edited = db.query(OmniAIDraft).filter(OmniAIDraft.owner_id == admin.id, OmniAIDraft.status == "SENT", OmniAIDraft.edited_text.isnot(None)).count()
    drafts_rejected = db.query(OmniAIDraft).filter(OmniAIDraft.owner_id == admin.id, OmniAIDraft.status == "REJECTED").count()
    drafts_terminal = drafts_sent_unedited + drafts_sent_edited + drafts_rejected

    return {
        "conversations_total": conversations_total,
        "conversations_open": conversations_open,
        "messages_received": messages_received,
        "messages_sent": messages_sent,
        "ai_drafts_approved_unedited": drafts_sent_unedited,
        "ai_drafts_approved_edited": drafts_sent_edited,
        "ai_drafts_rejected": drafts_rejected,
        "ai_acceptance_rate": round(drafts_sent_unedited / drafts_terminal, 4) if drafts_terminal else None,
        "ai_edit_rate": round(drafts_sent_edited / drafts_terminal, 4) if drafts_terminal else None,
        "ai_rejection_rate": round(drafts_rejected / drafts_terminal, 4) if drafts_terminal else None,
    }
