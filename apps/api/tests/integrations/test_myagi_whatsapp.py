"""
myAGI: il connettore WhatsApp sul nostro gateway WAHA e il suo client.

Come per Maytapi, le proprieta' che contano sono quelle di cio' che NON deve
entrare in inbox (i nostri stessi messaggi, i gruppi) e di come si prova che il
webhook venga dal gateway (segreto nel path + firma HMAC del corpo). Il client
WAHA e' stato verificato dal vivo il 2026-10-26 contro devlikeapro/waha:noweb
2026.9.2: le risposte simulate qui sono quelle osservate.
"""
import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.myagi import waha
from app.integrations.omnichannel.connectors.whatsapp_myagi import (
    MyAgiWhatsAppConnector,
)
from app.integrations.omnichannel.exceptions import ConnectorError

ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-00000000abcd")
SESSION = waha.session_name_for(ACCOUNT_ID)


def _account(secret="s3cret"):
    return SimpleNamespace(id=ACCOUNT_ID, channel="whatsapp_myagi", webhook_secret=secret, config_json=None, status="connected", external_account_id=None)


def _connector(**kw):
    return MyAgiWhatsAppConnector(_account(**kw), access_token=None)


def _event(**overrides):
    payload = {
        "id": "false_393331112222@c.us_AAAA", "timestamp": 1667561485, "from": "393331112222@c.us",
        "fromMe": False, "to": "393330000000@c.us", "body": "Ciao, siete aperti?", "hasMedia": False,
        "_data": {"notifyName": "Mario Rossi"},
    }
    payload.update(overrides)
    return {"event": "message", "session": SESSION, "payload": payload}


# --------------------------------------------------------------- parse_webhook
def test_a_text_message_becomes_a_normalized_message():
    [msg] = _connector().parse_webhook(_event())
    assert msg.external_user_id == "393331112222@c.us"
    assert msg.text == "Ciao, siete aperti?"
    assert msg.message_type == "TEXT"
    assert msg.external_message_id == "false_393331112222@c.us_AAAA"
    assert msg.customer_display_name == "Mario Rossi"
    assert msg.metadata["whatsapp_phone"] == "393331112222"


def test_our_own_messages_groups_and_other_events_are_never_ingested():
    c = _connector()
    assert c.parse_webhook(_event(fromMe=True)) == []
    assert c.parse_webhook(_event(**{"from": "120363012345678@g.us"})) == []
    assert c.parse_webhook(_event(**{"from": "status@broadcast"})) == []
    assert c.parse_webhook({"event": "message.ack", "session": SESSION, "payload": {"from": "1@c.us"}}) == []
    assert c.parse_webhook({"event": "session.status", "session": SESSION, "payload": {"status": "WORKING"}}) == []


def test_a_message_from_another_session_is_not_ours():
    event = _event()
    event["session"] = "agi_altro"
    assert _connector().parse_webhook(event) == []


def test_media_messages_keep_the_caption_and_the_attachment():
    [msg] = _connector().parse_webhook(_event(body="guarda", hasMedia=True, media={"url": "http://myagi_wa:3000/api/files/x.jpg", "mimetype": "image/jpeg", "filename": "x.jpg"}))
    assert msg.message_type == "IMAGE"
    assert msg.text == "guarda"
    assert msg.attachments == [{"type": "IMAGE", "url": "http://myagi_wa:3000/api/files/x.jpg", "mime_type": "image/jpeg", "filename": "x.jpg"}]
    [doc] = _connector().parse_webhook(_event(body="", hasMedia=True, media={"url": "u", "mimetype": "application/pdf"}))
    assert doc.message_type == "DOCUMENT" and doc.text is None


# -------------------------------------------------------------- verify_webhook
def test_verify_requires_the_path_secret_and_checks_hmac_when_present():
    c = _connector(secret="s3cret")
    body = json.dumps(_event()).encode()
    good = hmac.new(b"s3cret", body, hashlib.sha512).hexdigest()
    assert c.verify_webhook({}, "s3cret", body) is True  # solo path (gateway senza hmac)
    assert c.verify_webhook({"x-webhook-hmac": good}, "s3cret", body) is True
    assert c.verify_webhook({"x-webhook-hmac": "deadbeef"}, "s3cret", body) is False
    assert c.verify_webhook({"x-webhook-hmac": good}, "wrong", body) is False
    assert c.verify_webhook({}, "", body) is False


# ------------------------------------------------------------------- send/status
def test_send_message_posts_to_the_gateway_with_the_session_name(monkeypatch):
    seen = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        seen.update(method=method, url=url, json=json, headers=headers)
        return httpx.Response(201, json={"id": {"_serialized": "true_393331112222@c.us_BBBB"}})

    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", "http://myagi_wa:3000")
    monkeypatch.setattr(waha.settings, "MYAGI_WA_API_KEY", "k")
    monkeypatch.setattr(httpx, "request", fake_request)
    result = _connector().send_message("393331112222", "Buongiorno!")
    assert result.external_message_id == "true_393331112222@c.us_BBBB"
    assert seen["method"] == "POST" and seen["url"] == "http://myagi_wa:3000/api/sendText"
    assert seen["json"] == {"session": SESSION, "chatId": "393331112222@c.us", "text": "Buongiorno!"}
    assert seen["headers"]["X-Api-Key"] == "k"


def test_send_message_reports_the_gateway_refusal(monkeypatch):
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", "http://myagi_wa:3000")
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(422, json={"error": "Session status is not as expected", "status": "SCAN_QR_CODE"}))
    with pytest.raises(ConnectorError) as exc:
        _connector().send_message("393331112222@c.us", "x")
    assert "422" in exc.value.message and "SCAN_QR_CODE" in exc.value.message  # lo stato dice cosa fare: riscansionare il QR


