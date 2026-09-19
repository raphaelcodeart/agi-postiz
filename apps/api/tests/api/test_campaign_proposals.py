"""
Proposte di campagna: cosa un promoter puo' fare, e soprattutto cosa non puo'.

La regola che questo modulo esiste per proteggere e' una sola, ed e' quella che
il cliente ha chiesto a parole: *la campagna vera la lancia sempre e solo
l'amministratore*. Tutto il resto qui sotto sono i modi in cui quella regola
potrebbe rompersi - un promoter che pubblica, uno che legge le proposte di un
altro, una proposta che risulta approvata senza che nessuna campagna esista.
"""
import uuid

import pytest

from app.models.administrator import Administrator
from app.models.campaign import Campaign
from app.models.campaign_proposal import CampaignProposal
from app.models.media import MediaFile
from app.models.user import User


@pytest.fixture()
def people(db):
    anna = User(name="Anna", email="anna@proposte.test", status="active", password_hash="x")
    bruno = User(name="Bruno", email="bruno@proposte.test", status="active", password_hash="x")
    admin = Administrator(
        email="admin@proposte.test", password_hash="x", full_name="Amministratore", is_active=True
    )
    db.add_all([anna, bruno, admin])
    db.commit()
    return {"anna": anna, "bruno": bruno, "admin": admin}


def _proposal(db, user, **overrides):
    data = {
        "user_id": user.id,
        "title": "Video sul prodotto nuovo",
        "default_text": "Ho girato un video, secondo me funziona.",
        "status": CampaignProposal.STATUS_DRAFT,
    }
    data.update(overrides)
    proposal = CampaignProposal(**data)
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def _media(db, user_id=None):
    media = MediaFile(
        original_filename="video.mp4", stored_filename="v.mp4", storage_key="/s/v.mp4",
        public_url="https://cdn.test/v.mp4", mime_type="video/mp4", size_bytes=1024,
        uploaded_by_user_id=user_id,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


# --- il confine fra promoter ------------------------------------------------

def test_a_promoter_only_sees_their_own_proposals(client, db, people, portal_token):
    _proposal(db, people["anna"], title="Idea di Anna")
    _proposal(db, people["bruno"], title="Idea di Bruno")

    response = client.get("/api/v1/portal/proposals", headers=portal_token(people["anna"]))
    assert response.status_code == 200
    assert [p["title"] for p in response.json()] == ["Idea di Anna"]


def test_another_promoters_proposal_is_not_readable_or_editable(client, db, people, portal_token):
    bruno_proposal = _proposal(db, people["bruno"])
    anna = portal_token(people["anna"])

    assert client.get(f"/api/v1/portal/proposals/{bruno_proposal.id}", headers=anna).status_code == 404
    assert client.patch(
        f"/api/v1/portal/proposals/{bruno_proposal.id}", json={"title": "Dirottata"}, headers=anna
    ).status_code == 404
    assert client.delete(f"/api/v1/portal/proposals/{bruno_proposal.id}", headers=anna).status_code == 404


def test_a_promoter_cannot_attach_media_they_did_not_upload(client, db, people, portal_token):
    """
    La libreria media e' condivisa con l'amministratore. Senza questo controllo
    bastava indovinare un UUID per farsi restituire, nella propria proposta,
    l'URL di un file non proprio.
    """
    admin_media = _media(db, user_id=None)
    bruno_media = _media(db, user_id=people["bruno"].id)

    for media in (admin_media, bruno_media):
        response = client.post(
            "/api/v1/portal/proposals",
            json={"title": "Prova", "default_text": "Testo", "media_file_id": str(media.id)},
            headers=portal_token(people["anna"]),
        )
        assert response.status_code == 404

    own = _media(db, user_id=people["anna"].id)
    ok = client.post(
        "/api/v1/portal/proposals",
        json={"title": "Prova", "default_text": "Testo", "media_file_id": str(own.id)},
        headers=portal_token(people["anna"]),
    )
    assert ok.status_code == 201
    assert ok.json()["media_url"] == "https://cdn.test/v.mp4"


# --- il ciclo di vita -------------------------------------------------------

def test_a_proposal_can_be_saved_as_a_draft_or_sent_straight_away(client, people, portal_token):
    headers = portal_token(people["anna"])

    draft = client.post(
        "/api/v1/portal/proposals", json={"title": "Bozza", "default_text": "T"}, headers=headers
    ).json()
    sent = client.post(
        "/api/v1/portal/proposals",
        json={"title": "Consegnata", "default_text": "T", "submit": True},
        headers=headers,
    ).json()

    assert draft["status"] == "draft"
    assert draft["submitted_at"] is None
    assert sent["status"] == "submitted"
    assert sent["submitted_at"] is not None


def test_a_submitted_proposal_is_frozen_for_its_author(client, db, people, portal_token):
    """
    Cambiarla dopo la consegna significherebbe far approvare all'amministratore
    un testo diverso da quello che ha letto.
    """
    proposal = _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)
    headers = portal_token(people["anna"])

    assert client.patch(
        f"/api/v1/portal/proposals/{proposal.id}", json={"default_text": "Altro"}, headers=headers
    ).status_code == 409
    assert client.delete(f"/api/v1/portal/proposals/{proposal.id}", headers=headers).status_code == 409


