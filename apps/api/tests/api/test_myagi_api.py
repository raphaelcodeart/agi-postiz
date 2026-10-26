"""
La pagina myAGI via HTTP e il webhook del gateway: un numero e' un canale
whatsapp_myagi del proprio owner, il QR arriva solo quando il gateway lo
chiede, e un messaggio firmato dal gateway finisce in inbox una volta sola.
"""
import hashlib
import hmac
import json
import uuid

import pytest

from app.core.security import SecurityService
from app.integrations.myagi import waha
from app.models.administrator import Administrator
from app.models.omnichannel import OmniChannelAccount, OmniMessage

BASE = "/api/v1/myagi"


@pytest.fixture()
def admin(db):
    row = Administrator(email=f"a-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(row)
    db.commit()
    return row


class FakeGateway:
    def __init__(self):
        self.sessions = {}
        self.deleted = []

    def get_session(self, name):
        return self.sessions.get(name)

    def ensure_session(self, name, webhook_url, hmac_key):
        self.sessions[name] = {"name": name, "status": "SCAN_QR_CODE", "me": None, "config": {"webhooks": [{"url": webhook_url, "hmac": {"key": hmac_key}}]}}
        return self.sessions[name]

    def qr_code(self, name):
        return {"mimetype": "image/png", "data": "QRBASE64"}

    def logout_session(self, name):
        self.sessions[name]["status"] = "STOPPED"

    def restart_session(self, name):
        self.sessions[name]["status"] = "STARTING"

    def delete_session(self, name):
        self.deleted.append(name)
        self.sessions.pop(name, None)

    def server_version(self):
        return {"version": "2026.9.2", "engine": "NOWEB"}


@pytest.fixture()
def gateway(monkeypatch):
    gw = FakeGateway()
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", "http://gw:3000")
    monkeypatch.setattr(waha.settings, "MYAGI_WA_API_KEY", "k")
    monkeypatch.setattr(waha, "WahaClient", lambda *a, **kw: gw)
    return gw


def test_gateway_not_configured_is_reported_not_crashed(client, admin, admin_token, monkeypatch):
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", None)
    headers = admin_token(admin)
    assert client.get(f"{BASE}/status", headers=headers).json()["configured"] is False
    assert client.post(f"{BASE}/sessions", json={"name": "Assistenza"}, headers=headers).status_code == 503
    assert client.get(f"{BASE}/sessions", headers=headers).json() == []


def test_create_start_qr_logout_delete(client, db, admin, admin_token, gateway):
    headers = admin_token(admin)
    assert client.get(f"{BASE}/status", headers=headers).json() == {"configured": True, "reachable": True, "version": "2026.9.2", "engine": "NOWEB", "detail": None}

    created = client.post(f"{BASE}/sessions", json={"name": "Assistenza"}, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    account_id = body["channel_account_id"]
    assert body["session_status"] == "SCAN_QR_CODE" and body["account_status"] == "pending"
    assert body["session_name"] == waha.session_name_for(uuid.UUID(account_id))

    account = db.query(OmniChannelAccount).filter(OmniChannelAccount.id == uuid.UUID(account_id)).one()
    assert account.channel == "whatsapp_myagi" and account.owner_id == admin.id
    [hook] = gateway.sessions[body["session_name"]]["config"]["webhooks"]
    assert hook["url"].endswith(f"/webhooks/myagi/{account_id}/{account.webhook_secret}")
    assert hook["hmac"]["key"] == account.webhook_secret

    qr = client.get(f"{BASE}/sessions/{account_id}/qr", headers=headers).json()
    assert qr == {"session_status": "SCAN_QR_CODE", "mimetype": "image/png", "data": "QRBASE64"}

    # Il telefono si collega: lo stato del canale segue quello della sessione.
    gateway.sessions[body["session_name"]].update(status="WORKING", me={"id": "393330000000@c.us", "pushName": "Assistenza"})
    [listed] = client.get(f"{BASE}/sessions", headers=headers).json()
    assert listed["session_status"] == "WORKING" and listed["account_status"] == "connected"
    assert listed["phone_number"] == "393330000000" and listed["push_name"] == "Assistenza"
    assert client.get(f"{BASE}/sessions/{account_id}/qr", headers=headers).json()["data"] is None

    assert client.post(f"{BASE}/sessions/{account_id}/logout", headers=headers).json()["session_status"] == "STOPPED"
    assert client.post(f"{BASE}/sessions/{account_id}/start", headers=headers).json()["session_status"] == "SCAN_QR_CODE"

    # Eliminare il canale dalla pagina Canali elimina anche la sessione sul gateway.
    assert client.delete(f"/api/v1/omnichannel-responder/channel-accounts/{account_id}", headers=headers).status_code == 204
    assert gateway.deleted == [body["session_name"]]

    # Un altro amministratore non vede i numeri altrui.
    other = Administrator(email=f"o-{uuid.uuid4().hex[:6]}@example.com", full_name="O", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(other)
    db.commit()
    assert client.get(f"{BASE}/sessions/{account_id}", headers=admin_token(other)).status_code == 404


def test_webhook_accepts_only_the_right_secret_and_signature_and_ingests_once(client, db, admin, admin_token, gateway, monkeypatch):
    headers = admin_token(admin)
    created = client.post(f"{BASE}/sessions", json={"name": "Assistenza"}, headers=headers).json()
    account = db.query(OmniChannelAccount).filter(OmniChannelAccount.id == uuid.UUID(created["channel_account_id"])).one()
    # Niente Celery nei test: la coda della bozza AI viene stubbata.
    import app.tasks.omnichannel as tasks
    monkeypatch.setattr(tasks.generate_ai_draft_task, "delay", lambda *a, **k: None)

    event = {"event": "message", "session": created["session_name"], "payload": {"id": "false_1@c.us_X", "timestamp": 1, "from": "393331112222@c.us", "fromMe": False, "body": "Ciao", "hasMedia": False, "_data": {"notifyName": "Mario"}}}
    body = json.dumps(event).encode()
    url = f"/api/v1/omnichannel-responder/webhooks/myagi/{account.id}/{account.webhook_secret}"
    signature = hmac.new(account.webhook_secret.encode(), body, hashlib.sha512).hexdigest()

    assert client.post(f"/api/v1/omnichannel-responder/webhooks/myagi/{account.id}/sbagliato", content=body, headers={"Content-Type": "application/json"}).status_code == 403
    assert client.post(url, content=body, headers={"Content-Type": "application/json", "X-Webhook-Hmac": "00"}).status_code == 403
    assert client.post(url, content=body, headers={"Content-Type": "application/json", "X-Webhook-Hmac": signature}).status_code == 200
    assert client.post(url, content=body, headers={"Content-Type": "application/json", "X-Webhook-Hmac": signature}).status_code == 200  # ritentato dal gateway

    messages = db.query(OmniMessage).filter(OmniMessage.channel_account_id == account.id).all()
    assert len(messages) == 1 and messages[0].text == "Ciao"
    assert client.post(f"/api/v1/omnichannel-responder/webhooks/myagi/{uuid.uuid4()}/{account.webhook_secret}", content=body, headers={"Content-Type": "application/json"}).status_code == 404


def test_il_numero_collegato_viene_ricordato_sul_canale(client, db, admin, admin_token, gateway):
    headers = admin_token(admin)
    created = client.post("/api/v1/myagi/sessions", json={"name": "Vendite"}, headers=headers).json()
    account_id = created["channel_account_id"]
    gateway.sessions[created["session_name"]].update({"status": "WORKING", "me": {"id": "393331234567@c.us", "pushName": "AGI"}})

    row = client.get(f"/api/v1/myagi/sessions/{account_id}", headers=headers).json()
    assert row["phone_number"] == "393331234567" and row["push_name"] == "AGI"

    account = db.query(OmniChannelAccount).filter(OmniChannelAccount.id == uuid.UUID(account_id)).one()
    db.refresh(account)
    assert account.external_account_id == "393331234567"
    # ...e l'Inbox lo vede nella lista canali senza passare dal gateway.
    listed = {r["id"]: r for r in client.get("/api/v1/omnichannel-responder/channel-accounts", headers=headers).json()}
    assert listed[account_id]["external_account_id"] == "393331234567"
