"""ASGI middleware: request ids, structured access logs, early body-size guard, safe response headers.

Implemented as plain ASGI (not ``BaseHTTPMiddleware``) so streaming responses used by the
mounted Gradio dashboard are not buffered.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from footscan.config import settings
from footscan.logging_config import request_id_ctx

logger = logging.getLogger("footscan.access")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUIET_PATHS = {"/health", "/ready"}  # probes are polled constantly; log them at DEBUG only

# /api/compare carries two images plus multipart framing.
_MAX_IMAGES_PER_REQUEST = 2
_MULTIPART_OVERHEAD = 1024 * 1024


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming_id = headers.get("x-request-id", "")
        request_id = incoming_id if _VALID_REQUEST_ID.match(incoming_id) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id  # visible as request.state.request_id

        path: str = scope["path"]
        method: str = scope["method"]
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                out = MutableHeaders(scope=message)
                out["X-Request-ID"] = request_id
                out["X-Content-Type-Options"] = "nosniff"
                out["Referrer-Policy"] = "no-referrer"
                if path.startswith("/api/"):
                    out["Cache-Control"] = "no-store"  # responses may contain patient data
            await send(message)

        try:
            if path.startswith("/api/") and method in {"POST", "PUT", "PATCH"}:
                declared = headers.get("content-length")
                limit = settings.max_upload_bytes * _MAX_IMAGES_PER_REQUEST + _MULTIPART_OVERHEAD
                if declared and declared.isdigit() and int(declared) > limit:
                    response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
                    await response(scope, receive, send_wrapper)
                    return
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            level = logging.DEBUG if path in _QUIET_PATHS and status_code < 500 else logging.INFO
            # Path only: never the query string (it can carry patient names).
            logger.log(
                level,
                "%s %s -> %d (%.1f ms)",
                method,
                path,
                status_code,
                duration_ms,
                extra={"http_method": method, "http_path": path, "http_status": status_code, "duration_ms": duration_ms},
            )
            request_id_ctx.reset(token)
