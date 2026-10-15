"""HTTP API tests driven through FastAPI's TestClient.

Most tests replace the segmentation model with a deterministic fake, so they run in CI without
the (Git LFS) weights. Tests that need the real network are marked ``integration``.
"""

import io
import re

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from footscan.analysis.result import AnalysisResult
from footscan.config import settings
from footscan.ml.model import ModelLoadError, weights_available

requires_model = pytest.mark.skipif(
    not weights_available(), reason="model weights not present (or only a Git LFS pointer)"
)


# --------------------------------------------------------------------------- fixtures / helpers


@pytest.fixture
def client():
    from footscan.api.main import app

    with TestClient(app) as c:
        yield c


def _encode(image_rgb: np.ndarray, ext: str = ".jpg") -> bytes:
    ok, buf = cv2.imencode(ext, cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def _upload(image_rgb: np.ndarray, *, name="scan.jpg", ctype="image/jpeg", ext=".jpg", field="image"):
    return {field: (name, io.BytesIO(_encode(image_rgb, ext)), ctype)}


def _fake_result(**overrides) -> AnalysisResult:
    size = settings.image_size
    img = np.full((size, size, 3), 150, dtype=np.uint8)
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[100:140, 100:140] = 255
    fields = dict(
        status="ULCER DETECTED",
        view_type="Plantar (Bottom)",
        area_cm2=1.2345,
        ulcer_percent=2.44,
        max_confidence=0.93,
        shape="Round",
        color_profile="Red/Granulating (Healthy)",
        sinbad_score=2,
        severity="Mild",
        est_healing_days=21,
        treatment="Standard wound care.",
        threshold=0.5,
        preprocessing="None",
        original=img,
        mask=mask,
        heatmap=img,
        blended=img,
        edges=img,
        cropped=img,
    )
    fields.update(overrides)
    return AnalysisResult(**fields)


@pytest.fixture
def fake_model(monkeypatch):
    """Swap the analysis pipeline for a deterministic fake (no weights needed)."""
    calls: list[dict] = []

    def fake_analyze(image, **kwargs):
        calls.append(kwargs)
        return _fake_result(view_type=kwargs.get("view_type", "Plantar (Bottom)"), threshold=kwargs["threshold"])

    def fake_compare(old, new, **kwargs):
        return {
            "status": "IMPROVED",
            "old_area_cm2": 2.0,
            "new_area_cm2": 1.0,
            "change_cm2": -1.0,
            "diff_map": np.zeros((settings.image_size, settings.image_size, 3), dtype=np.uint8),
        }

    monkeypatch.setattr("footscan.api.routes.analysis.analyze_image", fake_analyze)
    monkeypatch.setattr("footscan.api.routes.analysis.compare_images", fake_compare)
    return calls


# --------------------------------------------------------------------------- health / readiness


def test_health_is_liveness_and_never_needs_the_model(client, monkeypatch):
    monkeypatch.setattr("footscan.api.routes.health.is_model_loaded", lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded", "device": resp.json()["device"], "model_loaded": False}


def test_health_reports_ok_when_model_loaded(client, monkeypatch):
    monkeypatch.setattr("footscan.api.routes.health.is_model_loaded", lambda: True)
    monkeypatch.setattr("footscan.api.routes.health.current_device", lambda: "cpu")
    assert client.get("/health").json() == {"status": "ok", "device": "cpu", "model_loaded": True}


def test_ready_200_when_db_and_model_ok(client, monkeypatch):
    monkeypatch.setattr("footscan.api.routes.health.get_model", lambda: (object(), "cpu"))
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"database": "ok", "model": "ok"}}


def test_ready_503_when_model_unavailable(client, monkeypatch):
    def boom():
        raise ModelLoadError("weights missing")

    monkeypatch.setattr("footscan.api.routes.health.get_model", boom)
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"database": "ok", "model": "unavailable"}
    assert "weights missing" not in resp.text  # internal detail must not leak


def test_probes_do_not_require_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", SecretStr("k"))
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code in (200, 503)


# --------------------------------------------------------------------------- cross-cutting headers


