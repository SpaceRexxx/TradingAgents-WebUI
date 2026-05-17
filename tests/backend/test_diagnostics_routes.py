from fastapi.testclient import TestClient

from backend.main import create_app


def _client():
    return TestClient(create_app())


def test_get_diagnostics_returns_list():
    with _client() as client:
        resp = client.get("/api/diagnostics")
        assert resp.status_code == 200
        body = resp.json()
        assert "degraded" in body
        assert isinstance(body["degraded"], list)


def test_run_diagnostics_returns_list_and_timestamp():
    with _client() as client:
        resp = client.post("/api/diagnostics/run")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["degraded"], list)
        assert "checked_at" in body and body["checked_at"]
