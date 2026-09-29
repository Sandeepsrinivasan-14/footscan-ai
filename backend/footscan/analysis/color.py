import cv2
import numpy as np


def analyze_color(image: np.ndarray, binary_mask: np.ndarray) -> str:
    """Heuristic tissue-color classification from HSV brightness/saturation
    within the masked wound region. NOT clinically validated -- see README
    "Clinical Disclaimer" section.
    """
    if np.sum(binary_mask) == 0:
        return "None"

    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    roi_hsv = hsv[binary_mask == 1]
    mean_v = np.mean(roi_hsv[:, 2])
    mean_s = np.mean(roi_hsv[:, 1])

    if mean_v < 60:
        return "High Necrosis (Dark/Black Tissue)"
    if mean_s > 150:
        return "High Granulation (Red/Healthy Healing)"
    return "Mixed/Slough (Yellow/Fibrinous)"
