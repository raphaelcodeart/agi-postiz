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
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer, joinedload
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.omnichannel import (
    OmniAIDraft,
    OmniChannelAccount,
    OmniConversation,
    OmniCustomer,
    OmniKnowledgeChunk,
    OmniKnowledgeCompany,
    OmniKnowledgeDocument,
    OmniMessage,
    OmniNotification,
    OmniTag,
    omni_conversation_tags,
)
from app.integrations.omnichannel.connectors.maytapi import MaytapiConnector
from app.integrations.omnichannel.connectors.registry import get_connector, SUPPORTED_CHANNELS
from app.integrations.omnichannel.connectors.telegram import TelegramConnector
from app.integrations.omnichannel.exceptions import ConnectorError
from app.integrations.omnichannel import ai as omni_ai
from app.integrations.omnichannel import knowledge
from app.integrations.omnichannel.crm import tools as crm_tools
from app.integrations.omnichannel.crm.mamify import MamifyError, MamifyRagClient
from app.core.security import EncryptionService
from app.services.ai_settings_service import get_openai_credentials
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
    OmniKnowledgeCompanyCreate,
    OmniKnowledgeCompanyResponse,
    OmniKnowledgeCompanyUpdate,
    OmniKnowledgeDocumentCreate,
    OmniKnowledgeDocumentMove,
    OmniKnowledgeDocumentResponse,
    OmniKnowledgeDocumentUpdate,
    OmniKnowledgeSearchRequest,
    OmniKnowledgeSearchResponse,
    OmniKnowledgeSearchHit,
    OmniKnowledgeStatsResponse,
    OmniTagCreate,
    OmniTagResponse,
    OmniInternalNoteCreate,
    OmniInternalNoteResponse,
    OmniNotificationResponse,
    OmniCrmKeyCheckResponse,
    OmniCustomerCrmProfileResponse,
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
    Points the channel provider at our webhook endpoint.

    Only two channels can do this from here: Telegram (setWebhook) and
    WhatsApp-via-Maytapi (setWebhook). Facebook/Instagram/WhatsApp Cloud API
    are registered by hand in the Meta App dashboard instead - Meta has no
    API to subscribe a webhook, it's a screen - which is what the "Info
    webhook" dialog in the channels list exists to support.

    Maytapi's URL carries the account's webhook_secret as a path segment,
    Telegram's doesn't: Telegram sends the secret back in a header on every
    request, Maytapi signs nothing at all, so for it the URL is the only
    place a secret can live. See connectors/maytapi.py.
    """
    account = _owned_channel_account(db, admin, account_id)
    if account.channel not in ("telegram", "whatsapp_maytapi"):
        raise HTTPException(
            status_code=400,
            detail="La registrazione automatica del webhook è disponibile solo per Telegram e WhatsApp (Maytapi). Per i canali Meta usa \"Info webhook\" e incolla URL e token nella dashboard dell'app.",
        )

    connector = get_connector(account)
    base = f"{public_base_url.rstrip('/')}{settings.API_V1_STR}/omnichannel-responder/webhooks"

    if account.channel == "telegram":
        if not isinstance(connector, TelegramConnector):
            raise HTTPException(status_code=400, detail="Connettore non valido per questo canale")
        webhook_url = f"{base}/telegram/{account.id}"
    else:
        if not isinstance(connector, MaytapiConnector):
            raise HTTPException(status_code=400, detail="Connettore non valido per questo canale")
        webhook_url = f"{base}/maytapi/{account.id}/{account.webhook_secret}"

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


@router.get("/customers/{customer_id}/crm-profile", response_model=OmniCustomerCrmProfileResponse)
def get_customer_crm_profile(
    customer_id: uuid.UUID, channel: Optional[str] = None,
    db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin),
):
    """
    Scheda CRM del contatto per l'operatore: identificazione (con la stessa
    regola di fiducia dell'AI, crm/tools.py) piu' anagrafica e saldi. Lettura
    a richiesta, mai in lista: ogni apertura e' una chiamata al CRM e finisce
    nell'audit.
    """
    customer = db.query(OmniCustomer).filter(OmniCustomer.id == customer_id, OmniCustomer.owner_id == admin.id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    config = OmnichannelService.get_or_create_ai_agent_config(db, admin.id)
    client = crm_tools.client_for(config)
    if client is None:
        return OmniCustomerCrmProfileResponse(status="disabled", message="Integrazione CRM non attiva (pagina AI Agent).")

    ctx = crm_tools.prepare(client, customer, channel)
    wallets = None
    if ctx.customer_tools_enabled:
        try:
            wallets = client.wallets(customer_id=ctx.customer_id)
            ctx.lookups.append({"tool": "customer/wallets", "ok": True})
        except MamifyError as e:
            ctx.lookups.append({"tool": "customer/wallets", "ok": False, "error": e.code})

    OmnichannelService.log_audit(db, admin.id, admin.id, "CRM_PROFILE_VIEWED", "customer", customer.id, ctx.summary())
    db.commit()

    messages = {
        "identified": None,
        "ambiguous": "Il numero corrisponde a più account nel CRM: l'AI chiederà l'email al cliente per distinguerli.",
        "not_found": "Nessun account Mamify con questo numero: l'AI non fornirà dati di account.",
        "unverified": "Nessuna identità verificabile su questo canale. Inserisci telefono o email nella scheda per collegarlo al CRM.",
        "unavailable": "CRM non raggiungibile o chiave rifiutata.",
    }
    return OmniCustomerCrmProfileResponse(
        status=ctx.status, identity_source=ctx.identity.source if ctx.identity else None,
        customer=ctx.customer, wallets=wallets, candidates=ctx.candidates_count or None,
        message=messages.get(ctx.status),
    )


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
    except ConnectorError as e:
        # Unlike the first generation, which records the failure on the draft
        # itself (generate_draft_for_message marks it FAILED with a
        # failure_reason the inbox displays), regenerate() has an existing
        # draft to preserve and lets the error out. Without this it surfaced
        # as a bare 500 "Internal Server Error" and the real cause - an
        # exhausted OpenAI balance, on 2026-09-22 - never reached the screen.
        raise HTTPException(status_code=502, detail=e.message)


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
def _agent_config_response(config) -> OmniAIAgentConfigResponse:
    """La chiave CRM non lascia mai il server: si dice solo se c'e' e da dove viene."""
    response = OmniAIAgentConfigResponse.model_validate(config)
    if config.crm_api_key_encrypted:
        response.crm_api_key_set, response.crm_api_key_source = True, "config"
    elif settings.MAMIFY_RAG_API_KEY:
        response.crm_api_key_set, response.crm_api_key_source = True, "env"
    return response


@router.get("/ai-agent", response_model=OmniAIAgentConfigResponse)
def get_ai_agent_config(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return _agent_config_response(OmnichannelService.get_or_create_ai_agent_config(db, admin.id))


@router.put("/ai-agent", response_model=OmniAIAgentConfigResponse)
def update_ai_agent_config(payload: OmniAIAgentConfigUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    config = OmnichannelService.get_or_create_ai_agent_config(db, admin.id)
    updates = payload.model_dump(exclude_unset=True)

    if "response_mode" in updates and updates["response_mode"] not in ("MANUAL", "APPROVAL_REQUIRED", "AUTO_REPLY"):
        raise HTTPException(status_code=400, detail=f"response_mode non valido: {updates['response_mode']}")

    # La chiave CRM si cifra e si registra come evento a parte: e' una
    # credenziale verso dati personali di terzi, non un'impostazione di tono.
    if "crm_api_key" in updates:
        raw_key = (updates.pop("crm_api_key") or "").strip()
        config.crm_api_key_encrypted = EncryptionService.encrypt(raw_key) if raw_key else None
        OmnichannelService.log_audit(
            db, admin.id, admin.id, "CRM_KEY_CHANGED", "ai_agent_config", config.id, {"set": bool(raw_key)},
        )
    if "crm_base_url" in updates:
        base_url = (updates["crm_base_url"] or "").strip()
        if base_url and not base_url.startswith("https://"):
            raise HTTPException(status_code=400, detail="L'indirizzo del CRM deve iniziare con https://")
        updates["crm_base_url"] = base_url or None
    if updates.get("crm_enabled") and not (config.crm_api_key_encrypted or settings.MAMIFY_RAG_API_KEY):
        raise HTTPException(status_code=400, detail="Per attivare il CRM serve prima una chiave API Mamify")
    if "crm_enabled" in updates and updates["crm_enabled"] != config.crm_enabled:
        OmnichannelService.log_audit(
            db, admin.id, admin.id, "CRM_TOGGLED", "ai_agent_config", config.id, {"enabled": updates["crm_enabled"]},
        )

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
    return _agent_config_response(config)


@router.post("/ai-agent/crm/check", response_model=OmniCrmKeyCheckResponse)
def check_crm_key(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Prova la chiave CRM salvata senza leggere dati di nessuno (vedi
    MamifyRagClient.check_key). Non richiede crm_enabled: serve proprio a
    decidere se accenderlo.
    """
    config = OmnichannelService.get_or_create_ai_agent_config(db, admin.id)
    api_key = crm_tools.resolve_api_key(config)
    if not api_key:
        return OmniCrmKeyCheckResponse(status="not_configured", message="Nessuna chiave API Mamify impostata.")
    client = MamifyRagClient(api_key, config.crm_base_url or None)
    return OmniCrmKeyCheckResponse(**client.check_key())


