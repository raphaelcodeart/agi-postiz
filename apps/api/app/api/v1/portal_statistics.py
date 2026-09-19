"""
Statistiche del promoter, dentro il suo portale.

Stesso modulo Statistiche dell'amministratore (docs/STATISTICS.md), ristretto a
un solo utente: quello del token. Non e' una seconda implementazione delle
aggregazioni - chiama gli stessi ``statistics_service.build_user_detail`` /
``build_channel_detail`` che alimentano le pagine admin, passando
``current_user.id``. Cosi' i numeri che il promoter vede e quelli che
l'amministratore vede per lui non possono divergere: sono la stessa funzione
sulle stesse righe ``stat_post_metrics``.

Regola invariante di tutto il portale (vedi il docstring di portal.py): l'id
utente viene dal token validato, mai da un parametro di path o di body. Qui non
esiste nemmeno un endpoint che accetti uno ``user_id`` - il drill-down per il
promoter e' "io -> mio canale -> mio post", non "utente -> canale -> post".

Router separato da portal.py solo per dimensione: e' montato sullo stesso
prefisso ``/api/v1/portal`` e usa la stessa dipendenza di autenticazione.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.portal import get_current_portal_user
from app.db.session import get_db
from app.models.statistics import StatSyncRun
from app.models.user import User
from app.schemas.schemas import (
    StatChannelDetailResponse,
    StatSyncDispatchResponse,
    StatSyncRunResponse,
    StatUserDetailResponse,
)
from app.services import statistics_service
from app.services.xlsx_export import METRIC_HEADERS, build_xlsx, metric_values, xlsx_response
from app.tasks.statistics import sync_user_statistics_task

router = APIRouter()

# Stati di uno StatSyncRun che non e' ancora finito.
IN_FLIGHT_SYNC_STATUSES = ("queued", "running")


def _safe_filename(stem: str) -> str:
    """Nome file dell'export a partire da un nome scelto dall'utente (il nome
    del canale arriva dal social, non da noi). Tiene solo caratteri innocui:
    virgolette e newline nel nome finirebbero dentro l'header
    Content-Disposition."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem.strip().lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:60] or "statistiche"


