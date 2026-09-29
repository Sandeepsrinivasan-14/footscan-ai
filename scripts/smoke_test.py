"""Quick manual sanity check: load the model and run inference on one real
sample image from the dataset. Run after `scripts/install.ps1` finishes.

    .\\footscan_env\\Scripts\\python.exe scripts\\smoke_test.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import cv2  # noqa: E402

from footscan.service import analyze_image  # noqa: E402

SAMPLE_DIR = REPO_ROOT / "FootScan_AI_Core" / "data" / "Foot Ulcer Segmentation Challenge" / "test" / "images"


def main() -> None:
    samples = sorted(SAMPLE_DIR.glob("*.png"))[:3] or sorted(SAMPLE_DIR.glob("*.jpg"))[:3]
    if not samples:
        print(f"No sample images found under {SAMPLE_DIR}")
        sys.exit(1)

    for path in samples:
        img_bgr = cv2.imread(str(path))
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        result = analyze_image(img_rgb)
        print(
            f"{path.name}: status={result.status} area={result.area_cm2:.3f}cm2 "
            f"shape={result.shape} color={result.color_profile} "
            f"sinbad={result.sinbad_score}/6 ({result.severity})"
        )

    print("\nSmoke test passed: model loaded and produced predictions for all samples.")


if __name__ == "__main__":
    main()
