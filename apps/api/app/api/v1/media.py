import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.models.media import MediaFile
from app.services.media_service import MediaService
from app.tasks.media import inspect_media_task
from app.schemas.schemas import MediaResponse, MediaRenameRequest

router = APIRouter()

@router.get("/", response_model=List[MediaResponse])
def list_media(
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve all active media resources."""
    return db.query(MediaFile).filter(MediaFile.deleted_at.is_(None)).order_by(MediaFile.created_at.desc()).all()


@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Handles secure media uploads. Saves file to persistent storage, 
    creates database record, and queues inspection.
    """
    media_file = MediaService.validate_and_save_upload(db, file)
    
    # Enqueue metadata inspection and thumbnail generation
    inspect_media_task.delay(str(media_file.id))
    
    return media_file


@router.get("/{media_id}", response_model=MediaResponse)
def get_media_detail(
    media_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """Retrieve detailed metadata for a single media asset."""
    media = db.query(MediaFile).filter(MediaFile.id == media_id, MediaFile.deleted_at.is_(None)).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media file not found")
    return media


@router.patch("/{media_id}", response_model=MediaResponse)
def rename_media(
    media_id: uuid.UUID,
    payload: MediaRenameRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Renames the display name only (original_filename). Never touches
    stored_filename/storage_key/public_url - the physical file on disk and its
    URL stay exactly as they are, so this can't ever break an already-referenced
    media (campaigns, Buffer post URLs already sent).
    """
    media = db.query(MediaFile).filter(MediaFile.id == media_id, MediaFile.deleted_at.is_(None)).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media file not found")
    media.original_filename = payload.original_filename.strip()
    db.commit()
    db.refresh(media)
    return media


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    media_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Safely deletes a media file. If active campaigns reference the media, 
    the deletion is rejected.
    """
    try:
        success = MediaService.delete_media_safely(db, media_id)
        if not success:
            raise HTTPException(status_code=404, detail="Media file not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return
