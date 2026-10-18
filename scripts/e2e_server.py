"""Run the real FastAPI app with a deterministic fake segmentation model, for browser tests.

The fake "model" marks strongly red pixels as wound, so the synthetic images used by the
Playwright suite (a skin-coloured square with a red ellipse) produce a predictable mask. No
weights, no GPU and no Git LFS are needed; everything else (routing, validation, SQLite, PDF
reports, security headers) is the production code path.

    python scripts/e2e_server.py --port 8765

Data goes to a fresh temporary directory that is removed on exit.
"""

import argparse
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    data_dir = Path(tempfile.mkdtemp(prefix="footscan-e2e-"))
    atexit.register(shutil.rmtree, data_dir, ignore_errors=True)
    os.environ["FOOTSCAN_DATA_DIR"] = str(data_dir)
    os.environ["FOOTSCAN_DATABASE_URL"] = f"sqlite:///{(data_dir / 'e2e.db').as_posix()}"
    os.environ["FOOTSCAN_ENVIRONMENT"] = "test"
    os.environ["FOOTSCAN_RATE_LIMIT_PER_MINUTE"] = "0"
    sys.path.insert(0, str(REPO_ROOT / "backend"))

    import cv2
    import numpy as np
    import uvicorn

    from footscan.ml import model as model_module

    def fake_run_inference(image: np.ndarray, prep_method: str = "None"):
        rgb = image.astype(np.int16)
        redness = np.clip((rgb[..., 0] - rgb[..., 1] - 40) / 110.0, 0.0, 1.0)
        confidence = cv2.GaussianBlur(redness.astype(np.float32), (0, 0), 2.0)
        return np.clip(confidence * 1.15, 0.0, 1.0).astype(np.float32), image

    model_module.run_inference = fake_run_inference
    model_module.get_model = lambda: (object(), "cpu")
    model_module.is_model_loaded = lambda: True
    model_module.current_device = lambda: "cpu (fake)"

    # Modules that did `from footscan.ml.model import ...` hold their own references.
    import footscan.api.main  # noqa: F401  (imports routes/health/service)
    import footscan.api.routes.health as health
    import footscan.service as service

    service.run_inference = fake_run_inference
    health.get_model = model_module.get_model
    health.is_model_loaded = model_module.is_model_loaded
    health.current_device = model_module.current_device
    footscan.api.main.get_model = model_module.get_model

    uvicorn.run(footscan.api.main.app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
