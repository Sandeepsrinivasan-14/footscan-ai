# Staged install: torch/torchvision are installed separately from everything else.
# Resolving them together with the rest of requirements.txt (which pulls from PyPI)
# against a second index causes pip's resolver to backtrack combinatorially
# (observed: 20+ min of pure CPU churn with no network/disk progress).
#
# Defaults to the CPU build via plain PyPI, which was the only reliable path on this
# machine -- download.pytorch.org's CDN dropped ~2.4GB downloads repeatedly (DNS
# flakiness + a Windows file-lock race right after each download completed). If you
# have an NVIDIA GPU and a more reliable connection to pytorch.org, swap the torch
# install line below for:
#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = ".\footscan_env\Scripts\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install torch torchvision
& $py -m pip install -r requirements-dev.txt

Write-Host "`nInstalled versions:" -ForegroundColor Cyan
& $py -m pip freeze
