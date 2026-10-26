"""
Knowledge Base dell'Omnichannel Responder.

Il difetto da cui nasce (2026-10-15): la v1 cercava le parole del messaggio
con ILIKE, e "prezzi" non trovava "prezzo", "quanto costa?" non trovava il
listino, "e la spedizione?" perdeva il contesto. Il bot rispondeva come se la
Knowledge Base fosse vuota. Questi test inchiodano "il blocco giusto arriva
al modello", non "la funzione gira".
"""
import io
import uuid

import numpy as np
import pytest

from app.integrations.omnichannel import ai as omni_ai
from app.integrations.omnichannel import knowledge


# ------------------------------------------------------------------------------
# Funzioni pure
# ------------------------------------------------------------------------------
def test_i_paragrafi_brevi_si_raggruppano_e_nessun_blocco_supera_il_massimo():
    paragraphs = [f"Paragrafo {i}: " + "parola " * 40 for i in range(30)]
    chunks = knowledge.chunk_text("\n\n".join(paragraphs))

    assert 1 < len(chunks) < 30
    assert all(len(c) <= knowledge.CHUNK_MAX_CHARS for c in chunks)
    # Nessun paragrafo spezzato a meta': ognuno compare intero in un blocco.
    for paragraph in paragraphs:
        assert any(paragraph.strip() in c for c in chunks)


