"""
CRM Mamify nell'Omnichannel Responder: la regola che un cliente chiede solo di
se stesso deve reggere nel codice, non nel prompt.

Quello che si inchioda qui:
- l'identita' fidata viene dal canale (numero WhatsApp) o dall'operatore, mai
  dal testo; su Telegram senza scheda compilata non c'e' identita';
- il modello non puo' scegliere il cliente: email/telefono/id passati come
  argomenti vengono scartati e il customer_id e' sempre quello risolto;
- nel caso ambiguo l'email del cliente viaggia INSIEME al telefono fidato;
- gli strumenti customer/* esistono solo a cliente identificato;
- il loop di function calling esegue gli strumenti e somma i token;
- dalla rete del cliente escono nomi, non contatti di terzi.
"""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.omnichannel import ai as omni_ai
from app.integrations.omnichannel.crm import tools
from app.integrations.omnichannel.crm.mamify import (
    ERR_IDENTIFIER_REQUIRED,
    MamifyError,
    MamifyRagClient,
    normalize_phone,
)
from app.integrations.omnichannel.exceptions import ConnectorError


# ------------------------------------------------------------------ helpers
class FakeCrm:
    """Un MamifyRagClient finto che registra ogni chiamata con i suoi parametri."""

    def __init__(self, find_result=None, find_error=None):
        self.calls = []
        self.find_result = find_result or {"customer": {"id": 42, "first_name": "Giulia", "last_name": "Verdi", "email": "g@x.it", "phone": "393331234567"}, "network": {"direct": 3, "total": 10}}
        self.find_error = find_error

    def find_customer(self, **ids):
        self.calls.append(("customer/find", ids))
        if self.find_error:
            raise self.find_error
        return self.find_result

    def wallets(self, **kw):
        self.calls.append(("customer/wallets", kw))
        return {"mamix": {"balance": 120}, "mamicash": {"balance": 30, "personal": 30, "business": 0}}

    def transactions(self, **kw):
        self.calls.append(("customer/transactions", kw))
        return {"items": [{"date": "2026-10-01", "amount": -10}]}

    def orders(self, **kw):
        self.calls.append(("customer/orders", kw))
        return {"items": [{"id": 7, "status": "paid"}]}

    def network(self, **kw):
        self.calls.append(("customer/network", kw))
        return {"items": [{"first_name": "Anna", "email": "anna@x.it", "phone": "3330000000", "level": 1}]}

    def search_products(self, **kw):
        self.calls.append(("products/search", kw))
        return {"items": [{"name": "Luce casa", "price": 10}]}

    def search_giftcards(self, **kw):
        self.calls.append(("giftcards/search", kw))
        return {"items": []}


def _identity(channel, external_user_id):
    return SimpleNamespace(channel=channel, external_user_id=external_user_id)


def _customer(identities=(), phone=None, email=None):
    return SimpleNamespace(identities=list(identities), phone=phone, email=email)


# ------------------------------------------------------------ normalizzazione
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+39 333 123 4567", "393331234567"),
        ("393331234567@c.us", "393331234567"),
        ("393331234567", "393331234567"),
        ("120363012345678@g.us", None),  # gruppo WhatsApp: non e' un cliente
        ("12345", None),  # troppo corto per il confronto sulle ultime 10 cifre
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


# ------------------------------------------------------------ identita' fidata
def test_il_numero_whatsapp_del_canale_e_l_identita_fidata():
    customer = _customer([_identity("whatsapp_maytapi", "393331234567@c.us")])
    identity = tools.trusted_identity_for_customer(customer, "whatsapp_maytapi")
    assert identity.phone == "393331234567"
    assert identity.source == "channel"


def test_su_telegram_senza_scheda_non_c_e_identita():
    customer = _customer([_identity("telegram", "123456789")])
    assert tools.trusted_identity_for_customer(customer, "telegram") is None


def test_su_telegram_vale_cio_che_ha_scritto_l_operatore():
    customer = _customer([_identity("telegram", "123456789")], phone="+39 333 1234567", email="  G@X.IT ")
    identity = tools.trusted_identity_for_customer(customer, "telegram")
    assert identity.source == "operator"
    assert identity.phone == "393331234567"
    assert identity.email == "g@x.it"


