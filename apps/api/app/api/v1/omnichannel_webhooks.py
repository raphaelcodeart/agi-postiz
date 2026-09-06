"""
Inbound entrypoints for the Omnichannel Responder: the real Telegram,
Facebook Messenger, Instagram Direct and WhatsApp webhooks (unauthenticated
- no provider can send our JWT, each verified its own way, see
TelegramConnector/FacebookConnector/WhatsAppConnector.verify_webhook) and
the admin-only "simulate message" dev tool (spec section 51), which only
works against channel_accounts of type 'mock' so it can never be pointed at
a real customer channel by mistake.

Facebook/Instagram/WhatsApp all share the exact same Meta webhook
subscription mechanics (GET handshake with hub.mode/hub.verify_token/
hub.challenge, POST with an X-Hub-Signature-256-signed body) - factored
into _meta_webhook_verify/_meta_webhook_receive below, parameterized by
channel, rather than three near-identical copies.

Kept in its own router/file, separate from api/v1/omnichannel.py, because
its auth model is fundamentally different (no admin JWT on these paths) -
never processes anything slow inline, just ingests the message and hands
off to Celery (spec section 30).
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.omnichannel import OmniChannelAccount
from app.integrations.omnichannel.connectors.registry import get_connector
from app.services.omnichannel_service import OmnichannelService
from app.schemas.schemas import OmniSimulateMessageRequest, OmniMessageResponse

router = APIRouter()


# Message ingestion + "does this queue an AI draft" now lives in
# OmnichannelService.ingest_messages_and_trigger_ai, shared with the Gmail
# poller (app/tasks/omnichannel.py::poll_gmail_channels_task) - kept as a
# private alias here so every call site below didn't need touching.
_ingest_and_trigger = OmnichannelService.ingest_messages_and_trigger_ai


@router.post("/webhooks/telegram/{channel_account_id}")
async def telegram_webhook(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    account = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.id == channel_account_id, OmniChannelAccount.channel == "telegram"
    ).first()
    if not account:
        # Deliberately identical 404 whether the account doesn't exist or the
        # channel doesn't match - never confirm/deny a channel_account_id to
        # an unauthenticated caller.
        raise HTTPException(status_code=404, detail="Not found")

    connector = get_connector(account)
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not connector.verify_webhook(headers, account.webhook_secret):
        raise HTTPException(status_code=403, detail="Webhook verification failed")

    if account.status == "disabled":
        # Admin has this channel switched off (channels/page.tsx toggle) -
        # acknowledge to Telegram so it stops retrying, but don't ingest.
        # Signature is still verified above first, so this never becomes a
        # way to probe a channel_account_id's disabled state unauthenticated.
        return {"ok": True}

    payload = await request.json()
    messages = connector.parse_webhook(payload)
    _ingest_and_trigger(db, account, messages)
    return {"ok": True}


async def _meta_webhook_verify(channel: str, channel_account_id: uuid.UUID, request: Request, db: Session):
    """
    Meta's one-time subscription handshake (configured from the App
    Dashboard's Messenger/Instagram/WhatsApp > Webhooks screen, not
    something this backend calls on its own like Telegram's setWebhook -
    see docs/OMNICHANNEL_RESPONDER.md §11). Meta sends hub.mode=subscribe,
    hub.verify_token (must match channel_account.webhook_secret - the admin
    pastes it into the Meta dashboard) and hub.challenge, which must be
    echoed back verbatim as plain text for the subscription to succeed.
    """
    account = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.id == channel_account_id, OmniChannelAccount.channel == channel
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Not found")

    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == account.webhook_secret:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


async def _meta_webhook_receive(channel: str, channel_account_id: uuid.UUID, request: Request, db: Session):
    account = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.id == channel_account_id, OmniChannelAccount.channel == channel
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Not found")

    connector = get_connector(account)
    headers = {k.lower(): v for k, v in request.headers.items()}
    raw_body = await request.body()
    if not connector.verify_webhook(headers, account.webhook_secret, body=raw_body):
        raise HTTPException(status_code=403, detail="Webhook verification failed")

    if account.status == "disabled":
        # Same reasoning as the Telegram webhook above: admin switched this
        # channel off, acknowledge (Meta expects 200) but don't ingest -
        # after signature verification, never before.
        return {"ok": True}

    payload = await request.json()
    messages = connector.parse_webhook(payload)
    _ingest_and_trigger(db, account, messages)
    return {"ok": True}


@router.get("/webhooks/facebook/{channel_account_id}")
async def facebook_webhook_verify(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_verify("facebook", channel_account_id, request, db)


@router.post("/webhooks/facebook/{channel_account_id}")
async def facebook_webhook_receive(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_receive("facebook", channel_account_id, request, db)


@router.get("/webhooks/instagram/{channel_account_id}")
async def instagram_webhook_verify(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_verify("instagram", channel_account_id, request, db)


@router.post("/webhooks/instagram/{channel_account_id}")
async def instagram_webhook_receive(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_receive("instagram", channel_account_id, request, db)


@router.get("/webhooks/whatsapp/{channel_account_id}")
async def whatsapp_webhook_verify(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_verify("whatsapp", channel_account_id, request, db)


@router.post("/webhooks/whatsapp/{channel_account_id}")
async def whatsapp_webhook_receive(channel_account_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return await _meta_webhook_receive("whatsapp", channel_account_id, request, db)


@router.post("/dev/simulate-message", response_model=OmniMessageResponse, status_code=status.HTTP_201_CREATED)
def simulate_message(payload: OmniSimulateMessageRequest, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    account = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.id == payload.channel_account_id, OmniChannelAccount.owner_id == admin.id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Canale non trovato")
    if account.channel != "mock":
        raise HTTPException(
            status_code=400,
            detail="La simulazione è disponibile solo per canali di tipo 'mock' - crea un canale mock in Impostazioni per testare l'intero flusso senza credenziali reali",
        )

    connector = get_connector(account)
    normalized = connector.parse_webhook({
        "external_user_id": payload.external_user_id,
        "text": payload.text,
        "customer_name": payload.customer_name,
    })
    messages = _ingest_and_trigger(db, account, normalized)
    if not messages:
        raise HTTPException(status_code=400, detail="Messaggio duplicato o non ingerito")
    return messages[0]