def test_un_paragrafo_enorme_viene_spezzato_senza_perdere_testo():
    text = " ".join(f"frase{i}." for i in range(800))
    chunks = knowledge.chunk_text(text)

    assert all(len(c) <= knowledge.CHUNK_MAX_CHARS for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_un_listino_csv_mantiene_i_nomi_delle_colonne_su_ogni_riga():
    data = "Prodotto;Prezzo;Formato\nCrema viso;19 euro;50 ml\nSiero;29 euro;30 ml\n".encode()

    content = knowledge.extract_text("listino.csv", data)

    assert "Prodotto: Crema viso; Prezzo: 19 euro; Formato: 50 ml" in content
    assert "Prodotto: Siero; Prezzo: 29 euro; Formato: 30 ml" in content


def test_un_file_excel_diventa_righe_leggibili():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Codice", "Nome", "Disponibile"])
    sheet.append(["AB-12", "Borraccia", "si"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    content = knowledge.extract_text("prodotti.xlsx", buffer.getvalue())

    assert "Codice: AB-12; Nome: Borraccia; Disponibile: si" in content


def test_un_file_word_porta_testo_e_tabelle():
    import docx

    document = docx.Document()
    document.add_paragraph("Politica di reso: 30 giorni dalla consegna.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Servizio", "Costo"
    table.rows[1].cells[0].text, table.rows[1].cells[1].text = "Spedizione", "5 euro"
    buffer = io.BytesIO()
    document.save(buffer)

    content = knowledge.extract_text("policy.docx", buffer.getvalue())

    assert "Politica di reso: 30 giorni" in content
    assert "Servizio: Spedizione; Costo: 5 euro" in content


def _pdf_with_text(text: str) -> bytes:
    """PDF minimale scritto a mano: una pagina, un font standard, una riga di testo."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def test_dal_pdf_si_estrae_il_testo():
    content = knowledge.extract_text("catalogo.pdf", _pdf_with_text("Il kit base costa 49 euro e include tre accessori per la cucina di casa."))

    assert "kit base costa 49 euro" in content


def test_un_pdf_senza_testo_lo_dice_invece_di_risultare_caricato():
    """Una scansione ha pagine ma nessun testo: caricarla "con successo"
    darebbe un bot che non sa niente e un operatore convinto del contrario."""
    with pytest.raises(knowledge.KnowledgeExtractionError, match="scansione"):
        knowledge.extract_text("scansione.pdf", _pdf_with_text(""))


def test_formati_non_supportati_sono_rifiutati_con_l_elenco_di_quelli_validi():
    with pytest.raises(knowledge.KnowledgeExtractionError, match="PDF, DOCX"):
        knowledge.extract_text("foto.jpg", b"\xff\xd8")


def test_una_domanda_breve_si_porta_dietro_il_contesto_dei_messaggi_prima():
    query = knowledge.build_search_query(["Vorrei informazioni sul corso di yoga per principianti", "quanto costa?"])

    assert "yoga" in query and "quanto costa" in query


def test_una_domanda_gia_completa_non_si_trascina_dietro_la_conversazione():
    query = knowledge.build_search_query([
        "Buongiorno, ho un problema con il mio ordine di ieri",
        "Vorrei sapere quali sono i tempi di consegna per la Sardegna con il corriere espresso",
    ])

    assert "problema" not in query
    assert "Sardegna" in query


def test_le_informazioni_della_knowledge_base_vanno_in_fondo_dopo_la_cronologia():
    """Il prefisso stabile (prompt di sistema + cronologia) e' quello che
    OpenAI mette in cache a meta' prezzo: i blocchi, che cambiano a ogni
    messaggio, devono stare dopo."""
    history = [{"role": "user", "content": "ciao"}, {"role": "assistant", "content": "ciao!"}, {"role": "user", "content": "prezzi?"}]

    messages = omni_ai.build_messages("PROMPT", history, "INFORMAZIONI DALLA KNOWLEDGE BASE: ...")

    assert messages[0] == {"role": "system", "content": "PROMPT"}
    assert messages[1:4] == history
    assert messages[-1]["role"] == "system" and "KNOWLEDGE BASE" in messages[-1]["content"]


def test_senza_blocchi_pertinenti_non_si_aggiunge_nulla():
    assert len(omni_ai.build_messages("PROMPT", [{"role": "user", "content": "ciao"}], "")) == 2


# ------------------------------------------------------------------------------
# Ricerca su database vero
# ------------------------------------------------------------------------------
@pytest.fixture()
def owner(db):
    from app.models.administrator import Administrator

    admin = Administrator(email=f"kb-{uuid.uuid4().hex[:6]}@test.local", password_hash="x", full_name="KB", is_active=True)
    db.add(admin)
    db.commit()
    return admin


def _company(db, owner, name, **fields):
    from app.models.omnichannel import OmniKnowledgeCompany

    company = OmniKnowledgeCompany(owner_id=owner.id, name=name, **fields)
    db.add(company)
    db.flush()
    return company


def _add(db, owner, title, content, company=None, **fields):
    from app.models.omnichannel import OmniKnowledgeDocument

    if isinstance(company, str):
        company = _company(db, owner, company)
    document = OmniKnowledgeDocument(owner_id=owner.id, title=title, content_text=content, status="ready", company_ref=company, **fields)
    db.add(document)
    db.flush()
    knowledge.rebuild_chunks(db, document)
    db.commit()
    return document


# Embedding finti ma con un significato: ogni dimensione e' un "concetto", e
# un testo accende i concetti delle parole che contiene. Basta a verificare
# che la ricerca semantica trovi un blocco che non condivide parole con la
# domanda - il caso che la ricerca testuale da sola non copre.
_CONCEPTS = [
    {"spedizione", "consegna", "corriere", "arriva", "arrivo", "pacco"},
    {"prezzo", "costa", "costo", "euro", "listino"},
    {"reso", "rimborso", "restituire", "restituzione"},
]


def _fake_embed(api_key, texts):
    vectors = []
    for text in texts:
        words = set(text.lower().replace("?", " ").replace(".", " ").split())
        vector = np.zeros(knowledge.EMBEDDING_DIMENSIONS, dtype=np.float32)
        for index, concept in enumerate(_CONCEPTS):
            if words & concept:
                vector[index] = 1.0
        vector[100 + (hash(text) % 300)] = 0.05  # rumore, per non avere vettori nulli
        vectors.append(knowledge._normalize(vector))
    return vectors


def test_la_ricerca_testuale_capisce_plurali_e_forme_diverse(db, owner):
    _add(db, owner, "Listino", "Il prezzo della consulenza iniziale e' di 80 euro a sessione.")
    _add(db, owner, "Orari", "Siamo aperti dal lunedi' al venerdi' dalle 9 alle 18.")

    hits, warning = knowledge.search(db, owner.id, "Quali sono i vostri prezzi?", api_key=None)

    assert warning is None
    assert [h.document_title for h in hits][:1] == ["Listino"]


def test_un_codice_prodotto_si_trova_anche_se_lo_stemmer_italiano_lo_storpierebbe(db, owner):
    _add(db, owner, "Catalogo", "Articolo XR-500: frullatore professionale, 1200 W.")

    hits, _ = knowledge.search(db, owner.id, "avete ancora il XR-500?", api_key=None)

    assert hits and hits[0].document_title == "Catalogo"


def test_il_titolo_e_l_azienda_contano_anche_se_il_testo_non_li_ripete(db, owner):
    _add(db, owner, "Politica di reso", "Entro 30 giorni dalla consegna, con scontrino.", company="Bottega Rossi")

    hits, _ = knowledge.search(db, owner.id, "come funziona il reso da Bottega Rossi?", api_key=None)

    assert hits and hits[0].company == "Bottega Rossi"
    assert "Bottega Rossi" in knowledge.format_context(hits)


def test_le_parole_vuote_non_tirano_dentro_blocchi_a_caso(db, owner):
    """"come", "per", "che" stanno in quasi ogni testo: senza filtro, la
    configurazione 'simple' farebbe arrivare al modello mezza Knowledge Base
    per un saluto."""
    _add(db, owner, "Procedura", "Come spiegato per telefono, il ritiro avviene che tu sia in negozio o no.")

    hits, _ = knowledge.search(db, owner.id, "ciao, come va? per caso sei li?", api_key=None)

    assert hits == []


def test_la_ricerca_semantica_trova_il_blocco_anche_senza_parole_in_comune(db, owner, monkeypatch):
    monkeypatch.setattr(knowledge, "embed_texts", _fake_embed)
    _add(db, owner, "Logistica", "Il pacco viene affidato al corriere entro 24 ore lavorative.")
    _add(db, owner, "Listino", "La consulenza iniziale costa 80 euro.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)

    hits, _ = knowledge.search(db, owner.id, "Quando mi arriva l'ordine?", api_key="sk-test")

    assert hits and hits[0].document_title == "Logistica"
    assert "significato" in hits[0].matched_by


def test_un_saluto_non_porta_dietro_blocchi_a_caso(db, owner, monkeypatch):
    """Ogni blocco inviato senza motivo e' token pagati per niente."""
    monkeypatch.setattr(knowledge, "embed_texts", _fake_embed)
    _add(db, owner, "Logistica", "Il pacco viene affidato al corriere entro 24 ore lavorative.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)

    hits, _ = knowledge.search(db, owner.id, "ciao!", api_key="sk-test")

    assert hits == []


def test_se_openai_rifiuta_l_embedding_resta_la_ricerca_testuale(db, owner, monkeypatch):
    from app.integrations.omnichannel.exceptions import ConnectorError

    monkeypatch.setattr(knowledge, "embed_texts", _fake_embed)
    _add(db, owner, "Listino", "Il prezzo della consulenza e' 80 euro.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)

    def _no_credit(api_key, texts):
        raise ConnectorError("Credito OpenAI esaurito")

    monkeypatch.setattr(knowledge, "embed_texts", _no_credit)
    hits, warning = knowledge.search(db, owner.id, "prezzi della consulenza", api_key="sk-test")

    assert hits and hits[0].document_title == "Listino"
    assert "Credito OpenAI esaurito" in warning


def test_le_informazioni_di_un_altro_account_non_escono_mai(db, owner):
    from app.models.administrator import Administrator

    other = Administrator(email="altro@test.local", password_hash="x", full_name="Altro", is_active=True)
    db.add(other)
    db.commit()
    _add(db, other, "Listino segreto", "Il prezzo riservato e' 10 euro.")

    hits, _ = knowledge.search(db, owner.id, "prezzo riservato", api_key=None)

    assert hits == []


def test_le_istruzioni_sempre_attive_stanno_nel_prompt_e_non_nella_ricerca(db, owner):
    rule = _add(db, owner, "Preventivi", "Per un preventivo chiedi sempre citta' e data dell'evento.", kind="instruction", always_on=True)
    _add(db, owner, "Eventi", "Organizziamo eventi aziendali e matrimoni, preventivo gratuito.")

    hits, _ = knowledge.search(db, owner.id, "vorrei un preventivo per un evento", api_key=None)
    standing = knowledge.always_on_instructions(db, owner.id)
    prompt = omni_ai.build_system_prompt(None, standing)

    assert [h.document_title for h in hits] == ["Eventi"]
    assert standing == [rule]
    assert "chiedi sempre citta'" in prompt


def test_un_istruzione_pertinente_arriva_come_istruzione_non_come_informazione(db, owner):
    _add(db, owner, "Reclami", "Se il cliente si lamenta di un ritardo, scusati e offri il 10% di sconto sul prossimo ordine.", kind="instruction")

    hits, _ = knowledge.search(db, owner.id, "il mio ordine e' in ritardo, sono arrabbiato", api_key=None)
    context = knowledge.format_context(hits)

    assert hits and hits[0].kind == "instruction"
    assert context.startswith("ISTRUZIONI DELL'AZIENDA")


def test_il_budget_di_caratteri_limita_quanto_testo_arriva_al_modello(db, owner):
    for i in range(10):
        _add(db, owner, f"Scheda {i}", f"Prezzo del prodotto numero {i}: " + "dettaglio " * 80)

    hits, _ = knowledge.search(db, owner.id, "prezzo prodotto", api_key=None, limit=10, char_budget=2000)

    assert 1 <= len(hits) < 10
    assert sum(len(h.content) for h in hits) <= 2000 or len(hits) == 1


def test_la_cache_dei_vettori_si_accorge_di_un_documento_nuovo(db, owner, monkeypatch):
    monkeypatch.setattr(knowledge, "embed_texts", _fake_embed)
    _add(db, owner, "Listino", "La consulenza costa 80 euro.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)
    knowledge.search(db, owner.id, "costo", api_key="sk-test")  # riempie la cache

    _add(db, owner, "Logistica", "Il pacco parte con il corriere entro 24 ore.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)
    hits, _ = knowledge.search(db, owner.id, "quando arriva?", api_key="sk-test")

    assert hits and hits[0].document_title == "Logistica"


def test_la_scheda_azienda_risponde_a_contatti_e_indirizzo(db, owner):
    """Telefono e indirizzo non stanno in nessun PDF: li trova la scheda generata dai dati dell'azienda."""
    company = _company(db, owner, "Bottega Rossi", phone="+39 055 123456", address="Via Roma 1, Firenze")
    knowledge.sync_company_profile(db, company)
    db.commit()

    hits, _ = knowledge.search(db, owner.id, "qual e' il vostro telefono?", api_key=None)

    assert hits and hits[0].kind == "profile"
    assert "+39 055 123456" in hits[0].content
    assert "Scheda azienda" in knowledge.format_context(hits)


def test_la_scheda_azienda_non_si_rigenera_se_i_dati_non_cambiano(db, owner):
    company = _company(db, owner, "Bottega Rossi", phone="055 1")
    assert knowledge.sync_company_profile(db, company) is not None
    db.commit()

    assert knowledge.sync_company_profile(db, company) is None
    company.notes = "nota interna"
    assert knowledge.sync_company_profile(db, company) is None, "le note interne non vanno al bot"


def test_il_filtro_azienda_esclude_le_altre_ma_tiene_i_documenti_generali(db, owner, monkeypatch):
    monkeypatch.setattr(knowledge, "embed_texts", _fake_embed)
    rossi = _company(db, owner, "Bottega Rossi")
    _add(db, owner, "Spedizioni Rossi", "Il pacco arriva con il corriere in 48 ore.", company=rossi)
    _add(db, owner, "Spedizioni Bianchi", "Il pacco arriva con il corriere in 5 giorni.", company="Ferramenta Bianchi")
    _add(db, owner, "Pagamenti", "Il pacco si paga anche alla consegna.")
    knowledge.embed_pending_chunks(db, "sk-test", owner_id=owner.id)

    hits, _ = knowledge.search(db, owner.id, "quando arriva il pacco?", api_key="sk-test", company_id=rossi.id)

    titles = {h.document_title for h in hits}
    assert "Spedizioni Rossi" in titles and "Pagamenti" in titles
    assert "Spedizioni Bianchi" not in titles
