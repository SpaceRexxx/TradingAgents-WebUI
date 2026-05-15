from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("DEEPSEEK_API_KEY=existing-value\n")
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(env))
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "existing-value")
    return env


def _client():
    return TestClient(create_app())


def test_list_providers_reports_configured_without_leaking_keys(env_file):
    with _client() as client:
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        items = {p["id"]: p for p in resp.json()["providers"]}
        assert items["deepseek"]["configured"] is True
        assert items["volcengine"]["configured"] is False
        assert "existing-value" not in resp.text
        for p in items.values():
            assert "key" not in p


def test_set_key_writes_env_and_marks_configured(env_file):
    with _client() as client:
        resp = client.post(
            "/api/providers/volcengine/key",
            json={"api_key": "ark-secret-123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"id": "volcengine", "configured": True}
        assert "ark-secret-123" not in resp.text
    assert "ARK_API_KEY=ark-secret-123" in env_file.read_text()


def test_set_key_unknown_provider_returns_404(env_file):
    with _client() as client:
        resp = client.post("/api/providers/notaprovider/key", json={"api_key": "x"})
        assert resp.status_code == 404


def test_set_key_for_keyless_provider_returns_400(env_file):
    with _client() as client:
        resp = client.post("/api/providers/ollama/key", json={"api_key": "x"})
        assert resp.status_code == 400


def test_set_key_rejects_newline_injection(env_file):
    # A key containing a newline must be rejected (422) so it cannot inject
    # a second KEY=value line into the .env file.
    with _client() as client:
        resp = client.post(
            "/api/providers/deepseek/key",
            json={"api_key": "good\nARK_API_KEY=evil"},
        )
        assert resp.status_code == 422
    # .env must NOT have gained an ARK_API_KEY line.
    assert "ARK_API_KEY=evil" not in env_file.read_text()


def test_test_provider_not_configured_returns_ok_false(env_file, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    with _client() as client:
        resp = client.post("/api/providers/volcengine/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "volcengine"
        assert body["ok"] is False
        assert body["reason"] == "not_configured"


def test_test_provider_reachable(env_file, monkeypatch):
    from backend.services import providers as ps

    monkeypatch.setattr(ps, "_probe_models_endpoint", lambda url, key: (True, 200))
    with _client() as client:
        resp = client.post("/api/providers/deepseek/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"id": "deepseek", "ok": True, "reason": "reachable", "status": 200}


def test_test_provider_unreachable(env_file, monkeypatch):
    from backend.services import providers as ps

    monkeypatch.setattr(ps, "_probe_models_endpoint", lambda url, key: (False, 0))
    with _client() as client:
        resp = client.post("/api/providers/deepseek/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "unreachable"


def test_test_unknown_provider_returns_404(env_file):
    with _client() as client:
        resp = client.post("/api/providers/nope/test")
        assert resp.status_code == 404
