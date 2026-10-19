import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# Origins allowed by default when running locally; production defaults to none (same-origin only).
_DEV_CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden with a ``FOOTSCAN_<NAME>`` env var."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FOOTSCAN_", extra="ignore")

    # App
    app_name: str = "FootScan AI"
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"
    log_format: Literal["auto", "json", "text"] = "auto"  # auto = json in production, text otherwise
    image_size: int = 256

    # ML
    model_weights_path: Path = REPO_ROOT / "FootScan_AI_Core" / "footscan_best_model.pth"
    encoder_name: str = "resnet34"
    device: str = "auto"  # auto | cpu | cuda

    # Storage
    data_dir: Path = REPO_ROOT / "data"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'footscan.db').as_posix()}"

    # Security
    # If set, all /api routes require a matching X-API-Key header. Held as SecretStr so it
    # never shows up in repr()/logs.
    api_key: SecretStr | None = None
    # Comma-separated list (or a JSON array) of allowed browser origins. When unset: localhost
    # origins in development, none (same-origin only) in production. "*" is accepted but discouraged.
    cors_origins: Annotated[list[str] | None, NoDecode] = None

    # Upload limits (applied to every image upload)
    max_upload_bytes: int = 15 * 1024 * 1024
    max_image_pixels: int = 40_000_000  # decompression-bomb guard, checked before full decode
    max_image_side: int = 12_000

    # Per-client rate limit for the expensive inference endpoints, requests/minute. 0 disables.
    rate_limit_per_minute: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.startswith("["):
                return json.loads(value)
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def effective_cors_origins(self) -> list[str]:
        if self.cors_origins is not None:
            return self.cors_origins
        return [] if self.is_production else list(_DEV_CORS_ORIGINS)

    @property
    def api_key_value(self) -> str | None:
        return self.api_key.get_secret_value() if self.api_key and self.api_key.get_secret_value() else None

    @property
    def scans_dir(self) -> Path:
        path = self.data_dir / "scans"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reports_dir(self) -> Path:
        path = self.data_dir / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
