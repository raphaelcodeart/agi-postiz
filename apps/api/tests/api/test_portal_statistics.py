"""
Le statistiche che un promoter vede nel proprio portale.

Il modulo Statistiche e' condiviso con l'amministratore: queste pagine chiamano
gli stessi statistics_service.build_user_detail/build_channel_detail. Quello che
va verificato qui non e' quindi l'aggregazione - gia' coperta altrove - ma il
confine: il payload deve contenere i dati di chi ha in mano il token e nient'altro,
compreso quando l'id di un canale altrui viene passato a mano nell'URL.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.campaign import Campaign, CampaignTarget
from app.models.publication import Publication
from app.models.statistics import StatPostMetric, StatSyncRun
from app.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture()
def promoters(db):
    """Due promoter con un canale ciascuno e un post gia' sincronizzato.

    Numeri volutamente diversi fra i due: un filtro mancante non produrrebbe un
    errore, produrrebbe la somma - che si riconosce solo se gli addendi non si
    somigliano.
    """
    campaign = Campaign(title="Lancio autunnale", default_text="Testo", status="completed")
    db.add(campaign)
    db.flush()

    def make(name, email, platform, views, likes):
        # email_verified_at e privacy_accepted_at valorizzati: questi sono promoter che il portale lo
        # stanno gia' usando. Senza, ogni rotta risponderebbe 403 - vedi
        # get_verified_portal_user in app/api/v1/portal.py.
        user = User(
            name=name, email=email, status="active", password_hash="x",
            email_verified_at=datetime.now(timezone.utc),
            privacy_accepted_at=datetime.now(timezone.utc),
            profile_completed_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        connection = BufferConnection(
            user_id=user.id, provider="bundle_social", status="connected",
            provider_account_ref=f"team_{name}",
        )
        db.add(connection)
        db.flush()
        org = BufferOrganization(
            buffer_connection_id=connection.id, external_organization_id=f"org_{name}", name=name
        )
        db.add(org)
        db.flush()
        channel = SocialChannel(
            buffer_organization_id=org.id,
            external_channel_id=f"ext_{uuid.uuid4().hex[:8]}",
            provider="bundle_social", platform=platform,
            name=f"{name} {platform}", username=name.lower(), is_active=True,
        )
        db.add(channel)
        db.flush()
        target = CampaignTarget(
            campaign_id=campaign.id, user_id=user.id, social_channel_id=channel.id,
            resolved_text="Testo", status="created",
        )
        db.add(target)
        db.flush()
        publication = Publication(
            campaign_id=campaign.id, campaign_target_id=target.id, user_id=user.id,
            social_channel_id=channel.id, buffer_connection_id=connection.id,
            external_channel_id=channel.external_channel_id,
            status="published", idempotency_key=f"idem_{uuid.uuid4().hex}",
            external_post_id=f"post_{uuid.uuid4().hex[:8]}",
            published_at=_now() - timedelta(days=3),
        )
        db.add(publication)
        db.flush()
        db.add(
            StatPostMetric(
                publication_id=publication.id, campaign_id=campaign.id, user_id=user.id,
                social_channel_id=channel.id, buffer_connection_id=connection.id,
                platform=platform, external_post_id=publication.external_post_id,
                published_at=publication.published_at,
                views=views, likes=likes, comments=2, shares=1,
                last_synced_at=_now() - timedelta(hours=2),
            )
        )
        db.flush()
        return {"user": user, "channel": channel, "publication": publication}

    anna = make("Anna", "anna@example.test", "instagram", views=1000, likes=100)
    bruno = make("Bruno", "bruno@example.test", "tiktok", views=7, likes=3)
    db.commit()
    return {"anna": anna, "bruno": bruno, "campaign": campaign}


# --- scoping ----------------------------------------------------------------

def test_the_overview_only_counts_the_signed_in_promoters_own_posts(client, promoters, portal_token):
    response = client.get("/api/v1/portal/statistics", headers=portal_token(promoters["anna"]["user"]))
    assert response.status_code == 200

    body = response.json()
    assert body["user_name"] == "Anna"
    # 1000, non 1007: il post di Bruno non entra in questo totale.
    assert body["totals"]["views"] == 1000
    assert [c["channel_name"] for c in body["channels"]] == ["Anna instagram"]


def test_another_promoters_channel_is_not_readable_by_id(client, promoters, portal_token):
    """
    Il caso che conta: l'id del canale sta nell'URL, quindi e' l'unico parametro
    che un utente puo' cambiare a mano. build_channel_detail lo verifica contro
    la connessione dell'utente del token, percio' il canale di Bruno deve
    rispondere 404 ad Anna - indistinguibile da un canale inesistente.
    """
    response = client.get(
        f"/api/v1/portal/statistics/channels/{promoters['bruno']['channel'].id}",
        headers=portal_token(promoters["anna"]["user"]),
    )
    assert response.status_code == 404


def test_own_channel_lists_its_posts_with_the_campaign_they_belong_to(client, promoters, portal_token):
    response = client.get(
        f"/api/v1/portal/statistics/channels/{promoters['anna']['channel'].id}",
        headers=portal_token(promoters["anna"]["user"]),
    )
    assert response.status_code == 200

    body = response.json()
    assert body["channel_name"] == "Anna instagram"
    assert len(body["posts"]) == 1
    post = body["posts"][0]
    assert post["campaign_title"] == "Lancio autunnale"
    assert post["metrics"]["views"] == 1000
    assert post["publication_id"] == str(promoters["anna"]["publication"].id)


def test_statistics_require_a_session(client, promoters):
    for path in ("/api/v1/portal/statistics", "/api/v1/portal/statistics/export.xlsx"):
        assert client.get(path).status_code == 401


def test_headline_stats_expose_the_metrics_the_home_page_shows(client, promoters, portal_token):
    """follows/clicks/engagement_rate sono stati aggiunti a PortalStatsResponse
    per le tile della home: se sparissero, la home mostrerebbe caselle vuote
    senza che nulla fallisca."""
    response = client.get("/api/v1/portal/stats", headers=portal_token(promoters["anna"]["user"]))
    assert response.status_code == 200

    body = response.json()
    assert body["total_views"] == 1000
    assert body["total_follows"] == 0
    assert body["total_clicks"] == 0
    # Nessun post riporta il tasso di coinvolgimento: None, non 0.0 - "non
    # riportato" e "coinvolgimento nullo" non sono la stessa cosa.
    assert body["engagement_rate"] is None


# --- sincronizzazione self-service ------------------------------------------

@pytest.fixture()
def captured_dispatch(monkeypatch):
    """Intercetta il dispatch Celery: qui interessa cosa viene messo in coda e
    con quale scope, non che un worker giri davvero."""
    calls = []
    monkeypatch.setattr(
        "app.api.v1.portal_statistics.sync_user_statistics_task.delay",
        lambda *args: calls.append(args),
    )
    return calls


def test_sync_is_scoped_to_the_promoter_and_records_who_asked(
    client, promoters, portal_token, captured_dispatch, db
):
    anna = promoters["anna"]["user"]
    response = client.post("/api/v1/portal/statistics/sync", headers=portal_token(anna))
    assert response.status_code == 202

    run_id = response.json()["sync_run_id"]
    run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(run_id)).one()
    assert run.scope == "user"
    assert run.scope_user_id == anna.id
    # Colonna aggiunta apposta: triggered_by punta ad administrators, quindi da
    # sola non distinguerebbe un sync del promoter da uno di un admin cancellato.
    assert run.triggered_by_user_id == anna.id
    assert run.triggered_by is None
    # Il task riceve l'id dal token, mai uno arrivato dalla richiesta.
    assert captured_dispatch == [(run_id, str(anna.id))]


def test_a_second_click_joins_the_run_already_in_flight(
    client, promoters, portal_token, captured_dispatch
):
    """Una pagina ricaricata su un telefono ripreme il bottone. Senza questo,
    ogni click lascerebbe dietro di se' un run in piu' da seguire in polling."""
    headers = portal_token(promoters["anna"]["user"])
    first = client.post("/api/v1/portal/statistics/sync", headers=headers)
    second = client.post("/api/v1/portal/statistics/sync", headers=headers)

    assert second.json()["sync_run_id"] == first.json()["sync_run_id"]
    assert len(captured_dispatch) == 1


def test_a_finished_run_does_not_block_a_new_one(
    client, promoters, portal_token, captured_dispatch, db
):
    headers = portal_token(promoters["anna"]["user"])
    first = client.post("/api/v1/portal/statistics/sync", headers=headers)

    run = db.query(StatSyncRun).filter(StatSyncRun.id == uuid.UUID(first.json()["sync_run_id"])).one()
    run.status = "completed"
    db.commit()

    second = client.post("/api/v1/portal/statistics/sync", headers=headers)
    assert second.json()["sync_run_id"] != first.json()["sync_run_id"]
    assert len(captured_dispatch) == 2


def test_another_promoters_sync_run_is_not_readable(
    client, promoters, portal_token, captured_dispatch
):
    bruno_run = client.post(
        "/api/v1/portal/statistics/sync", headers=portal_token(promoters["bruno"]["user"])
    ).json()["sync_run_id"]

    response = client.get(
        f"/api/v1/portal/statistics/sync/{bruno_run}",
        headers=portal_token(promoters["anna"]["user"]),
    )
    assert response.status_code == 404


# --- export -----------------------------------------------------------------

def test_export_returns_a_spreadsheet_named_after_the_promoter(client, promoters, portal_token):
    response = client.get(
        "/api/v1/portal/statistics/export.xlsx", headers=portal_token(promoters["anna"]["user"])
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert response.headers["content-disposition"] == 'attachment; filename="statistiche-anna.xlsx"'
    # PK\x03\x04: un .xlsx e' uno zip, quindi questo dice che il file e' davvero
    # un foglio e non un messaggio d'errore servito con l'header giusto.
    assert response.content[:4] == b"PK\x03\x04"


def test_channel_export_refuses_a_channel_that_is_not_the_promoters(client, promoters, portal_token):
    response = client.get(
        f"/api/v1/portal/statistics/channels/{promoters['bruno']['channel'].id}/export.xlsx",
        headers=portal_token(promoters["anna"]["user"]),
    )
    assert response.status_code == 404