def test_get_status_maps_waha_states(monkeypatch):
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", "http://myagi_wa:3000")
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(200, json={"name": SESSION, "status": "WORKING", "me": {"id": "393330000000@c.us", "pushName": "Assistenza"}}))
    status = _connector().get_status()
    assert status == {"status": "connected", "waha_status": "WORKING", "phone_number": "393330000000", "push_name": "Assistenza"}
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(200, json={"name": SESSION, "status": "SCAN_QR_CODE", "me": None}))
    assert _connector().get_status()["status"] == "error"
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(404, json={"message": "Session not found"}))
    assert "non presente" in _connector().get_status()["detail"]


# ---------------------------------------------------------------- WahaClient
class _Gateway:
    """Finto WAHA: registra le chiamate e risponde come l'originale (osservato dal vivo)."""

    def __init__(self, session=None):
        self.session = session
        self.calls = []

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        path = url.replace("http://gw:3000", "")
        self.calls.append((method, path, json))
        if path == f"/api/sessions/{SESSION}" and method == "GET":
            return httpx.Response(200, json=self.session) if self.session else httpx.Response(404, json={"message": "Session not found", "statusCode": 404})
        if path == "/api/sessions" and method == "POST":
            self.session = {"name": SESSION, "status": "STARTING", "config": json["config"], "me": None}
            return httpx.Response(201, json=self.session)
        if path == f"/api/sessions/{SESSION}" and method == "PUT":
            self.session = {**self.session, "status": "STARTING", "config": json["config"]}
            return httpx.Response(200, json=self.session)
        if path.endswith("/start") or path.endswith("/stop") or path.endswith("/logout") or path.endswith("/restart"):
            return httpx.Response(201, json={})
        if method == "DELETE":
            return httpx.Response(200, json={})
        if path == f"/api/{SESSION}/auth/qr":
            return httpx.Response(200, json={"mimetype": "image/png", "data": "iVBOR..."})
        raise AssertionError(f"chiamata inattesa {method} {path}")


@pytest.fixture()
def gateway(monkeypatch):
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", "http://gw:3000")
    monkeypatch.setattr(waha.settings, "MYAGI_WA_API_KEY", "k")
    gw = _Gateway()
    monkeypatch.setattr(httpx, "request", gw)
    return gw


def _hook():
    return waha.webhook_url_for(ACCOUNT_ID, "s3cret")


def test_webhook_url_points_to_the_internal_api_with_the_secret_in_the_path():
    assert _hook() == f"http://api:8000/api/v1/omnichannel-responder/webhooks/myagi/{ACCOUNT_ID}/s3cret"


def test_ensure_session_creates_the_session_with_webhook_and_hmac(gateway):
    created = waha.WahaClient().ensure_session(SESSION, _hook(), "s3cret")
    assert created["status"] == "STARTING"
    method, path, body = gateway.calls[-1]
    assert (method, path) == ("POST", "/api/sessions")
    assert body["name"] == SESSION and body["start"] is True
    [hook] = body["config"]["webhooks"]
    assert hook["url"] == _hook() and hook["events"] == ["message"] and hook["hmac"] == {"key": "s3cret"}


def test_ensure_session_does_not_restart_a_working_session_with_the_same_webhook(gateway):
    gateway.session = {"name": SESSION, "status": "WORKING", "config": {"webhooks": [{"url": _hook(), "events": ["message"], "hmac": {"key": "s3cret"}}]}, "me": {"id": "1@c.us"}}
    result = waha.WahaClient().ensure_session(SESSION, _hook(), "s3cret")
    assert result["status"] == "WORKING"
    assert [c[0] for c in gateway.calls] == ["GET"]  # nessun PUT, nessun start


def test_ensure_session_updates_the_webhook_when_the_secret_changed(gateway):
    gateway.session = {"name": SESSION, "status": "WORKING", "config": {"webhooks": [{"url": _hook(), "events": ["message"], "hmac": {"key": "vecchio"}}]}, "me": None}
    waha.WahaClient().ensure_session(SESSION, _hook(), "s3cret")
    assert gateway.calls[-1][0:2] == ("PUT", f"/api/sessions/{SESSION}")


def test_ensure_session_starts_a_stopped_session(gateway):
    gateway.session = {"name": SESSION, "status": "STOPPED", "config": {"webhooks": [{"url": _hook(), "events": ["message"], "hmac": {"key": "s3cret"}}]}, "me": None}
    waha.WahaClient().ensure_session(SESSION, _hook(), "s3cret")
    assert gateway.calls[-1][0:2] == ("POST", f"/api/sessions/{SESSION}/start")


def test_qr_code_and_delete_are_tolerant(gateway):
    client = waha.WahaClient()
    assert client.qr_code(SESSION) == {"mimetype": "image/png", "data": "iVBOR..."}
    client.delete_session(SESSION)
    assert gateway.calls[-1][0:2] == ("DELETE", f"/api/sessions/{SESSION}")


def test_client_without_url_is_not_configured(monkeypatch):
    monkeypatch.setattr(waha.settings, "MYAGI_WA_URL", None)
    assert waha.is_configured() is False
    with pytest.raises(ConnectorError):
        waha.WahaClient()


def test_normalize_chat_id():
    assert waha.normalize_chat_id("+39 333 111 2222") == "393331112222@c.us"
    assert waha.normalize_chat_id("393331112222@c.us") == "393331112222@c.us"
