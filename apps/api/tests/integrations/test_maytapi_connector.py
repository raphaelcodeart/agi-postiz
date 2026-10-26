"""
Il connettore WhatsApp via Maytapi.

Maytapi non firma i payload e rimanda sul webhook anche cio' che parte dal
telefono stesso: le due cose messe insieme fanno si' che le proprieta' da
inchiodare qui non siano "il parsing funziona" ma "cosa NON deve entrare in
inbox". Un messaggio nostro ingerito come messaggio del cliente, con
l'autorisponditore acceso, e' un ciclo di risposte a se stessi.
"""
from types import SimpleNamespace

import pytest

from app.integrations.omnichannel.connectors.maytapi import MaytapiConnector
from app.integrations.omnichannel.exceptions import ConnectorError


def _account(secret="s3cret", product_id="p1", phone_id="7"):
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        channel="whatsapp_maytapi",
        webhook_secret=secret,
        config_json={"product_id": product_id, "phone_id": phone_id},
        status="connected",
        external_account_id=None,
    )


def _connector(**kwargs):
    return MaytapiConnector(_account(**kwargs), access_token="token")


def _inbound(**overrides):
    payload = {
        "type": "message",
        "product_id": "p1",
        "phone_id": "7",
        "conversation": "393331112222@c.us",
        "user": {"id": "393331112222@c.us", "name": "Mario Rossi", "phone": "393331112222"},
        "message": {"type": "text", "text": "Ciao, siete aperti?", "id": "msg-1", "fromMe": False},
    }
    payload.update(overrides)
    return payload


# --- cosa non deve entrare in inbox -----------------------------------------

def test_our_own_outgoing_message_is_never_ingested():
    """
    La proprieta' piu' importante del file. Maytapi rimanda sul webhook anche le
    risposte che abbiamo appena inviato noi (fromMe=true): ingerirle vorrebbe
    dire generare una bozza AI sulla nostra stessa risposta e, con
    l'autorisponditore acceso, rispondere a se stessi all'infinito.
    """
    message = {"type": "text", "text": "Buongiorno, certo!", "id": "msg-2", "fromMe": True}
    assert _connector().parse_webhook(_inbound(message=message)) == []


def test_delivery_receipts_and_status_events_are_ignored():
    """Sullo stesso webhook arrivano anche ack (spunte), status (telefono
    connesso/disconnesso) ed error: nessuno e' qualcosa che un cliente ha
    scritto."""
    for event_type in ("ack", "status", "error"):
        assert _connector().parse_webhook(_inbound(type=event_type)) == []


def test_a_payload_from_another_maytapi_instance_is_ignored():
    """Difesa in profondita' sopra al segreto nell'URL: il webhook e' per
    prodotto, e un payload che dichiara un'altra istanza non e' roba di questo
    canale."""
    assert _connector().parse_webhook(_inbound(product_id="altro")) == []
    assert _connector().parse_webhook(_inbound(phone_id="99")) == []


def test_a_message_without_an_identity_is_dropped_rather_than_ingested_anonymously():
    payload = _inbound(conversation=None, user={})
    assert _connector().parse_webhook(payload) == []


# --- parsing ----------------------------------------------------------------

def test_a_customer_text_message_is_normalized():
    [message] = _connector().parse_webhook(_inbound())

    assert message.external_user_id == "393331112222@c.us"
    assert message.text == "Ciao, siete aperti?"
    assert message.message_type == "TEXT"
    assert message.external_message_id == "msg-1"
    assert message.customer_display_name == "Mario Rossi"
    # Il JID non e' un numero componibile: il numero in chiaro va tenuto a parte
    # perche' la scheda cliente possa mostrarlo.
    assert message.metadata["whatsapp_phone"] == "393331112222"


def test_a_voice_note_keeps_its_type_and_media_url():
    payload = _inbound(message={"type": "ptt", "url": "https://cdn.maytapi.test/a.ogg", "id": "m", "fromMe": False})
    [message] = _connector().parse_webhook(payload)

    assert message.message_type == "VOICE"
    assert message.attachments == [{"type": "VOICE", "url": "https://cdn.maytapi.test/a.ogg", "mime_type": None}]


def test_an_attachment_caption_is_kept_as_the_message_text():
    """Su un allegato la didascalia e' spesso l'unica cosa che il cliente ha
    scritto: perderla lascerebbe in inbox un messaggio vuoto."""
    payload = _inbound(message={"type": "image", "caption": "È questo il prodotto?", "url": "u", "id": "m", "fromMe": False})
    [message] = _connector().parse_webhook(payload)

    assert message.text == "È questo il prodotto?"
    assert message.message_type == "IMAGE"


def test_an_unknown_message_type_still_reaches_the_inbox():
    """Meglio un messaggio etichettato OTHER che un messaggio sparito perche'
    non sapevamo come chiamarlo."""
    payload = _inbound(message={"type": "qualcosa_di_nuovo", "text": "?", "id": "m", "fromMe": False})
    [message] = _connector().parse_webhook(payload)

    assert message.message_type == "OTHER"


# --- verifica del webhook ----------------------------------------------------

