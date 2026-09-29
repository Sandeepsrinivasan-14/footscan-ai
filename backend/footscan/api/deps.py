from fastapi import Header, HTTPException, status

from footscan.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """No-op if FOOTSCAN_API_KEY is unset (local/dev default).

    In production, set FOOTSCAN_API_KEY and every /api/* request must send a
    matching X-API-Key header.
    """
    if settings.api_key is None:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
