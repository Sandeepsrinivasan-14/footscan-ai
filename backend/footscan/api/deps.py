import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from footscan.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """No-op if FOOTSCAN_API_KEY is unset (local/dev default).

    In production, set FOOTSCAN_API_KEY and every /api/* request must send a
    matching X-API-Key header. The comparison is constant-time.
    """
    expected = settings.api_key_value
    if expected is None:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


class SlidingWindowRateLimiter:
    """Small in-memory, per-process sliding-window limiter keyed by client address.

    Good enough to blunt accidental floods and trivial abuse of the inference endpoints on a
    single-worker deployment. For multi-replica or internet-facing deployments, enforce limits
    at the reverse proxy / API gateway instead (see README, "Deployment notes").
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> float | None:
        """Record a hit. Returns None if allowed, else the seconds until the client may retry."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= limit:
                return max(self.window - (now - hits[0]), 0.0)
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory under address churn
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    del self._hits[stale]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = SlidingWindowRateLimiter()


def enforce_rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    retry_after = rate_limiter.check(client, limit)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded; slow down and retry shortly",
            headers={"Retry-After": str(max(int(retry_after) + 1, 1))},
        )
