# Security Policy

FootScan AI is a **research prototype and not a medical device**. It processes images that may be
health data, so please treat security reports seriously and never post patient data publicly.

## Reporting a vulnerability

Please report privately using GitHub's
[private vulnerability reporting](https://github.com/Sandeepsrinivasan-14/footscan-ai/security/advisories/new)
(Security tab -> "Report a vulnerability"). Do not open a public issue for security problems.

Include: affected version/commit, a description and impact, reproduction steps (use synthetic or
public-dataset images, never real patient data), and any suggested fix.

You can expect an acknowledgement within 7 days. This is a volunteer-maintained project, so fix
timelines are best-effort; critical issues are prioritised.

## Supported versions

Only the latest commit on `main` receives security fixes.

## Security model and known limits

What the service does today:

- Optional shared API key (`FOOTSCAN_API_KEY`, `X-API-Key` header, constant-time comparison) on all `/api/*` routes.
- Upload validation: size cap, real-format sniffing (JPEG/PNG/WEBP/BMP only), pixel and dimension caps (decompression-bomb guard).
- In-process per-IP rate limiting on `/api/analyze` and `/api/compare`.
- CORS is explicit and env-configured; no wildcard by default; credentials not allowed.
- Model checkpoints are loaded with `torch.load(weights_only=True)`; verify downloads with `FootScan_AI_Core/WEIGHTS.sha256`.
- Containers run as a non-root user with a read-only root filesystem (compose) and no extra capabilities.
- Logs never include request bodies, filenames, query strings or patient names.

What it does **not** do (so do not deploy it as a multi-user clinical system without addressing these):

- No per-user accounts, roles, audit trail, or encryption at rest for the SQLite database and stored scan images.
- No TLS termination: run it behind a reverse proxy that provides HTTPS, request-size limits and, for multi-replica setups, shared rate limiting.
- The optional Gradio dashboard (`/dashboard`) has no API-key protection and is disabled by default in production.
- Not assessed against HIPAA, GDPR or medical-device regulations.

## Secrets and patient data

- Never commit `.env`, API keys, databases (`data/`), or real patient images. `.gitignore` and `.dockerignore` exclude them.
- If you believe a secret was committed, rotate it immediately, then report it as above.
