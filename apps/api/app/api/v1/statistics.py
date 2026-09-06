import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_admin
from app.db.session import get_db
from app.integrations.buffer.exceptions import BufferApiError
from app.models.administrator import Administrator
from app.models.campaign import Campaign
from app.models.publication import Publication
from app.models.statistics import StatSyncRun
from app.models.user import User
from app.schemas.schemas import (
    StatChannelDetailResponse,
    StatDashboardResponse,
    StatPostRow,
    StatSyncDispatchResponse,
    StatSyncRunResponse,
    StatUserDetailResponse,
)
from app.services import statistics_service
from app.services.statistics_service import ALL_METRIC_COLUMNS
from app.services.xlsx_export import build_xlsx
from app.tasks.statistics import (
    SyncBusyError,
    sync_all_statistics_task,
    sync_campaign_statistics_task,
    sync_publication_now,
    sync_user_statistics_task,
)

router = APIRouter()

METRIC_COLUMN_LABELS: dict[str, str] = {
    "reactions": "Reazioni",
    "likes": "Mi piace (Facebook)",
    "views": "Visualizzazioni",
    "impressions": "Impression",
    "reach": "Copertura",
    "follows": "Nuovi iscritti",
    "clicks": "Clic",
    "comments": "Commenti",
    "shares": "Condivisioni",
    "engagement_rate": "Tasso di coinvolgimento (%)",
}
METRIC_HEADERS: list[str] = [METRIC_COLUMN_LABELS[c] for c in ALL_METRIC_COLUMNS]


def _metric_values(totals: dict[str, Any]) -> list[Any]:
    return [totals.get(c) for c in ALL_METRIC_COLUMNS]


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# Dashboard / drill-down (sola lettura sui dati gia' sincronizzati)
# ==============================================================================
@router.get("/dashboard", response_model=StatDashboardResponse)
def get_dashboard(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return statistics_service.build_dashboard(db)


@router.get("/users/{user_id}", response_model=StatUserDetailResponse)
def get_user_statistics(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    data = statistics_service.build_user_detail(db, user_id)
    if not data:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return data


@router.get("/users/{user_id}/channels/{channel_id}", response_model=StatChannelDetailResponse)
def get_channel_statistics(
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    data = statistics_service.build_channel_detail(db, user_id, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Canale non trovato per questo utente")
    return data


# ==============================================================================
# Sincronizzazione (3 livelli: utente, campagna, tutti) + refresh singolo post
# ==============================================================================
@router.post("/sync/users/{user_id}", response_model=StatSyncDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_user_statistics(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    run = StatSyncRun(scope="user", scope_user_id=user_id, triggered_by=admin.id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)

    sync_user_statistics_task.delay(str(run.id), str(user_id))
    return StatSyncDispatchResponse(sync_run_id=run.id, message="Sincronizzazione dell'utente avviata")


@router.post(
    "/sync/campaigns/{campaign_id}", response_model=StatSyncDispatchResponse, status_code=status.HTTP_202_ACCEPTED
)
def sync_campaign_statistics(
    campaign_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagna non trovata")

    run = StatSyncRun(scope="campaign", scope_campaign_id=campaign_id, triggered_by=admin.id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)

    sync_campaign_statistics_task.delay(str(run.id), str(campaign_id))
    return StatSyncDispatchResponse(sync_run_id=run.id, message="Sincronizzazione della campagna avviata")


@router.post("/sync/all", response_model=StatSyncDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_all_statistics(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    run = StatSyncRun(scope="global", triggered_by=admin.id, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)

    sync_all_statistics_task.delay(str(run.id))
    return StatSyncDispatchResponse(sync_run_id=run.id, message="Sincronizzazione generale avviata")


@router.get("/sync/{sync_run_id}", response_model=StatSyncRunResponse)
def get_sync_run(
    sync_run_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    run = db.query(StatSyncRun).filter(StatSyncRun.id == sync_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Sincronizzazione non trovata")
    return run


@router.post("/posts/{publication_id}/sync", response_model=StatPostRow)
def sync_single_post(
    publication_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    """Refresh sincrono di un solo post (bottone "aggiorna" per riga nel
    drill-down canale) - bypassa la guardia anti-spreco perche' e' un'azione
    esplicita su un singolo post, non uno scope ampio."""
    pub = db.query(Publication).filter(Publication.id == publication_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Pubblicazione non trovata")
    if pub.status not in ("published", "scheduled") or not pub.external_post_id:
        raise HTTPException(
            status_code=400,
            detail="Le statistiche sono disponibili solo per pubblicazioni riuscite (pubblicate o programmate).",
        )

    try:
        row = sync_publication_now(db, pub)
    except SyncBusyError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except BufferApiError as e:
        raise HTTPException(status_code=502, detail=e.message)

    return StatPostRow(
        publication_id=row.publication_id,
        campaign_id=row.campaign_id,
        campaign_title=pub.campaign.title if pub.campaign else "—",
        platform=row.platform,
        external_post_url=row.external_post_url,
        published_at=row.published_at,
        metrics={c: getattr(row, c) for c in ALL_METRIC_COLUMNS},
        last_synced_at=row.last_synced_at,
        last_sync_error=row.last_sync_error,
    )


# ==============================================================================
# Export Excel
# ==============================================================================
@router.get("/export/dashboard.xlsx")
def export_dashboard_xlsx(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    data = statistics_service.build_dashboard(db)
    headers = ["Utente", "Azienda", "Canali", "Post", *METRIC_HEADERS, "Ultima sincronizzazione"]
    rows = [
        [
            u["user_name"],
            u["company_name"] or "",
            u["channel_count"],
            u["post_count"],
            *_metric_values(u["totals"]),
            u["last_synced_at"],
        ]
        for u in data["users"]
    ]
    content = build_xlsx("Statistiche generali", headers, rows)
    return _xlsx_response(content, "statistiche-generali.xlsx")


@router.get("/export/users/{user_id}.xlsx")
def export_user_xlsx(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)
):
    data = statistics_service.build_user_detail(db, user_id)
    if not data:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    headers = ["Canale", "Username", "Piattaforma", "Post", *METRIC_HEADERS, "Ultima sincronizzazione"]
    rows = [
        [
            c["channel_name"],
            c["username"] or "",
            c["platform"],
            c["post_count"],
            *_metric_values(c["totals"]),
            c["last_synced_at"],
        ]
        for c in data["channels"]
    ]
    content = build_xlsx("Statistiche utente", headers, rows)
    filename = f"statistiche-{data['user_name'].replace(' ', '-').lower()}.xlsx"
    return _xlsx_response(content, filename)


@router.get("/export/users/{user_id}/channels/{channel_id}.xlsx")
def export_channel_xlsx(
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    data = statistics_service.build_channel_detail(db, user_id, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Canale non trovato per questo utente")

    headers = ["Campagna", "Piattaforma", "Pubblicato il", "Link post", *METRIC_HEADERS, "Ultima sincronizzazione"]
    rows = [
        [
            p["campaign_title"],
            p["platform"],
            p["published_at"],
            p["external_post_url"] or "",
            *_metric_values(p["metrics"]),
            p["last_synced_at"],
        ]
        for p in data["posts"]
    ]
    content = build_xlsx("Post del canale", headers, rows)
    filename = f"statistiche-{data['channel_name'].replace(' ', '-').lower()}.xlsx"
    return _xlsx_response(content, filename)
