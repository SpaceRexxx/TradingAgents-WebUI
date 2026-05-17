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


_LLM_VARS = (
    "TRADINGAGENTS_LLM_PROVIDER",
    "TRADINGAGENTS_DEEP_THINK_LLM",
    "TRADINGAGENTS_QUICK_THINK_LLM",
    "TRADINGAGENTS_LLM_BACKEND_URL",
)


def _clear_llm_env(monkeypatch):
    # App code writes os.environ directly; monkeypatch won't auto-revert
    # those, so start each test from a clean slate.
    for v in _LLM_VARS:
        monkeypatch.delenv(v, raising=False)


def test_put_llm_settings_persist_and_round_trip(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(env_file))
    _clear_llm_env(monkeypatch)
    with _client() as client:
        put = client.put(
            "/api/settings",
            json={"llm_provider": "OpenAI", "deep_think_llm": "gpt-4o"},
        )
        assert put.status_code == 200
        body = put.json()
        assert body["llm_provider"] == "OpenAI"
        assert body["deep_think_llm"] == "gpt-4o"
        assert body["quick_think_llm"]  # untouched field keeps default
        assert client.get("/api/settings").json()["deep_think_llm"] == "gpt-4o"
        assert client.get("/api/health").json()["model"] == "gpt-4o"
    txt = env_file.read_text()
    assert "TRADINGAGENTS_LLM_PROVIDER=OpenAI" in txt
    assert "TRADINGAGENTS_DEEP_THINK_LLM=gpt-4o" in txt


def test_put_llm_settings_partial_does_not_touch_others(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", str(tmp_path / ".env"))
    _clear_llm_env(monkeypatch)
    with _client() as client:
        before = client.get("/api/settings").json()
        client.put("/api/settings", json={"deep_think_llm": "deepseek-v4-pro"})
        after = client.get("/api/settings").json()
    assert after["deep_think_llm"] == "deepseek-v4-pro"
    assert after["quick_think_llm"] == before["quick_think_llm"]
