"""Structured logging with per-request correlation ids.

Logs are emitted as one JSON object per line in production (``FOOTSCAN_LOG_FORMAT=json``,
the default when ``FOOTSCAN_ENVIRONMENT=production``) and as readable text otherwise.
Never log request bodies, filenames or patient names: they may be PHI.
"""

import logging
import sys
from contextvars import ContextVar

from footscan.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def _use_json() -> bool:
    fmt = settings.log_format
    return fmt == "json" or (fmt == "auto" and settings.is_production)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_footscan", False) for h in root.handlers):
        return  # already configured (e.g. re-imported under uvicorn --reload)

    handler = logging.StreamHandler(sys.stdout)
    handler._footscan = True  # type: ignore[attr-defined]
    handler.addFilter(RequestIdFilter())

    if _use_json():
        from pythonjsonlogger.jsonlogger import JsonFormatter

        handler.setFormatter(
            JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s [%(request_id)s] :: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root.setLevel(settings.log_level.upper())
    root.addHandler(handler)

    # Quiet noisy third-party loggers at INFO
    for noisy in ("PIL", "matplotlib", "urllib3", "multipart", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
