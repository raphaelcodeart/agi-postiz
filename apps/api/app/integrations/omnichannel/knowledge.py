"""
Knowledge Base dell'Omnichannel Responder: estrazione del testo, divisione in
blocchi, embedding e ricerca.

Perche' cosi' (2026-10-15). La v1 cercava le singole parole del messaggio con
ILIKE: "prezzi" non trovava "prezzo", "quanto costa?" non trovava "listino", e
un "e la spedizione?" perdeva il contesto del messaggio prima. In pratica il
bot non usava quasi mai la Knowledge Base.

La ricerca ora e' ibrida, e nessuna delle due meta' chiama il modello di chat:

- testuale: full-text search di Postgres con lo stemming italiano ('italian',
  quindi prezzi ~ prezzo) piu' la configurazione 'simple' per codici prodotto,
  sigle e parole straniere che lo stemmer italiano storpierebbe. Gratuita e
  sempre disponibile, anche senza credito OpenAI.
- semantica: embedding OpenAI text-embedding-3-small a 512 dimensioni. Costa
  ~0,02 $ per milione di token: indicizzare un PDF di 100 pagine costa meno di
  un decimo di centesimo, e cercare costa un embedding del messaggio.

Le due classifiche sono fuse con Reciprocal Rank Fusion, poi al modello di chat
arrivano solo i pochi blocchi pertinenti (budget fisso di caratteri, vedi
CONTEXT_CHAR_BUDGET): il costo per risposta non cresce con la dimensione della
Knowledge Base.

Niente pgvector: l'immagine postgres:16-alpine di produzione non lo include, e
cambiare immagine a un database gia' in uso (alpine -> debian cambia anche le
collation) e' un intervento a parte. Gli embedding stanno in una colonna bytea
(float32) e il confronto si fa in numpy su una matrice tenuta in memoria per
proprietario, ricaricata solo quando la Knowledge Base cambia (vedi
_VectorCache). Regge comodamente decine di migliaia di blocchi; oltre, la
strada e' pgvector, e tocca solo _vector_search().
"""
import csv
import io
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import httpx
import numpy as np
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.integrations.omnichannel.exceptions import ConnectorError
from app.models.omnichannel import OmniKnowledgeChunk, OmniKnowledgeCompany, OmniKnowledgeDocument

logger = logging.getLogger(__name__)

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512

# Dimensione dei blocchi: abbastanza grandi da contenere una risposta intera
# (una voce di FAQ, una scheda prodotto), abbastanza piccoli che 4-5 blocchi
# stiano in ~1000 token.
CHUNK_TARGET_CHARS = 900
CHUNK_MAX_CHARS = 1200

# Quanto testo della Knowledge Base puo' finire in una singola richiesta di
# chat (~1000-1200 token). E' il tetto che tiene basso il costo per risposta.
CONTEXT_CHAR_BUDGET = 4500
DEFAULT_RESULT_LIMIT = 5

# Sotto questa similarita' coseno un blocco trovato solo dalla ricerca
# semantica non e' pertinente (con text-embedding-3-small i testi sullo stesso
# argomento stanno sopra ~0.3, un "ciao" contro un listino sotto ~0.2). Un
# blocco trovato anche dalla ricerca testuale non ha bisogno della soglia.
MIN_VECTOR_SIMILARITY = 0.28

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx"}

_EMBED_BATCH = 128
_RRF_K = 60


# ------------------------------------------------------------------------------
# Estrazione del testo dai file
# ------------------------------------------------------------------------------
class KnowledgeExtractionError(ValueError):
    """Il file non contiene testo utilizzabile; il messaggio e' per l'operatore."""


def source_type_for_filename(filename: str) -> str:
    ext = _extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise KnowledgeExtractionError(
            f"Formato non supportato ({ext or 'senza estensione'}). Formati accettati: PDF, DOCX, TXT, MD, CSV, XLSX."
        )
    return ext.lstrip(".")