def test_editing_only_touches_the_fields_that_were_sent(client, db, people, portal_token):
    """Salvare il solo titolo non deve svuotare le note ne' staccare il video."""
    media = _media(db, user_id=people["anna"].id)
    proposal = _proposal(db, people["anna"], notes="Il video dura 30 secondi", media_file_id=media.id)

    body = client.patch(
        f"/api/v1/portal/proposals/{proposal.id}",
        json={"title": "Titolo migliore"},
        headers=portal_token(people["anna"]),
    ).json()

    assert body["title"] == "Titolo migliore"
    assert body["notes"] == "Il video dura 30 secondi"
    assert body["media_file_id"] == str(media.id)


def test_a_proposal_can_ask_for_a_custom_video_and_name_its_platforms(client, people, portal_token):
    """
    Chi non sa girare il video lo chiede ad AGI Post e dice su quali social
    vorrebbe uscire; l'amministratore ritrova entrambe le cose nella proposta.
    """
    headers = portal_token(people["anna"])

    created = client.post(
        "/api/v1/portal/proposals",
        json={
            "title": "Video su misura",
            "default_text": "T",
            "video_request": "Un reel di 20 secondi sul prodotto, stile ironico.",
            "target_platforms": ["instagram", "tiktok", "instagram"],
        },
        headers=headers,
    ).json()

    assert created["video_request"] == "Un reel di 20 secondi sul prodotto, stile ironico."
    assert created["target_platforms"] == ["instagram", "tiktok"]

    cleared = client.patch(
        f"/api/v1/portal/proposals/{created['id']}",
        json={"video_request": None, "target_platforms": None},
        headers=headers,
    ).json()
    assert cleared["video_request"] is None
    assert cleared["target_platforms"] == []

    assert client.post(
        "/api/v1/portal/proposals",
        json={"title": "Social inesistente", "default_text": "T", "target_platforms": ["myspace"]},
        headers=headers,
    ).status_code == 422


# --- il lato amministratore -------------------------------------------------

def test_the_administrator_never_sees_unfinished_drafts(client, db, people, admin_token):
    """Una bozza sono appunti che il promoter sta ancora scrivendo: nessuno
    gliel'ha mandata."""
    _proposal(db, people["anna"], title="Ancora da finire")
    _proposal(db, people["bruno"], title="Consegnata", status=CampaignProposal.STATUS_SUBMITTED)

    body = client.get("/api/v1/campaign-proposals/", headers=admin_token(people["admin"])).json()
    assert [p["title"] for p in body] == ["Consegnata"]
    assert body[0]["user_name"] == "Bruno"


def test_the_pending_counter_only_counts_what_awaits_a_decision(client, db, people, admin_token):
    _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)
    _proposal(db, people["anna"], status=CampaignProposal.STATUS_REJECTED)
    _proposal(db, people["bruno"])  # bozza, invisibile

    body = client.get("/api/v1/campaign-proposals/summary", headers=admin_token(people["admin"])).json()
    assert body["by_status"]["submitted"] == 1
    assert body["by_status"]["rejected"] == 1
    assert "draft" not in body["by_status"]


def test_a_rejection_carries_a_reason_and_reopens_the_proposal(client, db, people, admin_token, portal_token):
    proposal = _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)

    rejected = client.post(
        f"/api/v1/campaign-proposals/{proposal.id}/reject",
        json={"review_notes": "Il video è troppo lungo per Instagram."},
        headers=admin_token(people["admin"]),
    ).json()
    assert rejected["status"] == "rejected"
    assert rejected["review_notes"] == "Il video è troppo lungo per Instagram."

    # Torna modificabile: un rifiuto che non lascia correggere è un vicolo cieco.
    fixed = client.patch(
        f"/api/v1/portal/proposals/{proposal.id}",
        json={"default_text": "Versione più corta"},
        headers=portal_token(people["anna"]),
    )
    assert fixed.status_code == 200

    resubmitted = client.post(
        f"/api/v1/portal/proposals/{proposal.id}/submit", headers=portal_token(people["anna"])
    ).json()
    # Il motivo del vecchio rifiuto non deve restare accanto a un testo cambiato:
    # l'amministratore leggerebbe una critica che non riguarda più ciò che ha davanti.
    assert resubmitted["status"] == "submitted"
    assert resubmitted["review_notes"] is None


