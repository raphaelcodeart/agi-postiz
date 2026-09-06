import os
import uuid
import hashlib
import json
import subprocess
import shutil
from typing import Dict, Any, Tuple, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.media import MediaFile
from app.models.campaign import Campaign

class MediaService:
    @staticmethod
    def calculate_checksum(file_path: str) -> str:
        """Calculate SHA-256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @classmethod
    def validate_and_save_upload(cls, db: Session, upload_file: UploadFile) -> MediaFile:
        """
        Validates the uploaded file size and MIME type, saves it with a UUID-based
        filename to the persistent media storage directory, and creates a database record.
        """
        # 1. Read size and validate
        upload_file.file.seek(0, os.SEEK_END)
        size_bytes = upload_file.file.tell()
        upload_file.file.seek(0)
        
        if size_bytes > settings.UPLOAD_MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds maximum upload size of {settings.UPLOAD_MAX_SIZE_BYTES / (1024*1024):.1f}MB"
            )

        # 2. Validate MIME type
        mime_type = upload_file.content_type or "application/octet-stream"
        allowed_mimes = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "video/mp4", "video/quicktime", "video/x-matroska", "video/webm"
        ]
        
        if mime_type not in allowed_mimes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {mime_type}. Allowed types are images and videos."
            )

        # 3. Create unique storage filenames
        original_filename = upload_file.filename or "unnamed_media"
        _, ext = os.path.splitext(original_filename)
        if not ext:
            # Fallback extension
            ext = ".mp4" if "video" in mime_type else ".jpg"
            
        stored_filename = f"{uuid.uuid4()}{ext}"
        storage_key = os.path.join(settings.MEDIA_STORAGE_DIR, stored_filename)
        
        # Ensure target folder exists
        os.makedirs(settings.MEDIA_STORAGE_DIR, exist_ok=True)

        # 4. Save file to disk
        try:
            with open(storage_key, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write file to disk: {str(e)}")

        # 5. Calculate checksum
        checksum = cls.calculate_checksum(storage_key)
        
        # 6. Generate public URL mapping (served by the "media" nginx vhost,
        # see infrastructure/nginx/nginx.conf)
        public_url = f"{settings.PUBLIC_MEDIA_BASE_URL}/uploads/{stored_filename}"

        media_file = MediaFile(
            original_filename=original_filename,
            stored_filename=stored_filename,
            storage_key=storage_key,
            public_url=public_url,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            processing_status="uploaded",
            validation_status="pending",
        )
        db.add(media_file)
        db.commit()
        db.refresh(media_file)
        return media_file

    @classmethod
    def inspect_media_file(cls, file_path: str) -> Dict[str, Any]:
        """
        Executes ffprobe to inspect video/image metadata.
        Returns a dict of extracted properties.
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            metadata = {}
            streams = info.get("streams", [])
            format_info = info.get("format", {})
            
            # Find video/image stream
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
            
            if video_stream:
                metadata["width"] = int(video_stream.get("width", 0))
                metadata["height"] = int(video_stream.get("height", 0))
                metadata["video_codec"] = video_stream.get("codec_name")
                
                # Check aspect ratio
                dar = video_stream.get("display_aspect_ratio")
                if dar and dar != "0:1":
                    metadata["aspect_ratio"] = dar
                elif metadata["width"] and metadata["height"]:
                    # calculate decimal aspect ratio
                    gcd = cls._gcd(metadata["width"], metadata["height"])
                    metadata["aspect_ratio"] = f"{metadata['width']//gcd}:{metadata['height']//gcd}"
                
                # Duration
                duration = video_stream.get("duration") or format_info.get("duration")
                if duration:
                    metadata["duration_seconds"] = float(duration)
            
            if audio_stream:
                metadata["audio_codec"] = audio_stream.get("codec_name")
                
            metadata["raw_info"] = info
            return metadata
        except Exception as e:
            return {"error": f"Failed to execute ffprobe: {str(e)}"}

    @classmethod
    def generate_video_thumbnail(cls, video_path: str, thumbnail_filename: str) -> Optional[str]:
        """
        Runs ffmpeg to extract a frame at 1-second timestamp for the video thumbnail.
        """
        os.makedirs(settings.THUMBNAIL_STORAGE_DIR, exist_ok=True)
        thumbnail_path = os.path.join(settings.THUMBNAIL_STORAGE_DIR, thumbnail_filename)
        
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            thumbnail_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return thumbnail_path
        except Exception:
            # Try capturing frame at 00:00:00 if 00:00:01 fails (e.g. video is very short)
            cmd[2] = "00:00:00"
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                return thumbnail_path
            except Exception:
                return None

    @classmethod
    def run_media_inspection_task(cls, db: Session, media_id: uuid.UUID) -> None:
        """
        Inspects the media, extracts properties, creates thumbnails, and updates state.
        This is intended to run inside a Celery task.
        """
        media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media:
            return

        media.processing_status = "inspecting"
        db.flush()

        if not os.path.exists(media.storage_key):
            media.processing_status = "failed"
            media.validation_status = "invalid"
            media.validation_errors = [{"error": "Physical file missing on disk"}]
            db.commit()
            return

        metadata = cls.inspect_media_file(media.storage_key)
        
        if "error" in metadata:
            # ffprobe failed, let's fallback to standard properties for images
            if "image" in media.mime_type:
                # Basic check, set defaults
                media.processing_status = "ready"
                media.validation_status = "valid"
            else:
                media.processing_status = "failed"
                media.validation_status = "invalid"
                media.validation_errors = [{"error": metadata["error"]}]
            db.commit()
            return

        # Update metadata properties
        media.width = metadata.get("width")
        media.height = metadata.get("height")
        media.duration_seconds = metadata.get("duration_seconds")
        media.aspect_ratio = metadata.get("aspect_ratio")
        media.video_codec = metadata.get("video_codec")
        media.audio_codec = metadata.get("audio_codec")
        media.metadata_json = metadata.get("raw_info")

        # Generate thumbnail for videos
        if "video" in media.mime_type and media.duration_seconds:
            thumb_name = f"thumb_{media.id}.jpg"
            thumb_path = cls.generate_video_thumbnail(media.storage_key, thumb_name)
            if thumb_path:
                media.metadata_json = {
                    **(media.metadata_json or {}),
                    "thumbnail_path": thumb_path,
                    "thumbnail_url": f"{settings.PUBLIC_MEDIA_BASE_URL}/thumbnails/{thumb_name}"
                }

        media.processing_status = "ready"
        media.validation_status = "valid"
        db.commit()

    @classmethod
    def delete_media_safely(cls, db: Session, media_id: uuid.UUID) -> bool:
        """
        Deletes the media file both on disk and in database only if there are no campaigns
        actively referencing it.
        """
        media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media:
            return False

        # Check references in campaigns (exclude completed or cancelled campaigns)
        referenced_campaigns = db.query(Campaign).filter(
            Campaign.media_file_id == media_id,
            Campaign.status.notin_(["completed", "cancelled", "draft"])
        ).count()

        if referenced_campaigns > 0:
            raise ValueError(f"Cannot delete media as it is actively used in {referenced_campaigns} running campaigns.")

        # Delete physical file
        if os.path.exists(media.storage_key):
            try:
                os.remove(media.storage_key)
            except Exception:
                pass # Proceed to clean up DB record

        # Delete thumbnail if any
        if media.metadata_json and "thumbnail_path" in media.metadata_json:
            thumb_path = media.metadata_json["thumbnail_path"]
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass

        # Remove from database
        db.delete(media)
        db.commit()
        return True

    @staticmethod
    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a