def extract_text(filename: str, data: bytes) -> str:
    """Testo del file, pronto per chunk_text(). Solleva KnowledgeExtractionError con un motivo leggibile."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise KnowledgeExtractionError(f"File troppo grande: il limite e' {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    kind = source_type_for_filename(filename)
    if kind == "pdf":
        content = _extract_pdf(data)
    elif kind == "docx":
        content = _extract_docx(data)
    elif kind == "csv":
        content = _rows_to_text(_read_csv(data))
    elif kind == "xlsx":
        content = _extract_xlsx(data)
    else:
        content = _decode(data)
    content = _normalize_whitespace(content)
    if not content.strip():
        raise KnowledgeExtractionError("Il file non contiene testo leggibile.")
    return content


def _extension(filename: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", filename or "")
    return match.group(1).lower() if match else ""


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001 - qualunque fallimento qui vuol dire "protetto"
                raise KnowledgeExtractionError("Il PDF e' protetto da password: salvalo senza protezione e ricaricalo.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except KnowledgeExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError) as e:
        raise KnowledgeExtractionError(f"PDF non leggibile: {e}")

    content = "\n\n".join(p for p in pages if p)
    # Un PDF fatto di scansioni ha pagine ma nessun testo: dirlo esplicitamente,
    # altrimenti l'operatore vede "caricato" e un bot che non sa niente.
    if pages and len(content) < 30 * len(pages) and len(content) < 200:
        raise KnowledgeExtractionError(
            "Il PDF non contiene testo selezionabile (probabilmente e' una scansione o sono immagini). "
            "Serve un PDF con testo, oppure incolla il contenuto come documento di testo."
        )
    return content


def _extract_docx(data: bytes) -> str:
    import docx  # python-docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, ValueError, KeyError) as e:
        raise KnowledgeExtractionError(f"File Word non leggibile: {e}")

    parts: List[str] = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        parts.append(_rows_to_text(rows))
    return "\n\n".join(parts)


def _read_csv(data: bytes) -> List[List[str]]:
    content = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(content), dialect) if any(cell.strip() for cell in row)]


def _extract_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 - openpyxl solleva tipi diversi a seconda del danno
        raise KnowledgeExtractionError(f"File Excel non leggibile: {e}")
    sections = []
    for sheet in workbook.worksheets:
        rows = [
            ["" if value is None else str(value).strip() for value in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        rows = [row for row in rows if any(rows_cell for rows_cell in row)]
        if rows:
            body = _rows_to_text(rows)
            sections.append(f"Foglio {sheet.title}\n\n{body}" if len(workbook.worksheets) > 1 else body)
    return "\n\n".join(sections)


def _rows_to_text(rows: List[List[str]]) -> str:
    """
    Una riga per paragrafo, con i nomi delle colonne ripetuti su ogni riga:
    "Prodotto: Crema X; Prezzo: 19 euro; Formato: 50 ml". Un listino diviso a
    blocchi resta cosi' comprensibile blocco per blocco, mentre una riga di soli
    valori ("Crema X; 19; 50 ml") perde il significato appena si stacca
    dall'intestazione.
    """
    if not rows:
        return ""
    header = [h.strip() for h in rows[0]]
    has_header = len(rows) > 1 and all(header) and len(set(header)) == len(header)
    lines = []
    for row in rows[1:] if has_header else rows:
        if has_header:
            pairs = [f"{header[i]}: {value}" for i, value in enumerate(row) if i < len(header) and value]
            lines.append("; ".join(pairs))
        else:
            lines.append("; ".join(value for value in row if value))
    return "\n\n".join(line for line in lines if line)


def _normalize_whitespace(content: str) -> str:
    content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    content = re.sub(r"[ \t\f\v]+", " ", content)
    content = re.sub(r" *\n *", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


# ------------------------------------------------------------------------------
# Divisione in blocchi
# ------------------------------------------------------------------------------
def chunk_text(content: str, target: int = CHUNK_TARGET_CHARS, hard_max: int = CHUNK_MAX_CHARS) -> List[str]:
    """
    Raggruppa i paragrafi fino a ~target caratteri senza spezzarli; spezza su
    frasi (poi su spazi) solo un paragrafo che da solo supera hard_max. Le
    righe singole vanno a capo dentro lo stesso blocco: in un PDF un a capo
    e' quasi sempre l'impaginazione, non la fine di un concetto.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", _normalize_whitespace(content)) if p.strip()]
    pieces: List[str] = []
    for paragraph in paragraphs:
        pieces.extend(_split_long(paragraph, hard_max) if len(paragraph) > hard_max else [paragraph])

    chunks: List[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if current and len(candidate) > target:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph: str, hard_max: int) -> List[str]:
    sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
    parts: List[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > hard_max:
            cut = sentence.rfind(" ", 0, hard_max)
            cut = cut if cut > hard_max // 2 else hard_max
            head, sentence = sentence[:cut].strip(), sentence[cut:].strip()
            if current:
                parts.append(current)
                current = ""
            parts.append(head)
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > hard_max and current:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


_KIND_LABELS = {"instruction": "Istruzione", "profile": "Scheda azienda"}


def chunk_heading(document: OmniKnowledgeDocument) -> str:
    """Intestazione ripetuta su ogni blocco: azienda e titolo. Entra nell'embedding e nella ricerca testuale."""
    parts = []
    if document.company:
        parts.append(f"Azienda: {document.company}")
    parts.append(f"{_KIND_LABELS.get(document.kind, 'Documento')}: {document.title}")
    return " | ".join(parts)


def rebuild_chunks(db: Session, document: OmniKnowledgeDocument) -> int:
    """Rigenera i blocchi del documento (senza embedding: li calcola embed_document()). Non fa commit."""
    db.query(OmniKnowledgeChunk).filter(OmniKnowledgeChunk.document_id == document.id).delete(synchronize_session=False)
    heading = chunk_heading(document)
    contents = chunk_text(document.content_text or "")
    for index, content in enumerate(contents):
        db.add(OmniKnowledgeChunk(
            owner_id=document.owner_id, document_id=document.id, chunk_index=index,
            heading=heading, content=content,
        ))
    document.chunk_count = len(contents)
    return len(contents)


def company_profile_text(company: OmniKnowledgeCompany) -> str:
    """Dati dell'azienda come li leggera' il bot. Le note interne restano fuori."""
    lines = [f"Nome: {company.name}"]
    for label, value in (
        ("Chi siamo", company.description), ("Sito web", company.website), ("Email", company.email),
        ("Telefono", company.phone), ("Indirizzo", company.address),
    ):
        if value and value.strip():
            lines.append(f"{label}: {value.strip()}")
    return "\n".join(lines)


def sync_company_profile(db: Session, company: OmniKnowledgeCompany) -> Optional[OmniKnowledgeDocument]:
    """
    Crea o aggiorna la scheda dell'azienda (documento kind="profile") e ne
    rigenera i blocchi. Ritorna il documento se i blocchi sono cambiati e vanno
    rifatti gli embedding, altrimenti None. Non fa commit.
    """
    profile = (
        db.query(OmniKnowledgeDocument)
        .filter(OmniKnowledgeDocument.company_id == company.id, OmniKnowledgeDocument.kind == "profile")
        .first()
    )
    content = company_profile_text(company)
    title = f"Scheda {company.name}"[:255]
    if profile and profile.content_text == content and profile.title == title:
        return None
    if not profile:
        profile = OmniKnowledgeDocument(
            owner_id=company.owner_id, company_id=company.id, kind="profile", source_type="manual", status="ready",
        )
        db.add(profile)
    profile.company_ref = company
    profile.title = title
    profile.content_text = content
    profile.status = "ready"
    db.flush()
    rebuild_chunks(db, profile)
    return profile


# ------------------------------------------------------------------------------
# Embedding
# ------------------------------------------------------------------------------
def embed_texts(api_key: str, texts: Sequence[str]) -> List[np.ndarray]:
    """Un vettore float32 normalizzato (norma 1) per testo. Solleva ConnectorError con il motivo di OpenAI."""
    from app.integrations.omnichannel.ai import _describe_openai_error

    vectors: List[np.ndarray] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        batch = [t[:8000] for t in texts[start:start + _EMBED_BATCH]]
        try:
            response = httpx.post(
                OPENAI_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": EMBEDDING_MODEL, "input": batch, "dimensions": EMBEDDING_DIMENSIONS},
                timeout=60.0,
            )
        except httpx.RequestError as e:
            raise ConnectorError(f"Errore di rete verso OpenAI: {e}")
        if response.status_code != 200:
            raise ConnectorError(_describe_openai_error(response), status_code=response.status_code)
        try:
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors.extend(_normalize(np.asarray(item["embedding"], dtype=np.float32)) for item in items)
        except (KeyError, TypeError, ValueError) as e:
            raise ConnectorError(f"Risposta embedding OpenAI non valida: {e}")
    return vectors


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def _embedding_input(chunk: OmniKnowledgeChunk) -> str:
    return f"{chunk.heading}\n{chunk.content}" if chunk.heading else chunk.content


def embed_pending_chunks(db: Session, api_key: str, owner_id: Optional[uuid.UUID] = None,
                         document_id: Optional[uuid.UUID] = None, limit: int = 2000) -> int:
    """
    Calcola gli embedding mancanti e fa commit a ogni lotto, cosi' un errore a
    meta' (credito finito) non butta via il lavoro gia' pagato. Ritorna quanti
    blocchi ha completato; solleva ConnectorError se OpenAI rifiuta.
    """
    query = db.query(OmniKnowledgeChunk).filter(OmniKnowledgeChunk.embedding.is_(None))
    if owner_id:
        query = query.filter(OmniKnowledgeChunk.owner_id == owner_id)
    if document_id:
        query = query.filter(OmniKnowledgeChunk.document_id == document_id)
    chunks = query.order_by(OmniKnowledgeChunk.created_at).limit(limit).all()

    done = 0
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start:start + _EMBED_BATCH]
        vectors = embed_texts(api_key, [_embedding_input(c) for c in batch])
        now = datetime.now(timezone.utc)
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector.astype(np.float32).tobytes()
            chunk.embedding_model = f"{EMBEDDING_MODEL}:{EMBEDDING_DIMENSIONS}"
            chunk.embedded_at = now
        db.commit()
        done += len(batch)
    return done


