import cv2
import numpy as np


def analyze_shape(binary_mask: np.ndarray) -> str:
    """Classify the dominant contour in a binary mask as Round / Oval / Irregular / Unknown."""
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "Unknown"

    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    perimeter = cv2.arcLength(c, True)
    if perimeter == 0:
        return "Irregular"

    circularity = 4 * np.pi * (area / (perimeter * perimeter))
    x, y, w, h = cv2.boundingRect(c)
    aspect_ratio = float(w) / h

    if circularity > 0.7:
        return "Round"
    if 0.5 < aspect_ratio < 2.0 and circularity > 0.5:
        return "Oval"
    return "Irregular"


def extract_edges(binary_mask: np.ndarray, original: np.ndarray) -> np.ndarray:
    edges = cv2.Canny((binary_mask * 255).astype(np.uint8), 100, 200)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edge_overlay = original.copy()
    edge_overlay[edges > 0] = [255, 0, 0]
    return edge_overlay


def auto_crop_wound(image: np.ndarray, binary_mask: np.ndarray, pad: int = 20) -> np.ndarray:
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    height, width = image.shape[:2]
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(width, x + w + pad)
    y2 = min(height, y + h + pad)
    return image[y1:y2, x1:x2]