def test_request_id_is_generated_and_echoed(client):
    generated = client.get("/health").headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", generated)
    assert client.get("/health", headers={"X-Request-ID": "trace-abc.123"}).headers["x-request-id"] == "trace-abc.123"


def test_malicious_request_id_is_replaced(client):
    resp = client.get("/health", headers={"X-Request-ID": "bad id with spaces & <script>"})
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


def test_security_headers_and_no_store_on_api(client):
    resp = client.get("/api/patients")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["cache-control"] == "no-store"


def test_cors_allows_configured_origin_only(client):
    ok = client.options(
        "/api/patients",
        headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "access-control-allow-credentials" not in ok.headers

    bad = client.options(
        "/api/patients",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


# --------------------------------------------------------------------------- auth


def test_api_key_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", SecretStr("secret-for-tests"))

    missing = client.get("/api/patients")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "ApiKey"
    assert client.get("/api/patients", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/patients", headers={"X-API-Key": "secret-for-tests"}).status_code == 200


def test_api_key_protects_inference_endpoints(client, monkeypatch, fake_model, sample_image):
    monkeypatch.setattr(settings, "api_key", SecretStr("secret-for-tests"))
    assert client.post("/api/analyze", files=_upload(sample_image)).status_code == 401
    ok = client.post("/api/analyze", files=_upload(sample_image), headers={"X-API-Key": "secret-for-tests"})
    assert ok.status_code == 200


def test_api_key_never_appears_in_settings_repr(monkeypatch):
    monkeypatch.setattr(settings, "api_key", SecretStr("super-secret-value"))
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.model_dump())


# --------------------------------------------------------------------------- upload validation


def test_analyze_rejects_non_image_bytes_even_with_image_content_type(client):
    files = {"image": ("scan.jpg", io.BytesIO(b"definitely not an image"), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 400


def test_analyze_rejects_text_file(client):
    files = {"image": ("scan.txt", io.BytesIO(b"not an image"), "text/plain")}
    assert client.post("/api/analyze", files=files).status_code == 400


def test_analyze_rejects_empty_upload(client):
    files = {"image": ("scan.jpg", io.BytesIO(b""), "image/jpeg")}
    assert client.post("/api/analyze", files=files).status_code == 400


def test_analyze_rejects_disallowed_image_format(client, sample_image):
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(sample_image).save(buf, format="GIF")
    files = {"image": ("scan.gif", io.BytesIO(buf.getvalue()), "image/gif")}
    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 415
    assert "GIF" in resp.json()["detail"]


def test_analyze_rejects_oversized_upload(client, monkeypatch, sample_image):
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    resp = client.post("/api/analyze", files=_upload(sample_image, ext=".png"))
    assert resp.status_code == 413


def test_oversized_content_length_is_rejected_before_parsing(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    resp = client.post(
        "/api/analyze", content=b"x" * (3 * 1024 * 1024), headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}


def test_analyze_rejects_decompression_bomb_dimensions(client, monkeypatch):
    # A tiny, highly-compressible PNG that declares a large canvas.
    monkeypatch.setattr(settings, "max_image_pixels", 10_000)
    big = np.zeros((300, 300, 3), dtype=np.uint8)
    resp = client.post("/api/analyze", files=_upload(big, ext=".png", ctype="image/png", name="x.png"))
    assert resp.status_code == 413
    assert "dimensions" in resp.json()["detail"]


def test_analyze_rejects_tiny_images(client):
    tiny = np.zeros((4, 4, 3), dtype=np.uint8)
    resp = client.post("/api/analyze", files=_upload(tiny, ext=".png", ctype="image/png", name="x.png"))
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "form",
    [
        {"threshold": "1.5"},
        {"threshold": "-0.1"},
        {"ref_px": "0"},
        {"ref_px": "-3"},
        {"ref_cm": "0"},
        {"ref_cm": "nan-ish"},
        {"prep_method": "Sharpen"},
        {"view_type": "Sideways"},
        {"patient_id": "x" * 37},
    ],
)
def test_analyze_validates_form_parameters(client, fake_model, sample_image, form):
    resp = client.post("/api/analyze", files=_upload(sample_image), data=form)
    assert resp.status_code == 422, resp.text
    assert fake_model == []  # never reached the model


def test_validation_errors_do_not_echo_input(client, sample_image):
    resp = client.post("/api/analyze", files=_upload(sample_image), data={"prep_method": "SECRET-INPUT-VALUE"})
    assert resp.status_code == 422
    assert "SECRET-INPUT-VALUE" not in resp.text
    assert set(resp.json()["detail"][0]) == {"loc", "msg", "type"}


# --------------------------------------------------------------------------- analyze / compare / reports


def test_analyze_success_persists_scan_and_returns_disclaimer(client, fake_model, sample_image):
    resp = client.post(
        "/api/analyze",
        files=_upload(sample_image),
        data={"threshold": "0.4", "prep_method": "CLAHE", "view_type": "Dorsal (Top)"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scan_id"]
    assert body["status"] == "ULCER DETECTED"
    assert "not a medical device" in body["disclaimer"].lower()
    assert set(body["images"]) == {"original", "mask", "heatmap", "blended", "edges", "cropped"}
    assert all(v.startswith("data:image/jpeg;base64,") for v in body["images"].values())
    assert fake_model[0]["threshold"] == 0.4 and fake_model[0]["prep_method"] == "CLAHE"
    assert resp.headers["x-request-id"]

    for kind in ("original", "overlay"):
        img = client.get(f"/api/scans/{body['scan_id']}/image/{kind}")
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_analyze_save_false_does_not_persist(client, fake_model, sample_image):
    resp = client.post("/api/analyze", files=_upload(sample_image), data={"save": "false"})
    assert resp.status_code == 200
    assert resp.json()["scan_id"] is None


def test_analyze_accepts_png_and_webp(client, fake_model, sample_image):
    for ext, ctype in ((".png", "image/png"), (".webp", "image/webp")):
        resp = client.post("/api/analyze", files=_upload(sample_image, ext=ext, ctype=ctype, name=f"s{ext}"))
        assert resp.status_code == 200, (ext, resp.text)


def test_analyze_unknown_patient_is_404(client, fake_model, sample_image):
    resp = client.post("/api/analyze", files=_upload(sample_image), data={"patient_id": "does-not-exist"})
    assert resp.status_code == 404


def test_analyze_links_scan_to_patient(client, fake_model, sample_image):
    patient = client.post("/api/patients", json={"name": "Linked Patient"}).json()
    resp = client.post("/api/analyze", files=_upload(sample_image), data={"patient_id": patient["id"]})
    assert resp.status_code == 200
    scans = client.get(f"/api/patients/{patient['id']}/scans").json()
    assert [s["id"] for s in scans] == [resp.json()["scan_id"]]


def test_analyze_returns_503_when_model_unavailable(client, monkeypatch, sample_image):
    def boom(*a, **k):
        raise ModelLoadError("internal path /secret/weights.pth missing")

    monkeypatch.setattr("footscan.api.routes.analysis.analyze_image", boom)
    resp = client.post("/api/analyze", files=_upload(sample_image))
    assert resp.status_code == 503
    assert "/secret" not in resp.text


def test_unhandled_errors_return_generic_500_with_request_id(monkeypatch, sample_image):
    from footscan.api.main import app

    def boom(*a, **k):
        raise RuntimeError("kaboom: internal details /etc/passwd")

    monkeypatch.setattr("footscan.api.routes.analysis.analyze_image", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post("/api/analyze", files=_upload(sample_image))
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == resp.headers["x-request-id"]
    assert "kaboom" not in resp.text and "passwd" not in resp.text


def test_compare_success(client, fake_model, sample_image):
    files = {**_upload(sample_image, field="old_image"), **_upload(sample_image, field="new_image")}
    resp = client.post("/api/compare", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "IMPROVED" and body["change_cm2"] == -1.0
    assert body["diff_image"].startswith("data:image/jpeg;base64,")
    assert "disclaimer" in body


def test_compare_rejects_bad_second_image(client, fake_model, sample_image):
    files = {**_upload(sample_image, field="old_image"), "new_image": ("n.jpg", io.BytesIO(b"junk"), "image/jpeg")}
    assert client.post("/api/compare", files=files).status_code == 400


def test_report_download_is_pdf_with_safe_filename_and_is_cleaned_up(client, fake_model, sample_image):
    scan_id = client.post("/api/analyze", files=_upload(sample_image)).json()["scan_id"]
    before = set(settings.reports_dir.glob("*.pdf"))

    resp = client.get(f"/api/scans/{scan_id}/report", params={"patient_name": "../../evil\\name:*?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    disposition = resp.headers["content-disposition"]
    assert scan_id in disposition and "evil" not in disposition and ".." not in disposition
    assert set(settings.reports_dir.glob("*.pdf")) == before  # rendered copy deleted after serving


def test_report_for_unknown_scan_is_404(client):
    assert client.get("/api/scans/nope/report").status_code == 404
    assert client.get("/api/scans/nope/image/original").status_code == 404


def test_scan_image_unknown_kind_is_404(client):
    assert client.get("/api/scans/anything/image/../../secret").status_code in (404, 405)
    assert client.get("/api/scans/anything/image/bogus").status_code == 404


def test_stored_path_escaping_data_dir_is_refused(client):
    from footscan.db.models import ScanRecord
    from footscan.db.session import SessionLocal

    with SessionLocal() as db:
        scan = ScanRecord(
            area_cm2=1.0, ulcer_percent=1.0, max_confidence=0.9, shape="Round", color_profile="x",
            sinbad_score=0, severity="Mild", est_healing_days=1, treatment="t",
            original_image_path="../../../../etc/hostname", overlay_image_path="../pyproject.toml",
        )
        db.add(scan)
        db.commit()
        scan_id = scan.id

    assert client.get(f"/api/scans/{scan_id}/image/original").status_code == 404
    assert client.get(f"/api/scans/{scan_id}/image/overlay").status_code == 404
    assert client.get(f"/api/scans/{scan_id}/report").status_code == 404


# --------------------------------------------------------------------------- rate limiting


def test_rate_limit_applies_to_inference_endpoints(client, monkeypatch, fake_model, sample_image):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    codes = [client.post("/api/analyze", files=_upload(sample_image)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]

    limited = client.post("/api/analyze", files=_upload(sample_image))
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    # Cheap read endpoints and probes are not limited.
    assert client.get("/api/patients").status_code == 200
    assert client.get("/health").status_code == 200


def test_rate_limit_disabled_with_zero(client, monkeypatch, fake_model, sample_image):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    assert all(client.post("/api/analyze", files=_upload(sample_image)).status_code == 200 for _ in range(5))


# --------------------------------------------------------------------------- patients


def test_patient_crud(client):
    resp = client.post("/api/patients", json={"name": "  Test Patient  "})
    assert resp.status_code == 201
    patient = resp.json()
    assert patient["name"] == "Test Patient"  # whitespace stripped

    assert client.get(f"/api/patients/{patient['id']}").status_code == 200
    assert client.get("/api/patients/does-not-exist").status_code == 404
    assert client.get("/api/patients/does-not-exist/scans").status_code == 404


@pytest.mark.parametrize("payload", [{"name": ""}, {"name": "   "}, {"name": "x" * 256}, {"name": "a\x00b"}, {}])
def test_patient_create_validation(client, payload):
    assert client.post("/api/patients", json=payload).status_code == 422


def test_patient_listing_is_paginated(client):
    for i in range(3):
        client.post("/api/patients", json={"name": f"Page {i}"})
    assert len(client.get("/api/patients", params={"limit": 2}).json()) == 2
    assert client.get("/api/patients", params={"limit": 0}).status_code == 422
    assert client.get("/api/patients", params={"limit": 5000}).status_code == 422


# --------------------------------------------------------------------------- real model (integration)


@pytest.mark.integration
@requires_model
def test_analyze_endpoint_with_real_model_persists_scan_and_report_downloads(client, sample_image):
    resp = client.post("/api/analyze", files=_upload(sample_image), data={"threshold": "0.5"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] is not None
    assert body["status"] in ("HEALTHY", "ULCER DETECTED")

    report = client.get(f"/api/scans/{body['scan_id']}/report")
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"


@pytest.mark.integration
@requires_model
def test_ready_with_real_model(client):
    assert client.get("/ready").status_code == 200
    assert client.get("/health").json()["model_loaded"] is True
