from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.auth import get_current_admin
from app.models.administrator import Administrator
from app.integrations.openai.client import generate_campaign_text
from app.integrations.openai.exceptions import OpenAIApiError
from app.services.ai_settings_service import get_openai_credentials
from app.schemas.schemas import AIGenerateTextRequest, AIGenerateTextResponse

router = APIRouter()


@router.post("/generate-campaign-text", response_model=AIGenerateTextResponse)
def generate_campaign_text_endpoint(
    payload: AIGenerateTextRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin)
):
    """
    Drafts campaign copy for every platform-specific text field from a topic
    description, via OpenAI. Purely a writing aid for the campaign wizard - the
    admin can freely edit every field afterward, nothing is saved by this call.
    """
    api_key, model = get_openai_credentials(db)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Generazione AI non configurata: collega una chiave API OpenAI in Impostazioni."
        )

    try:
        result = generate_campaign_text(
            api_key, model, payload.topic, payload.include_referral_link, payload.include_personal_contacts
        )
    except OpenAIApiError as e:
        raise HTTPException(status_code=502, detail=e.message)

    return result
