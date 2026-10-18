# Contributing

Thanks for helping improve FootScan AI. This is a research project: contributions must never
imply clinical validation, and must never include real patient data.

## Ground rules

- **No PHI.** Do not commit, attach to issues, or paste in PRs any real patient images, names or identifiers. Use synthetic images or the public datasets referenced in `FootScan_AI_Core/README.md`.
- **No secrets.** Config comes from `FOOTSCAN_*` env vars; document new ones in `.env.example` and the README.
- **No model weights in normal commits** beyond the existing Git LFS-tracked checkpoints. See "Model weights" in the README.
- Branch from `main`, open a PR; do not push to `main` directly.

## Dev setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
git lfs pull        # only needed for the real-model integration tests / running the app
```

## Checks (the same ones CI runs)

```bash
ruff check backend tests scripts
pytest -m "not integration"          # unit + API tests with a fake model, no weights needed
pytest -m integration                # real model; needs the weights (git lfs pull)
(cd e2e && npm ci && npx playwright install chromium && npx playwright test)   # browser tests
```

## Conventions

- Python 3.11, `ruff` for lint/import order (config in `pyproject.toml`), line length 115.
- Every API behaviour change needs a test in `tests/test_api.py` (FastAPI `TestClient`); UI changes need a case in `e2e/tests/smoke.spec.js`.
- Frontend: plain ES modules and CSS, no build step, no inline script/style (strict CSP), build DOM with `textContent` (never `innerHTML`). Vendored libraries must be pinned with a SRI hash.
- Keep inference/analysis logic in `backend/footscan/service.py` and below; routes stay thin.
- Commit messages: short imperative subject, explanatory body when the "why" is not obvious.

## Reporting security issues

See [SECURITY.md](SECURITY.md); do not use public issues.
