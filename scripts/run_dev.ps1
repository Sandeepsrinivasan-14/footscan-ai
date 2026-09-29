$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$env:PYTHONPATH = "backend"
& ".\footscan_env\Scripts\python.exe" -m uvicorn footscan.api.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
