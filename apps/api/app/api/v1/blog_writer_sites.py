import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.blog_writer import WordpressSite
from app.core.security import EncryptionService
from app.integrations.wordpress import client as wp_client
from app.integrations.wordpress.exceptions import WordpressApiError
from app.schemas.schemas import (
    WordpressSiteCreate,
    WordpressSiteUpdate,
    WordpressSiteResponse,
    WordpressOptionItem,
    WordpressTestConnectionResponse,
)

router = APIRouter()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/", response_model=List[WordpressSiteResponse])
def list_sites(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    return db.query(WordpressSite).order_by(WordpressSite.created_at.desc()).all()


@router.post("/", response_model=WordpressSiteResponse, status_code=201)
def create_site(
    payload: WordpressSiteCreate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Validates the URL (SSRF guard, see integrations/wordpress/client.py) and
    the credentials against the real site before saving - same UX precedent as
    Buffer's POST /connections and OpenAI's PUT /settings/ai.
    """
    try:
        wp_client.validate_public_url(payload.api_url)
        wp_client.test_connection(payload.api_url, payload.username, payload.application_password)
    except WordpressApiError as e:
        raise HTTPException(status_code=400, detail=f"Impossibile collegarsi al sito: {e.message}")

    site = WordpressSite(
        user_id=payload.user_id,
        name=payload.name,
        site_url=payload.site_url,
        api_url=payload.api_url.rstrip("/"),
        username=payload.username,
        encrypted_application_password=EncryptionService.encrypt(payload.application_password),
        default_author_id=payload.default_author_id,
        default_category_id=payload.default_category_id,
        default_status=payload.default_status,
        language=payload.language,
        connection_status="connected",
        last_connection_test_at=utc_now(),
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.get("/{site_id}", response_model=WordpressSiteResponse)
def get_site(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = db.query(WordpressSite).filter(WordpressSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sito WordPress non trovato")
    return site


@router.put("/{site_id}", response_model=WordpressSiteResponse)
def update_site(
    site_id: uuid.UUID,
    payload: WordpressSiteUpdate,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    site = db.query(WordpressSite).filter(WordpressSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sito WordPress non trovato")

    data = payload.model_dump(exclude_unset=True, exclude={"application_password"})
    for key, value in data.items():
        setattr(site, key, value)

    if payload.application_password:
        site.encrypted_application_password = EncryptionService.encrypt(payload.application_password)
        site.connection_status = "untested"

    db.commit()
    db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = db.query(WordpressSite).filter(WordpressSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sito WordPress non trovato")
    db.delete(site)
    db.commit()
    return


@router.post("/{site_id}/test-connection", response_model=WordpressTestConnectionResponse)
def test_site_connection(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = db.query(WordpressSite).filter(WordpressSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sito WordPress non trovato")

    password = EncryptionService.decrypt(site.encrypted_application_password)
    site.last_connection_test_at = utc_now()
    try:
        result = wp_client.test_connection(site.api_url, site.username, password)
        site.connection_status = "connected"
        site.last_connection_error = None
        db.commit()
        return {"success": True, "message": "Connessione riuscita", "wp_user_name": result.get("name")}
    except WordpressApiError as e:
        site.connection_status = "error"
        site.last_connection_error = e.message
        db.commit()
        return {"success": False, "message": e.message, "wp_user_name": None}


@router.get("/{site_id}/categories", response_model=List[WordpressOptionItem])
def get_site_categories(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = _get_site_or_404(db, site_id)
    password = EncryptionService.decrypt(site.encrypted_application_password)
    try:
        return wp_client.get_categories(site.api_url, site.username, password)
    except WordpressApiError as e:
        raise HTTPException(status_code=502, detail=e.message)


@router.get("/{site_id}/authors", response_model=List[WordpressOptionItem])
def get_site_authors(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = _get_site_or_404(db, site_id)
    password = EncryptionService.decrypt(site.encrypted_application_password)
    try:
        return wp_client.get_authors(site.api_url, site.username, password)
    except WordpressApiError as e:
        raise HTTPException(status_code=502, detail=e.message)


@router.get("/{site_id}/tags", response_model=List[WordpressOptionItem])
def get_site_tags(site_id: uuid.UUID, db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    site = _get_site_or_404(db, site_id)
    password = EncryptionService.decrypt(site.encrypted_application_password)
    try:
        return wp_client.get_tags(site.api_url, site.username, password)
    except WordpressApiError as e:
        raise HTTPException(status_code=502, detail=e.message)


def _get_site_or_404(db: Session, site_id: uuid.UUID) -> WordpressSite:
    site = db.query(WordpressSite).filter(WordpressSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sito WordPress non trovato")
    return site