def test_senza_identita_fidata_niente_find_e_stato_unverified():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, None)
    assert ctx.status == "unverified"
    assert crm.calls == []
    names = {t["function"]["name"] for t in tools.tool_definitions(ctx)}
    assert names == {"search_products", "search_giftcards"}


# --------------------------------------------------------------- risoluzione
def test_cliente_identificato_sblocca_gli_strumenti_del_cliente():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    assert ctx.status == "identified"
    assert ctx.customer_id == "42"
    assert crm.calls == [("customer/find", {"phone": "393331234567"})]
    names = {t["function"]["name"] for t in tools.tool_definitions(ctx)}
    assert {"get_my_wallets", "get_my_transactions", "get_my_orders", "get_my_network"} <= names
    assert "confirm_identity_by_email" not in names


def test_cliente_non_trovato_non_ha_strumenti_del_cliente():
    crm = FakeCrm(find_error=MamifyError("customer_not_found", "nessuno"))
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    assert ctx.status == "not_found"
    names = {t["function"]["name"] for t in tools.tool_definitions(ctx)}
    assert names == {"search_products", "search_giftcards"}
    assert "NON puoi fornire dati di account" in tools.system_prompt_section(ctx)


def test_caso_ambiguo_offre_solo_la_conferma_via_email():
    crm = FakeCrm(find_error=MamifyError("customer_ambiguous", "", data={"candidates": [{"id": 1}, {"id": 2}]}))
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    assert ctx.status == "ambiguous"
    assert ctx.candidates_count == 2
    names = {t["function"]["name"] for t in tools.tool_definitions(ctx)}
    assert names == {"search_products", "search_giftcards", "confirm_identity_by_email"}


def test_la_conferma_via_email_porta_sempre_anche_il_telefono_fidato():
    crm = FakeCrm(find_error=MamifyError("customer_ambiguous", ""))
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    crm.find_error = None  # la seconda find (telefono + email) riesce
    out = json.loads(tools.execute_tool(crm, ctx, "confirm_identity_by_email", {"email": " Giulia@X.it "}))
    assert out["ok"] is True
    assert crm.calls[-1] == ("customer/find", {"phone": "393331234567", "email": "giulia@x.it"})
    assert ctx.status == "identified" and ctx.customer_id == "42"
    assert "get_my_wallets" in {t["function"]["name"] for t in tools.tool_definitions(ctx)}


def test_la_conferma_via_email_non_esiste_senza_telefono_fidato():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, None)
    out = json.loads(tools.execute_tool(crm, ctx, "confirm_identity_by_email", {"email": "altro@x.it"}))
    assert out["error"] == "not_applicable"
    assert crm.calls == []  # nessuna find con la sola email


# ------------------------------------------------------- esecuzione strumenti
def test_il_modello_non_puo_scegliere_il_cliente():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    tools.execute_tool(crm, ctx, "get_my_wallets", {"customer_id": "999", "email": "mario@x.it", "phone": "3339999999"})
    tools.execute_tool(crm, ctx, "get_my_orders", {"customer_id": 1, "status": "open"})
    tools.execute_tool(crm, ctx, "get_my_transactions", {"wallet": "mamix", "code": "VA206", "limit": 500})
    assert crm.calls[1] == ("customer/wallets", {"customer_id": "42"})
    assert crm.calls[2] == ("customer/orders", {"customer_id": "42", "order_id": None, "status": "open", "limit": 5})
    assert crm.calls[3][1]["customer_id"] == "42"
    assert crm.calls[3][1]["limit"] == 10  # tetto, non 500


def test_senza_identificazione_gli_strumenti_del_cliente_rifiutano():
    crm = FakeCrm(find_error=MamifyError("customer_not_found", ""))
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    out = json.loads(tools.execute_tool(crm, ctx, "get_my_wallets", {}))
    assert out["error"] == "not_identified"
    assert all(name != "customer/wallets" for name, _ in crm.calls)


def test_dalla_rete_escono_i_nomi_ma_non_i_contatti_di_terzi():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    out = json.loads(tools.execute_tool(crm, ctx, "get_my_network", {"scope": "all"}))
    person = out["items"][0]
    assert person["first_name"] == "Anna"
    assert "email" not in person and "phone" not in person


