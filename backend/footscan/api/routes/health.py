import logging

from fastapi import APIRouter

from footscan.api.schemas import HealthResponse
from footscan.ml.model import ModelLoadError, get_model

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Unauthenticated liveness/readiness probe. Verifies the model can load."""
    try:
        _, device = get_model()
        return HealthResponse(status="ok", device=str(device), model_loaded=True)
    except ModelLoadError as exc:
        logger.error("Health check: model failed to load: %s", exc)
        return HealthResponse(status="degraded", device="unknown", model_loaded=False)
