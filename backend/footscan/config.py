from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FOOTSCAN_", extra="ignore")

    # App
    app_name: str = "FootScan AI"
    environment: str = "development"  # development | production
    log_level: str = "INFO"
    image_size: int = 256

    # ML
    model_weights_path: Path = REPO_ROOT / "FootScan_AI_Core" / "footscan_best_model.pth"
    encoder_name: str = "resnet34"
    device: str = "auto"  # auto | cpu | cuda

    # Storage
    data_dir: Path = REPO_ROOT / "data"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'footscan.db').as_posix()}"

    # Security
    api_key: str | None = None  # if set, all /api routes require X-API-Key header
    cors_origins: list[str] = ["*"]

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
