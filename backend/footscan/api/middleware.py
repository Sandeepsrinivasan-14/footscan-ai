"""ASGI middleware: request ids, structured access logs, early body-size guard, security headers.

Implemented as plain ASGI (not ``BaseHTTPMiddleware``) so streamed responses (e.g. the PDF report)
are never buffered.
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


# Content-Security-Policy for the web app and the JSON API. The frontend is plain same-origin ES
# modules + CSS with no inline script/style, so nothing needs 'unsafe-inline' or a third-party host.
# Images may be data: (inline analysis results) or blob: (authenticated scan thumbnails).
# three.js is vendored under /vendor/ (Subresource Integrity checked) and the font is self-hosted.
APP_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "worker-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

# Swagger UI (/api/docs) is the one page that loads its assets from a CDN and runs an inline
# bootstrap script, so it gets its own, still restrictive, policy instead of loosening APP_CSP.
DOCS_CSP = "; ".join(
    [
        "default-src 'none'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "connect-src 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ]
)
_DOCS_PATHS = {"/api/docs", "/api/docs/oauth2-redirect"}

_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"


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
                out["X-Frame-Options"] = "DENY"
                out["Permissions-Policy"] = _PERMISSIONS_POLICY
                out["Cross-Origin-Opener-Policy"] = "same-origin"
                out["Content-Security-Policy"] = DOCS_CSP if path in _DOCS_PATHS else APP_CSP
                if path.startswith("/api/"):
                    out["Cache-Control"] = "no-store"  # responses may contain patient data
                elif "cache-control" not in out:
                    out["Cache-Control"] = "no-cache"  # static assets: always revalidate (ETag), so deploys apply at once
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
