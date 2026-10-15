#!/usr/bin/env bash
# Run the dev server with auto-reload. Uses .venv if present, else whatever `python` is on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
else PY="python"; fi

exec "$PY" -m uvicorn footscan.api.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
