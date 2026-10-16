import logging
import threading
from pathlib import Path

import albumentations as A
import numpy as np
import segmentation_models_pytorch as smp
import torch
from albumentations.pytorch import ToTensorV2

from footscan.config import settings
from footscan.ml.preprocessing import apply_preprocessing

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model: torch.nn.Module | None = None
_device: torch.device | None = None


class ModelLoadError(RuntimeError):
    """Raised when the segmentation model weights cannot be loaded."""


_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"


def weights_file_state(path: Path | None = None) -> str:
    """Classify the weights file: 'ok', 'missing', or 'lfs_pointer' (cloned without `git lfs pull`)."""
    path = path or settings.model_weights_path
    if not path.is_file():
        return "missing"
    with path.open("rb") as fh:
        if fh.read(len(_LFS_POINTER_PREFIX)) == _LFS_POINTER_PREFIX:
            return "lfs_pointer"
    return "ok"


def weights_available() -> bool:
    return weights_file_state() == "ok"


def is_model_loaded() -> bool:
    """True if the model singleton is already in memory (never triggers a load)."""
    return _model is not None


def current_device() -> str:
    return str(_device) if _device is not None else "unknown"


def resolve_device() -> torch.device:
    if settings.device == "cpu":
        return torch.device("cpu")
    if settings.device == "cuda":
        if not torch.cuda.is_available():
            raise ModelLoadError("FOOTSCAN_DEVICE=cuda requested but CUDA is not available")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model() -> tuple[torch.nn.Module, torch.device]:
    """Lazily load the segmentation model as a process-wide singleton (thread-safe)."""
    global _model, _device
    if _model is not None:
        return _model, _device  # type: ignore[return-value]

    with _lock:
        if _model is not None:
            return _model, _device  # type: ignore[return-value]

        state = weights_file_state()
        if state == "missing":
            raise ModelLoadError(
                f"Model weights not found at {settings.model_weights_path}. "
                "See 'Model weights' in the README (git lfs pull / scripts/download_weights.py)."
            )
        if state == "lfs_pointer":
            raise ModelLoadError(
                f"{settings.model_weights_path} is a Git LFS pointer, not the real weights. "
                "Run `git lfs pull` or scripts/download_weights.py."
            )

        device = resolve_device()
        model = smp.Unet(
            encoder_name=settings.encoder_name,
            encoder_weights=None,
            in_channels=3,
            classes=1,
        )
        try:
            # weights_only=True: refuse to unpickle arbitrary objects from a (possibly tampered) checkpoint.
            state_dict = torch.load(settings.model_weights_path, map_location=device, weights_only=True)
            model.load_state_dict(state_dict)
        except Exception as exc:  # noqa: BLE001 - re-raised with context
            raise ModelLoadError(f"Failed to load weights from {settings.model_weights_path}: {exc}") from exc

        model.to(device)
        model.eval()
        logger.info("Segmentation model loaded on %s (encoder=%s)", device, settings.encoder_name)

        _model, _device = model, device
        return _model, _device


def run_inference(image: np.ndarray, prep_method: str = "None") -> tuple[np.ndarray, np.ndarray]:
    """Run the segmentation model on an RGB uint8 image.

    Returns (confidence_map, preprocessed_image) where confidence_map is a
    float32 array in [0, 1] at settings.image_size x settings.image_size.
    """
    model, device = get_model()
    processed_img = apply_preprocessing(image, prep_method)

    transform = A.Compose(
        [
            A.Resize(settings.image_size, settings.image_size),
            A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ToTensorV2(),
        ]
    )
    input_tensor = transform(image=processed_img)["image"].unsqueeze(0).to(device)

    with torch.no_grad():
        output = model(input_tensor)
        confidence = torch.sigmoid(output).squeeze().cpu().numpy()

    return confidence, processed_img
