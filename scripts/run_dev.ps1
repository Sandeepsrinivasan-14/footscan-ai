$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

# Prefer the repo's .venv, fall back to PATH python.
$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

& $py -m uvicorn footscan.api.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
