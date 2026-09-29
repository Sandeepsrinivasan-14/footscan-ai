# FootScan AI

AI-assisted diabetic foot ulcer (DFU) segmentation and triage dashboard. Upload a foot photo,
get a wound segmentation mask, area/shape/tissue-color analysis, a heuristic severity score, and
a downloadable PDF report. Includes before/after comparison and per-patient healing tracking.

## ⚠️ Clinical Disclaimer

This is a research/demo application, **not a medical device**. It has not been clinically
validated or FDA cleared. The SINBAD-style severity score, healing-time estimate, and tissue-color
classification are heuristics carried over from an early prototype, not sourced from a validated
guideline. Do not use this to make real treatment decisions — always defer to a qualified clinician.

## Architecture

```
FootScan_AI/
├── backend/footscan/
│   ├── config.py         # env-driven settings (pydantic-settings)
│   ├── ml/                # model loading (singleton) + preprocessing
│   ├── analysis/          # pure functions: shape, color, SINBAD scoring, healing estimate
│   ├── reports/           # PDF report generation
│   ├── db/                # SQLAlchemy models + session (SQLite by default)
│   ├── service.py         # orchestrates ml + analysis + persistence; used by both API and UI
│   ├── api/                # FastAPI app: REST endpoints under /api, /health
│   └── ui/                 # Gradio dashboard, mounted onto the FastAPI app at "/"
├── tests/                 # pytest: unit tests (pure functions) + integration tests (real model/API)
├── FootScan_AI_Core/       # original prototype + trained weights + datasets (kept as-is)
├── Dockerfile, docker-compose.yml
└── .github/workflows/ci.yml
```

One process serves both the JSON API (`/api/*`, docs at `/api/docs`) and the human-facing
Gradio dashboard (`/`), via `gr.mount_gradio_app`. The Gradio UI and the REST API both call
into the same `footscan.service` layer — no duplicated business logic.

### Why this differs from the original prototype (`FootScan_AI_Core/app_ultimate.py`)

- **State was global and shared across every visitor.** The prototype stored the "last analysis"
  in module-level dict/list variables, so concurrent users could see each other's data, and a
  PDF export could grab the wrong patient's results. Now each browser session gets its own
  `gr.State`, and all history is persisted per-patient in a real database.
- **Nothing was persisted.** The "Healing Tracker" tab held data in an in-memory Python list that
  reset on every restart and had no notion of a specific patient. Now every scan is written to
  SQLite (`ScanRecord`, linked to a `Patient`), so history survives restarts and is queryable via
  the API (`GET /api/patients/{id}/scans`).
- **No API.** The prototype was Gradio-only, so nothing else could integrate with it. There's now
  a documented REST API (multipart image upload → JSON metrics + persisted scan + PDF report).
- **No environment/config management, logging, or auth.** Model path, device, DB location, and an
  optional API key are now environment-driven (`.env` / `FOOTSCAN_*`), with structured logging and
  a global exception handler instead of unhandled tracebacks leaking to clients.
- **No tests, no containerization, no CI.** Added a pytest suite (pure-function unit tests +
  model/API integration tests), a Dockerfile + docker-compose (GPU-aware, falls back to CPU),
  and a GitHub Actions workflow.

## Setup

**Prerequisites:** Python 3.11. An NVIDIA GPU is optional — the app runs on CPU by default
(inference on a 256×256 ResNet34-UNet takes well under a second on CPU) and falls back
automatically via `FOOTSCAN_DEVICE=auto`.

```powershell
# from the repo root
.\scripts\install.ps1
Copy-Item .env.example .env   # edit if your paths differ
```

`install.ps1` installs torch/torchvision separately from the rest of `requirements-dev.txt` —
see the comments in that script and in `requirements.txt` for why (pip's resolver backtracks
combinatorially if you don't, and `download.pytorch.org`'s CUDA-wheel CDN was unreliable enough
on this network that CPU-via-PyPI is the default; swap in the cu121 index yourself if you have a
GPU and a steadier connection to it).

