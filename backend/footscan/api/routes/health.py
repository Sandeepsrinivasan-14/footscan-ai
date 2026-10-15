import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from footscan.api.schemas import HealthResponse, ReadinessResponse
from footscan.db.session import engine
from footscan.ml.model import ModelLoadError, current_device, get_model, is_model_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe: the process is up and serving. Always 200; never loads the model.

    ``status`` is ``degraded`` if the model is not (yet) in memory.
    """
    loaded = is_model_loaded()
    return HealthResponse(status="ok" if loaded else "degraded", device=current_device(), model_loaded=loaded)


@router.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}})
def ready() -> ReadinessResponse | JSONResponse:
    """Readiness probe: 200 only if the database is reachable AND the model is loaded.

    Returns 503 otherwise so orchestrators stop routing traffic to this instance.
    """
    checks: dict[str, str] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - report, don't crash the probe
        logger.exception("Readiness: database check failed")
        checks["database"] = "unavailable"

    try:
        get_model()
        checks["model"] = "ok"
    except ModelLoadError as exc:
        logger.error("Readiness: model not available: %s", exc)
        checks["model"] = "unavailable"

    is_ready = all(v == "ok" for v in checks.values())
    body = ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
    if is_ready:
        return body
    return JSONResponse(status_code=503, content=body.model_dump())