def test_the_url_secret_is_what_authenticates_the_webhook():
    connector = _connector(secret="s3cret")
    assert connector.verify_webhook({}, "s3cret") is True
    assert connector.verify_webhook({}, "sbagliato") is False
    # Un URL senza segreto non deve passare: e' l'unica prova che abbiamo.
    assert connector.verify_webhook({}, "") is False


# --- invio -------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_send_uses_the_documented_endpoint_and_headers(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse({"success": True, "data": {"msgId": "sent-1"}})

    monkeypatch.setattr("app.integrations.omnichannel.connectors.maytapi.httpx.post", fake_post)

    result = _connector().send_message("393331112222@c.us", "Buongiorno")

    assert captured["url"] == "https://api.maytapi.com/api/p1/7/sendMessage"
    assert captured["headers"]["x-maytapi-key"] == "token"
    assert captured["json"] == {"to_number": "393331112222@c.us", "type": "text", "message": "Buongiorno"}
    assert result.external_message_id == "sent-1"


def test_a_refusal_returned_with_http_200_is_still_a_failure(monkeypatch):
    """
    Maytapi risponde 200 anche quando rifiuta: l'esito sta in `success`. Fidarsi
    del codice HTTP farebbe risultare inviato un messaggio mai partito - e da
    li' in poi non sapremmo piu' quali invii sono riusciti davvero.
    """
    monkeypatch.setattr(
        "app.integrations.omnichannel.connectors.maytapi.httpx.post",
        lambda *a, **k: _FakeResponse({"success": False, "message": "Phone is not connected"}),
    )

    with pytest.raises(ConnectorError, match="Phone is not connected"):
        _connector().send_message("393331112222@c.us", "Buongiorno")


def test_missing_configuration_is_reported_before_any_network_call():
    connector = MaytapiConnector(_account(product_id="", phone_id=""), access_token="token")
    with pytest.raises(ConnectorError, match="Product ID"):
        connector.send_message("x", "y")


# --- registrazione del webhook -----------------------------------------------

def test_setwebhook_success_is_not_expected_to_carry_a_success_field(monkeypatch):
    """
    La regressione del 2026-09-22. A differenza di /status e /sendMessage,
    setWebhook risponde 200 con la configurazione del prodotto e **nessun**
    campo `success`. Pretenderlo faceva fallire ogni registrazione riuscita:
    il webhook veniva registrato davvero e la dashboard diceva "errore
    sconosciuto", mandando a cercare il problema dalla parte sbagliata.
    """
    url = "https://api.example.test/api/v1/omnichannel-responder/webhooks/maytapi/abc/s3cret"

    def fake_post(post_url, headers=None, json=None, timeout=None):
        return _FakeResponse({
            "pid": "p1",
            "webhook": json["webhook"],
            "ack_delivery": True,
            "phone_limit": 1,
        })

    monkeypatch.setattr("app.integrations.omnichannel.connectors.maytapi.httpx.post", fake_post)

    assert _connector().register_webhook(url)["webhook"] == url


def test_setwebhook_uses_the_product_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse({"pid": "p1", "webhook": json["webhook"]})

    monkeypatch.setattr("app.integrations.omnichannel.connectors.maytapi.httpx.post", fake_post)
    _connector().register_webhook("https://api.example.test/hook")

    assert captured["url"] == "https://api.maytapi.com/api/p1/setWebhook"
    assert captured["headers"]["x-maytapi-key"] == "token"
    assert captured["json"] == {"webhook": "https://api.example.test/hook"}


def test_an_explicit_refusal_is_still_a_failure(monkeypatch):
    """`success` assente significa riuscito, `success: False` no."""
    monkeypatch.setattr(
        "app.integrations.omnichannel.connectors.maytapi.httpx.post",
        lambda *a, **k: _FakeResponse({"success": False, "message": "Webhook url is not valid"}),
    )

    with pytest.raises(ConnectorError, match="Webhook url is not valid"):
        _connector().register_webhook("https://api.example.test/hook")


def test_an_error_without_a_message_reports_the_raw_body(monkeypatch):
    """"errore sconosciuto" non dice nulla a chi deve risolvere: se Maytapi non
    spiega il rifiuto, si mostra almeno cosa ha risposto."""
    monkeypatch.setattr(
        "app.integrations.omnichannel.connectors.maytapi.httpx.post",
        lambda *a, **k: _FakeResponse({}, status_code=402, text='{"quota":"exceeded"}'),
    )

    with pytest.raises(ConnectorError, match="quota"):
        _connector().register_webhook("https://api.example.test/hook")


def test_a_webhook_stored_under_another_url_is_reported(monkeypatch):
    """Chiamata accettata ma webhook di qualcun altro: i messaggi non
    arriverebbero mai e senza questo controllo lo si scoprirebbe solo dal
    silenzio dell'inbox."""
    monkeypatch.setattr(
        "app.integrations.omnichannel.connectors.maytapi.httpx.post",
        lambda *a, **k: _FakeResponse({"pid": "p1", "webhook": "https://qualcun-altro.test/hook"}),
    )

    with pytest.raises(ConnectorError, match="qualcun-altro"):
        _connector().register_webhook("https://api.example.test/hook")
