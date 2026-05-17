import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routes import quote as quote_mod


def _client():
    return TestClient(create_app())


def setup_function():
    quote_mod._cache.clear()


def test_quote_success(monkeypatch):
    monkeypatch.setattr(quote_mod, "_opencli_available", lambda: True)
    payload = [{"name": "英伟达", "price": 225.32, "change": -10.4, "changePercent": "-4.42%"}]
    monkeypatch.setattr(
        quote_mod.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )
    with _client() as client:
        resp = client.get("/api/quote/NVDA")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "name": "英伟达",
        "price": 225.32,
        "change": -10.4,
        "changePercent": "-4.42%",
    }


def test_quote_204_when_opencli_missing(monkeypatch):
    monkeypatch.setattr(quote_mod, "_opencli_available", lambda: False)
    with _client() as client:
        resp = client.get("/api/quote/NVDA")
    assert resp.status_code == 204
    assert resp.content == b""


def test_quote_204_on_subprocess_failure(monkeypatch):
    monkeypatch.setattr(quote_mod, "_opencli_available", lambda: True)

    def _boom(*a, **k):
        raise quote_mod.subprocess.TimeoutExpired(cmd="opencli", timeout=8)

    monkeypatch.setattr(quote_mod.subprocess, "run", _boom)
    with _client() as client:
        resp = client.get("/api/quote/NVDA")
    assert resp.status_code == 204


def test_quote_cached_within_ttl(monkeypatch):
    monkeypatch.setattr(quote_mod, "_opencli_available", lambda: True)
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return SimpleNamespace(returncode=0, stdout=json.dumps({"name": "X", "price": 1}))

    monkeypatch.setattr(quote_mod.subprocess, "run", _run)
    with _client() as client:
        client.get("/api/quote/NVDA")
        client.get("/api/quote/NVDA")
    assert calls["n"] == 1
