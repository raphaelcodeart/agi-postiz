"""
Conferma dell'indirizzo e recupero password, visti dall'HTTP.

Due proprieta' sono quelle che contano davvero, e nessuna delle due si puo'
verificare guardando solo le funzioni:

1. Il blocco di chi non ha confermato vive nell'API, non nel browser. La
   finestra che il portale mostra e' una spiegazione; se l'unica difesa fosse
   quella, basterebbe chiamare l'endpoint da fuori.
2. Il recupero password non deve dire a nessuno chi ha un account qui. La
   risposta e' identica per un indirizzo conosciuto e uno inventato.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import SecurityService
from app.models.auth_token import UserAuthToken
from app.models.user import User
from app.services import auth_tokens


def _ttl() -> timedelta:
    return timedelta(hours=1)


@pytest.fixture()
def captured_emails(monkeypatch):
    """
    Intercetta l'accodamento invece di parlare con Redis.

    Si sostituisce ``.delay`` del task, cioe' esattamente il confine fra "la
    richiesta ha finito il suo lavoro" e "il messaggio partira'": tutto quello
    che sta prima - token, URL, testo - resta sotto test.
    """
    from app.tasks import email as email_task

    sent = []

    class _Stub:
        @staticmethod
        def delay(**kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(email_task, "send_transactional_email", _Stub)
    return sent


def _make_user(
    db,
    *,
    email="promoter@example.com",
    verified=False,
    password="password-lunga",
    retroactive=False,
):
    now = datetime.now(timezone.utc)
    user = User(
        name="Luca Bianchi",
        email=email,
        status="active",
        password_hash=SecurityService.hash_password(password),
        email_verified_at=now if verified else None,
        privacy_accepted_at=now if verified else None,
        profile_completed_at=now if verified else None,
        verification_retroactive=retroactive,
    )
    db.add(user)
    db.commit()
    return user


# --- registrazione ---------------------------------------------------------

def test_registration_sends_the_welcome_email_and_leaves_the_account_unverified(
    client, db, captured_emails
):
    response = client.post(
        "/api/v1/portal/auth/register",
        json={
            "name": "Sara Neri",
            "email": "sara@example.com",
            "password": "una-password-lunga",
        },
    )

    assert response.status_code == 201
    user = db.query(User).filter(User.email == "sara@example.com").one()
    assert user.email_verified_at is None
    assert len(captured_emails) == 1
    assert captured_emails[0]["to_address"] == "sara@example.com"
    # Il link spedito deve puntare alla pagina che lo sa consumare.
    assert "/portal/verify-email?token=" in captured_emails[0]["text_body"]


def test_a_failed_email_does_not_fail_the_registration(client, db, monkeypatch):
    """
    Se il broker non risponde, l'account creato resta creato: dire "errore" a chi
    ha appena registrato un account che esiste lo porta a crearne un secondo.
    """
    from app.tasks import email as email_task

    class _Broken:
        @staticmethod
        def delay(**kwargs):
            raise RuntimeError("broker irraggiungibile")

    monkeypatch.setattr(email_task, "send_transactional_email", _Broken)

    response = client.post(
        "/api/v1/portal/auth/register",
        json={"name": "Ada Blu", "email": "ada@example.com", "password": "una-password-lunga"},
    )

    assert response.status_code == 201
    assert db.query(User).filter(User.email == "ada@example.com").count() == 1


# --- il blocco vive nell'API ----------------------------------------------

def test_unverified_user_is_refused_by_the_portal_endpoints(client, db, portal_token):
    user = _make_user(db, verified=False)

    response = client.get("/api/v1/portal/channels", headers=portal_token(user))

    assert response.status_code == 403
    assert response.json()["detail"] == "email_not_verified"


def test_unverified_user_can_still_read_me(client, db, portal_token):
    """
    L'eccezione voluta: e' da /me che il portale scopre di dover mostrare la
    finestra di attesa. Se anche questa fosse chiusa, non resterebbe niente da
    dire all'utente.
    """
    user = _make_user(db, verified=False)

    response = client.get("/api/v1/portal/me", headers=portal_token(user))

    assert response.status_code == 200
    assert response.json()["email_verified"] is False


def test_verified_user_passes(client, db, portal_token):
    user = _make_user(db, verified=True, email="ok@example.com")

    assert client.get("/api/v1/portal/channels", headers=portal_token(user)).status_code == 200


# --- iscritti di prima della conferma --------------------------------------

def test_me_tells_whether_a_confirmation_email_ever_left(client, db, portal_token, captured_emails):
    """
    E' su questo che la finestra sceglie fra "controlla la tua email" e "ti
    mandiamo un'email": all'iscritto di vecchia data non e' ancora partito niente.
    """
    user = _make_user(db, verified=False, retroactive=True)

    assert client.get("/api/v1/portal/me", headers=portal_token(user)).json()[
        "verification_email_sent"
    ] is False

    client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))

    assert client.get("/api/v1/portal/me", headers=portal_token(user)).json()[
        "verification_email_sent"
    ] is True


def test_an_existing_member_gets_the_email_for_who_was_already_here(
    client, db, portal_token, captured_emails
):
    user = _make_user(db, verified=False, retroactive=True)

    client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))

    (email,) = captured_emails
    assert "benvenuto" not in email["text_body"].lower()
    assert "quando ti sei iscritto non c'erano ancora" in email["text_body"]
    # Il consenso resta esplicito anche nella variante.
    assert "accetti la privacy" in email["text_body"]


def test_a_new_member_still_gets_the_welcome(client, db, captured_emails):
    client.post(
        "/api/v1/portal/auth/register",
        json={"name": "Sara Neri", "email": "sara@example.com", "password": "una-password-lunga"},
    )

    (email,) = captured_emails
    assert "benvenuto in AGI Post" in email["text_body"]


def test_resend_is_refused_only_once_both_address_and_privacy_are_done(
    client, db, portal_token, captured_emails
):
    """Indirizzo confermato dal reset ma privacy ancora da accettare: l'email serve."""
    user = _make_user(db, verified=False, retroactive=True)
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    response = client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))

    assert response.status_code == 200
    assert len(captured_emails) == 1