# ------------------------------------------------------------------------------
# Ricerca
# ------------------------------------------------------------------------------
@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    company: Optional[str]
    kind: str
    heading: Optional[str]
    content: str
    score: float = 0.0
    matched_by: List[str] = field(default_factory=list)
    similarity: Optional[float] = None


def build_search_query(customer_texts: Sequence[str], max_chars: int = 600) -> str:
    """
    Testo da cercare a partire dagli ultimi messaggi del cliente (dal piu'
    vecchio al piu' recente). Un messaggio breve ("e la spedizione?",
    "quanto costa?") da solo non dice di cosa si parla: in quel caso si
    aggiungono i messaggi precedenti. Nessuna chiamata a un modello per
    riscrivere la domanda: costerebbe una richiesta in piu' a ogni messaggio.
    """
    texts = [t.strip() for t in customer_texts if t and t.strip()]
    if not texts:
        return ""
    selected = [texts[-1]]
    for previous in reversed(texts[:-1]):
        if len(" ".join(selected).split()) >= 12 or len(selected) >= 3:
            break
        selected.insert(0, previous)
    return " ".join(selected)[-max_chars:]


# Parole che non dicono niente dell'argomento. La configurazione 'italian' di
# Postgres le scarta da sola; 'simple' no, e senza questo filtro un "ciao, come
# va?" troverebbe "come" in mezza Knowledge Base e porterebbe al modello
# blocchi a caso - token pagati per niente.
_STOPWORDS = set("""
a ad al allo ai agli all alla alle anche ancora avete abbiamo ho hai ha hanno che chi ci con col come cosa cui da dal dallo
dai dagli dall dalla dalle del dello dei degli dell della delle di dov dove e ed era essere fa fare gli ha il in io la le lei
li lo loro lui ma me mi mia mie miei mio ne nei negli nel nello nell nella nelle no noi non nostro nostra o per perche piu
poi puo qua quale quali qualche quando quanto quanti quella quelle quelli quello questa queste questi questo qui se sei si
sia siamo siete sono su sua sue sugli sui sul sullo sull sulla sulle suo suoi te ti tra tu tua tue tuo tuoi tutti tutto vostro vostra vostri vostre
un una uno vi voi vorrei volevo grazie ciao salve buongiorno buonasera sapere chiedo chiedere info informazioni gentile
the and for are you your with can what when how have this that from about please hello thanks
""".split())

