"""
Automated Verification Suite for Audit, Connectivity, and Security Fixes.
Tests configuration resilience, CORS regex, health probes, clean frontend routes,
inventory interoperability, report export authorization, and dependency requirements.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings, _get_mongo_uri, PROJECT_ROOT

client = TestClient(app)


def get_auth_token(email: str = "consumer@foodfresh.com", password: str = "ConsumerPass123!") -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_health_probe_endpoints():
    """Verify both /health and /api/health probes respond with operational health data."""
    res_root = client.get("/health")
    assert res_root.status_code == 200
    data_root = res_root.json()
    assert data_root["status"] == "healthy"
    assert "database" in data_root

    res_api = client.get("/api/health")
    assert res_api.status_code == 200
    assert res_api.json()["status"] == "healthy"


def test_readiness_probe_endpoint():
    """Verify readiness probe checks database and AI pipeline components."""
    res = client.get("/ready")
    assert res.status_code in [200, 503]
    if res.status_code == 200:
        data = res.json()
        assert data["status"] == "ready"
        assert "models" in data
        assert "cv_analyzer" in data["models"]


def test_clean_frontend_routes_including_scan():
    """Verify clean frontend routing for index, inventory, scan, etc."""
    res_index = client.get("/")
    assert res_index.status_code == 200

    res_inventory = client.get("/inventory")
    assert res_inventory.status_code == 200

    res_scan = client.get("/scan")
    assert res_scan.status_code == 200


def test_config_mongo_uri_validation():
    """Verify _get_mongo_uri handles local connections and enforces security rules."""
    uri = _get_mongo_uri()
    assert uri.startswith(("mongodb://", "mongodb+srv://"))
    assert "<" not in uri and ">" not in uri


def test_requirements_contains_critical_dependencies():
    """Verify backend/requirements.txt contains opencv and numpy for ML analyzer."""
    req_file = PROJECT_ROOT / "backend" / "requirements.txt"
    assert req_file.exists()
    req_text = req_file.read_text(encoding="utf-8")
    assert "opencv-python" in req_text
    assert "numpy" in req_text
    assert "fastapi" in req_text
    assert "pymongo" in req_text


def test_cors_preflight_and_headers():
    """Verify CORS headers respond correctly to localhost origins."""
    headers = {
        "Origin": "http://localhost:5500",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    res = client.options("/api/health", headers=headers)
    assert res.status_code == 200
    assert "access-control-allow-origin" in res.headers


def test_report_export_csv_auth_enforcement():
    """Verify /api/reports/export-csv rejects unauthenticated requests and succeeds for authenticated users."""
    res_unauth = client.get("/api/reports/export-csv")
    assert res_unauth.status_code == 401

    token = get_auth_token()
    res_auth = client.get("/api/reports/export-csv", headers={"Authorization": f"Bearer {token}"})
    assert res_auth.status_code == 200
    assert "text/csv" in res_auth.headers.get("content-type", "")


def test_retailer_report_csv_auth_enforcement():
    """Verify /api/retailer/reports/export-csv rejects unauthenticated requests."""
    res_unauth = client.get("/api/retailer/reports/export-csv")
    assert res_unauth.status_code == 401

    ret_token = get_auth_token("retailer@foodfresh.com", "RetailerPass123!")
    res_auth = client.get("/api/retailer/reports/export-csv", headers={"Authorization": f"Bearer {ret_token}"})
    assert res_auth.status_code == 200
    assert "text/csv" in res_auth.headers.get("content-type", "")


def test_inventory_list_and_empty_state_contract():
    """Verify /api/inventory returns a list (not a dictionary error) for authenticated users."""
    token = get_auth_token()
    res = client.get("/api/inventory", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        item = data[0]
        assert "id" in item
        assert "food_name" in item
        assert "category" in item
        assert "quantity" in item
        assert "freshness_status" in item