# --- conferma dell'indirizzo ----------------------------------------------

def test_verify_email_confirms_the_address_and_records_the_consent(client, db):
    user = _make_user(db, verified=False)
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, _ttl())
    db.commit()

    response = client.post("/api/v1/portal/auth/verify-email", json={"token": raw})

    assert response.status_code == 200
    assert response.json()["access_token"]  # si entra senza ripassare dall'accesso
    db.refresh(user)
    assert user.email_verified_at is not None
    assert user.privacy_accepted_at is not None


def test_verify_email_refuses_a_used_link(client, db):
    user = _make_user(db, verified=False)
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, _ttl())
    db.commit()

    assert client.post("/api/v1/portal/auth/verify-email", json={"token": raw}).status_code == 200
    assert client.post("/api/v1/portal/auth/verify-email", json={"token": raw}).status_code == 400


def test_resend_is_available_to_whoever_is_waiting(client, db, portal_token, captured_emails):
    user = _make_user(db, verified=False)

    response = client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))

    assert response.status_code == 200
    assert len(captured_emails) == 1


def test_resend_stops_after_the_rate_limit(client, db, portal_token, captured_emails):
    user = _make_user(db, verified=False)

    for _ in range(auth_tokens.MAX_REQUESTS_PER_WINDOW):
        client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))

    response = client.post("/api/v1/portal/auth/resend-verification", headers=portal_token(user))
    assert response.status_code == 429


# --- recupero password -----------------------------------------------------

def test_forgot_password_answers_the_same_for_a_stranger(client, db, captured_emails):
    """
    La proprieta' che rende questo endpoint non utilizzabile come elenco di
    iscritti: stesso codice, stesso testo, indirizzo noto o no.
    """
    known = _make_user(db, email="noto@example.com")

    first = client.post("/api/v1/portal/auth/forgot-password", json={"email": known.email})
    second = client.post(
        "/api/v1/portal/auth/forgot-password", json={"email": "mai-visto@example.com"}
    )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    # Ma l'email parte solo per chi esiste davvero.
    assert [e["to_address"] for e in captured_emails] == ["noto@example.com"]


def test_reset_password_changes_the_password_and_burns_the_link(client, db):
    user = _make_user(db, password="vecchia-password")
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, _ttl())
    db.commit()

    response = client.post(
        "/api/v1/portal/auth/reset-password",
        json={"token": raw, "password": "nuova-password-lunga"},
    )
    assert response.status_code == 200

    db.refresh(user)
    assert SecurityService.verify_password("nuova-password-lunga", user.password_hash)
    assert not SecurityService.verify_password("vecchia-password", user.password_hash)

    # Riusare lo stesso link non deve piu' funzionare.
    assert (
        client.post(
            "/api/v1/portal/auth/reset-password",
            json={"token": raw, "password": "terza-password-lunga"},
        ).status_code
        == 400
    )


def test_reset_password_also_confirms_the_address(client, db):
    """
    Chi reimposta la password ha appena letto un messaggio arrivato in quella
    casella: chiedergli la stessa prova due volte lo lascerebbe bloccato fuori
    subito dopo.
    """
    user = _make_user(db, verified=False)
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, _ttl())
    db.commit()

    client.post(
        "/api/v1/portal/auth/reset-password",
        json={"token": raw, "password": "nuova-password-lunga"},
    )

    db.refresh(user)
    assert user.email_verified_at is not None


def test_reset_password_does_not_count_as_privacy_consent(client, db, portal_token):
    """
    L'email di reset non nomina privacy e termini: chi la usa non ha accettato
    niente. Un iscritto di prima della conferma che passa dal reset deve
    ritrovarsi comunque davanti alla finestra che glielo chiede.
    """
    user = _make_user(db, verified=False, retroactive=True)
    raw = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, _ttl())
    db.commit()

    client.post(
        "/api/v1/portal/auth/reset-password",
        json={"token": raw, "password": "nuova-password-lunga"},
    )

    db.refresh(user)
    assert user.email_verified_at is not None
    assert user.privacy_accepted_at is None
    assert client.get("/api/v1/portal/channels", headers=portal_token(user)).status_code == 403


def test_reset_password_closes_any_other_open_link(client, db):
    user = _make_user(db, verified=False)
    verification = auth_tokens.issue(
        db, user, auth_tokens.PURPOSE_EMAIL_VERIFICATION, _ttl()
    )
    reset = auth_tokens.issue(db, user, auth_tokens.PURPOSE_PASSWORD_RESET, _ttl())
    db.commit()

    client.post(
        "/api/v1/portal/auth/reset-password",
        json={"token": reset, "password": "nuova-password-lunga"},
    )

    assert (
        client.post("/api/v1/portal/auth/verify-email", json={"token": verification}).status_code
        == 400
    )


def test_a_suspended_account_cannot_be_recovered_by_email(client, db, captured_emails):
    """Una sospensione e' una decisione: un'email non deve poterla aggirare."""
    user = _make_user(db, email="sospeso@example.com")
    user.status = "suspended"
    db.commit()

    client.post("/api/v1/portal/auth/forgot-password", json={"email": user.email})

    assert captured_emails == []
    assert db.query(UserAuthToken).filter(UserAuthToken.user_id == user.id).count() == 0
