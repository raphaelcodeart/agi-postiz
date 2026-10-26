"""
Requisito "almeno due canali social" visto dall'amministratore.

Tre cose devono reggere, e nessuna si verifica guardando una funzione sola:

1. Conta solo quello che una campagna userebbe davvero. Due canali di cui uno
   spento, o appesi a una connessione scollegata, non sono due canali: chi li
   ha deve comparire nella lista.
2. Ogni avviso lascia traccia. La pagina mostra quando e quante volte una
   persona e' stata avvisata, e "Notifica a tutti" salta chi l'ha gia'
   ricevuto da poco - a meno che l'amministratore non chieda il contrario.
3. Senza SMTP configurato non parte niente e non si registra niente: un
   avviso "inviato" che nessuno ha ricevuto sarebbe peggio di nessun avviso.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.administrator import Administrator
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.user import User
from app.models.user_notification import KIND_CHANNEL_REQUIREMENT, UserNotification


@pytest.fixture()
def admin(db):
    row = Administrator(email=f"admin-{uuid.uuid4().hex[:6]}@example.com", password_hash="x", full_name="Admin")
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def captured_emails(monkeypatch):
    """Intercetta ``.delay`` del task: tutto quello che sta prima resta sotto test."""
    from app.tasks import email as email_task

    sent = []

    class _Stub:
        @staticmethod
        def delay(**kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(email_task, "send_transactional_email", _Stub)
    return sent


@pytest.fixture()
def email_on(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "noreply@test.example")


@pytest.fixture()
def email_off(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "")


def _make_user(db, name, *, channels=(), status="active", connection_status="connected", password=True):
    """``channels`` e' una lista di (piattaforma, is_active, publication_mode)."""
    user = User(
        name=name,
        email=f"{name.lower().replace(' ', '.')}-{uuid.uuid4().hex[:6]}@example.com",
        status=status,
        password_hash="x" if password else None,
    )
    db.add(user)
    db.flush()
    if channels:
        connection = BufferConnection(
            user_id=user.id, provider="bundle_social", status=connection_status,
            provider_account_ref=f"team_{uuid.uuid4().hex[:6]}",
        )
        db.add(connection)
        db.flush()
        org = BufferOrganization(
            buffer_connection_id=connection.id, external_organization_id=f"org_{uuid.uuid4().hex[:6]}", name=name
        )
        db.add(org)
        db.flush()
        for platform, is_active, mode in channels:
            db.add(SocialChannel(
                buffer_organization_id=org.id,
                external_channel_id=f"ext_{uuid.uuid4().hex[:8]}",
                provider="bundle_social", platform=platform,
                name=f"{name} {platform}", is_active=is_active, publication_mode=mode,
            ))
    db.commit()
    return user


OK = ("instagram", True, "automatic")


# --- la lista -----------------------------------------------------------------

def test_only_users_with_fewer_usable_channels_than_required_are_listed(client, db, admin, admin_token):
    complete = _make_user(db, "Anna Completa", channels=[OK, ("facebook", True, "automatic")])
    one = _make_user(db, "Bruno Uno", channels=[OK])
    none = _make_user(db, "Carla Zero")
    half_dead = _make_user(db, "Dario Spento", channels=[OK, ("facebook", False, "automatic")])
    disabled_mode = _make_user(db, "Elena Disabilitata", channels=[OK, ("facebook", True, "disabled")])
    disconnected = _make_user(db, "Fabio Scollegato", channels=[OK, OK], connection_status="disconnected")
    removed = _make_user(db, "Gina Rimossa", channels=[OK, OK])
    second = list(removed.buffer_connections[0].organizations[0].channels)[1]
    second.deleted_at = datetime.now(timezone.utc)
    db.commit()

    response = client.get("/api/v1/users/channel-requirement", headers=admin_token(admin))
    assert response.status_code == 200, response.text
    body = response.json()

    listed = {row["id"]: row for row in body["users"]}
    assert str(complete.id) not in listed
    for user in (one, none, half_dead, disabled_mode, disconnected, removed):
        assert str(user.id) in listed, user.name

    assert body["required_channels"] == settings.MIN_SOCIAL_CHANNELS_PER_USER
    assert listed[str(none.id)]["connected_channels_count"] == 0
    assert listed[str(one.id)]["connected_channels_count"] == 1
    assert listed[str(one.id)]["connected_channels"] == [{"platform": "instagram", "name": "Bruno Uno instagram"}]
    assert listed[str(disconnected.id)]["connected_channels_count"] == 0
    assert listed[str(removed.id)]["connected_channels_count"] == 1

    # Prima chi non ha nessun canale, poi gli altri, ciascun gruppo per nome.
    counts = [row["connected_channels_count"] for row in body["users"]]
    assert counts == sorted(counts)
    assert body["without_channels"] == 2  # Carla Zero e Fabio Scollegato: nessun canale utilizzabile
    assert body["never_notified"] == body["total"] == 6


def test_status_filter_and_search_narrow_the_list(client, db, admin, admin_token):
    _make_user(db, "Attivo Senza")
    suspended = _make_user(db, "Sospeso Senza", status="suspended")

    response = client.get(
        "/api/v1/users/channel-requirement", params={"status_filter": "active"}, headers=admin_token(admin)
    )
    ids = {row["id"] for row in response.json()["users"]}
    assert str(suspended.id) not in ids

    response = client.get(
        "/api/v1/users/channel-requirement", params={"search": "sospeso"}, headers=admin_token(admin)
    )
    assert [row["id"] for row in response.json()["users"]] == [str(suspended.id)]


