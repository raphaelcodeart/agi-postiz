"""
myAGI: la pagina amministrativa del gateway WhatsApp in casa.

Un "numero myAGI" e' un canale `whatsapp_myagi` dell'Omnichannel Responder
(stessa tabella omni_channel_accounts, stesso owner_id, stessa inbox) piu' una
sessione sul container WAHA, il cui nome deriva dall'id del canale
(integrations/myagi/waha.py::session_name_for). Questo router fa solo cio' che
la pagina Canali non sa fare: avviare la sessione, mostrare il QR da
scansionare, dire se il telefono e' collegato, scollegarlo.

Niente qui tocca i canali degli altri tipi: filtra sempre per
channel == "whatsapp_myagi" e per owner.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_admin
from app.db.session import get_db
from app.integrations.myagi import waha
from app.integrations.omnichannel.exceptions import ConnectorError
from app.models.administrator import Administrator
from app.models.omnichannel import OmniChannelAccount, OmniConversation
from app.schemas.schemas import (
    MyAgiGatewayStatus,
    MyAgiQrResponse,
    MyAgiSessionCreate,
    MyAgiSessionResponse,
    OmniChannelAccountCreate,
)
from app.services.omnichannel_service import OmnichannelService

router = APIRouter()

CHANNEL = "whatsapp_myagi"


def _require_gateway() -> waha.WahaClient:
    if not waha.is_configured():
        raise HTTPException(status_code=503, detail="Gateway myAGI non configurato: imposta MYAGI_WA_URL e MYAGI_WA_API_KEY e avvia il servizio myagi_wa.")
    return waha.WahaClient()


def _owned(db: Session, admin: Administrator, account_id: uuid.UUID) -> OmniChannelAccount:
    account = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.id == account_id,
        OmniChannelAccount.owner_id == admin.id,
        OmniChannelAccount.channel == CHANNEL,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Numero myAGI non trovato")
    return account


def _sync_account_status(db: Session, account: OmniChannelAccount, session_status: str) -> None:
    """Riflette lo stato WAHA sul canale, salvo "disabled" che e' una scelta dell'amministratore."""
    if account.status == "disabled":
        return
    mapped = waha.STATUS_MAP.get(session_status)
    if mapped and mapped != account.status:
        account.status = mapped
        db.commit()


def _to_response(db: Session, account: OmniChannelAccount, session: Optional[dict], detail: Optional[str] = None, session_status: Optional[str] = None) -> MyAgiSessionResponse:
    me = (session or {}).get("me") or {}
    phone = str(me.get("id") or "").split("@", 1)[0] or None
    # Il numero lo conosce solo il gateway, e solo a telefono collegato: lo
    # copiamo in external_account_id cosi' l'Inbox puo' mostrare "+39..."
    # accanto al nome senza interrogare WAHA (il campo per questo canale non
    # ha altri usi: autenticazione e webhook vanno per id e segreto).
    if phone and account.external_account_id != phone:
        account.external_account_id = phone
        db.commit()
    count = db.query(func.count(OmniConversation.id)).filter(OmniConversation.channel_account_id == account.id).scalar() or 0
    waha_status = session_status or str((session or {}).get("status") or "MISSING")
    if waha_status == "SCAN_QR_CODE" and not detail:
        detail = "Apri WhatsApp sul telefono > Dispositivi collegati > Collega un dispositivo e scansiona il QR."
    return MyAgiSessionResponse(
        channel_account_id=account.id, name=account.name, session_name=waha.session_name_for(account.id),
        account_status=account.status, session_status=waha_status, phone_number=phone, push_name=me.get("pushName"),
        detail=detail, conversation_count=count, created_at=account.created_at,
    )


def _load(db: Session, client: Optional[waha.WahaClient], account: OmniChannelAccount) -> MyAgiSessionResponse:
    if client is None:
        return _to_response(db, account, None, "Gateway non configurato", "UNAVAILABLE")
    try:
        session = client.get_session(waha.session_name_for(account.id))
    except ConnectorError as e:
        return _to_response(db, account, None, e.message, "UNAVAILABLE")
    if session is None:
        return _to_response(db, account, None, "Sessione non ancora avviata sul gateway: premi Avvia.", "MISSING")
    _sync_account_status(db, account, str(session.get("status") or ""))
    return _to_response(db, account, session)


# ------------------------------------------------------------------ gateway
@router.get("/status", response_model=MyAgiGatewayStatus)
def gateway_status(admin: Administrator = Depends(get_current_admin)):
    if not waha.is_configured():
        return MyAgiGatewayStatus(configured=False, reachable=False, detail="MYAGI_WA_URL non impostato")
    try:
        info = waha.WahaClient().server_version()
    except ConnectorError as e:
        return MyAgiGatewayStatus(configured=True, reachable=False, detail=e.message)
    return MyAgiGatewayStatus(configured=True, reachable=True, version=str(info.get("version") or ""), engine=info.get("engine"))


# ----------------------------------------------------------------- sessioni
@router.get("/sessions", response_model=List[MyAgiSessionResponse])
def list_sessions(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    accounts = db.query(OmniChannelAccount).filter(
        OmniChannelAccount.owner_id == admin.id, OmniChannelAccount.channel == CHANNEL,
    ).order_by(OmniChannelAccount.created_at.desc()).all()
    client = waha.WahaClient() if waha.is_configured() else None
    return [_load(db, client, account) for account in accounts]


@router.post("/sessions", response_model=MyAgiSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(payload: MyAgiSessionCreate, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Crea il canale (come farebbe la pagina Canali scegliendo "WhatsApp
    myAGI") e avvia subito la sessione sul gateway, cosi' il QR e' pronto al
    primo sguardo. Se il gateway non risponde il canale resta, in stato
    pending, e si riprova con Avvia.
    """
    client = _require_gateway()
    account = OmnichannelService.create_channel_account(
        db, admin.id, OmniChannelAccountCreate(channel=CHANNEL, name=payload.name.strip()),
    )
    OmnichannelService.log_audit(db, admin.id, admin.id, "MYAGI_SESSION_CREATED", "channel_account", account.id)
    db.commit()
    try:
        session = client.ensure_session(waha.session_name_for(account.id), waha.webhook_url_for(account.id, account.webhook_secret), account.webhook_secret)
    except ConnectorError as e:
        return _to_response(db, account, None, e.message, "UNAVAILABLE")
    _sync_account_status(db, account, str(session.get("status") or ""))
    return _to_response(db, account, session)


