import io

import cv2
import pytest
from fastapi.testclient import TestClient

from footscan.config import settings

pytestmark = pytest.mark.integration
requires_model = pytest.mark.skipif(not settings.model_weights_path.exists(), reason="model weights not present")


@pytest.fixture
def client():
    from footscan.api.main import app

    with TestClient(app) as c:
        yield c


def _jpeg_bytes(image) -> bytes:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")


def test_patient_crud(client):
    resp = client.post("/api/patients", json={"name": "Test Patient"})
    assert resp.status_code == 201
    patient = resp.json()
    assert patient["name"] == "Test Patient"

    resp = client.get(f"/api/patients/{patient['id']}")
    assert resp.status_code == 200

    resp = client.get("/api/patients/does-not-exist")
    assert resp.status_code == 404


@requires_model
def test_analyze_endpoint_persists_scan_and_report_downloads(client, sample_image):
    files = {"image": ("scan.jpg", io.BytesIO(_jpeg_bytes(sample_image)), "image/jpeg")}
    data = {"ref_cm": "1.0", "ref_px": "38.46", "threshold": "0.5", "prep_method": "None"}

    resp = client.post("/api/analyze", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_id"] is not None
    assert body["status"] in ("HEALTHY", "ULCER DETECTED")

    report_resp = client.get(f"/api/scans/{body['scan_id']}/report")
    assert report_resp.status_code == 200
    assert report_resp.headers["content-type"] == "application/pdf"


def test_analyze_rejects_bad_content_type(client):
    files = {"image": ("scan.txt", io.BytesIO(b"not an image"), "text/plain")}
    resp = client.post("/api/analyze", files=files, data={})
    assert resp.status_code == 415


def test_api_key_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret123")
    resp = client.get("/api/patients")
    assert resp.status_code == 401

    resp = client.get("/api/patients", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200