# ==============================================================================
# Lettura (nessuna chiamata al provider: solo dati gia' sincronizzati)
# ==============================================================================
@router.get("/statistics", response_model=StatUserDetailResponse)
def get_my_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Totali del promoter, i suoi canali con i mini-totali per riga e le due serie
    storiche (mensile/annuale) - lo stesso payload della pagina admin
    ``/statistics/users/{id}``, per l'utente del token.

    ``build_user_detail`` restituisce sempre un risultato per un utente che
    esiste (liste vuote se non c'e' ancora nulla di sincronizzato), quindi qui
    un None significherebbe soltanto utente cancellato - caso gia' escluso dalla
    dipendenza di autenticazione, che non risolve un utente con deleted_at.
    """
    data = statistics_service.build_user_detail(db, current_user.id)
    if not data:
        raise HTTPException(status_code=404, detail="Statistiche non disponibili")
    return data


@router.get("/statistics/channels/{channel_id}", response_model=StatChannelDetailResponse)
def get_my_channel_statistics(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Un canale del promoter e i suoi post, uno per riga con le metriche.

    ``build_channel_detail`` verifica che il canale appartenga davvero a questo
    utente (join canale -> organizzazione -> connessione -> utente), quindi un
    id di un canale altrui risponde 404 come uno inesistente - non c'e' modo di
    distinguerli dall'esterno, che e' esattamente quello che si vuole.
    """
    data = statistics_service.build_channel_detail(db, current_user.id, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Canale non trovato")
    return data


# ==============================================================================
# Sincronizzazione self-service (solo sui propri post)
# ==============================================================================
@router.post("/statistics/sync", response_model=StatSyncDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_my_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Aggiorna le statistiche dei propri post.

    Identico al bottone "Sincronizza utente" dell'amministratore - stesso task,
    stesso ``scope="user"`` sul proprio id - quindi eredita senza aggiungere
    nulla le due protezioni che rendono sostenibile metterlo in mano a ogni
    promoter (docs/STATISTICS.md ss4): la guardia anti-spreco, per cui un post
    gia' scaricato nelle ultime 20 ore viene saltato e non costa nessuna
    chiamata al provider, e il RateLimiter Redis per connessione, che impedisce
    a questo sync di competere con una campagna in corso di pubblicazione sulla
    stessa API key.

    In piu', qui c'e' una cosa che il bottone admin non ha bisogno di avere: se
    un run dell'utente e' gia' in corso viene restituito quello invece di
    crearne un secondo. Un amministratore preme il suo bottone una volta e
    guarda la barra; una pagina pubblica aperta su un telefono viene ricaricata,
    il bottone viene ripremuto, e senza questo ogni click lascerebbe dietro di
    se' un run in piu' da seguire in polling.
    """
    existing = (
        db.query(StatSyncRun)
        .filter(
            StatSyncRun.scope == "user",
            StatSyncRun.scope_user_id == current_user.id,
            StatSyncRun.status.in_(IN_FLIGHT_SYNC_STATUSES),
        )
        .order_by(StatSyncRun.started_at.desc())
        .first()
    )
    if existing:
        return StatSyncDispatchResponse(
            sync_run_id=existing.id, message="Aggiornamento gia' in corso"
        )

    run = StatSyncRun(
        scope="user",
        scope_user_id=current_user.id,
        triggered_by_user_id=current_user.id,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    sync_user_statistics_task.delay(str(run.id), str(current_user.id))
    return StatSyncDispatchResponse(sync_run_id=run.id, message="Aggiornamento avviato")


@router.get("/statistics/sync/{sync_run_id}", response_model=StatSyncRunResponse)
def get_my_sync_run(
    sync_run_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """Progresso di un aggiornamento, per il polling del bottone. Il filtro su
    ``scope_user_id`` e' il controllo di accesso: il run di un altro promoter
    non e' leggibile, nemmeno conoscendone l'id."""
    run = (
        db.query(StatSyncRun)
        .filter(
            StatSyncRun.id == sync_run_id,
            StatSyncRun.scope_user_id == current_user.id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Aggiornamento non trovato")
    return run


# ==============================================================================
# Export Excel (stesse colonne degli export dell'amministratore)
# ==============================================================================
@router.get("/statistics/export.xlsx")
def export_my_statistics_xlsx(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """Un foglio con una riga per canale - la controparte per il promoter di
    ``/statistics/export/users/{id}.xlsx``."""
    data = statistics_service.build_user_detail(db, current_user.id)
    if not data:
        raise HTTPException(status_code=404, detail="Statistiche non disponibili")

    headers = ["Canale", "Username", "Piattaforma", "Post", *METRIC_HEADERS, "Ultima sincronizzazione"]
    rows = [
        [
            c["channel_name"],
            c["username"] or "",
            c["platform"],
            c["post_count"],
            *metric_values(c["totals"]),
            c["last_synced_at"],
        ]
        for c in data["channels"]
    ]
    content = build_xlsx("Le mie statistiche", headers, rows)
    return xlsx_response(content, f"statistiche-{_safe_filename(data['user_name'])}.xlsx")


@router.get("/statistics/channels/{channel_id}/export.xlsx")
def export_my_channel_xlsx(
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """Un foglio con una riga per post di quel canale."""
    data = statistics_service.build_channel_detail(db, current_user.id, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Canale non trovato")

    headers = ["Campagna", "Piattaforma", "Pubblicato il", "Link post", *METRIC_HEADERS, "Ultima sincronizzazione"]
    rows = [
        [
            p["campaign_title"],
            p["platform"],
            p["published_at"],
            p["external_post_url"] or "",
            *metric_values(p["metrics"]),
            p["last_synced_at"],
        ]
        for p in data["posts"]
    ]
    content = build_xlsx("Post del canale", headers, rows)
    return xlsx_response(content, f"statistiche-{_safe_filename(data['channel_name'])}.xlsx")