# Codici prodotto, SKU, modelli: lettere e cifre unite da - / . _ ("XR-500",
# "AB12/C"). Il parser di Postgres li smonta ("xr" + il numero "-500"), quindi
# si cercano come sottostringa esatta: sono abbastanza specifici da non dare
# falsi positivi.
_CODE_RE = re.compile(r"\b(?=[\w./-]*\d)(?=[\w./-]*[^\W\d_])[\w]+(?:[-./][\w]+)+\b|\b(?=\w*\d)(?=\w*[^\W\d_])\w{3,}\b")


def _fts_terms(query_text: str) -> List[str]:
    terms: List[str] = []
    for term in re.findall(r"[^\W_]+", query_text.lower()):
        if (len(term) >= 3 or term.isdigit()) and term not in _STOPWORDS and term not in terms:
            terms.append(term)
    return terms[:30]


def _code_terms(query_text: str) -> List[str]:
    codes: List[str] = []
    for code in _CODE_RE.findall(query_text):
        if code.lower() not in (c.lower() for c in codes):
            codes.append(code)
    return codes[:5]


_FTS_DOCUMENT = "coalesce(c.heading, '') || ' ' || c.content"


def _fts_search(
    db: Session, owner_id: uuid.UUID, query_text: str, limit: int, company_id: Optional[uuid.UUID] = None,
    include_always_on: bool = False,
) -> List[Tuple[uuid.UUID, float]]:
    terms = _fts_terms(query_text)
    codes = _code_terms(query_text)
    if not terms and not codes:
        return []
    params: Dict[str, object] = {"owner_id": owner_id, "limit": limit}
    # Le istruzioni sempre attive stanno gia' nel prompt: il bot non le cerca.
    # L'operatore che cerca un file invece le vuole trovare come tutto il resto.
    always_on_filter = "" if include_always_on else "AND NOT d.always_on"
    company_filter = ""
    if company_id:
        params["company_id"] = company_id
        company_filter = "AND (d.company_id = :company_id OR d.company_id IS NULL)"
    # OR fra i termini: un messaggio di cliente non e' una query booleana, e un
    # AND (plainto_tsquery) scarterebbe ogni blocco a cui manca una sola parola.
    params["q"] = " | ".join(terms) if terms else "zzznessuntermine"
    code_conditions = []
    for i, code in enumerate(codes):
        params[f"code{i}"] = f"%{code}%"
        code_conditions.append(f"({_FTS_DOCUMENT}) ILIKE :code{i}")
    code_match = " OR ".join(code_conditions) if code_conditions else "FALSE"
    code_bonus = " + ".join(f"CASE WHEN {cond} THEN 1.0 ELSE 0 END" for cond in code_conditions) or "0"

    sql = text(f"""
        WITH q AS (
            SELECT to_tsquery('italian', :q) AS it, to_tsquery('simple', :q) AS si
        )
        SELECT c.id,
               ts_rank_cd(to_tsvector('italian', {_FTS_DOCUMENT}), q.it)
             + 0.5 * ts_rank_cd(to_tsvector('simple', {_FTS_DOCUMENT}), q.si)
             + {code_bonus} AS rank
        FROM omni_knowledge_chunks c
        JOIN omni_knowledge_documents d ON d.id = c.document_id
        CROSS JOIN q
        WHERE c.owner_id = :owner_id
          AND d.status = 'ready' {always_on_filter}
          {company_filter}
          AND (to_tsvector('italian', {_FTS_DOCUMENT}) @@ q.it
               OR to_tsvector('simple', {_FTS_DOCUMENT}) @@ q.si
               OR {code_match})
        ORDER BY rank DESC
        LIMIT :limit
    """)
    rows = db.execute(sql, params).all()
    return [(row[0], float(row[1])) for row in rows]


