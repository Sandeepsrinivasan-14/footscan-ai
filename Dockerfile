# syntax=docker/dockerfile:1.7
#
# Stages
#   builder  - installs Python dependencies into a venv (CPU torch by default)
#   runtime  - slim, non-root image WITHOUT model weights (mount them at runtime; see README)
#   app      - runtime + the segmentation weights baked in (default target)
#
# Build examples
#   docker build -t footscan-ai .                                  # CPU, weights baked in (needs `git lfs pull` first)
#   docker build --target runtime -t footscan-ai:slim .            # no weights; mount ./FootScan_AI_Core at run time
#   docker build --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121 -t footscan-ai:gpu .

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /build
# Install torch first and separately: resolving it together with the rest against a second
# index makes pip backtrack badly (see requirements.txt).
RUN pip install torch==2.4.1 torchvision==0.19.1 --index-url "${TORCH_INDEX_URL}"
COPY requirements.txt .
RUN pip install -r requirements.txt


FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="FootScan AI" \
      org.opencontainers.image.description="Diabetic foot ulcer segmentation and triage API (research use only; not a medical device)" \
      org.opencontainers.image.source="https://github.com/Sandeepsrinivasan-14/footscan-ai" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/backend \
    FOOTSCAN_ENVIRONMENT=production \
    FOOTSCAN_DATA_DIR=/app/data \
    FOOTSCAN_DATABASE_URL=sqlite:////app/data/footscan.db \
    FOOTSCAN_MODEL_WEIGHTS_PATH=/app/FootScan_AI_Core/footscan_best_model.pth

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 footscan \
    && useradd --system --uid 10001 --gid footscan --home-dir /app --shell /usr/sbin/nologin footscan

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=footscan:footscan backend/ backend/
COPY --chown=footscan:footscan frontend/ frontend/
RUN mkdir -p /app/data /app/FootScan_AI_Core && chown -R footscan:footscan /app/data /app/FootScan_AI_Core

USER footscan
VOLUME ["/app/data"]
EXPOSE 8000

# /ready = database reachable AND model loaded. Use /health for a pure liveness check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4)"]

# One worker: the model is a per-process singleton and rate limiting is in-process.
# Scale out with replicas behind a load balancer rather than --workers.
CMD ["python", "-m", "uvicorn", "footscan.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]


FROM runtime AS app
COPY --chown=footscan:footscan FootScan_AI_Core/footscan_best_model.pth /app/FootScan_AI_Core/footscan_best_model.pth
# Fail the build (instead of shipping a broken image) if Git LFS was not pulled and this is a ~130 byte pointer file.
RUN python -c "import os,sys; p='/app/FootScan_AI_Core/footscan_best_model.pth'; s=os.path.getsize(p); sys.exit(0 if s > 1_000_000 else 'weights file is %d bytes: looks like a Git LFS pointer; run git lfs pull before building' % s)"