def test_un_errore_del_crm_diventa_un_messaggio_per_il_modello_non_un_crash():
    class Flaky(FakeCrm):
        def wallets(self, **kw):
            raise MamifyError("rate_limited", "troppo", 429)

    crm = Flaky()
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    out = json.loads(tools.execute_tool(crm, ctx, "get_my_wallets", {}))
    assert out["error"] == "rate_limited"
    assert ctx.lookups[-1] == {"tool": "get_my_wallets", "ok": False, "error": "rate_limited"}


def test_il_riepilogo_per_l_audit_non_contiene_dati_personali():
    crm = FakeCrm()
    ctx = tools.resolve_customer(crm, tools.TrustedIdentity(phone="393331234567"))
    tools.execute_tool(crm, ctx, "get_my_wallets", {})
    summary = json.dumps(ctx.summary())
    assert "393331234567" not in summary and "g@x.it" not in summary and "Giulia" not in summary
    assert ctx.summary()["lookups"] == [{"tool": "customer/find", "ok": True}, {"tool": "get_my_wallets", "ok": True}]


# ------------------------------------------------------------- client HTTP
def _transport(handler):
    return httpx.MockTransport(handler)


def test_il_client_manda_la_chiave_nell_header_e_legge_data(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Fw360-Key")
        return httpx.Response(200, json={"status": 1, "data": {"customer": {"id": 5}}})

    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Client(transport=_transport(handler)).get(url, **kw))
    client = MamifyRagClient("SEGRETA")
    data = client.find_customer(phone="393331234567")
    assert data == {"customer": {"id": 5}}
    assert seen["key"] == "SEGRETA"
    assert seen["url"] == "https://mamify.app/m/api/plugins/mamify/rag/customer/find?phone=393331234567"


def test_il_client_traduce_status_0_in_errore_con_codice_e_candidati(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": 0, "error": "customer_ambiguous", "message": "due", "candidates": [{"id": 1}, {"id": 2}]})

    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Client(transport=_transport(handler)).get(url, **kw))
    with pytest.raises(MamifyError) as exc:
        MamifyRagClient("k").find_customer(phone="393331234567")
    assert exc.value.code == "customer_ambiguous"
    assert len(exc.value.data["candidates"]) == 2
    assert "k" not in str(exc.value) or exc.value.message == "due"


def test_il_client_gestisce_429_e_non_json(monkeypatch):
    responses = iter([
        httpx.Response(429, headers={"Retry-After": "7"}, json={"status": 0}),
        httpx.Response(502, text="<html>bad gateway</html>"),
    ])
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Client(transport=_transport(lambda r: next(responses))).get(url, **kw))
    client = MamifyRagClient("k")
    with pytest.raises(MamifyError) as exc:
        client.wallets(customer_id="1")
    assert exc.value.code == "rate_limited" and "7" in exc.value.message
    with pytest.raises(MamifyError) as exc:
        client.wallets(customer_id="1")
    assert exc.value.code == "crm_unavailable"


def test_check_key_non_legge_dati_e_distingue_i_tre_esiti(monkeypatch):
    for error, expected in [("customer_identifier_required", "ok"), ("wrong_api_key", "invalid"), ("insufficient_permissions", "no_permission")]:
        def fake_get(url, _error=error, **kw):
            return httpx.Client(transport=_transport(lambda r: httpx.Response(200, json={"status": 0, "error": _error}))).get(url, **kw)

        monkeypatch.setattr(httpx, "get", fake_get)
        assert MamifyRagClient("k").check_key()["status"] == expected


def test_check_key_riconosce_wrong_endpoint_del_dispatcher_mamify(monkeypatch):
    # Risposta reale del server quando il plugin RAG non e' pubblicato:
    # HTTP 200 con una lista, non un oggetto.
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Client(transport=_transport(lambda r: httpx.Response(200, json=["status", "wrong_endpoint"]))).get(url, **kw))
    result = MamifyRagClient("k").check_key()
    assert result["status"] == "error"
    assert "wrong_endpoint" in result["message"] and "mamify.app" in result["message"]
    with pytest.raises(MamifyError) as exc:
        MamifyRagClient("k").wallets(customer_id="1")
    assert exc.value.code == "wrong_endpoint"


