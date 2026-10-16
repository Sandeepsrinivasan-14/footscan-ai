"""Helpers for moving images across the API boundary.

* ``decode_upload`` validates and decodes an untrusted upload into an RGB numpy array.
* ``encode_image_b64`` turns analysis-pipeline arrays back into inline, displayable images.

The service layer works entirely in RGB numpy arrays (see AnalysisResult).
"""

import base64
import io

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from footscan.config import settings

# Real formats (sniffed from the bytes, not the client-supplied Content-Type).
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}
_READ_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    """Read an upload without ever buffering more than ``limit`` + one chunk."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"Image exceeds the {limit // (1024 * 1024)}MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_image_bytes(raw: bytes) -> None:
    """Check format + dimensions from the header only, before paying for a full decode."""
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail="Could not read image; is it a valid image file?") from exc

    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=415, detail=f"Unsupported image format: {fmt}. Allowed: {', '.join(sorted(ALLOWED_FORMATS))}"
        )
    if width < 8 or height < 8:
        raise HTTPException(status_code=422, detail="Image is too small (minimum 8x8 pixels)")
    if max(width, height) > settings.max_image_side or width * height > settings.max_image_pixels:
        raise HTTPException(
            status_code=413,
            detail=f"Image dimensions {width}x{height} exceed the allowed maximum "
            f"({settings.max_image_side}px per side, {settings.max_image_pixels // 1_000_000}MP total)",
        )


async def decode_upload(file: UploadFile) -> np.ndarray:
    """Validate an untrusted image upload and return it as an RGB uint8 array."""
    raw = await _read_limited(file, settings.max_upload_bytes)
    validate_image_bytes(raw)

    image_bgr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Could not decode image; is it a valid image file?")
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def encode_image_b64(image_rgb: np.ndarray, *, quality: int = 88) -> str:
    """Encode an RGB uint8 array as a JPEG data URI for direct use in an <img src>."""
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Failed to encode image")
    encoded = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
