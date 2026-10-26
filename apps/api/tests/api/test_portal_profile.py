"""
La finestra obbligatoria del primo accesso: citta', CAP e gruppi.

Il blocco che conta e' nell'API, non nel browser: un utente con l'indirizzo
confermato ma il profilo vuoto deve trovare chiuso tutto il portale tranne le
due rotte che servono a compilarlo. E la compilazione deve lasciare l'utente
dentro i gruppi che ha scelto - sono gli stessi gruppi che il targeting delle
campagne usa, ed e' per questo che glieli chiediamo.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.user import User, UserGroup


def _make_user(db, *, verified=True, completed=False):
    now = datetime.now(timezone.utc)
    user = User(
        name="Giulia Promoter",
        email=f"giulia-{uuid.uuid4().hex[:6]}@example.com",
        status="active",
        password_hash="x",
        email_verified_at=now if verified else None,
        privacy_accepted_at=now if verified else None,
        profile_completed_at=now if completed else None,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def groups(db):
    rows = [
        UserGroup(name=f"Nord {uuid.uuid4().hex[:4]}", description="Promoter del nord"),
        UserGroup(name=f"Sud {uuid.uuid4().hex[:4]}", description=None),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def test_incomplete_profile_closes_the_portal_but_not_the_two_rooms_needed_to_fill_it(
    client, db, portal_token, groups
):
    user = _make_user(db)
    headers = portal_token(user)

    me = client.get("/api/v1/portal/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["profile_completed"] is False
    assert me.json()["group_ids"] == []

    closed = client.get("/api/v1/portal/channels", headers=headers)
    assert closed.status_code == 403
    assert closed.json()["detail"] == "profile_incomplete"

    listed = client.get("/api/v1/portal/groups", headers=headers)
    assert listed.status_code == 200
    names = {g["name"] for g in listed.json()}
    assert {groups[0].name, groups[1].name} <= names


def test_saving_the_profile_puts_the_user_in_the_chosen_groups_and_opens_the_portal(
    client, db, portal_token, groups
):
    user = _make_user(db)
    headers = portal_token(user)

    response = client.post(
        "/api/v1/portal/profile",
        json={"city": "  Torino ", "postal_code": "10121", "group_ids": [str(groups[0].id)]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile_completed"] is True
    assert body["city"] == "Torino"
    assert body["postal_code"] == "10121"
    assert body["group_ids"] == [str(groups[0].id)]

    db.refresh(user)
    assert [g.id for g in user.groups] == [groups[0].id]
    assert user.profile_completed_at is not None
    first_completion = user.profile_completed_at

    assert client.get("/api/v1/portal/channels", headers=headers).status_code == 200

    # Una seconda compilazione sostituisce i gruppi e non sposta la data.
    again = client.post(
        "/api/v1/portal/profile",
        json={"city": "Torino", "postal_code": "10121", "group_ids": [str(groups[1].id)]},
        headers=headers,
    )
    assert again.status_code == 200
    db.refresh(user)
    assert [g.id for g in user.groups] == [groups[1].id]
    assert user.profile_completed_at == first_completion


@pytest.mark.parametrize(
    "payload",
    [
        {"city": "Torino", "postal_code": "10121", "group_ids": []},
        {"city": "T", "postal_code": "10121", "group_ids": ["__group__"]},
        {"city": "Torino", "postal_code": "1", "group_ids": ["__group__"]},
        {"city": "Torino", "postal_code": "10121"},
    ],
)
def test_half_profiles_are_refused(client, db, portal_token, groups, payload):
    user = _make_user(db)
    if payload.get("group_ids") == ["__group__"]:
        payload["group_ids"] = [str(groups[0].id)]

    response = client.post("/api/v1/portal/profile", json=payload, headers=portal_token(user))
    assert response.status_code == 422
    db.refresh(user)
    assert user.profile_completed_at is None


def test_an_unknown_group_is_an_error_not_a_partial_save(client, db, portal_token, groups):
    user = _make_user(db)
    response = client.post(
        "/api/v1/portal/profile",
        json={"city": "Torino", "postal_code": "10121", "group_ids": [str(groups[0].id), str(uuid.uuid4())]},
        headers=portal_token(user),
    )
    assert response.status_code == 422
    db.refresh(user)
    assert user.groups == []
    assert user.profile_completed_at is None


def test_the_profile_waits_for_the_email_confirmation(client, db, portal_token, groups):
    user = _make_user(db, verified=False)
    headers = portal_token(user)
    for call in (
        lambda: client.get("/api/v1/portal/groups", headers=headers),
        lambda: client.post(
            "/api/v1/portal/profile",
            json={"city": "Torino", "postal_code": "10121", "group_ids": [str(groups[0].id)]},
            headers=headers,
        ),
    ):
        response = call()
        assert response.status_code == 403
        assert response.json()["detail"] == "email_not_verified"


def test_a_completed_profile_is_reported_to_the_administration(client, db, admin_token, groups):
    from app.models.administrator import Administrator

    admin = Administrator(email=f"admin-{uuid.uuid4().hex[:6]}@example.com", password_hash="x", full_name="Admin")
    db.add(admin)
    user = _make_user(db, completed=True)
    user.city = "Bari"
    user.postal_code = "70121"
    db.commit()

    response = client.get(f"/api/v1/users/{user.id}", headers=admin_token(admin))
    assert response.status_code == 200
    assert response.json()["city"] == "Bari"
    assert response.json()["postal_code"] == "70121"
    assert response.json()["profile_completed_at"] is not None
