"""
Contatori per canale della lista account: l'Inbox li usa nel selettore
"su quale numero sto lavorando", quindi devono distinguere il totale dalle
conversazioni che chiedono attenzione adesso.
"""
import uuid

import pytest

from app.core.security import SecurityService
from app.models.administrator import Administrator
from app.models.omnichannel import OmniChannelAccount, OmniConversation, OmniCustomer

BASE = "/api/v1/omnichannel-responder"


@pytest.fixture()
def admin(db):
    row = Administrator(email=f"a-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(row)
    db.commit()
    return row


def _account(db, admin, name):
    account = OmniChannelAccount(owner_id=admin.id, channel="mock", name=name, webhook_secret=uuid.uuid4().hex, status="connected")
    db.add(account)
    db.commit()
    return account


def _conversation(db, admin, account, status="OPEN", unread=0):
    customer = OmniCustomer(owner_id=admin.id, name="C")
    db.add(customer)
    db.flush()
    conv = OmniConversation(owner_id=admin.id, channel_account_id=account.id, customer_id=customer.id, status=status, unread_count=unread)
    db.add(conv)
    db.commit()
    return conv


def test_i_contatori_sono_per_canale_e_distinguono_il_lavoro_da_fare(client, db, admin, admin_token):
    busy = _account(db, admin, "Numero vendite")
    quiet = _account(db, admin, "Numero assistenza")
    _conversation(db, admin, busy, status="WAITING_APPROVAL")          # bozza da approvare
    _conversation(db, admin, busy, status="OPEN", unread=3)            # non letta
    _conversation(db, admin, busy, status="RESOLVED")                  # chiusa: conta nel totale e basta
    _conversation(db, admin, quiet, status="RESOLVED")

    other = Administrator(email=f"b-{uuid.uuid4().hex[:6]}@example.com", full_name="B", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(other)
    db.commit()
    foreign = _account(db, other, "Di un altro")
    _conversation(db, other, foreign, status="WAITING_APPROVAL")

    response = client.get(f"{BASE}/channel-accounts", headers=admin_token(admin))
    assert response.status_code == 200, response.text
    by_name = {row["name"]: row for row in response.json()}
    assert set(by_name) == {"Numero vendite", "Numero assistenza"}
    assert by_name["Numero vendite"]["conversation_count"] == 3
    assert by_name["Numero vendite"]["pending_count"] == 2
    assert by_name["Numero vendite"]["unread_count"] == 3
    assert by_name["Numero assistenza"] | {"conversation_count": 1, "pending_count": 0, "unread_count": 0} == by_name["Numero assistenza"]


def test_il_filtro_per_account_restituisce_solo_quel_numero(client, db, admin, admin_token):
    first = _account(db, admin, "Uno")
    second = _account(db, admin, "Due")
    _conversation(db, admin, first)
    _conversation(db, admin, second)
    headers = admin_token(admin)
    rows = client.get(f"{BASE}/conversations?channel_account_id={first.id}", headers=headers).json()
    assert len(rows) == 1 and rows[0]["channel_account_name"] == "Uno"
    assert len(client.get(f"{BASE}/conversations", headers=headers).json()) == 2