The two trained checkpoints live in `FootScan_AI_Core/` and are tracked via **Git LFS** (93MB +
143MB — too large for plain git). Clone with LFS enabled, or run `git lfs pull` after a plain
clone:
- `footscan_best_model.pth` — ResNet34-UNet, used for segmentation (the one this app loads)
- `footscan_attention_model.pth` — dual-attention UNet variant (used by the standalone
  `FootScan_AI_Core/train_attention.py` / `evaluate_with_post_processing.py` scripts, not by the
  API/UI in this repo)

Superseded prototype iterations (`app.py`, `app_simple.py`, etc.) and the unused original
TensorFlow scripts are archived in `FootScan_AI_Core/legacy/` for reference only.

## Running

```powershell
.\scripts\run_dev.ps1
```

Then open:
- **Dashboard:** http://127.0.0.1:8000/
- **API docs (Swagger):** http://127.0.0.1:8000/api/docs
- **Health check:** http://127.0.0.1:8000/health

### Docker

```bash
docker compose up --build
```

Requires the NVIDIA Container Toolkit for GPU passthrough; delete the `deploy.resources` block in
`docker-compose.yml` to run CPU-only.

## API

All endpoints below are under `/api` and require `X-API-Key` **only if** `FOOTSCAN_API_KEY` is
set (unset by default — fine for local use, must be set for any real deployment).

| Method | Path                          | Purpose                                              |
|--------|-------------------------------|-------------------------------------------------------|
| POST   | `/api/analyze`                | Upload an image, get segmentation + metrics; optionally persists a scan |
| POST   | `/api/compare`                | Upload two images (before/after), get area delta      |
| GET    | `/api/scans/{id}/report`      | Render and download the PDF report for a saved scan   |
| POST   | `/api/patients`               | Create a patient                                       |
| GET    | `/api/patients`               | List patients                                          |
| GET    | `/api/patients/{id}/scans`    | A patient's scan history                                |
| GET    | `/health`                     | Liveness/readiness probe (also confirms model loaded)  |

Full interactive schema: `/api/docs`.

## Testing

```powershell
# fast: pure-function unit tests, no model/GPU needed
.\footscan_env\Scripts\python.exe -m pytest -m "not integration"

# full: also loads the real model and exercises the API end-to-end
.\footscan_env\Scripts\python.exe -m pytest
```

## Verified working (2026-09-28)

All three UI tabs and the REST API were exercised live in a browser against the real model and
a real SQLite DB, not just unit-tested:
- **Advanced Analysis**: uploaded a real DFU photo, ran inference, all 6 visualizations rendered
  correctly (mask/heatmap/overlay/edges/crop all localized on the actual wound), PDF report
  downloaded and its embedded images/metrics verified correct.
- **Before & After**: uploaded two different scans, got a correct area delta and diff map.
- **Healing Tracker**: added two scans under the same patient name; confirmed via
  `GET /api/patients/{id}/scans` that both persisted to SQLite under one patient record.
- Full pytest suite (26 tests, unit + integration) passes; `ruff check` is clean.

## Known limitations / what's intentionally out of scope

- **Clinical validity** (see disclaimer above) — the scoring heuristics need a real clinical
  source before this could be trusted beyond a demo.
- **Model accuracy** hasn't been benchmarked here; `FootScan_AI_Core/evaluate.py` computes
  Dice/IoU against the held-out test set but its output hasn't been reviewed as part of this build.
- **No auth beyond a single shared API key** — no per-user accounts, roles, or audit log. Fine
  for a single-clinician demo; not sufficient for multi-tenant or regulated (HIPAA-grade) use.
- **No rate limiting** — put a reverse proxy in front of this in any public deployment.
- **CORS defaults to `*`** — tighten `FOOTSCAN_CORS_ORIGINS` before exposing this beyond localhost.
