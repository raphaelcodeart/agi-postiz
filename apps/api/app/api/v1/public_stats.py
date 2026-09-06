"""Public, unauthenticated read-only statistics for the marketing site
(agimarketing.app) - see docs/STATISTICS.md §5.

Deliberately outside get_current_admin: this router exposes aggregate-only
totals (per platform, never per user/channel - see
statistics_service.build_public_summary) so the public site can render a
real, self-updating results chart without exposing any client's identity or
individual numbers.

CORS is handled by hand here (a fixed origin allow-list, no credentials)
instead of through the app-wide CORSMiddleware in main.py: that middleware
stays scoped to the authenticated app origins with allow_credentials=True,
and this endpoint - which has no session/cookie check of its own - must
never ride on that credentialed configuration.
"""
from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import PublicStatsResponse
from app.services import statistics_service

router = APIRouter()

_ALLOWED_ORIGINS = {
    "https://agimarketing.app",
    "https://www.agimarketing.app",
}


@router.get("", response_model=PublicStatsResponse)
def get_public_stats(
    response: Response,
    origin: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Cache-Control"] = "public, max-age=300"
    return statistics_service.build_public_summary(db)
