import pytest

from footscan.config import Settings
from footscan.ml.model import ModelLoadError, get_model, weights_file_state


def _settings(monkeypatch, **env) -> Settings:
    for key in ("FOOTSCAN_CORS_ORIGINS", "FOOTSCAN_ENVIRONMENT", "FOOTSCAN_API_KEY", "FOOTSCAN_ENABLE_DASHBOARD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_cors_defaults_to_localhost_in_development_and_none_in_production(monkeypatch):
    dev = _settings(monkeypatch)
    assert dev.effective_cors_origins == ["http://localhost:8000", "http://127.0.0.1:8000"]
    prod = _settings(monkeypatch, FOOTSCAN_ENVIRONMENT="production")
    assert prod.effective_cors_origins == []


def test_cors_origins_accept_comma_separated_and_json(monkeypatch):
    csv = _settings(monkeypatch, FOOTSCAN_CORS_ORIGINS="https://a.example, https://b.example")
    assert csv.effective_cors_origins == ["https://a.example", "https://b.example"]
    js = _settings(monkeypatch, FOOTSCAN_CORS_ORIGINS='["https://c.example"]')
    assert js.effective_cors_origins == ["https://c.example"]
    empty = _settings(monkeypatch, FOOTSCAN_CORS_ORIGINS="")
    assert empty.effective_cors_origins == ["http://localhost:8000", "http://127.0.0.1:8000"]


def test_api_key_is_secret_and_empty_means_disabled(monkeypatch):
    assert _settings(monkeypatch).api_key_value is None
    assert _settings(monkeypatch, FOOTSCAN_API_KEY="").api_key_value is None
    configured = _settings(monkeypatch, FOOTSCAN_API_KEY="abc123")
    assert configured.api_key_value == "abc123"
    assert "abc123" not in repr(configured)


def test_weights_file_state(tmp_path):
    assert weights_file_state(tmp_path / "missing.pth") == "missing"

    pointer = tmp_path / "pointer.pth"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n")
    assert weights_file_state(pointer) == "lfs_pointer"

    real = tmp_path / "real.pth"
    real.write_bytes(b"PK\x03\x04 pretend this is a torch zip archive")
    assert weights_file_state(real) == "ok"


def test_get_model_explains_lfs_pointer(monkeypatch, tmp_path):
    import footscan.ml.model as model_module

    pointer = tmp_path / "w.pth"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    monkeypatch.setattr(model_module.settings, "model_weights_path", pointer)
    monkeypatch.setattr(model_module, "_model", None)
    with pytest.raises(ModelLoadError, match="git lfs pull"):
        get_model()