def test_summary_counts_active_users_below_requirement(client, db, admin, admin_token):
    _make_user(db, "Anna Completa", channels=[OK, OK])
    _make_user(db, "Bruno Uno", channels=[OK])
    _make_user(db, "Carla Inattiva", status="inactive")

    response = client.get("/api/v1/users/summary", headers=admin_token(admin))
    assert response.status_code == 200
    assert response.json()["below_channel_requirement"] == 1


def test_requires_an_administrator(client, db):
    assert client.get("/api/v1/users/channel-requirement").status_code == 401


# --- avviso singolo ---------------------------------------------------------

def test_notifying_one_user_queues_the_email_and_records_it(
    client, db, admin, admin_token, captured_emails, email_on
):
    user = _make_user(db, "Bruno Uno", channels=[OK])

    response = client.post(f"/api/v1/users/{user.id}/channel-requirement/notify", headers=admin_token(admin))
    assert response.status_code == 200, response.text
    assert response.json()["notifications_count"] == 1
    assert response.json()["email"] == user.email

    assert len(captured_emails) == 1
    email = captured_emails[0]
    assert email["to_address"] == user.email
    assert "AGI Post" in email["subject"]
    assert f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/channels" in email["html_body"]
    assert f"{settings.PORTAL_PUBLIC_BASE_URL}/portal/channels" in email["text_body"]
    assert "Bruno Uno instagram" in email["html_body"]

    notices = db.query(UserNotification).filter(UserNotification.user_id == user.id).all()
    assert len(notices) == 1
    assert notices[0].kind == KIND_CHANNEL_REQUIREMENT
    assert notices[0].sent_by_administrator_id == admin.id
    assert notices[0].metadata_json["connected_channels"] == 1

    listed = client.get("/api/v1/users/channel-requirement", headers=admin_token(admin)).json()
    row = next(r for r in listed["users"] if r["id"] == str(user.id))
    assert row["notifications_count"] == 1
    assert row["last_notified_at"] is not None


def test_single_notice_has_no_cooldown(client, db, admin, admin_token, captured_emails, email_on):
    user = _make_user(db, "Carla Zero")
    for _ in range(2):
        assert client.post(
            f"/api/v1/users/{user.id}/channel-requirement/notify", headers=admin_token(admin)
        ).status_code == 200
    assert len(captured_emails) == 2


def test_notice_for_unknown_user_is_404(client, db, admin, admin_token, captured_emails, email_on):
    response = client.post(f"/api/v1/users/{uuid.uuid4()}/channel-requirement/notify", headers=admin_token(admin))
    assert response.status_code == 404
    assert captured_emails == []


# --- avviso a tutti ---------------------------------------------------------

def test_notify_all_skips_recently_notified_users(client, db, admin, admin_token, captured_emails, email_on):
    fresh = _make_user(db, "Bruno Uno", channels=[OK])
    recent = _make_user(db, "Carla Zero")
    stale = _make_user(db, "Dario Vecchio")
    _make_user(db, "Anna Completa", channels=[OK, OK])
    _make_user(db, "Elena Sospesa", status="suspended")

    now = datetime.now(timezone.utc)
    db.add(UserNotification(user_id=recent.id, kind=KIND_CHANNEL_REQUIREMENT, email=recent.email, sent_at=now - timedelta(days=1)))
    db.add(UserNotification(user_id=stale.id, kind=KIND_CHANNEL_REQUIREMENT, email=stale.email, sent_at=now - timedelta(days=30)))
    db.commit()

    response = client.post(
        "/api/v1/users/channel-requirement/notify-all", json={}, headers=admin_token(admin)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] == 2
    assert body["skipped_recent"] == 1
    assert body["failed"] == 0
    assert set(body["sent_user_ids"]) == {str(fresh.id), str(stale.id)}
    assert {e["to_address"] for e in captured_emails} == {fresh.email, stale.email}


def test_notify_all_without_cooldown_reaches_everyone(client, db, admin, admin_token, captured_emails, email_on):
    recent = _make_user(db, "Carla Zero")
    db.add(UserNotification(user_id=recent.id, kind=KIND_CHANNEL_REQUIREMENT, email=recent.email))
    db.commit()

    response = client.post(
        "/api/v1/users/channel-requirement/notify-all",
        json={"skip_notified_within_days": 0},
        headers=admin_token(admin),
    )
    assert response.json()["sent"] == 1
    assert response.json()["skipped_recent"] == 0


# --- SMTP non configurato ---------------------------------------------------

def test_without_smtp_nothing_is_sent_or_recorded(client, db, admin, admin_token, captured_emails, email_off):
    user = _make_user(db, "Carla Zero")

    listed = client.get("/api/v1/users/channel-requirement", headers=admin_token(admin)).json()
    assert listed["email_enabled"] is False

    single = client.post(f"/api/v1/users/{user.id}/channel-requirement/notify", headers=admin_token(admin))
    everyone = client.post("/api/v1/users/channel-requirement/notify-all", json={}, headers=admin_token(admin))
    assert single.status_code == 503
    assert everyone.status_code == 503
    assert captured_emails == []
    assert db.query(UserNotification).count() == 0
