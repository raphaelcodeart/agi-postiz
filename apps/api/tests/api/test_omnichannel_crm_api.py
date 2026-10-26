"""
Impostazioni CRM e scheda CRM del cliente, via HTTP.

La chiave e' una credenziale verso dati personali di terzi: entra, si cifra,
e non esce piu' - l'API dice solo se c'e'. E la scheda CRM di un contatto si
apre solo per i contatti del proprio owner.
"""
import uuid

import pytest

from app.core.security import EncryptionService, SecurityService
from app.integrations.omnichannel.crm import tools as crm_tools
from app.models.administrator import Administrator
from app.models.omnichannel import (
    OmniAIAgentConfig,
    OmniAuditLog,
    OmniCustomer,
    OmniCustomerIdentity,
)

BASE = "/api/v1/omnichannel-responder"


@pytest.fixture()
def admin(db):
    row = Administrator(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin Test",
        password_hash=SecurityService.hash_password("x"), is_active=True,
    )
    db.add(row)
    db.commit()
    return row


def test_la_chiave_entra_cifrata_e_non_esce_mai(client, db, admin, admin_token, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAMIFY_RAG_API_KEY", None)
    headers = admin_token(admin)

    before = client.get(f"{BASE}/ai-agent", headers=headers).json()
    assert before["crm_enabled"] is False and before["crm_api_key_set"] is False

    # Accendere senza chiave non si puo'.
    assert client.put(f"{BASE}/ai-agent", json={"crm_enabled": True}, headers=headers).status_code == 400

    saved = client.put(f"{BASE}/ai-agent", json={"crm_api_key": "  LA-CHIAVE  ", "crm_enabled": True, "crm_base_url": "https://mamify.app/m/api/plugins/mamify/rag/"}, headers=headers)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["crm_enabled"] is True
    assert body["crm_api_key_set"] is True and body["crm_api_key_source"] == "config"
    assert "LA-CHIAVE" not in saved.text and "crm_api_key_encrypted" not in body

    config = db.query(OmniAIAgentConfig).filter(OmniAIAgentConfig.owner_id == admin.id).one()
    assert config.crm_api_key_encrypted != "LA-CHIAVE"
    assert EncryptionService.decrypt(config.crm_api_key_encrypted) == "LA-CHIAVE"

    actions = {row.action for row in db.query(OmniAuditLog).filter(OmniAuditLog.owner_id == admin.id)}
    assert {"CRM_KEY_CHANGED", "CRM_TOGGLED"} <= actions

    # Stringa vuota = rimuovi la chiave; http non cifrato rifiutato.
    assert client.put(f"{BASE}/ai-agent", json={"crm_base_url": "http://insicuro"}, headers=headers).status_code == 400
    removed = client.put(f"{BASE}/ai-agent", json={"crm_api_key": ""}, headers=headers).json()
    assert removed["crm_api_key_set"] is False


def test_check_senza_chiave_e_con_chiave(client, db, admin, admin_token, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAMIFY_RAG_API_KEY", None)
    headers = admin_token(admin)
    assert client.post(f"{BASE}/ai-agent/crm/check", headers=headers).json()["status"] == "not_configured"

    client.put(f"{BASE}/ai-agent", json={"crm_api_key": "k"}, headers=headers)
    monkeypatch.setattr(crm_tools.MamifyRagClient, "check_key", lambda self: {"status": "ok", "message": "bene"})
    assert client.post(f"{BASE}/ai-agent/crm/check", headers=headers).json() == {"status": "ok", "message": "bene"}


def test_scheda_crm_del_cliente(client, db, admin, admin_token, monkeypatch):
    headers = admin_token(admin)
    customer = OmniCustomer(owner_id=admin.id, name="Giulia")
    db.add(customer)
    db.flush()
    db.add(OmniCustomerIdentity(owner_id=admin.id, customer_id=customer.id, channel="whatsapp_maytapi", external_user_id="393331234567@c.us"))
    db.commit()

    # Integrazione spenta: lo dice, senza chiamare nessuno.
    off = client.get(f"{BASE}/customers/{customer.id}/crm-profile", headers=headers)
    assert off.status_code == 200 and off.json()["status"] == "disabled"

    client.put(f"{BASE}/ai-agent", json={"crm_api_key": "k", "crm_enabled": True}, headers=headers)

    seen = {}

    def fake_find(self, **ids):
        seen["find"] = ids
        return {"customer": {"id": 42, "first_name": "Giulia", "last_name": "Verdi", "email": "g@x.it"}}

    monkeypatch.setattr(crm_tools.MamifyRagClient, "find_customer", fake_find)
    monkeypatch.setattr(crm_tools.MamifyRagClient, "wallets", lambda self, **kw: {"mamix": {"balance": 1}})

    on = client.get(f"{BASE}/customers/{customer.id}/crm-profile", headers=headers)
    assert on.status_code == 200, on.text
    body = on.json()
    assert body["status"] == "identified" and body["identity_source"] == "channel"
    assert body["customer"]["first_name"] == "Giulia"
    assert body["wallets"] == {"mamix": {"balance": 1}}
    assert seen["find"] == {"phone": "393331234567"}

    viewed = db.query(OmniAuditLog).filter(OmniAuditLog.owner_id == admin.id, OmniAuditLog.action == "CRM_PROFILE_VIEWED").all()
    assert len(viewed) == 1 and viewed[0].metadata_json["customer_id"] == "42"

    # Un altro amministratore non vede la scheda di un contatto non suo.
    other = Administrator(email=f"o-{uuid.uuid4().hex[:6]}@example.com", full_name="Other", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(other)
    db.commit()
    assert client.get(f"{BASE}/customers/{customer.id}/crm-profile", headers=admin_token(other)).status_code == 404