def test_nessun_identificativo_e_un_errore_locale_senza_chiamata():
    with pytest.raises(MamifyError) as exc:
        MamifyRagClient("k").find_customer()
    assert exc.value.code == ERR_IDENTIFIER_REQUIRED


# -------------------------------------------------- loop di function calling
def _openai_reply(content=None, tool_calls=None, prompt=10, completion=5):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


def test_complete_chat_esegue_gli_strumenti_e_somma_i_token(monkeypatch):
    bodies = []
    replies = iter([
        _openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {"name": "get_my_wallets", "arguments": "{}"}}], prompt=100, completion=10),
        _openai_reply(content="Hai 120 Mamix.", prompt=150, completion=20),
    ])

    def fake_post(url, headers, json, timeout):
        bodies.append(json)
        return httpx.Response(200, json=next(replies))

    monkeypatch.setattr(omni_ai.httpx, "post", fake_post)
    executed = []

    def executor(name, args):
        executed.append((name, args))
        return '{"mamix": {"balance": 120}}'

    result = omni_ai.complete_chat("k", "gpt-x", [{"role": "system", "content": "s"}], 0.2, tools=lambda: [{"type": "function", "function": {"name": "get_my_wallets", "parameters": {}}}], tool_executor=executor)

    assert result["text"] == "Hai 120 Mamix."
    assert result["input_tokens"] == 250 and result["output_tokens"] == 30
    assert result["tool_calls"] == 1
    assert executed == [("get_my_wallets", {})]
    assert "tools" in bodies[0]
    # Il secondo giro contiene la chiamata dell'assistente e il risultato dello strumento.
    roles = [m["role"] for m in bodies[1]["messages"]]
    assert roles[-2:] == ["assistant", "tool"]
    assert bodies[1]["messages"][-1]["tool_call_id"] == "c1"


def test_complete_chat_senza_strumenti_non_manda_tools(monkeypatch):
    bodies = []

    def fake_post(url, headers, json, timeout):
        bodies.append(json)
        return httpx.Response(200, json=_openai_reply(content="Ciao"))

    monkeypatch.setattr(omni_ai.httpx, "post", fake_post)
    result = omni_ai.complete_chat("k", "gpt-x", [{"role": "user", "content": "ciao"}], 0.7)
    assert result["text"] == "Ciao" and "tools" not in bodies[0]


def test_complete_chat_si_ferma_dopo_il_tetto_di_giri(monkeypatch):
    call = {"id": "c", "type": "function", "function": {"name": "get_my_wallets", "arguments": "non json"}}
    monkeypatch.setattr(omni_ai.httpx, "post", lambda url, headers, json, timeout: httpx.Response(200, json=_openai_reply(tool_calls=[call])))
    with pytest.raises(ConnectorError):
        omni_ai.complete_chat("k", "gpt-x", [], 0.7, tools=[{"type": "function"}], tool_executor=lambda n, a: "{}", max_tool_rounds=2)


# ------------------------------------------------------------- client factory
def test_client_for_rispetta_interruttore_e_chiave(monkeypatch):
    from app.core.config import settings
    from app.core.security import EncryptionService

    monkeypatch.setattr(settings, "MAMIFY_RAG_API_KEY", None)
    assert tools.client_for(None) is None
    assert tools.client_for(SimpleNamespace(crm_enabled=False, crm_api_key_encrypted=EncryptionService.encrypt("k"), crm_base_url=None)) is None
    assert tools.client_for(SimpleNamespace(crm_enabled=True, crm_api_key_encrypted=None, crm_base_url=None)) is None
    client = tools.client_for(SimpleNamespace(crm_enabled=True, crm_api_key_encrypted=EncryptionService.encrypt("k"), crm_base_url="https://staging.example/rag"))
    assert client is not None and client.base_url == "https://staging.example/rag/"
    monkeypatch.setattr(settings, "MAMIFY_RAG_API_KEY", "env-key")
    assert tools.client_for(SimpleNamespace(crm_enabled=True, crm_api_key_encrypted=None, crm_base_url=None)) is not None