@router.get("/sessions/{account_id}", response_model=MyAgiSessionResponse)
def get_session(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    account = _owned(db, admin, account_id)
    return _load(db, waha.WahaClient() if waha.is_configured() else None, account)


@router.post("/sessions/{account_id}/start", response_model=MyAgiSessionResponse)
def start_session(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Idempotente: crea la sessione se manca, riallinea il webhook se e' cambiato, riavvia se ferma."""
    client = _require_gateway()
    account = _owned(db, admin, account_id)
    try:
        session = client.ensure_session(waha.session_name_for(account.id), waha.webhook_url_for(account.id, account.webhook_secret), account.webhook_secret)
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message) from e
    OmnichannelService.log_audit(db, admin.id, admin.id, "MYAGI_SESSION_STARTED", "channel_account", account.id)
    db.commit()
    _sync_account_status(db, account, str(session.get("status") or ""))
    return _to_response(db, account, session)


@router.post("/sessions/{account_id}/restart", response_model=MyAgiSessionResponse)
def restart_session(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    client = _require_gateway()
    account = _owned(db, admin, account_id)
    name = waha.session_name_for(account.id)
    try:
        if client.get_session(name) is None:
            session = client.ensure_session(name, waha.webhook_url_for(account.id, account.webhook_secret), account.webhook_secret)
        else:
            client.restart_session(name)
            session = client.get_session(name) or {"status": "STARTING"}
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message) from e
    _sync_account_status(db, account, str(session.get("status") or ""))
    return _to_response(db, account, session)


@router.post("/sessions/{account_id}/logout", response_model=MyAgiSessionResponse)
def logout_session(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Scollega il telefono (il numero sparisce da "Dispositivi collegati" di
    WhatsApp). La sessione resta e torna a chiedere un QR: e' il modo giusto
    per cambiare numero senza perdere le conversazioni gia' in inbox.
    """
    client = _require_gateway()
    account = _owned(db, admin, account_id)
    name = waha.session_name_for(account.id)
    try:
        client.logout_session(name)
        session = client.get_session(name) or {"status": "STOPPED"}
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message) from e
    OmnichannelService.log_audit(db, admin.id, admin.id, "MYAGI_SESSION_LOGOUT", "channel_account", account.id)
    db.commit()
    _sync_account_status(db, account, str(session.get("status") or ""))
    return _to_response(db, account, session)


@router.get("/sessions/{account_id}/qr", response_model=MyAgiQrResponse)
def session_qr(account_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """
    Il QR cambia ogni ~20 secondi finche' non viene scansionato: la pagina lo
    richiede a intervalli, e questa risposta dice anche lo stato cosi' il
    client sa quando smettere (WORKING) o quando riavviare (FAILED).
    """
    client = _require_gateway()
    account = _owned(db, admin, account_id)
    name = waha.session_name_for(account.id)
    try:
        session = client.get_session(name)
        session_status = str((session or {}).get("status") or "MISSING")
        qr = client.qr_code(name) if session_status == "SCAN_QR_CODE" else None
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=e.message) from e
    if session is not None:
        _sync_account_status(db, account, session_status)
    return MyAgiQrResponse(session_status=session_status, mimetype=(qr or {}).get("mimetype"), data=(qr or {}).get("data"))