# ==============================================================================
# Knowledge base - RAG ibrido, vedi integrations/omnichannel/knowledge.py
# ==============================================================================
def _owned_document(db: Session, admin: Administrator, document_id: uuid.UUID) -> OmniKnowledgeDocument:
    document = db.query(OmniKnowledgeDocument).filter(
        OmniKnowledgeDocument.id == document_id, OmniKnowledgeDocument.owner_id == admin.id, OmniKnowledgeDocument.kind != "profile",
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return document


def _owned_company(db: Session, admin: Administrator, company_id: Optional[uuid.UUID]) -> Optional[OmniKnowledgeCompany]:
    if company_id is None:
        return None
    company = db.query(OmniKnowledgeCompany).filter(OmniKnowledgeCompany.id == company_id, OmniKnowledgeCompany.owner_id == admin.id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Azienda non trovata")
    return company


def _document_response(document: OmniKnowledgeDocument, embedded: int) -> OmniKnowledgeDocumentResponse:
    response = OmniKnowledgeDocumentResponse.model_validate(document)
    response.embedded_chunks = embedded
    return response


def _embedded_counts(db: Session, owner_id: uuid.UUID, document_ids: Optional[List[uuid.UUID]] = None) -> Dict[uuid.UUID, int]:
    query = (
        db.query(OmniKnowledgeChunk.document_id, func.count(OmniKnowledgeChunk.id))
        .filter(OmniKnowledgeChunk.owner_id == owner_id, OmniKnowledgeChunk.embedding.isnot(None))
    )
    if document_ids is not None:
        query = query.filter(OmniKnowledgeChunk.document_id.in_(document_ids))
    return dict(query.group_by(OmniKnowledgeChunk.document_id).all())


def _queue_embedding(document_id: Optional[uuid.UUID]) -> None:
    """
    Gli embedding si calcolano nel worker: il salvataggio non aspetta OpenAI e
    la ricerca testuale funziona subito. Senza document_id recupera tutti i
    blocchi in attesa (dopo un cambio che tocca molti documenti insieme).
    """
    from app.tasks.omnichannel import embed_knowledge_document_task, embed_pending_knowledge_task
    if document_id is None:
        embed_pending_knowledge_task.delay()
    else:
        embed_knowledge_document_task.delay(str(document_id))


def _save_document(db: Session, admin: Administrator, document: OmniKnowledgeDocument, action: str) -> OmniKnowledgeDocumentResponse:
    if document.kind != "instruction":
        document.always_on = False
    document.error_message = None
    knowledge.rebuild_chunks(db, document)
    if not document.chunk_count:
        raise HTTPException(status_code=422, detail="Il contenuto e' vuoto")
    document.status = "ready"
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "knowledge_document", document.id, {"action": action, "kind": document.kind})
    db.commit()
    db.refresh(document)
    _queue_embedding(document.id)
    return _document_response(document, 0)


def _rechunk_documents(db: Session, documents: List[OmniKnowledgeDocument]) -> None:
    """Il nome dell'azienda sta nell'intestazione dei blocchi: cambiarlo (o spostare il documento) richiede blocchi nuovi."""
    for document in documents:
        knowledge.rebuild_chunks(db, document)
        document.updated_at = datetime.now(timezone.utc)


PREVIEW_CHARS = 300


@router.get("/knowledge-base", response_model=List[OmniKnowledgeDocumentResponse])
def list_knowledge_documents(
    company: Optional[str] = Query(None, description="id dell'azienda, oppure 'none' per i documenti senza azienda"),
    kind: Optional[str] = Query(None, pattern="^(document|instruction)$"),
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    # Il testo intero resta nel database: all'elenco basta l'inizio.
    query = (
        db.query(OmniKnowledgeDocument, func.left(OmniKnowledgeDocument.content_text, PREVIEW_CHARS))
        .options(defer(OmniKnowledgeDocument.content_text))
        .filter(OmniKnowledgeDocument.owner_id == admin.id, OmniKnowledgeDocument.kind != "profile")
    )
    if company == "none":
        query = query.filter(OmniKnowledgeDocument.company_id.is_(None))
    elif company:
        try:
            query = query.filter(OmniKnowledgeDocument.company_id == uuid.UUID(company))
        except ValueError:
            raise HTTPException(status_code=422, detail="Azienda non valida")
    if kind:
        query = query.filter(OmniKnowledgeDocument.kind == kind)
    if q and q.strip():
        needle = f"%{q.strip().replace('%', '').replace('_', ' ')}%"
        query = query.filter(or_(
            OmniKnowledgeDocument.title.ilike(needle),
            OmniKnowledgeDocument.file_name.ilike(needle),
            OmniKnowledgeDocument.content_text.ilike(needle),
        ))
    rows = query.order_by(OmniKnowledgeDocument.created_at.desc()).all()
    embedded = _embedded_counts(db, admin.id, [doc.id for doc, _ in rows])
    return [
        OmniKnowledgeDocumentResponse(
            id=doc.id, title=doc.title, source_type=doc.source_type, content_text=None, preview=preview,
            source_url=doc.source_url, status=doc.status, kind=doc.kind, always_on=doc.always_on,
            company_id=doc.company_id, company=doc.company, file_name=doc.file_name, chunk_count=doc.chunk_count,
            embedded_chunks=embedded.get(doc.id, 0), error_message=doc.error_message,
            created_at=doc.created_at, updated_at=doc.updated_at,
        )
        for doc, preview in rows
    ]


@router.get("/knowledge-base/stats", response_model=OmniKnowledgeStatsResponse)
def knowledge_stats(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    counts = dict(
        db.query(OmniKnowledgeDocument.kind, func.count(OmniKnowledgeDocument.id))
        .filter(OmniKnowledgeDocument.owner_id == admin.id)
        .group_by(OmniKnowledgeDocument.kind)
        .all()
    )
    always_on = db.query(func.count(OmniKnowledgeDocument.id)).filter(
        OmniKnowledgeDocument.owner_id == admin.id, OmniKnowledgeDocument.kind == "instruction", OmniKnowledgeDocument.always_on.is_(True),
    ).scalar() or 0
    chunks = db.query(func.count(OmniKnowledgeChunk.id)).filter(OmniKnowledgeChunk.owner_id == admin.id).scalar() or 0
    embedded = db.query(func.count(OmniKnowledgeChunk.id)).filter(OmniKnowledgeChunk.owner_id == admin.id, OmniKnowledgeChunk.embedding.isnot(None)).scalar() or 0
    companies = db.query(OmniKnowledgeCompany.name).filter(OmniKnowledgeCompany.owner_id == admin.id).all()
    return OmniKnowledgeStatsResponse(
        documents=counts.get("document", 0), instructions=counts.get("instruction", 0), always_on_instructions=always_on,
        chunks=chunks, embedded_chunks=embedded,
        companies=sorted((name for (name,) in companies), key=str.lower),
    )


# --- Aziende: le cartelle della Knowledge Base --------------------------------
def _company_response(company: OmniKnowledgeCompany, counts: Dict[tuple, int]) -> OmniKnowledgeCompanyResponse:
    response = OmniKnowledgeCompanyResponse.model_validate(company)
    response.document_count = counts.get((company.id, "document"), 0)
    response.instruction_count = counts.get((company.id, "instruction"), 0)
    return response


def _company_counts(db: Session, owner_id: uuid.UUID) -> Dict[tuple, int]:
    rows = (
        db.query(OmniKnowledgeDocument.company_id, OmniKnowledgeDocument.kind, func.count(OmniKnowledgeDocument.id))
        .filter(OmniKnowledgeDocument.owner_id == owner_id, OmniKnowledgeDocument.company_id.isnot(None))
        .group_by(OmniKnowledgeDocument.company_id, OmniKnowledgeDocument.kind)
        .all()
    )
    return {(company_id, kind): count for company_id, kind, count in rows}


def _clean_company_fields(values: Dict[str, Any]) -> Dict[str, Any]:
    return {key: ((value.strip() or None) if isinstance(value, str) else value) for key, value in values.items()}


def _check_company_name(db: Session, admin: Administrator, name: str, exclude_id: Optional[uuid.UUID] = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Il nome dell'azienda e' obbligatorio")
    query = db.query(OmniKnowledgeCompany.id).filter(
        OmniKnowledgeCompany.owner_id == admin.id, func.lower(OmniKnowledgeCompany.name) == name.lower(),
    )
    if exclude_id:
        query = query.filter(OmniKnowledgeCompany.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail=f"Esiste gia' un'azienda chiamata \"{name}\"")
    return name


def _commit_company(db: Session, admin: Administrator, company: OmniKnowledgeCompany, action: str, rechunked: bool) -> OmniKnowledgeCompanyResponse:
    profile = knowledge.sync_company_profile(db, company)
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "knowledge_company", company.id, {"action": action})
    db.commit()
    db.refresh(company)
    if rechunked:
        _queue_embedding(None)
    elif profile:
        _queue_embedding(profile.id)
    return _company_response(company, _company_counts(db, admin.id))


@router.get("/knowledge-base/companies", response_model=List[OmniKnowledgeCompanyResponse])
def list_knowledge_companies(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    companies = db.query(OmniKnowledgeCompany).filter(OmniKnowledgeCompany.owner_id == admin.id).order_by(func.lower(OmniKnowledgeCompany.name)).all()
    counts = _company_counts(db, admin.id)
    return [_company_response(company, counts) for company in companies]


@router.post("/knowledge-base/companies", response_model=OmniKnowledgeCompanyResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_company(payload: OmniKnowledgeCompanyCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    fields = _clean_company_fields(payload.model_dump())
    fields["name"] = _check_company_name(db, admin, payload.name)
    company = OmniKnowledgeCompany(owner_id=admin.id, **fields)
    db.add(company)
    db.flush()
    return _commit_company(db, admin, company, "created", rechunked=False)


@router.put("/knowledge-base/companies/{company_id}", response_model=OmniKnowledgeCompanyResponse)
def update_knowledge_company(company_id: uuid.UUID, payload: OmniKnowledgeCompanyUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    company = _owned_company(db, admin, company_id)
    fields = _clean_company_fields(payload.model_dump(exclude_unset=True))
    renamed = False
    if "name" in fields:
        fields["name"] = _check_company_name(db, admin, fields["name"] or "", exclude_id=company.id)
        renamed = fields["name"] != company.name
    for key, value in fields.items():
        setattr(company, key, value)
    if renamed:
        db.flush()
        _rechunk_documents(db, [d for d in company.documents if d.kind != "profile"])
    return _commit_company(db, admin, company, "updated", rechunked=renamed)


@router.delete("/knowledge-base/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_company(
    company_id: uuid.UUID,
    delete_documents: bool = Query(False, description="True elimina anche documenti e istruzioni; False li sposta fra quelli senza azienda"),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    company = _owned_company(db, admin, company_id)
    documents = list(company.documents)
    moved = []
    for document in documents:
        if delete_documents or document.kind == "profile":
            db.delete(document)
        else:
            # Esplicito e non lasciato al SET NULL del database: cosi' cambia
            # updated_at e la cache dei vettori si accorge dello spostamento.
            document.company_ref = None
            moved.append(document)
    db.flush()
    _rechunk_documents(db, moved)
    OmnichannelService.log_audit(db, admin.id, admin.id, "SETTINGS_CHANGED", "knowledge_company", company.id, {"action": "deleted", "delete_documents": delete_documents})
    db.delete(company)
    db.commit()
    if moved:
        _queue_embedding(None)
    return


@router.post("/knowledge-base/move", response_model=List[OmniKnowledgeDocumentResponse])
def move_knowledge_documents(payload: OmniKnowledgeDocumentMove, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    company = _owned_company(db, admin, payload.company_id)
    documents = db.query(OmniKnowledgeDocument).filter(
        OmniKnowledgeDocument.owner_id == admin.id,
        OmniKnowledgeDocument.id.in_(payload.document_ids),
        OmniKnowledgeDocument.kind != "profile",
    ).all()
    if not documents:
        raise HTTPException(status_code=404, detail="Nessun documento da spostare")
    changed = [d for d in documents if d.company_id != (company.id if company else None)]
    for document in changed:
        document.company_ref = company
    db.flush()
    _rechunk_documents(db, changed)
    db.commit()
    if changed:
        _queue_embedding(None)
    embedded = _embedded_counts(db, admin.id, [d.id for d in documents])
    return [_document_response(d, embedded.get(d.id, 0)) for d in documents]


# --- Documenti e istruzioni ---------------------------------------------------
@router.post("/knowledge-base", response_model=OmniKnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_document(payload: OmniKnowledgeDocumentCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    if not (payload.content_text or "").strip():
        raise HTTPException(status_code=422, detail="Il contenuto e' obbligatorio")
    company = _owned_company(db, admin, payload.company_id)
    document = OmniKnowledgeDocument(
        owner_id=admin.id, title=payload.title.strip(), source_type=payload.source_type,
        content_text=payload.content_text, source_url=payload.source_url, status="processing",
        kind=payload.kind, always_on=payload.always_on, company_ref=company,
    )
    db.add(document)
    db.flush()
    return _save_document(db, admin, document, "created")


@router.post("/knowledge-base/upload", response_model=OmniKnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_knowledge_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    company_id: Optional[uuid.UUID] = Form(None),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    company = _owned_company(db, admin, company_id)
    filename = file.filename or "documento"
    data = file.file.read(knowledge.MAX_UPLOAD_BYTES + 1)
    try:
        source_type = knowledge.source_type_for_filename(filename)
        content = knowledge.extract_text(filename, data)
    except knowledge.KnowledgeExtractionError as e:
        raise HTTPException(status_code=422, detail=f"{filename}: {e}")

    default_title = filename.rsplit(".", 1)[0].replace("_", " ").strip() or filename
    document = OmniKnowledgeDocument(
        owner_id=admin.id, title=((title or "").strip() or default_title)[:255], source_type=source_type,
        content_text=content, status="processing", kind="document", company_ref=company,
        file_name=filename[:255],
    )
    db.add(document)
    db.flush()
    return _save_document(db, admin, document, "uploaded")


@router.get("/knowledge-base/{document_id}", response_model=OmniKnowledgeDocumentResponse)
def get_knowledge_document(document_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    document = _owned_document(db, admin, document_id)
    return _document_response(document, _embedded_counts(db, admin.id, [document.id]).get(document.id, 0))


@router.put("/knowledge-base/{document_id}", response_model=OmniKnowledgeDocumentResponse)
def update_knowledge_document(document_id: uuid.UUID, payload: OmniKnowledgeDocumentUpdate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    document = _owned_document(db, admin, document_id)
    fields = payload.model_dump(exclude_unset=True)
    if "content_text" in fields and not (fields["content_text"] or "").strip():
        raise HTTPException(status_code=422, detail="Il contenuto e' obbligatorio")
    if "company_id" in fields:
        document.company_ref = _owned_company(db, admin, fields.pop("company_id"))
    for key, value in fields.items():
        setattr(document, key, value.strip() if key == "title" else value)
    # Titolo e azienda stanno nell'intestazione di ogni blocco, quindi anche
    # cambiare solo quelli richiede blocchi ed embedding nuovi.
    return _save_document(db, admin, document, "updated")


@router.delete("/knowledge-base/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_document(document_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    document = _owned_document(db, admin, document_id)
    db.delete(document)
    db.commit()
    return


@router.post("/knowledge-base/reindex", response_model=OmniKnowledgeStatsResponse)
def reindex_knowledge_base(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Calcola subito gli embedding mancanti (es. dopo aver ricaricato il credito OpenAI)."""
    api_key, _ = get_openai_credentials(db)
    if not api_key:
        raise HTTPException(status_code=400, detail="Nessuna API key OpenAI configurata (Impostazioni > AI)")
    try:
        knowledge.embed_pending_chunks(db, api_key, owner_id=admin.id)
    except ConnectorError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=e.message)
    db.query(OmniKnowledgeDocument).filter(
        OmniKnowledgeDocument.owner_id == admin.id, OmniKnowledgeDocument.error_message.isnot(None)
    ).update({OmniKnowledgeDocument.error_message: None}, synchronize_session=False)
    db.commit()
    return knowledge_stats(db, admin)


@router.post("/knowledge-base/search", response_model=OmniKnowledgeSearchResponse)
def search_knowledge_base(payload: OmniKnowledgeSearchRequest, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Prova della Knowledge Base dalla dashboard: mostra quali blocchi
    arriverebbero al bot per questa domanda e, a richiesta, la risposta che
    scriverebbe. E' la stessa ricerca usata per le bozze vere.
    """
    api_key, model = get_openai_credentials(db)
    agent_config = OmnichannelService.get_or_create_ai_agent_config(db, admin.id)
    company_id = _owned_company(db, admin, payload.company_id).id if payload.company_id else None

    def to_hits(chunks: List[knowledge.RetrievedChunk]) -> List[OmniKnowledgeSearchHit]:
        return [
            OmniKnowledgeSearchHit(
                document_id=c.document_id, document_title=c.document_title, company=c.company, kind=c.kind,
                content=c.content, score=c.score, similarity=c.similarity, matched_by=c.matched_by,
            )
            for c in chunks
        ]

    if not payload.generate_reply:
        chunks, warning = knowledge.search(db, admin.id, payload.query, api_key, company_id=company_id)
        return OmniKnowledgeSearchResponse(hits=to_hits(chunks), warning=warning)

    if not api_key:
        raise HTTPException(status_code=400, detail="Nessuna API key OpenAI configurata (Impostazioni > AI)")
    try:
        result = omni_ai.preview_reply(db, api_key, model, agent_config, admin.id, payload.query, company_id)
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message)
    return OmniKnowledgeSearchResponse(
        hits=to_hits(result["kb_chunks"]), warning=result["kb_warning"], reply=result["text"],
        input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
    )


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
