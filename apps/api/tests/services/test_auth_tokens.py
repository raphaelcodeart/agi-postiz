"""
Regole dei token monouso spediti per email.

Sono le condizioni per cui un link arrivato nella posta vale come prova
d'identita'. Ognuna di queste, se salta, e' un modo per entrare nell'account di
qualcun altro - percio' stanno scritte una per una invece che dentro un unico
test del "percorso felice".
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.auth_token import UserAuthToken
from app.models.user import User
from app.services import auth_tokens


@pytest.fixture()
def user(db):
    row = User(name="Giulia Verdi", email="giulia@example.com", status="active")
    db.add(row)
    db.flush()
    return row


def test_token_is_never_stored_in_clear(db, user):
    """
    Il valore spedito non deve esistere nel database.

    E' cio' che rende innocuo un backup finito nelle mani sbagliate: i link
    validi restano solo nelle caselle dei destinatari.
    """
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, timedelta(hours=1))

    stored = db.query(UserAuthToken).filter(UserAuthToken.user_id == user.id).one()
    assert stored.token_hash != raw
    assert len(stored.token_hash) == 64  # sha256 esadecimale


def test_valid_token_resolves_to_its_user(db, user):
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, timedelta(hours=1))

    assert auth_tokens.consume(db, raw, auth_tokens.PURPOSE_EMAIL_VERIFICATION) is user


def test_token_works_once(db, user):
    """Un link di reset che resta valido e' una password di riserva permanente."""
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))

    assert auth_tokens.consume(db, raw, auth_tokens.PURPOSE_PASSWORD_RESET) is user
    assert auth_tokens.consume(db, raw, auth_tokens.PURPOSE_PASSWORD_RESET) is None


def test_expired_token_is_refused(db, user):
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(seconds=1))
    stored = db.query(UserAuthToken).filter(UserAuthToken.user_id == user.id).one()
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()

    assert auth_tokens.consume(db, raw, auth_tokens.PURPOSE_PASSWORD_RESET) is None


def test_token_of_one_kind_does_not_work_as_the_other(db, user):
    """
    Senza questo controllo, un link di conferma - che e' lungo giorni e finisce
    in una casella per sempre - varrebbe come un link di reset.
    """
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, timedelta(hours=1))

    assert auth_tokens.consume(db, raw, auth_tokens.PURPOSE_PASSWORD_RESET) is None


def test_issuing_a_new_token_kills_the_previous_one(db, user):
    """Chi chiede un secondo link non deve lasciarsi dietro il primo ancora valido."""
    first = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))
    second = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))

    assert auth_tokens.consume(db, first, auth_tokens.PURPOSE_PASSWORD_RESET) is None
    assert auth_tokens.consume(db, second, auth_tokens.PURPOSE_PASSWORD_RESET) is user


def test_invalidate_pending_closes_every_open_link(db, user):
    """Dopo un cambio password non deve restare in giro nessuna altra porta aperta."""
    verification = auth_tokens.issue(
        db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, timedelta(hours=1)
    )
    reset = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))

    auth_tokens.invalidate_pending(db, user)

    assert auth_tokens.consume(db, verification, auth_tokens.PURPOSE_EMAIL_VERIFICATION) is None
    assert auth_tokens.consume(db, reset, auth_tokens.PURPOSE_PASSWORD_RESET) is None


def test_garbage_is_refused_without_blowing_up(db, user):
    assert auth_tokens.consume(db, "", auth_tokens.PURPOSE_PASSWORD_RESET) is None
    assert auth_tokens.consume(db, "non-e-un-token", auth_tokens.PURPOSE_PASSWORD_RESET) is None


def test_rate_limit_trips_after_the_allowed_requests(db, user):
    """
    Senza limite, questi endpoint sarebbero un modo gratuito per riempire la
    casella di chiunque di email che arrivano davvero da noi.
    """
    for _ in range(auth_tokens.MAX_REQUESTS_PER_WINDOW):
        assert not auth_tokens.rate_limited(db, user, auth_tokens.PURPOSE_PASSWORD_RESET)
        auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))

    assert auth_tokens.rate_limited(db, user, auth_tokens.PURPOSE_PASSWORD_RESET)
    # Il limite e' per tipo: non aver piu' reset disponibili non deve impedire
    # di farsi rimandare la conferma dell'indirizzo.
    assert not auth_tokens.rate_limited(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION)


def test_purge_only_removes_old_rows(db, user):
    auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, timedelta(hours=1))
    old = UserAuthToken(
        user_id=user.id,
        purpose=auth_tokens.PURPOSE_EMAIL_VERIFICATION,
        token_hash="f" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(days=60),
        created_at=datetime.now(timezone.utc) - timedelta(days=60),
    )
    db.add(old)
    db.flush()

    assert auth_tokens.purge_expired(db) == 1
    assert db.query(UserAuthToken).filter(UserAuthToken.user_id == user.id).count() == 1
