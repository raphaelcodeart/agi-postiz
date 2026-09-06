from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.ai_settings import AISettings
from app.core.security import EncryptionService
from app.core.config import settings


def get_openai_credentials(db: Session) -> Tuple[Optional[str], str]:
    """
    Returns (api_key, model). The admin-configured key from the ai_settings
    table (Settings page) always wins when present; the .env OPENAI_API_KEY is
    only a first-run/deployment-wide fallback so the feature keeps working
    without every admin having to configure their own key immediately.
    """
    row = db.query(AISettings).first()
    if row and row.openai_api_key_encrypted:
        key = EncryptionService.decrypt(row.openai_api_key_encrypted)
        if key:
            return key, row.openai_model or settings.OPENAI_MODEL

    model = row.openai_model if row and row.openai_model else settings.OPENAI_MODEL
    return settings.OPENAI_API_KEY, model
