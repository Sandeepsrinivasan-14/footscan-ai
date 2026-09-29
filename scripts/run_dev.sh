#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

./footscan_env/Scripts/python.exe -m uvicorn footscan.api.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
