import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seeded_results(tmp_path: Path, monkeypatch):
    ticker_dir = tmp_path / "TEST" / "2026-01-01"
    ticker_dir.mkdir(parents=True)
    (ticker_dir / "final_state_report.json").write_text(
        json.dumps({"final_trade_decision": "BUY: strong signal", "market_report": "x"})
    )
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path))

    from tradingagents.storage import sqlite_history

    sqlite_history.rebuild_from_disk(tmp_path)
    return tmp_path


def _client():
    from backend.main import create_app

    return TestClient(create_app())


def test_history_list_returns_seeded_record(seeded_results):
    with _client() as client:
        resp = client.get("/api/history")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(item["ticker"] == "TEST" for item in items)


def test_history_filter_by_ticker(seeded_results):
    with _client() as client:
        resp = client.get("/api/history?ticker=TEST")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items and all(item["ticker"] == "TEST" for item in items)


def test_patch_history_sets_note(seeded_results):
    from tradingagents.storage import sqlite_history

    with _client() as client:
        resp = client.patch(
            "/api/history/TEST/2026-01-01",
            json={"note": "Reviewed — good thesis"},
        )
        assert resp.status_code == 200
    note = sqlite_history.get_note(seeded_results, "TEST", "2026-01-01")
    assert note == "Reviewed — good thesis"


def test_patch_history_sets_rating(seeded_results):
    from tradingagents.storage import sqlite_history

    with _client() as client:
        resp = client.patch(
            "/api/history/TEST/2026-01-01",
            json={"rating": "good"},
        )
        assert resp.status_code == 200

    # Verify the DB write actually landed — guards against UPDATE matching
    # zero rows (which would silently pass a status-only assertion).
    rows = sqlite_history.query_analyses(seeded_results, ticker="TEST")
    assert rows and rows[0].get("user_rating") == "good"
