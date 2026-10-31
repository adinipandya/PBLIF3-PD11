"""
tests/test_health.py
Uji endpoint /health dan /ready.
"""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "aplikasi" in data
    assert "versi" in data


def test_ready_endpoint_exists(client: TestClient):
    """
    /ready dapat mengembalikan 200 (connected) atau 503 (disconnected).
    Test ini memastikan endpoint ada dan mengembalikan struktur yang benar.
    """
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "database" in data

