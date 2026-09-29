import cv2
import numpy as np

PreprocessMethod = str  # "None" | "CLAHE" | "Histogram Equalization"


def to_rgb(image: np.ndarray) -> np.ndarray:
    """Normalize an arbitrary uploaded image array to 3-channel RGB uint8."""
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    return image


def apply_preprocessing(image: np.ndarray, method: PreprocessMethod) -> np.ndarray:
    img = image.copy()
    if method == "CLAHE":
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl, a, b))
        img = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
    elif method == "Histogram Equalization":
        img_yuv = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
        img_yuv[:, :, 0] = cv2.equalizeHist(img_yuv[:, :, 0])
        img = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2RGB)
    return img
