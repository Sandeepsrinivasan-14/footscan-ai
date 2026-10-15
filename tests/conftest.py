import os
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TEST_DATA_DIR = TESTS_DIR / "_tmp_data"
TEST_DATA_DIR.mkdir(exist_ok=True)

# Must be set before the first `import footscan.config`, since Settings() is
# instantiated once at module import time.
os.environ.setdefault("FOOTSCAN_DATA_DIR", str(TEST_DATA_DIR))
os.environ.setdefault("FOOTSCAN_DATABASE_URL", f"sqlite:///{(TEST_DATA_DIR / 'test.db').as_posix()}")
os.environ.setdefault("FOOTSCAN_ENVIRONMENT", "test")
os.environ.setdefault("FOOTSCAN_RATE_LIMIT_PER_MINUTE", "0")  # tests that exercise limiting turn it on explicitly

BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import pytest


@pytest.fixture
def sample_image() -> np.ndarray:
    """A deterministic 256x256 RGB image, skin-tone-ish background."""
    rng = np.random.default_rng(42)
    img = rng.integers(140, 200, size=(256, 256, 3), dtype=np.uint8)
    return img


@pytest.fixture
def circular_mask() -> np.ndarray:
    """A near-perfect circle in the center of a 256x256 binary mask."""
    import cv2

    mask = np.zeros((256, 256), dtype=np.uint8)
    cv2.circle(mask, (128, 128), 40, 1, thickness=-1)
    return mask


@pytest.fixture
def elongated_mask() -> np.ndarray:
    """A thin elongated blob -> should classify as Irregular, not Round/Oval."""
    import cv2

    mask = np.zeros((256, 256), dtype=np.uint8)
    cv2.rectangle(mask, (20, 120), (236, 136), 1, thickness=-1)
    return mask


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from footscan.api.deps import rate_limiter

    rate_limiter.reset()
    yield
    rate_limiter.reset()
