"""
Knowledge Base via HTTP: caricamento di file, istruzioni, prova della ricerca.

Il caricamento passa dall'API vera perche' e' li' che si decide cosa vede
l'operatore: un file illeggibile deve tornare indietro con il motivo, non
risultare "caricato" e lasciare il bot senza informazioni.
"""
import io
import uuid

import pytest

from app.integrations.omnichannel import knowledge


@pytest.fixture()
def admin(db):
    from app.models.administrator import Administrator

    admin = Administrator(email=f"kb-api-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", full_name="KB", is_active=True)
    db.add(admin)
    db.commit()
    return admin


@pytest.fixture(autouse=True)
def no_worker(monkeypatch):
    """Gli embedding li calcola il worker: nei test non c'e' coda, si registra solo la richiesta."""
    queued = []
    from app.api.v1 import omnichannel

    monkeypatch.setattr(omnichannel, "_queue_embedding", lambda document_id: queued.append(document_id))
    return queued


BASE = "/api/v1/omnichannel-responder/knowledge-base"


def _create_company(client, admin, admin_token, name, **fields):
    response = client.post(f"{BASE}/companies", headers=admin_token(admin), json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_un_csv_caricato_diventa_cercabile_subito(client, admin, admin_token, no_worker):
    csv_data = "Prodotto;Prezzo\nCrema viso;19 euro\nSiero notte;29 euro\n".encode()
    company = _create_company(client, admin, admin_token, "  Beauty Srl ")
    no_worker.clear()

    response = client.post(
        f"{BASE}/upload", headers=admin_token(admin),
        files={"file": ("listino_primavera.csv", io.BytesIO(csv_data), "text/csv")},
        data={"company_id": company["id"]},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "listino primavera"
    assert body["company"] == "Beauty Srl"
    assert body["source_type"] == "csv"
    assert body["chunk_count"] >= 1
    assert no_worker == [uuid.UUID(body["id"])]

    search = client.post(f"{BASE}/search", headers=admin_token(admin), json={"query": "quanto costa il siero?"})
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits and "Siero notte" in hits[0]["content"]


def test_un_file_non_supportato_torna_indietro_con_il_motivo(client, admin, admin_token):
    response = client.post(
        f"{BASE}/upload", headers=admin_token(admin),
        files={"file": ("foto.png", io.BytesIO(b"\x89PNG"), "image/png")},
    )

    assert response.status_code == 422
    assert "foto.png" in response.json()["detail"]


def test_un_istruzione_si_salva_e_si_puo_rendere_sempre_attiva(client, admin, admin_token):
    created = client.post(BASE, headers=admin_token(admin), json={
        "title": "Tono con i clienti", "content_text": "Dai sempre del tu e usa frasi brevi.",
        "kind": "instruction", "always_on": True,
    })
    assert created.status_code == 201, created.text
    assert created.json()["always_on"] is True

    stats = client.get(f"{BASE}/stats", headers=admin_token(admin)).json()
    assert stats["instructions"] == 1 and stats["always_on_instructions"] == 1


def test_sempre_attiva_vale_solo_per_le_istruzioni(client, admin, admin_token):
    """Un documento lungo sempre nel prompt costerebbe token a ogni risposta."""
    created = client.post(BASE, headers=admin_token(admin), json={
        "title": "Catalogo", "content_text": "Tanti prodotti.", "kind": "document", "always_on": True,
    })

    assert created.json()["always_on"] is False


def test_modificare_un_documento_rigenera_i_blocchi(client, admin, admin_token, db):
    from app.models.omnichannel import OmniKnowledgeChunk

    company = _create_company(client, admin, admin_token, "Negozio Centro")
    created = client.post(BASE, headers=admin_token(admin), json={"title": "Orari", "content_text": "Aperti dalle 9."}).json()
    updated = client.put(f"{BASE}/{created['id']}", headers=admin_token(admin), json={"content_text": "Aperti dalle 10 alle 19.", "company_id": company["id"]})

    assert updated.status_code == 200, updated.text
    chunks = db.query(OmniKnowledgeChunk).filter(OmniKnowledgeChunk.document_id == uuid.UUID(created["id"])).all()
    assert [c.content for c in chunks] == ["Aperti dalle 10 alle 19."]
    assert chunks[0].heading == "Azienda: Negozio Centro | Documento: Orari"


def test_il_contenuto_vuoto_e_rifiutato(client, admin, admin_token):
    response = client.post(BASE, headers=admin_token(admin), json={"title": "Vuoto", "content_text": "   "})

    assert response.status_code == 422


def test_non_si_modificano_documenti_di_altri(client, admin, admin_token, db):
    from app.models.administrator import Administrator

    other = Administrator(email="altro-kb@test.local", password_hash="x", full_name="Altro", is_active=True)
    db.add(other)
    db.commit()
    created = client.post(BASE, headers=admin_token(other), json={"title": "Suo", "content_text": "Riservato."}).json()

    response = client.put(f"{BASE}/{created['id']}", headers=admin_token(admin), json={"title": "Mio"})

    assert response.status_code == 404


def test_l_elenco_si_filtra_per_azienda_e_non_trasporta_il_testo_intero(client, admin, admin_token):
    rossi = _create_company(client, admin, admin_token, "Bottega Rossi", phone="055 123")
    lungo = "Listino completo. " * 200
    client.post(BASE, headers=admin_token(admin), json={"title": "Listino Rossi", "content_text": lungo, "company_id": rossi["id"]})
    client.post(BASE, headers=admin_token(admin), json={"title": "Regole generali", "content_text": "Rispondi sempre con cortesia."})

    solo_rossi = client.get(BASE, headers=admin_token(admin), params={"company": rossi["id"]}).json()
    senza = client.get(BASE, headers=admin_token(admin), params={"company": "none"}).json()

    assert [d["title"] for d in solo_rossi] == ["Listino Rossi"], "la scheda azienda non compare nell'elenco"
    assert solo_rossi[0]["content_text"] is None and len(solo_rossi[0]["preview"]) <= 300
    assert [d["title"] for d in senza] == ["Regole generali"]
    full = client.get(f"{BASE}/{solo_rossi[0]['id']}", headers=admin_token(admin)).json()
    assert full["content_text"] == lungo

    companies = client.get(f"{BASE}/companies", headers=admin_token(admin)).json()
    assert companies[0]["name"] == "Bottega Rossi" and companies[0]["document_count"] == 1


def test_il_nome_azienda_e_unico_senza_badare_alle_maiuscole(client, admin, admin_token):
    _create_company(client, admin, admin_token, "Bottega Rossi")

    response = client.post(f"{BASE}/companies", headers=admin_token(admin), json={"name": "bottega rossi"})

    assert response.status_code == 409


def test_rinominare_l_azienda_aggiorna_le_intestazioni_dei_blocchi(client, admin, admin_token, db, no_worker):
    from app.models.omnichannel import OmniKnowledgeChunk

    company = _create_company(client, admin, admin_token, "Rossi")
    doc = client.post(BASE, headers=admin_token(admin), json={"title": "Orari", "content_text": "Aperti dalle 9.", "company_id": company["id"]}).json()

    response = client.put(f"{BASE}/companies/{company['id']}", headers=admin_token(admin), json={"name": "Bottega Rossi"})

    assert response.status_code == 200, response.text
    db.expire_all()
    chunk = db.query(OmniKnowledgeChunk).filter(OmniKnowledgeChunk.document_id == uuid.UUID(doc["id"])).one()
    assert chunk.heading == "Azienda: Bottega Rossi | Documento: Orari"
    assert no_worker[-1] is None, "embedding da rifare per tutti i documenti dell'azienda"


def test_eliminare_l_azienda_sposta_i_documenti_o_li_elimina(client, admin, admin_token):
    keep = _create_company(client, admin, admin_token, "Da svuotare")
    wipe = _create_company(client, admin, admin_token, "Da cancellare")
    client.post(BASE, headers=admin_token(admin), json={"title": "Resta", "content_text": "Testo.", "company_id": keep["id"]})
    client.post(BASE, headers=admin_token(admin), json={"title": "Sparisce", "content_text": "Testo.", "company_id": wipe["id"]})

    assert client.delete(f"{BASE}/companies/{keep['id']}", headers=admin_token(admin)).status_code == 204
    assert client.delete(f"{BASE}/companies/{wipe['id']}", headers=admin_token(admin), params={"delete_documents": True}).status_code == 204

    titles = [(d["title"], d["company_id"]) for d in client.get(BASE, headers=admin_token(admin)).json()]
    assert titles == [("Resta", None)]


def test_spostare_documenti_in_un_altra_azienda(client, admin, admin_token):
    company = _create_company(client, admin, admin_token, "Bottega Rossi")
    doc = client.post(BASE, headers=admin_token(admin), json={"title": "Orari", "content_text": "Aperti dalle 9."}).json()

    moved = client.post(f"{BASE}/move", headers=admin_token(admin), json={"document_ids": [doc["id"]], "company_id": company["id"]})

    assert moved.status_code == 200, moved.text
    assert moved.json()[0]["company"] == "Bottega Rossi"


def test_non_si_usano_aziende_di_altri(client, admin, admin_token, db):
    from app.models.administrator import Administrator

    other = Administrator(email=f"altro-az-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", full_name="Altro", is_active=True)
    db.add(other)
    db.commit()
    their = _create_company(client, other, admin_token, "Loro")

    response = client.post(BASE, headers=admin_token(admin), json={"title": "X", "content_text": "Y", "company_id": their["id"]})

    assert response.status_code == 404


# --- Ricerca avanzata dall'elenco (GET /knowledge-base/find) --------------------
def _add_document(client, admin, admin_token, title, content, company_id=None, **fields):
    response = client.post(BASE, headers=admin_token(admin), json={"title": title, "content_text": content, "company_id": company_id, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def _find(client, admin, admin_token, q, **params):
    response = client.get(f"{BASE}/find", headers=admin_token(admin), params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_la_ricerca_avanzata_trova_il_file_per_nome_e_lo_mette_prima_di_tutto(client, admin, admin_token):
    csv_data = "Prodotto;Prezzo\nCrema viso;19 euro\n".encode()
    upload = client.post(
        f"{BASE}/upload", headers=admin_token(admin),
        files={"file": ("Listino_Primavera_2026.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    # Un documento che PARLA di listini, ma non si chiama cosi'.
    _add_document(client, admin, admin_token, "Condizioni di vendita", "I prezzi del listino primavera valgono fino a giugno. Spedizione gratuita sopra 50 euro.")

    body = _find(client, admin, admin_token, "listino primavera")

    assert body["query"] == "listino primavera"
    titles = [hit["document"]["title"] for hit in body["hits"]]
    assert titles[0] == "Listino Primavera 2026"
    assert body["hits"][0]["matched_by"][0] == "nome"
    assert body["hits"][0]["document"]["content_text"] is None, "come nell'elenco, niente testo intero"
    # Il secondo e' uscito per contenuto, con il passaggio in cui se ne parla.
    assert "Condizioni di vendita" in titles
    by_content = next(hit for hit in body["hits"] if hit["document"]["title"] == "Condizioni di vendita")
    assert "testo" in by_content["matched_by"] and "nome" not in by_content["matched_by"]
    assert by_content["snippets"] and "listino primavera" in by_content["snippets"][0]["content"].lower()


def test_la_ricerca_avanzata_trova_il_documento_che_parla_dell_argomento(client, admin, admin_token):
    _add_document(client, admin, admin_token, "FAQ generali", "Le consegne in Sardegna richiedono 3 giorni lavorativi in piu' rispetto al continente.")
    _add_document(client, admin, admin_token, "Orari", "Siamo aperti dal lunedi' al venerdi' dalle 9 alle 18.")

    body = _find(client, admin, admin_token, "consegna sardegna")

    assert [hit["document"]["title"] for hit in body["hits"]] == ["FAQ generali"]
    assert body["hits"][0]["matched_by"] == ["testo"]
    assert "Sardegna" in body["hits"][0]["snippets"][0]["content"]


def test_la_ricerca_avanzata_rispetta_la_cartella_aperta(client, admin, admin_token):
    rossi = _create_company(client, admin, admin_token, "Bottega Rossi")
    _add_document(client, admin, admin_token, "Listino Rossi", "Vaso in ceramica 40 euro.", company_id=rossi["id"])
    _add_document(client, admin, admin_token, "Listino generale", "Spedizione standard 7 euro.")

    tutte = _find(client, admin, admin_token, "listino")
    solo_rossi = _find(client, admin, admin_token, "listino", company=rossi["id"])
    senza = _find(client, admin, admin_token, "listino", company="none")

    assert sorted(hit["document"]["title"] for hit in tutte["hits"]) == ["Listino Rossi", "Listino generale"]
    # Dentro una cartella si vede solo quella cartella: niente documenti generali, a differenza di "Prova il bot".
    assert [hit["document"]["title"] for hit in solo_rossi["hits"]] == ["Listino Rossi"]
    assert [hit["document"]["title"] for hit in senza["hits"]] == ["Listino generale"]
    assert client.get(f"{BASE}/find", headers=admin_token(admin), params={"q": "listino", "company": "non-un-id"}).status_code == 422


def test_la_ricerca_avanzata_filtra_per_tipo_e_trova_anche_le_istruzioni_sempre_attive(client, admin, admin_token):
    _add_document(client, admin, admin_token, "Politica resi", "Il reso e' gratuito entro 14 giorni.")
    _add_document(client, admin, admin_token, "Tono", "Parla sempre del reso con calma e senza promettere rimborsi.", kind="instruction", always_on=True)

    docs = _find(client, admin, admin_token, "reso", kind="document")
    instructions = _find(client, admin, admin_token, "reso", kind="instruction")
    everything = _find(client, admin, admin_token, "reso")

    assert [hit["document"]["title"] for hit in docs["hits"]] == ["Politica resi"]
    assert [hit["document"]["title"] for hit in instructions["hits"]] == ["Tono"]
    assert len(everything["hits"]) == 2
    assert client.get(f"{BASE}/find", headers=admin_token(admin), params={"q": "x"}).status_code == 422, "almeno 2 caratteri"


def test_la_ricerca_avanzata_non_mostra_le_schede_azienda_ne_i_documenti_di_altri(client, admin, admin_token, db):
    from app.models.administrator import Administrator
    from app.models.omnichannel import OmniKnowledgeDocument

    _create_company(client, admin, admin_token, "Ceramiche Blu", description="Bottega di ceramiche artigianali")
    other = Administrator(email=f"other-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", full_name="Other", is_active=True)
    db.add(other)
    db.flush()
    db.add(OmniKnowledgeDocument(owner_id=other.id, title="Ceramiche segrete", content_text="Ceramiche di un altro account", status="ready"))
    db.commit()

    body = _find(client, admin, admin_token, "ceramiche")

    assert body["hits"] == []


def test_un_nome_di_file_con_caratteri_speciali_non_rompe_la_ricerca(client, admin, admin_token):
    _add_document(client, admin, admin_token, "Listino 100% cotone_bio", "Magliette in cotone biologico.")

    assert [hit["document"]["title"] for hit in _find(client, admin, admin_token, "100% cotone")["hits"]] == ["Listino 100% cotone_bio"]
    assert _find(client, admin, admin_token, "%_")["hits"] == []
