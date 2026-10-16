import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from footscan.api.middleware import RequestContextMiddleware
from footscan.api.routes import analysis, health, patients
from footscan.config import REPO_ROOT, settings
from footscan.db.session import init_db
from footscan.logging_config import configure_logging
from footscan.ml.model import ModelLoadError, get_model

FRONTEND_DIR = REPO_ROOT / "frontend"

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.is_production and settings.api_key_value is None:
        logger.warning(
            "FOOTSCAN_API_KEY is not set: /api/* is unauthenticated. "
            "Set it (or put an authenticating reverse proxy in front) before exposing this service."
        )
    if "*" in settings.effective_cors_origins:
        logger.warning("CORS allows any origin ('*'); set FOOTSCAN_CORS_ORIGINS to your frontend origin(s).")
    try:
        get_model()  # fail fast at startup instead of on first request
    except ModelLoadError as exc:
        logger.error("Startup model load failed (inference routes return 503 until fixed): %s", exc)
    yield


def _error_headers(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None)
    return {"X-Request-ID": request_id} if request_id else {}


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.1.0",
        description=(
            "Diabetic foot ulcer segmentation and triage. **Research use only - not a medical device.** "
            "Outputs are heuristic and have not been clinically validated."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Added last = outermost, so request ids/headers also cover CORS preflights and error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.effective_cors_origins,
        allow_credentials=False,  # auth is a header API key, not cookies
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Drop the echoed `input`/`ctx` that FastAPI includes by default: it can contain
        # uploaded bytes or patient data.
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors}, headers=_error_headers(request))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", None)},
            headers=_error_headers(request),
        )

    app.include_router(health.router)
    app.include_router(analysis.router)
    app.include_router(patients.router)

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    else:
        logger.warning("Frontend directory not found at %s; root route will 404", FRONTEND_DIR)

    return app


app = create_app()
