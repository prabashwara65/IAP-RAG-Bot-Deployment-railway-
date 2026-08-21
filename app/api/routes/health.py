"""Phase 0 health and readiness endpoints."""

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["service-status"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report application process health without checking future services."""
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    """Report Phase 0 readiness after typed configuration has loaded."""
    _settings: Settings = request.app.state.settings
    return ReadinessResponse(status="ready")
