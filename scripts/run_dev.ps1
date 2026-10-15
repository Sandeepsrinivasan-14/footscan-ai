$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

# Prefer the repo's .venv, fall back to the legacy footscan_env, then PATH python.
$py = @(".\.venv\Scripts\python.exe", ".\footscan_env\Scripts\python.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { $py = "python" }

$env:PYTHONPATH = "backend"
& $py -m uvicorn footscan.api.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
