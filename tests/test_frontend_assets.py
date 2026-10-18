"""The static frontend is served by the API process: check delivery, CSP and asset integrity."""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footscan.api.middleware import APP_CSP, DOCS_CSP

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@pytest.fixture
def client():
    from footscan.api.main import app

    with TestClient(app) as c:
        yield c


def test_index_is_served_with_disclaimer(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Not a medical device" in resp.text
    assert "Research use only" in resp.text


def test_app_pages_get_strict_csp_and_headers(client):
    resp = client.get("/")
    csp = resp.headers["content-security-policy"]
    assert csp == APP_CSP
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["cache-control"] == "no-cache"  # static assets revalidate; API stays no-store
    assert "camera=()" in resp.headers["permissions-policy"]


def test_api_json_responses_carry_csp_and_stay_no_store(client):
    resp = client.get("/api/patients")
    assert resp.headers["content-security-policy"] == APP_CSP
    assert resp.headers["cache-control"] == "no-store"


def test_swagger_ui_has_its_own_policy_without_loosening_the_app_one(client):
    docs = client.get("/api/docs")
    assert docs.status_code == 200
    assert docs.headers["content-security-policy"] == DOCS_CSP
    assert "https://cdn.jsdelivr.net" not in APP_CSP


def test_every_module_and_asset_referenced_by_index_exists():
    html = (FRONTEND / "index.html").read_text(encoding="utf8")
    refs = re.findall(r'(?:href|src)="([^"#]+)"', html)
    local = [r for r in refs if not r.startswith(("http", "data:", "/api"))]
    assert local, "index.html should reference local assets"
    for ref in local:
        assert (FRONTEND / ref).is_file(), f"index.html references missing file {ref}"


def test_es_module_imports_resolve():
    for js in (FRONTEND / "js").rglob("*.js"):
        for spec in re.findall(r'(?:from|import)\s*\(?\s*"(\.{1,2}/[^"]+)"', js.read_text(encoding="utf8")):
            assert (js.parent / spec).resolve().is_file(), f"{js.relative_to(FRONTEND)} imports missing {spec}"


def test_no_inline_script_or_style_that_the_csp_would_block():
    html = (FRONTEND / "index.html").read_text(encoding="utf8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would violate script-src 'self'"
    assert not re.search(r"\sstyle=", html), "inline style attributes would violate style-src 'self'"
    assert not re.search(r"\son\w+=", html), "inline event handlers would violate script-src 'self'"
    assert "<style" not in html


def test_vendored_three_js_matches_its_sri_hash():
    """scene.js loads vendor/three.min.js with an integrity attribute; the pinned hash must match the file."""
    source = (FRONTEND / "js" / "scene.js").read_text(encoding="utf8")
    pinned = re.search(r'THREE_INTEGRITY\s*=\s*"sha384-([^"]+)"', source)
    assert pinned, "scene.js must pin a sha384 integrity hash"
    digest = hashlib.sha384((FRONTEND / "vendor" / "three.min.js").read_bytes()).digest()
    assert base64.b64encode(digest).decode() == pinned.group(1)


def test_vendored_libraries_ship_their_licences():
    for name in ("LICENSE.three", "LICENSE.inter", "LICENSE.jetbrains-mono"):
        assert (FRONTEND / "vendor" / name).is_file()


def test_docs_do_not_claim_hipaa_compliance_or_encrypted_storage():
    root = FRONTEND.parent
    bad = re.compile(r"HIPAA[- ]compliant|encrypted (storage|data)|AES-256", re.I)
    for doc in ("README.md", "SECURITY.md", "CONTRIBUTING.md"):
        text = (root / doc).read_text(encoding="utf8")
        # Stating that these are NOT provided is fine; claiming them is not.
        for line in text.splitlines():
            if bad.search(line):
                assert re.search(r"\bnot\b|\bno\b|unencrypted|without", line, re.I), f"{doc}: {line!r}"
