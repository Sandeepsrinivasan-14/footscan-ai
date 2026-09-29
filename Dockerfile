# syntax=docker/dockerfile:1
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 footscan
WORKDIR /app

COPY requirements.txt .
RUN python3.11 -m pip install --upgrade pip && python3.11 -m pip install -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY FootScan_AI_Core/footscan_best_model.pth FootScan_AI_Core/footscan_best_model.pth
COPY FootScan_AI_Core/footscan_attention_model.pth FootScan_AI_Core/footscan_attention_model.pth

ENV FOOTSCAN_ENVIRONMENT=production \
    FOOTSCAN_DATA_DIR=/app/data \
    FOOTSCAN_DATABASE_URL=sqlite:////app/data/footscan.db \
    PYTHONPATH=/app/backend

RUN mkdir -p /app/data && chown -R footscan:footscan /app
USER footscan

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python3.11 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["python3.11", "-m", "uvicorn", "footscan.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
