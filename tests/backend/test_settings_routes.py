from fastapi.testclient import TestClient

from backend.main import create_app


def _client():
    return TestClient(create_app())


def test_get_settings_returns_results_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))
    with _client() as client:
        resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["results_dir"] == str(tmp_path)


def test_put_settings_persists_and_round_trips(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(env_file))
    target = str(tmp_path / "newresults")
    with _client() as client:
        put = client.put("/api/settings", json={"results_dir": target})
        assert put.status_code == 200
        assert put.json()["results_dir"] == target
        # Subsequent GET reflects the new value (get_settings is uncached).
        assert client.get("/api/settings").json()["results_dir"] == target
    assert f"TRADINGAGENTS_RESULTS_DIR={target}" in env_file.read_text()


def test_put_settings_rejects_newline(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(tmp_path / ".env"))
    with _client() as client:
        resp = client.put("/api/settings", json={"results_dir": "/a\nINJECT=1"})
    assert resp.status_code == 422