# --- approvazione = creazione della campagna --------------------------------

def _campaign_payload(**overrides):
    payload = {
        "title": "Campagna dalla proposta",
        "default_text": "Testo proposto dal promoter",
        "targeting_mode": "all_active_channels",
        "publishing_mode": "immediate",
    }
    payload.update(overrides)
    return payload


def test_approving_is_creating_the_campaign_and_both_happen_together(client, db, people, admin_token):
    proposal = _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)

    created = client.post(
        "/api/v1/campaigns/",
        json=_campaign_payload(proposal_id=str(proposal.id)),
        headers=admin_token(people["admin"]),
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]

    db.refresh(proposal)
    assert proposal.status == "approved"
    assert str(proposal.campaign_id) == campaign_id
    assert proposal.reviewed_by == people["admin"].id
    # La campagna nasce in bozza come qualunque altra: destinatari, date e
    # lancio restano passaggi dell'amministratore.
    assert db.query(Campaign).filter(Campaign.id == uuid.UUID(campaign_id)).one().status == "draft"


def test_the_same_proposal_cannot_be_turned_into_two_campaigns(client, db, people, admin_token):
    proposal = _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)
    headers = admin_token(people["admin"])

    first = client.post("/api/v1/campaigns/", json=_campaign_payload(proposal_id=str(proposal.id)), headers=headers)
    second = client.post("/api/v1/campaigns/", json=_campaign_payload(proposal_id=str(proposal.id)), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409


def test_a_draft_proposal_cannot_be_approved(client, db, people, admin_token):
    """Non è stata consegnata a nessuno: approvarla vorrebbe dire pubblicare
    appunti che il promoter sta ancora scrivendo."""
    proposal = _proposal(db, people["anna"])

    response = client.post(
        "/api/v1/campaigns/",
        json=_campaign_payload(proposal_id=str(proposal.id)),
        headers=admin_token(people["admin"]),
    )
    assert response.status_code == 409
    db.refresh(proposal)
    assert proposal.status == "draft"


def test_a_failed_campaign_creation_leaves_the_proposal_untouched(client, db, people, admin_token):
    """
    L'atomicità nel verso opposto: se la campagna non nasce, la proposta non
    deve risultare approvata. Qui il media inesistente fa fallire la creazione
    prima ancora di toccare la proposta.
    """
    proposal = _proposal(db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED)

    response = client.post(
        "/api/v1/campaigns/",
        json=_campaign_payload(proposal_id=str(proposal.id), media_file_id=str(uuid.uuid4())),
        headers=admin_token(people["admin"]),
    )
    assert response.status_code == 404
    db.refresh(proposal)
    assert proposal.status == "submitted"
    assert proposal.campaign_id is None


def test_an_approved_proposal_can_no_longer_be_rejected(client, db, people, admin_token):
    proposal = _proposal(
        db, people["anna"], status=CampaignProposal.STATUS_SUBMITTED
    )
    headers = admin_token(people["admin"])
    client.post("/api/v1/campaigns/", json=_campaign_payload(proposal_id=str(proposal.id)), headers=headers)

    response = client.post(
        f"/api/v1/campaign-proposals/{proposal.id}/reject",
        json={"review_notes": "Ci ho ripensato"},
        headers=headers,
    )
    assert response.status_code == 409


# --- nessuna scorciatoia verso la pubblicazione -----------------------------

def test_a_promoter_token_cannot_reach_the_campaign_endpoints(client, people, portal_token):
    """
    La riga di fondo di tutta la funzionalità: un promoter propone, non lancia.
    Il token del portale non è accettato dall'audience admin (vedi
    test_portal_auth.py), quindi nessuno dei due endpoint che creano o lanciano
    una campagna gli risponde.
    """
    headers = portal_token(people["anna"])
    assert client.post("/api/v1/campaigns/", json=_campaign_payload(), headers=headers).status_code == 401
    assert client.get("/api/v1/campaign-proposals/", headers=headers).status_code == 401