class _VectorCache:
    """
    Matrice degli embedding per proprietario, in memoria nel processo (API o
    worker). Si ricarica quando cambia la firma della Knowledge Base: numero di
    blocchi con embedding, ultimo embedding calcolato, ultima modifica e numero
    dei documenti. Calcolarla costa una query di aggregazione; ricaricare la
    matrice solo quando serve evita di leggere megabyte di vettori a ogni
    messaggio.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[uuid.UUID, Tuple[tuple, List[uuid.UUID], List[Optional[uuid.UUID]], np.ndarray]] = {}

    def get(self, db: Session, owner_id: uuid.UUID) -> Tuple[List[uuid.UUID], List[Optional[uuid.UUID]], np.ndarray]:
        """(id dei blocchi, azienda di ciascun blocco, matrice degli embedding)."""
        signature = self._signature(db, owner_id)
        with self._lock:
            cached = self._entries.get(owner_id)
            if cached and cached[0] == signature:
                return cached[1], cached[2], cached[3]

        rows = (
            db.query(OmniKnowledgeChunk.id, OmniKnowledgeChunk.embedding, OmniKnowledgeDocument.company_id)
            .join(OmniKnowledgeDocument, OmniKnowledgeDocument.id == OmniKnowledgeChunk.document_id)
            .filter(
                OmniKnowledgeChunk.owner_id == owner_id,
                OmniKnowledgeChunk.embedding.isnot(None),
                OmniKnowledgeDocument.status == "ready",
                OmniKnowledgeDocument.always_on.is_(False),
            )
            .all()
        )
        expected = EMBEDDING_DIMENSIONS * 4
        rows = [row for row in rows if row[1] is not None and len(row[1]) == expected]
        ids = [row[0] for row in rows]
        companies = [row[2] for row in rows]
        matrix = (
            np.frombuffer(b"".join(bytes(row[1]) for row in rows), dtype=np.float32).reshape(len(rows), EMBEDDING_DIMENSIONS)
            if rows else np.zeros((0, EMBEDDING_DIMENSIONS), dtype=np.float32)
        )
        with self._lock:
            self._entries[owner_id] = (signature, ids, companies, matrix)
        return ids, companies, matrix

    @staticmethod
    def _signature(db: Session, owner_id: uuid.UUID) -> tuple:
        chunk_sig = (
            db.query(func.count(OmniKnowledgeChunk.id), func.max(OmniKnowledgeChunk.embedded_at))
            .filter(OmniKnowledgeChunk.owner_id == owner_id, OmniKnowledgeChunk.embedding.isnot(None))
            .one()
        )
        doc_sig = (
            db.query(func.count(OmniKnowledgeDocument.id), func.max(OmniKnowledgeDocument.updated_at))
            .filter(OmniKnowledgeDocument.owner_id == owner_id)
            .one()
        )
        return tuple(chunk_sig) + tuple(doc_sig)


_vector_cache = _VectorCache()


def _vector_search(
    db: Session, owner_id: uuid.UUID, query_vector: np.ndarray, limit: int, company_id: Optional[uuid.UUID] = None,
) -> List[Tuple[uuid.UUID, float]]:
    ids, companies, matrix = _vector_cache.get(db, owner_id)
    if not ids:
        return []
    similarities = matrix @ query_vector
    if company_id:
        # Fuori dalla classifica i blocchi delle altre aziende; restano quelli
        # senza azienda, che valgono per tutte.
        other = np.array([c is not None and c != company_id for c in companies], dtype=bool)
        similarities = np.where(other, -np.inf, similarities)
    top = [i for i in np.argsort(-similarities)[:limit] if np.isfinite(similarities[i])]
    return [(ids[i], float(similarities[i])) for i in top]


def _hybrid_rank(
    db: Session,
    owner_id: uuid.UUID,
    query_text: str,
    api_key: Optional[str],
    pool: int,
    company_id: Optional[uuid.UUID] = None,
    include_always_on: bool = False,
) -> Tuple[Dict[uuid.UUID, float], Dict[uuid.UUID, List[str]], Dict[uuid.UUID, float], Optional[str]]:
    """
    Il motore ibrido, senza presentazione: full-text + vettori fusi con RRF.
    Ritorna (punteggio per blocco, come e' stato trovato ciascuno, somiglianza
    coseno dove c'e', avviso). Lo usano search() per il bot e find_documents()
    per la ricerca avanzata dall'elenco: stessa classifica, letture diverse.
    """
    fts_hits = _fts_search(db, owner_id, query_text, pool, company_id, include_always_on)

    vector_hits: List[Tuple[uuid.UUID, float]] = []
    warning: Optional[str] = None
    if api_key and has_embeddings(db, owner_id):
        try:
            query_vector = embed_texts(api_key, [query_text])[0]
            vector_hits = _vector_search(db, owner_id, query_vector, pool, company_id)
        except ConnectorError as e:
            warning = f"Ricerca semantica non disponibile, uso solo quella testuale: {e.message}"
            logger.warning("Knowledge base vector search skipped for owner %s: %s", owner_id, e.message)

    similarity = {chunk_id: sim for chunk_id, sim in vector_hits}
    fused: Dict[uuid.UUID, float] = {}
    matched: Dict[uuid.UUID, List[str]] = {}
    for rank, (chunk_id, _) in enumerate(fts_hits):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        matched.setdefault(chunk_id, []).append("testo")
    for rank, (chunk_id, sim) in enumerate(vector_hits):
        if sim < MIN_VECTOR_SIMILARITY and chunk_id not in fused:
            continue
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        matched.setdefault(chunk_id, []).append("significato")
    return fused, matched, similarity, warning


def has_embeddings(db: Session, owner_id: uuid.UUID) -> bool:
    return db.query(OmniKnowledgeChunk.id).filter(
        OmniKnowledgeChunk.owner_id == owner_id, OmniKnowledgeChunk.embedding.isnot(None)
    ).first() is not None


def search(
    db: Session,
    owner_id: uuid.UUID,
    query_text: str,
    api_key: Optional[str],
    limit: int = DEFAULT_RESULT_LIMIT,
    char_budget: int = CONTEXT_CHAR_BUDGET,
    company_id: Optional[uuid.UUID] = None,
) -> Tuple[List[RetrievedChunk], Optional[str]]:
    """
    Ritorna (blocchi pertinenti, avviso). Con company_id cerca solo fra i
    documenti di quell'azienda e quelli senza azienda. L'avviso e' valorizzato quando la
    ricerca semantica non e' stata possibile (niente chiave, credito finito):
    la ricerca testuale da sola continua a funzionare, e la risposta parte lo
    stesso - un problema di embedding non deve mai bloccare una bozza.
    """
    query_text = (query_text or "").strip()
    if not query_text:
        return [], None

    pool = max(limit * 4, 20)
    fused, matched, similarity, warning = _hybrid_rank(db, owner_id, query_text, api_key, pool, company_id)
    if not fused:
        return [], warning

    ranked_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[: limit * 2]
    rows = (
        db.query(OmniKnowledgeChunk, OmniKnowledgeDocument)
        .join(OmniKnowledgeDocument, OmniKnowledgeDocument.id == OmniKnowledgeChunk.document_id)
        .filter(OmniKnowledgeChunk.id.in_(ranked_ids))
        .all()
    )
    by_id = {chunk.id: (chunk, document) for chunk, document in rows}

    results: List[RetrievedChunk] = []
    used = 0
    for chunk_id in ranked_ids:
        if chunk_id not in by_id:
            continue
        chunk, document = by_id[chunk_id]
        if results and used + len(chunk.content) > char_budget:
            continue
        results.append(RetrievedChunk(
            chunk_id=chunk.id, document_id=document.id, document_title=document.title,
            company=document.company, kind=document.kind, heading=chunk.heading, content=chunk.content,
            score=round(fused[chunk_id], 5), matched_by=matched.get(chunk_id, []),
            similarity=round(similarity[chunk_id], 3) if chunk_id in similarity else None,
        ))
        used += len(chunk.content)
        if len(results) >= limit:
            break
    return results, warning


# ------------------------------------------------------------------------------
# Ricerca avanzata dall'elenco: trova i documenti, per nome o per contenuto
# ------------------------------------------------------------------------------
# search() risponde "quali blocchi servono al bot per questa domanda"; questa
# risponde all'operatore "in quali file se ne parla, e dove". Stesso motore
# ibrido, ma pesca piu' blocchi, li raggruppa per documento con i passaggi
# trovati, e mette davanti a tutto i file il cui nome o titolo somiglia alla
# ricerca: chi scrive "listino 2026" vuole quel file, non i blocchi che
# parlano di listini.
FIND_POOL = 120
FIND_MAX_DOCUMENTS = 30
FIND_SNIPPETS_PER_DOCUMENT = 3
FIND_SNIPPET_CHARS = 280
# I punteggi RRF dei blocchi sono dell'ordine di 1/60: il nome vale piu' di
# qualunque somma di blocchi, cosi' un file trovato per nome sta sempre in cima.
_NAME_MATCH_SCORE = 1.0

# None = tutte le aziende, "none" = solo i documenti senza azienda, un id = solo
# quell'azienda (a differenza di search(), qui NON si aggiungono i documenti
# generali: l'operatore sta guardando dentro una cartella precisa).
CompanyScope = Union[None, str, uuid.UUID]


@dataclass
class FoundSnippet:
    heading: Optional[str]
    content: str
    matched_by: List[str]
    similarity: Optional[float]


@dataclass
class FoundDocument:
    document_id: uuid.UUID
    score: float
    matched_by: List[str]  # "nome", "testo", "significato"
    snippets: List[FoundSnippet] = field(default_factory=list)


def _name_terms(query_text: str) -> List[str]:
    return [term for term in re.findall(r"[^\W_]+", query_text.lower()) if len(term) >= 2][:10]


def _like_pattern(value: str) -> str:
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _scope_documents(query, company_scope: CompanyScope):
    if company_scope == "none":
        return query.filter(OmniKnowledgeDocument.company_id.is_(None))
    if company_scope:
        return query.filter(OmniKnowledgeDocument.company_id == company_scope)
    return query


def _in_scope(company_id: Optional[uuid.UUID], company_scope: CompanyScope) -> bool:
    if company_scope == "none":
        return company_id is None
    if company_scope:
        return company_id == company_scope
    return True


def _excerpt(content: str, terms: Sequence[str], width: int = FIND_SNIPPET_CHARS) -> str:
    """
    Il pezzo del blocco attorno alla prima parola cercata, tagliato su parole
    intere; l'inizio del blocco se nessuna parola compare (trovato per
    significato). All'operatore serve capire a colpo d'occhio perche' il file
    e' uscito, non rileggere tutto il blocco.
    """
    flat = re.sub(r"\s+", " ", content).strip()
    if len(flat) <= width:
        return flat
    lowered = flat.lower()
    positions = [pos for pos in (lowered.find(term) for term in terms) if pos >= 0]
    if not positions:
        cut = flat.rfind(" ", 0, width)
        return flat[: cut if cut > width // 2 else width].rstrip() + "…"
    start = max(min(positions) - width // 3, 0)
    end = min(start + width, len(flat))
    start = max(end - width, 0)
    if start > 0:
        space = flat.find(" ", start, start + 40)
        if space > 0:
            start = space + 1
    if end < len(flat):
        space = flat.rfind(" ", end - 40, end)
        if space > start:
            end = space
    return ("…" if start > 0 else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


def find_documents(
    db: Session,
    owner_id: uuid.UUID,
    query_text: str,
    api_key: Optional[str],
    company_scope: CompanyScope = None,
    kind: Optional[str] = None,
) -> Tuple[List[FoundDocument], Optional[str]]:
    """
    Documenti pertinenti alla ricerca, dal piu' al meno: prima quelli con il
    nome del file o il titolo che contiene la ricerca (tutta, o ogni sua
    parola), poi quelli in cui se ne parla, con fino a FIND_SNIPPETS_PER_DOCUMENT
    passaggi ciascuno. Le schede azienda restano fuori: non sono file
    dell'operatore. L'avviso e' lo stesso di search() (semantica non riuscita).
    Costa al massimo un embedding.
    """
    query_text = (query_text or "").strip()
    if not query_text:
        return [], None
    terms = _name_terms(query_text)

    # 1) Nome del file o titolo.
    base = db.query(OmniKnowledgeDocument.id).filter(
        OmniKnowledgeDocument.owner_id == owner_id, OmniKnowledgeDocument.kind != "profile",
    )
    base = _scope_documents(base, company_scope)
    if kind:
        base = base.filter(OmniKnowledgeDocument.kind == kind)
    name_field = func.lower(func.concat_ws(" ", OmniKnowledgeDocument.title, OmniKnowledgeDocument.file_name))
    conditions = [name_field.like(_like_pattern(query_text), escape="\\")]
    if terms:
        conditions.append(and_(*[name_field.like(_like_pattern(term), escape="\\") for term in terms]))
    name_ids = {row[0] for row in base.filter(or_(*conditions)).all()}

    # 2) Contenuto: il motore ibrido, con un bacino largo perche' i blocchi si
    # raggruppano per documento. Il filtro azienda del motore tiene anche i
    # documenti generali: si scartano dopo, in base alla cartella aperta.
    engine_company = company_scope if isinstance(company_scope, uuid.UUID) else None
    fused, matched, similarity, warning = _hybrid_rank(
        db, owner_id, query_text, api_key, FIND_POOL, engine_company, include_always_on=True,
    )

    found: Dict[uuid.UUID, FoundDocument] = {}
    if fused:
        rows = (
            db.query(OmniKnowledgeChunk, OmniKnowledgeDocument.kind, OmniKnowledgeDocument.company_id)
            .join(OmniKnowledgeDocument, OmniKnowledgeDocument.id == OmniKnowledgeChunk.document_id)
            .filter(OmniKnowledgeChunk.id.in_(list(fused)))
            .all()
        )
        per_document: Dict[uuid.UUID, List[OmniKnowledgeChunk]] = {}
        for chunk, document_kind, document_company in rows:
            if document_kind == "profile" or (kind and document_kind != kind) or not _in_scope(document_company, company_scope):
                continue
            per_document.setdefault(chunk.document_id, []).append(chunk)
        for document_id, chunks in per_document.items():
            chunks.sort(key=lambda c: fused[c.id], reverse=True)
            scores = [fused[c.id] for c in chunks]
            # Il blocco migliore decide, gli altri aggiungono poco: un file con
            # un passaggio centrato batte uno che sfiora l'argomento dieci volte.
            score = scores[0] + 0.25 * sum(scores[1:])
            matched_by: List[str] = []
            for chunk in chunks:
                for how in matched.get(chunk.id, []):
                    if how not in matched_by:
                        matched_by.append(how)
            snippets = [
                FoundSnippet(
                    heading=chunk.heading, content=_excerpt(chunk.content, terms), matched_by=matched.get(chunk.id, []),
                    similarity=round(similarity[chunk.id], 3) if chunk.id in similarity else None,
                )
                for chunk in chunks[:FIND_SNIPPETS_PER_DOCUMENT]
            ]
            found[document_id] = FoundDocument(document_id=document_id, score=round(score, 5), matched_by=matched_by, snippets=snippets)

    for document_id in name_ids:
        entry = found.get(document_id)
        if entry:
            entry.score = round(entry.score + _NAME_MATCH_SCORE, 5)
            entry.matched_by.insert(0, "nome")
        else:
            found[document_id] = FoundDocument(document_id=document_id, score=_NAME_MATCH_SCORE, matched_by=["nome"])

    results = sorted(found.values(), key=lambda f: f.score, reverse=True)[:FIND_MAX_DOCUMENTS]
    return results, warning


def always_on_instructions(db: Session, owner_id: uuid.UUID, company_id: Optional[uuid.UUID] = None) -> List[OmniKnowledgeDocument]:
    query = db.query(OmniKnowledgeDocument).filter(
        OmniKnowledgeDocument.owner_id == owner_id,
        OmniKnowledgeDocument.always_on.is_(True),
        OmniKnowledgeDocument.status == "ready",
    )
    if company_id:
        query = query.filter((OmniKnowledgeDocument.company_id == company_id) | OmniKnowledgeDocument.company_id.is_(None))
    return query.order_by(OmniKnowledgeDocument.created_at).all()


def format_context(chunks: Iterable[RetrievedChunk]) -> str:
    """Blocchi pertinenti per il modello, istruzioni prima dei fatti, ognuno con la sua provenienza."""
    chunks = list(chunks)
    instructions = [c for c in chunks if c.kind == "instruction"]
    facts = [c for c in chunks if c.kind != "instruction"]
    sections = []
    if instructions:
        body = "\n\n".join(f"[{c.heading or c.document_title}]\n{c.content}" for c in instructions)
        sections.append(f"ISTRUZIONI DELL'AZIENDA PERTINENTI A QUESTO MESSAGGIO (seguile):\n{body}")
    if facts:
        body = "\n\n".join(f"[{c.heading or c.document_title}]\n{c.content}" for c in facts)
        sections.append(f"INFORMAZIONI DALLA KNOWLEDGE BASE:\n{body}")
    return "\n\n".join(sections)
