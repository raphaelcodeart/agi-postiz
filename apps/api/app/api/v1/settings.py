import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.ai_settings import AISettings
from app.core.config import settings
from app.core.security import EncryptionService
from app.integrations.openai.client import validate_api_key
from app.schemas.schemas import (
    SystemSettingsResponse,
    SystemSettingsUpdate,
    HealthResponse,
    AISettingsResponse,
    AISettingsUpdateRequest,
)

router = APIRouter()

@router.get("/", response_model=SystemSettingsResponse)
def get_system_settings(
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve system configuration limits and concurrency properties."""
    # We fetch limits from Redis if updated, otherwise fallback to config values
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    global_limit = r.get("settings:global_concurrency_limit")
    conn_limit = r.get("settings:concurrent_jobs_per_connection")
    pause = r.get("settings:pause_between_requests_seconds")
    max_att = r.get("settings:max_publication_attempts")
    max_size = r.get("settings:upload_max_size_bytes")
    
    return {
        "global_concurrency_limit": int(global_limit) if global_limit else settings.GLOBAL_CONCURRENCY_LIMIT,
        "concurrent_jobs_per_connection": int(conn_limit) if conn_limit else settings.CONCURRENT_JOBS_PER_CONNECTION,
        "pause_between_requests_seconds": int(pause) if pause else settings.PAUSE_BETWEEN_REQUESTS_SECONDS,
        "max_publication_attempts": int(max_att) if max_att else settings.MAX_PUBLICATION_ATTEMPTS,
        "upload_max_size_bytes": int(max_size) if max_size else settings.UPLOAD_MAX_SIZE_BYTES,
        "buffer_integration_mode": settings.BUFFER_INTEGRATION_MODE,
        "celery_queue_health": "ok"
    }


@router.put("/", response_model=SystemSettingsResponse)
def update_system_settings(
    payload: SystemSettingsUpdate,
    admin: Administrator = Depends(get_current_admin)
):
    """Updates active processing parameters inside Redis, instantly updating background worker configs."""
    r = redis.from_url(settings.REDIS_URL)
    
    r.set("settings:global_concurrency_limit", payload.global_concurrency_limit)
    r.set("settings:concurrent_jobs_per_connection", payload.concurrent_jobs_per_connection)
    r.set("settings:pause_between_requests_seconds", payload.pause_between_requests_seconds)
    r.set("settings:max_publication_attempts", payload.max_publication_attempts)
    r.set("settings:upload_max_size_bytes", payload.upload_max_size_bytes)
    
    return {
        "global_concurrency_limit": payload.global_concurrency_limit,
        "concurrent_jobs_per_connection": payload.concurrent_jobs_per_connection,
        "pause_between_requests_seconds": payload.pause_between_requests_seconds,
        "max_publication_attempts": payload.max_publication_attempts,
        "upload_max_size_bytes": payload.upload_max_size_bytes,
        "buffer_integration_mode": settings.BUFFER_INTEGRATION_MODE,
        "celery_queue_health": "ok"
    }


@router.get("/ai", response_model=AISettingsResponse)
def get_ai_settings(
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Reports only whether an OpenAI key is configured and which model is set -
    never the key itself (same principle as never exposing Buffer tokens to
    the frontend, AGENTS.md rule 8).
    """
    row = db.query(AISettings).first()
    return {
        "configured": bool(row and row.openai_api_key_encrypted),
        "model": row.openai_model if row else settings.OPENAI_MODEL,
    }


@router.put("/ai", response_model=AISettingsResponse)
def update_ai_settings(
    payload: AISettingsUpdateRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Sets/replaces the admin's own OpenAI API key and/or model for the AI text-generation helper."""
    row = db.query(AISettings).first()
    if not row:
        row = AISettings()
        db.add(row)

    if payload.openai_api_key:
        if not validate_api_key(payload.openai_api_key):
            raise HTTPException(status_code=400, detail="Chiave API OpenAI non valida")
        row.openai_api_key_encrypted = EncryptionService.encrypt(payload.openai_api_key)

    if payload.openai_model:
        row.openai_model = payload.openai_model

    db.commit()
    db.refresh(row)
    return {
        "configured": bool(row.openai_api_key_encrypted),
        "model": row.openai_model,
    }


@router.delete("/ai", status_code=204)
def delete_ai_settings(
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Removes the configured OpenAI key. The "Genera con AI" button then falls back to the
    server's OPENAI_API_KEY env var if set, otherwise it errors until reconfigured."""
    row = db.query(AISettings).first()
    if row:
        row.openai_api_key_encrypted = None
        db.commit()
    return


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint validating databases, cache and Celery connections."""
    db_status = "ok"
    redis_status = "ok"
    celery_status = "ok"
    
    # 1. Check DB connection
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "failed"
        
    # 2. Check Redis connection
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
    except Exception:
        redis_status = "failed"
        
    # 3. Check Celery connections
    try:
        from app.workers.celery_app import celery
        inspector = celery.control.inspect()
        # If worker is active, ping returns list/dict
        ping_res = inspector.ping()
        if not ping_res:
            celery_status = "inactive"
    except Exception:
        celery_status = "failed"
        
    status_code = 200
    if "failed" in (db_status, redis_status):
        status_code = 503
        
    return HealthResponse(
        status="healthy" if status_code == 200 else "unhealthy",
        database=db_status,
        redis=redis_status,
        celery_worker=celery_status,
        timestamp=datetime.now(timezone.utc)
    )
