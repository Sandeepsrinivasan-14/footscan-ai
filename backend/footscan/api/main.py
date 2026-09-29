import logging
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from footscan.api.routes import analysis, health, patients
from footscan.config import settings
from footscan.db.session import init_db
from footscan.logging_config import configure_logging
from footscan.ml.model import ModelLoadError, get_model
from footscan.ui.gradio_app import CUSTOM_CSS, build_demo

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        get_model()  # fail fast at startup instead of on first request
    except ModelLoadError as exc:
        logger.error("Startup model load failed (routes will return 503 until fixed): %s", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(analysis.router)
    app.include_router(patients.router)

    demo = build_demo()
    demo.queue()
    gr.mount_gradio_app(app, demo, path="/", theme=gr.themes.Base(), css=CUSTOM_CSS)

    return app


app = create_app()
