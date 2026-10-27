"""
Una bozza aperta risponde a un messaggio preciso. Quando il cliente scrive di
nuovo, quella bozza non puo' restare "da approvare" come se rispondesse al
nuovo messaggio: l'operatore la vedeva comparire e pensava che l'AI avesse
generato da sola anche con la generazione automatica spenta.
"""
import uuid

import pytest

from app.core.security import SecurityService
from app.integrations.omnichannel.connectors.base import NormalizedIncomingMessage
from app.models.administrator import Administrator
from app.models.omnichannel import (
    OmniAIDraft,
    OmniAuditLog,
    OmniChannelAccount,
    OmniConversation,
)
from app.services.omnichannel_draft_service import (
    SUPERSEDED_BY_CUSTOMER,
    OmnichannelDraftService,
)
from app.services.omnichannel_service import OmnichannelService


@pytest.fixture()
def admin(db):
    row = Administrator(email=f"a-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin", password_hash=SecurityService.hash_password("x"), is_active=True)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def account(db, admin):
    row = OmniChannelAccount(owner_id=admin.id, channel="mock", name="Test", webhook_secret=uuid.uuid4().hex, status="connected")
    db.add(row)
    db.commit()
    return row


def _incoming(text, msg_id):
    return NormalizedIncomingMessage(external_user_id="user-1", text=text, external_message_id=msg_id, customer_display_name="Mario")


def _draft(db, admin, conversation, status, source_message_id=None):
    draft = OmniAIDraft(owner_id=admin.id, conversation_id=conversation.id, source_message_id=source_message_id, status=status, original_ai_text="Risposta vecchia")
    db.add(draft)
    db.commit()
    return draft


def test_il_nuovo_messaggio_del_cliente_archivia_le_bozze_aperte(db, admin, account):
    first = OmnichannelService.ingest_message(db, account, _incoming("Ciao, info?", "m1"))
    conversation = first.conversation
    pending = _draft(db, admin, conversation, "PENDING_APPROVAL", first.id)
    edited = _draft(db, admin, conversation, "EDITED", first.id)
    review = _draft(db, admin, conversation, "HUMAN_REVIEW_REQUIRED", first.id)
    failed = _draft(db, admin, conversation, "FAILED", first.id)
    sent = _draft(db, admin, conversation, "SENT", first.id)
    generating = _draft(db, admin, conversation, "GENERATING", first.id)

    OmnichannelService.ingest_message(db, account, _incoming("Anzi, un'altra cosa", "m2"))

    for draft in (pending, edited, review, failed):
        db.refresh(draft)
        assert draft.status == "SUPERSEDED", draft.status
        assert draft.failure_reason == SUPERSEDED_BY_CUSTOMER
        assert draft.original_ai_text == "Risposta vecchia"  # lo storico resta
    db.refresh(sent)
    db.refresh(generating)
    assert sent.status == "SENT" and generating.status == "GENERATING"

    audit = db.query(OmniAuditLog).filter(OmniAuditLog.action == "AI_SUPERSEDED", OmniAuditLog.owner_id == admin.id).count()
    assert audit == 4
    db.refresh(conversation)
    assert conversation.status == "OPEN" or conversation.status == "AI_PROCESSING"


def test_una_bozza_superata_non_si_approva_ne_si_rigenera(db, admin, account):
    first = OmnichannelService.ingest_message(db, account, _incoming("Ciao", "m1"))
    draft = _draft(db, admin, first.conversation, "PENDING_APPROVAL", first.id)
    OmnichannelService.ingest_message(db, account, _incoming("Ci sei?", "m2"))
    db.refresh(draft)
    assert draft.status == "SUPERSEDED"
    with pytest.raises(ValueError):
        OmnichannelDraftService.edit_draft(db, draft, "testo", admin)
    with pytest.raises(ValueError):
        OmnichannelDraftService.regenerate(db, draft, admin)
    with pytest.raises(ValueError):
        OmnichannelDraftService.approve_and_send(db, draft.id, admin=admin)


def test_supersede_rispetta_except_id_e_le_altre_conversazioni(db, admin, account):
    first = OmnichannelService.ingest_message(db, account, _incoming("Uno", "m1"))
    other_account_msg = OmnichannelService.ingest_message(db, account, NormalizedIncomingMessage(external_user_id="user-2", text="Altro cliente", external_message_id="m9"))
    keep = _draft(db, admin, first.conversation, "PENDING_APPROVAL", first.id)
    old = _draft(db, admin, first.conversation, "PENDING_APPROVAL", first.id)
    foreign = _draft(db, admin, other_account_msg.conversation, "PENDING_APPROVAL", other_account_msg.id)

    archived = OmnichannelDraftService.supersede_open_drafts(db, first.conversation.id, "test", except_id=keep.id)
    db.commit()
    assert archived == 1
    for draft in (keep, old, foreign):
        db.refresh(draft)
    assert keep.status == "PENDING_APPROVAL" and old.status == "SUPERSEDED" and foreign.status == "PENDING_APPROVAL"
    assert db.query(OmniConversation).count() == 2
