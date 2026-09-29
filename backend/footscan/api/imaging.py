"""Helpers for turning analysis-pipeline numpy arrays into API-transportable images.

The service layer works entirely in RGB numpy arrays (see AnalysisResult); the
REST API needs those as inline, displayable images for a browser frontend, so
this module is the one place that knows how to encode them.
"""

import base64

import cv2
import numpy as np


def encode_image_b64(image_rgb: np.ndarray, *, quality: int = 88) -> str:
    """Encode an RGB uint8 array as a JPEG data URI for direct use in an <img src>."""
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Failed to encode image")
    encoded = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
